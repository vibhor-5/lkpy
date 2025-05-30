# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University.
# Copyright (C) 2023-2025 Drexel University.
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
Bias scoring model.
"""

from __future__ import annotations

import logging
from collections.abc import Container
from dataclasses import dataclass
from typing import Annotated, Literal

import numpy as np
import torch
from pydantic import BaseModel, NonNegativeFloat, PlainSerializer
from scipy.sparse import coo_array
from typing_extensions import Self, TypeAlias, overload

from lenskit.data import ID, Dataset, ItemList, QueryInput, RecQuery, Vocabulary
from lenskit.pipeline.components import Component
from lenskit.torch import safe_tensor
from lenskit.training import Trainable, TrainingOptions

_logger = logging.getLogger(__name__)
BiasEntity: TypeAlias = Literal["user", "item"]
Damping: TypeAlias = float | dict[BiasEntity, float]


@dataclass
class BiasModel:
    """
    User-item bias models learned from rating data.  The :class:`BiasScorer`
    class uses this model to score items in a pipeline; the model is reusable
    in other components that need user-item bias models.

    This implements the following model:

    .. math::
       b_{ui} = b_g + b_i + b_u

    where :math:`b_g` is the global bias (global mean rating), :math:`b_i` is
    item bias, and :math:`b_u` is the user bias.  With the provided damping
    values :math:`\\beta_{\\mathrm{u}}` and :math:`\\beta_{\\mathrm{i}}`, they
    are computed as follows:

    .. math::
       \\begin{align*}
       b_g & = \\frac{\\sum_{r_{ui} \\in R} r_{ui}}{|R|} &
       b_i & = \\frac{\\sum_{r_{ui} \\in R_i} (r_{ui} - b_g)}{|R_i| + \\beta_{\\mathrm{i}}} &
       b_u & = \\frac{\\sum_{r_{ui} \\in R_u} (r_{ui} - b_g - b_i)}{|R_u| + \\beta_{\\mathrm{u}}}
       \\end{align*}

    The damping values can be interpreted as the number of default (mean)
    ratings to assume *a priori* for each user or item, damping low-information
    users and items towards a mean instead of permitting them to take on extreme
    values based on few ratings.

    Stability:
        Caller
    """

    damping: Damping
    "The mean damping terms."

    global_bias: float
    "The global bias term."

    items: Vocabulary | None = None
    "Vocabulary of items."
    item_biases: np.ndarray[tuple[int], np.dtype[np.float32]] | None = None
    "The item offsets (:math:`b_i` values)."

    users: Vocabulary | None = None
    "Vocabulary of users."
    user_biases: np.ndarray[tuple[int], np.dtype[np.float32]] | None = None
    "The user offsets (:math:`b_u` values)."

    @classmethod
    def learn(
        cls,
        data: Dataset,
        damping: Damping | tuple[float, float] = 0.0,
        *,
        entities: Container[BiasEntity] = frozenset({"user", "item"}),
    ) -> Self:
        """
        Learn a bias model and its parameters from a dataset.

        Args:
            data:
                The dataset from which to learn the bias model.
            damping:
                Bayesian damping to apply to computed biases.  Either a number, to
                damp both user and item biases the same amount, or a (user,item)
                tuple providing separate damping values.
            items:
                Whether to compute item biases
            users:
                Whether to compute user biases
        """

        if isinstance(damping, tuple):
            damping = {"user": damping[0], "item": damping[1]}
        _logger.info("building bias model for %d ratings", data.interaction_count)
        ratings = data.interaction_matrix(format="scipy", layout="coo", field="rating")
        nrows, ncols = ratings.shape  # type: ignore

        g_bias = float(np.mean(ratings.data))
        _logger.info("global mean: %.3f", g_bias)

        model = cls(damping, g_bias)

        centered = ratings.data - g_bias
        if np.allclose(centered, 0):
            _logger.warning("mean-centered ratings are all 0, bias probably meaningless")

        if "item" in entities:
            counts = np.full(ncols, entity_damping(damping, "item"))
            sums = np.zeros(ncols)
            np.add.at(counts, ratings.col, 1)
            np.add.at(sums, ratings.col, centered)

            # store 0 offsets
            i_bias = np.zeros(ncols, dtype=np.float32)
            np.divide(sums, counts, out=i_bias, where=counts > 0)

            model.items = data.items
            model.item_biases = i_bias
            centered -= i_bias[ratings.col]
            _logger.info("computed biases for %d items", len(i_bias))

        if "user" in entities:
            counts = np.full(nrows, entity_damping(damping, "user"))
            sums = np.zeros(nrows)
            np.add.at(counts, ratings.row, 1)
            np.add.at(sums, ratings.row, centered)

            u_bias = np.zeros(nrows, dtype=np.float32)
            np.divide(sums, counts, out=u_bias, where=counts > 0)

            model.users = data.users
            model.user_biases = u_bias
            _logger.info("computed biases for %d users", len(u_bias))

        return model

    @overload
    def compute_for_items(
        self,
        items: ItemList,
        user_id: ID | None = None,
        user_items: ItemList | None = None,
    ) -> tuple[np.ndarray[tuple[int], np.dtype[np.float32]], float]: ...
    @overload
    def compute_for_items(
        self,
        items: ItemList,
        *,
        bias: float,
    ) -> np.ndarray[tuple[int], np.dtype[np.float32]]: ...
    def compute_for_items(
        self,
        items: ItemList,
        user_id: ID | None = None,
        user_items: ItemList | None = None,
        *,
        bias: float | None = None,
    ):
        """
        Compute the personalized biases for a set of itemsm and optionally a
        user.  The user can be specified either by their identifier or by a list
        of ratings.

        Args:
            items:
                The items to score.
            user:
                The user identifier.
            user_items:
                The user's items, with ratings (takes precedence over ``user``
                if both are supplied).  If the supplied list does not have a
                ``rating`` field, it is ignored.
            bias:
                A pre-computed user bias.
        Returns:
            A tuple of the overall bias scores for the specified items and user,
            and the user's bias (needed to de-normalize scores efficiently
            later).  If a user bias is provided instead of user information,
            only the composite bias scores are returned.
        """
        n = len(items)
        scores = np.full(n, self.global_bias, dtype=np.float32)

        if self.item_biases is not None:
            assert self.items is not None
            idxes = items.numbers(vocabulary=self.items, missing="negative")
            mask = idxes >= 0
            scores[mask] += self.item_biases[idxes[mask]]

        if bias is not None:
            return scores + bias

        ratings = None
        if user_items is not None:
            ratings = user_items.field("rating")

        user_bias = 0.0
        if self.users is not None:
            assert self.user_biases is not None

            if ratings is not None:
                assert user_items is not None

                uoff = ratings - self.global_bias

                if self.item_biases is not None:
                    r_idxes = user_items.numbers(vocabulary=self.items, missing="negative")
                    r_mask = r_idxes >= 0
                    uoff[r_mask] -= self.item_biases[r_idxes[r_mask]]

                user_bias = np.sum(uoff) / (
                    np.sum(np.isfinite(uoff)) + entity_damping(self.damping, "user")
                )
                if np.isnan(user_bias):
                    user_bias = 0
                scores += user_bias

            elif user_id is not None:
                uno = self.users.number(user_id, missing="none")
                if uno is not None:
                    user_bias = self.user_biases[uno]
                    _logger.debug("using mean(user %s) = %.3f", user_id, user_bias)
                    scores += user_bias

        return scores, user_bias

    @overload
    def transform_matrix(self, matrix: coo_array) -> coo_array: ...
    @overload
    def transform_matrix(self, matrix: torch.Tensor) -> torch.Tensor: ...
    def transform_matrix(self, matrix: torch.Tensor | coo_array):
        """
        Transform a sparse ratings matrix by subtracting biases.

        Args:
            matrix:
                The matrix to transform.
        """
        if isinstance(matrix, torch.Tensor):
            if not matrix.is_sparse:
                raise TypeError("matrix is not sparse COO")

            indices = matrix.indices()
            unos = indices[0, :]
            inos = indices[1, :]
            values = matrix.values()

            values = matrix.values() - self.global_bias
            if self.item_biases is not None:
                values.subtract_(safe_tensor(self.item_biases)[inos])
            if self.user_biases is not None:
                values.subtract_(safe_tensor(self.user_biases)[unos])
            return torch.sparse_coo_tensor(indices, values, size=matrix.size())
        else:
            values = matrix.data - self.global_bias
            if self.item_biases is not None:
                values -= self.item_biases[matrix.col]
            if self.user_biases is not None:
                values -= self.user_biases[matrix.row]
            return coo_array((values, (matrix.row, matrix.col)), shape=matrix.shape)


class BiasConfig(BaseModel, extra="forbid"):
    """
    Configuration for :class:`BiasScorer`.
    """

    entities: Annotated[
        set[Literal["user", "item"]], PlainSerializer(lambda s: sorted(s), return_type=list[str])
    ] = {"user", "item"}
    """
    The entities to compute biases for, in addition to global bais.  Defaults to
    users and items.
    """
    damping: NonNegativeFloat | dict[Literal["user", "item"], NonNegativeFloat] = 0.0

    def entity_damping(self, entity: Literal["user", "item"]) -> float:
        """
        Look up the damping for a particular entity type.
        """
        return entity_damping(self.damping, entity)


class BiasScorer(Component[ItemList], Trainable):
    """
    A user-item bias rating prediction model.  This component uses
    :class:`BiasModel` to predict ratings for users and items.

    Args:
        config:
            The component configuration.

    Stability:
        Caller
    """

    config: BiasConfig
    model_: BiasModel

    def train(self, data: Dataset, options: TrainingOptions = TrainingOptions()):
        """
        Train the bias model on some rating data.

        Args:
            ratings:
                The training data (must have ratings).

        Returns:
            The trained bias object.
        """
        if hasattr(self, "model_") and not options.retrain:
            return

        self.model_ = BiasModel.learn(data, self.config.damping, entities=self.config.entities)

    def __call__(self, query: QueryInput, items: ItemList) -> ItemList:
        """
        Compute predictions for a user and items.  Unknown users and items are
        assumed to have zero bias.

        Args:
            query:
                The recommendation query.  If the query has an item list with
                ratings, those ratings are used to compute a new bias instead of
                using the user's recorded bias.
            items:
                The items to score.
        Returns:
            Scores for `items`.
        """
        query = RecQuery.create(query)

        scores, _bias = self.model_.compute_for_items(items, query.user_id, query.user_items)
        return ItemList(items, scores=scores)


def entity_damping(damping: Damping, entity: BiasEntity) -> float:
    """
    Look up the damping for a particular entity type.
    """
    if isinstance(damping, dict):
        return damping.get(entity, 0.0)
    else:
        return damping
