# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
User-based k-NN collaborative filtering.
"""

# pyright: basic
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd
import structlog
import torch
from scipy.sparse import csr_array
from typing_extensions import NamedTuple, Optional, Self, override

from lenskit import util
from lenskit.data import Dataset, FeedbackType, ItemList, QueryInput, RecQuery
from lenskit.data.vocab import Vocabulary
from lenskit.diagnostics import DataWarning
from lenskit.math.sparse import normalize_sparse_rows, safe_spmv, torch_sparse_to_scipy
from lenskit.parallel.config import ensure_parallel_init
from lenskit.pipeline import Component, Trainable

_log = structlog.stdlib.get_logger(__name__)


class UserKNNScorer(Component, Trainable):
    """
    User-user nearest-neighbor collaborative filtering with ratings. This
    user-user implementation is not terribly configurable; it hard-codes design
    decisions found to work well in the previous Java-based LensKit code.

    Args:
        nnbrs:
            the maximum number of neighbors for scoring each item (``None`` for
            unlimited).
        min_nbrs:
            The minimum number of neighbors for scoring each item.
        min_sim:
            Minimum similarity threshold for considering a neighbor.  Must be
            positive; if less than the smallest 32-bit normal (:math:`1.175
            \\times 10^{-38}`), is clamped to that value.
        feedback:
            Control how feedback should be interpreted.  Specifies defaults for
            the other settings, which can be overridden individually; can be one
            of the following values:

            ``explicit``
                Configure for explicit-feedback mode: use rating values, and
                predict using weighted averages.  This is the default setting.

            ``implicit``
                Configure for implicit-feedback mode: ignore rating values, and
                predict using the sums of similarities.
    """

    nnbrs: int
    min_nbrs: int
    min_sim: float
    feedback: FeedbackType

    users_: Vocabulary
    "The index of user IDs."
    items_: Vocabulary
    "The index of item IDs."
    user_means_: torch.Tensor | None
    "Mean rating for each known user."
    user_vectors_: torch.Tensor
    "Normalized rating matrix (CSR) to find neighbors at prediction time."
    user_ratings_: csr_array
    "Centered but un-normalized rating matrix (COO) to find neighbor ratings."

    def __init__(
        self,
        nnbrs: int,
        min_nbrs: int = 1,
        min_sim: float = 1.0e-6,
        feedback: FeedbackType = "explicit",
    ):
        self.nnbrs = nnbrs
        self.min_nbrs = min_nbrs
        if min_sim < 0:
            raise ValueError("minimum similarity must be positive")
        elif min_sim == 0:
            f4i = np.finfo("f4")
            self.min_sim = float(f4i.smallest_normal)
            _log.warning("minimum similarity %e is too low, using %e", min_sim, self.min_sim)
        else:
            self.min_sim = min_sim

        self.feedback = feedback

    @property
    def is_trained(self) -> bool:
        return hasattr(self, "users_")

    @override
    def train(self, data: Dataset) -> Self:
        """
        "Train" a user-user CF model.  This memorizes the rating data in a format that is usable
        for future computations.

        Args:
            ratings(pandas.DataFrame): (user, item, rating) data for collaborative filtering.
        """
        ensure_parallel_init()
        rmat = data.interaction_matrix(
            "torch", field="rating" if self.feedback == "explicit" else None
        )
        assert rmat.is_sparse_csr

        if self.feedback == "explicit":
            rmat, means = normalize_sparse_rows(rmat, "center")
            if np.allclose(rmat.values(), 0.0):
                _log.warning("normalized ratings are zero, centering is not recommended")
                warnings.warn(
                    "Ratings seem to have the same value, centering is not recommended.",
                    DataWarning,
                )
        else:
            means = None

        normed, _norms = normalize_sparse_rows(rmat, "unit")

        self.user_vectors_ = normed
        self.user_ratings_ = torch_sparse_to_scipy(rmat).tocsr()
        self.users_ = data.users.copy()
        self.user_means_ = means
        self.items_ = data.items.copy()

        return self

    @override
    def __call__(self, query: QueryInput, items: ItemList) -> ItemList:
        """
        Compute predictions for a user and items.

        Args:
            user: the user ID
            items (array-like): the items to predict
            ratings (pandas.Series):
                the user's ratings (indexed by item id); if provided, will be used to
                recompute the user's bias at prediction time.

        Returns:
            pandas.Series: scores for the items, indexed by item id.
        """
        query = RecQuery.create(query)
        watch = util.Stopwatch()
        log = _log.bind(user_id=query.user_id, n_items=len(items))

        udata = self._get_user_data(query)
        if udata is None:
            log.debug("user has no ratings, skipping")
            return ItemList(items, scores=np.nan)

        uidx, ratings, umean = udata
        assert ratings.shape == (len(self.items_),)  # ratings is a dense vector

        # now ratings has vbeen normalized to be a mean-centered unit vector
        # this means we can dot product to score neighbors
        # score the neighbors!
        nbr_sims = safe_spmv(self.user_vectors_, ratings)
        assert nbr_sims.shape == (len(self.users_),)
        if uidx is not None:
            # zero out the self-similarity
            nbr_sims[uidx] = 0

        # get indices for these neighbors
        nbr_idxs = torch.arange(len(self.users_), dtype=torch.int64)

        nbr_mask = nbr_sims >= self.min_sim

        kn_sims = nbr_sims[nbr_mask]
        kn_idxs = nbr_idxs[nbr_mask]
        if len(kn_sims) > 0:
            log.debug(
                "found %d candidate neighbors (of %d total), max sim %0.4f",
                len(kn_sims),
                len(self.users_),
                torch.max(kn_sims).item(),
            )
        else:
            log.warning("no candidate neighbors found")
            return ItemList(items, scores=np.nan)

        assert not torch.any(torch.isnan(kn_sims))

        iidxs = items.numbers(vocabulary=self.items_, missing="negative")
        iidxs = torch.from_numpy(iidxs).to(torch.int64)

        ki_mask = iidxs >= 0
        usable_iidxs = iidxs[ki_mask]

        scores = score_items_with_neighbors(
            log,
            usable_iidxs,
            kn_idxs,
            kn_sims,
            self.user_ratings_,
            self.nnbrs,
            self.min_nbrs,
            self.feedback == "explicit",
        )

        scores += umean

        results = pd.Series(scores, index=items.ids()[ki_mask.numpy()], name="prediction")
        results = results.reindex(items.ids())

        log.debug(
            "scored %d items in %s",
            results.notna().sum(),
            watch,
        )
        return ItemList(items, scores=results.values)  # type: ignore

    def _get_user_data(self, query: RecQuery) -> Optional[UserRatings]:
        "Get a user's data for user-user CF"

        index = self.users_.number(query.user_id, missing=None)

        if query.user_items is None:
            if index is None:
                _log.warning("user %s has no ratings and none provided", query.user_id)
                return None

            assert index >= 0
            row = self.user_vectors_[index].to_dense()
            if self.feedback == "explicit":
                assert self.user_means_ is not None
                umean = self.user_means_[index].item()
            else:
                umean = 0
            return UserRatings(index, row, umean)
        else:
            _log.debug("using provided item history")
            ratings = torch.zeros(len(self.items_), dtype=torch.float32)
            ui_nos = query.user_items.numbers("torch", missing="negative", vocabulary=self.items_)
            ui_mask = ui_nos >= 0

            if self.feedback == "explicit":
                urv = query.user_items.field("rating", "torch")
                if urv is None:
                    _log.warning("user %s has items but no ratings", query.user_id)
                    return None

                umean = urv.mean().item()
                ratings[ui_nos[ui_mask]] = urv[ui_mask] - umean
            else:
                umean = 0
                ratings[ui_nos[ui_mask]] = 1.0

            return UserRatings(index, ratings, umean)

    def __str__(self):
        return "UserUser(nnbrs={}, min_sim={})".format(self.nnbrs, self.min_sim)


class UserRatings(NamedTuple):
    """
    Dense user ratings.
    """

    index: int | None
    ratings: torch.Tensor
    mean: float


def score_items_with_neighbors(
    log: structlog.stdlib.BoundLogger,
    items: torch.Tensor,
    nbr_rows: torch.Tensor,
    nbr_sims: torch.Tensor,
    ratings: csr_array,
    max_nbrs: int,
    min_nbrs: int,
    average: bool,
) -> np.ndarray[tuple[int], np.dtype[np.float64]]:
    # select a sub-matrix for further manipulation
    (ni,) = items.shape
    (nrow, ncol) = ratings.shape
    # do matrix surgery
    nbr_rates = ratings[nbr_rows.numpy(), :]
    nbr_rates = nbr_rates[:, items.numpy()]

    nbr_t = nbr_rates.transpose().tocsr()

    # count nbrs for each item
    counts = np.diff(nbr_t.indptr)
    assert counts.shape == items.shape

    log.debug(
        "scoring items",
        max_count=np.max(counts),
        nbr_shape=nbr_rates.shape,
    )

    # fast-path items with small neighborhoods
    fp_mask = counts <= max_nbrs
    results = np.full(ni, np.nan)
    nbr_fp = nbr_rates[:, fp_mask]
    results[fp_mask] = nbr_fp.T @ nbr_sims

    if average:
        nbr_fp_ones = csr_array((np.ones(nbr_fp.nnz), nbr_fp.indices, nbr_fp.indptr), nbr_fp.shape)
        tot_sims = nbr_fp_ones.T @ nbr_sims
        assert np.all(np.isfinite(tot_sims))
        results[fp_mask] /= tot_sims

    # clear out too-small neighborhoods
    results[counts < min_nbrs] = torch.nan

    # deal with too-large items
    exc_mask = counts > max_nbrs
    n_bad = np.sum(exc_mask)
    if n_bad:
        log.debug("scoring %d slow-path items", n_bad)

    bads = np.argwhere(exc_mask)[:, 0]
    for badi in bads:
        s, e = nbr_t.indptr[badi : (badi + 2)]

        bi_users = nbr_t.indices[s:e]
        bi_rates = torch.from_numpy(nbr_t.data[s:e])
        bi_sims = nbr_sims[bi_users]

        tk_vs, tk_is = torch.topk(bi_sims, max_nbrs)
        sum = torch.sum(tk_vs)
        if average:
            results[badi] = torch.dot(tk_vs, bi_rates[tk_is]) / sum
        else:
            results[badi] = sum

    return results
