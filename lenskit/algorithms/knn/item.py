# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
Item-based k-NN collaborative filtering.
"""

from __future__ import annotations

import logging
import warnings
from sys import intern
from typing import Callable, Literal, Optional, TypeAlias

import numpy as np
import pandas as pd
import torch

from lenskit import ConfigWarning, DataWarning, util
from lenskit.data import FeedbackType
from lenskit.data.matrix import normalize_sparse_rows, sparse_ratings
from lenskit.parallel import ensure_parallel_init
from lenskit.util.logging import pbh_update, progress_handle

from .. import Predictor

_log = logging.getLogger(__name__)
MAX_BLOCKS = 1024


class ItemItem(Predictor):
    """
    Item-item nearest-neighbor collaborative filtering with ratings. This
    item-item implementation is not terribly configurable; it hard-codes design
    decisions found to work well in the previous Java-based LensKit code
    :cite:p:`lenskit-java`.  This implementation is based on the description
    of item-based CF by :cite:t:`deshpande:iknn`, and produces results
    equivalent to Java LensKit.

    The k-NN predictor supports several aggregate functions:

    ``weighted-average``
        The weighted average of the user's rating values, using item-item
        similarities as weights.

    ``sum``
        The sum of the similarities between the target item and the user's rated
        items, regardless of the rating the user gave the items.

    Args:
        nnbrs(int):
            the maximum number of neighbors for scoring each item (``None`` for
            unlimited)
        min_nbrs(int): the minimum number of neighbors for scoring each item
        min_sim(float): minimum similarity threshold for considering a neighbor
        save_nbrs(float):
            the number of neighbors to save per item in the trained model
            (``None`` for unlimited)
        feedback(str):
            Control how feedback should be interpreted.  Specifies defaults for
            the other settings, which can be overridden individually; can be one
            of the following values:

            ``explicit``
                Configure for explicit-feedback mode: use rating values, center
                ratings, and use the ``weighted-average`` aggregate method for
                prediction.  This is the default setting.

            ``implicit``
                Configure for implicit-feedback mode: ignore rating values, do
                not center ratings, and use the ``sum`` aggregate method for
                prediction.
        center(bool):
            whether to normalize (mean-center) rating vectors prior to computing
            similarities and aggregating user rating values.  Defaults to
            ``True``; turn this off when working with unary data and other data
            types that don't respond well to centering.
        aggregate(str):
            the type of aggregation to do. Can be ``weighted-average`` (the
            default) or ``sum``.
        use_ratings(bool):
            whether or not to use the rating values. If ``False``, it ignores
            rating values and considers an implicit feedback signal of 1 for
            every (user,item) pair present.
    """

    IGNORED_PARAMS = ["feedback"]
    EXTRA_PARAMS = ["center", "aggregate", "use_ratings"]

    AGG_SUM = intern("sum")
    AGG_WA = intern("weighted-average")
    RATING_AGGS = [AGG_WA]  # the aggregates that use rating values

    nnbrs: int
    min_nbrs: int
    min_sim: float
    save_nbrs: int | None
    feedback: Literal["explicit", "implicit"]
    block_size: int

    item_index_: pd.Index
    "The index of item IDs."
    item_means_: torch.Tensor | None
    "Mean rating for each known item."
    item_counts_: torch.Tensor
    "Number of saved neighbors for each item."
    sim_matrix_: torch.Tensor
    "Similarity matrix (sparse CSR tensor)."
    user_index_: pd.Index
    "Index of user IDs."
    rating_matrix_: torch.Tensor
    "Normalized rating matrix to look up user ratings at prediction time."

    def __init__(
        self,
        nnbrs: int,
        min_nbrs: int = 1,
        min_sim: float = 1.0e-6,
        save_nbrs: int | None = None,
        feedback: FeedbackType = "explicit",
        block_size: int = 250,
        **kwargs,
    ):
        self.nnbrs = nnbrs
        self.min_nbrs = min_nbrs
        if self.min_nbrs is not None and self.min_nbrs < 1:
            self.min_nbrs = 1
        self.min_sim = min_sim
        self.save_nbrs = save_nbrs
        self.block_size = block_size

        if feedback == "explicit":
            defaults = {"center": True, "aggregate": self.AGG_WA, "use_ratings": True}
        elif feedback == "implicit":
            defaults = {"center": False, "aggregate": self.AGG_SUM, "use_ratings": False}
        else:
            raise ValueError(f"invalid feedback mode: {feedback}")

        defaults.update(kwargs)
        self.center = defaults["center"]
        self.aggregate = intern(defaults["aggregate"])
        self.use_ratings = defaults["use_ratings"]

        self._check_setup()

    def _check_setup(self):
        if not self.use_ratings:
            if self.center:
                _log.warning(
                    "item-item configured to ignore ratings, but ``center=True`` - likely bug"
                )
                warnings.warn(
                    util.clean_str(
                        """
                    item-item configured to ignore ratings, but ``center=True``.  This configuration
                    is unlikely to work well.
                """
                    ),
                    ConfigWarning,
                )
            if self.aggregate == "weighted-average":
                _log.warning("item-item ignoring ratings but using weighted averages - likely bug")
                warnings.warn(
                    util.clean_str(
                        """
                    item-item ignoring ratings but using weighted averages.  This configuration
                    is unlikely to work well.
                """
                    ),
                    ConfigWarning,
                )

        if self.min_sim < 0:
            _log.warning("item-item does not currently support negative similarities")
            warnings.warn("item-item does not currently support negative similarities")

    def fit(self, ratings, **kwargs):
        """
        Train a model.

        The model-training process depends on ``save_nbrs`` and ``min_sim``, but *not* on other
        algorithm parameters.

        Args:
            ratings(pandas.DataFrame):
                (user,item,rating) data for computing item similarities.
        """
        ensure_parallel_init()
        # Training proceeds in 2 steps:
        # 1. Normalize item vectors to be mean-centered and unit-normalized
        # 2. Compute similarities with pairwise dot products
        self._timer = util.Stopwatch()

        _log.debug("[%s] beginning fit, memory use %s", self._timer, util.max_memory())

        init_rmat, users, items = sparse_ratings(ratings, torch=True)
        n_items = len(items)
        _log.info(
            "[%s] made sparse matrix for %d items (%d ratings from %d users)",
            self._timer,
            len(items),
            len(init_rmat.values()),
            len(users),
        )
        _log.debug("[%s] made matrix, memory use %s", self._timer, util.max_memory())

        # we operate on *transposed* rating matrix: items on the rows
        rmat = init_rmat.transpose(0, 1).to_sparse_csr().to(torch.float64)

        if self.center:
            rmat, means = normalize_sparse_rows(rmat, "center")
            if np.allclose(rmat.values(), 0.0):
                _log.warn("normalized ratings are zero, centering is not recommended")
                warnings.warn(
                    "Ratings seem to have the same value, centering is not recommended.",
                    DataWarning,
                )
        else:
            means = None
        _log.debug("[%s] centered, memory use %s", self._timer, util.max_memory())

        rmat, _norms = normalize_sparse_rows(rmat, "unit")
        _log.debug("[%s] normalized, memory use %s", self._timer, util.max_memory())

        _log.info("[%s] computing similarity matrix", self._timer)
        smat = self._compute_similarities(rmat)
        _log.debug("[%s] computed, memory use %s", self._timer, util.max_memory())

        _log.info(
            "[%s] got neighborhoods for %d of %d items",
            self._timer,
            np.sum(np.diff(smat.crow_indices()) > 0),
            n_items,
        )

        _log.info("[%s] computed %d neighbor pairs", self._timer, len(smat.col_indices()))

        self.item_index_ = items
        self.item_means_ = means
        self.item_counts_ = torch.diff(smat.crow_indices())
        self.sim_matrix_ = smat
        self.user_index_ = users
        self.rating_matrix_ = init_rmat
        _log.debug("[%s] done, memory use %s", self._timer, util.max_memory())

        return self

    def _compute_similarities(self, rmat: torch.Tensor):
        nitems, nusers = rmat.shape

        bs = max(self.block_size, nitems // MAX_BLOCKS)
        _log.debug("computing with effective block size %d", bs)
        with progress_handle(_log, "items", nitems, leave=False) as pbh:
            smat = _sim_blocks(rmat.to(torch.float64), self.min_sim, self.save_nbrs, bs, pbh)

        return smat.to(torch.float32)

    def predict_for_user(self, user, items, ratings=None):
        _log.debug("predicting %d items for user %s", len(items), user)
        if ratings is None:
            if user not in self.user_index_:
                _log.debug("user %s missing, returning empty predictions", user)
                return pd.Series(np.nan, index=items)
            upos = self.user_index_.get_loc(user)
            row = self.rating_matrix_[upos]  # type: ignore
            ratings = pd.Series(
                row.values().numpy(),
                index=pd.Index(self.item_index_[row.indices()[0]]),
            )

        if not ratings.index.is_unique:
            wmsg = "user {} has duplicate ratings, this is likely to cause problems".format(user)
            warnings.warn(wmsg, DataWarning)

        # set up rating array
        # get rated item positions & limit to in-model items
        ri_pos = self.item_index_.get_indexer(ratings.index)

        ri_vals = torch.from_numpy(ratings.values[ri_pos >= 0]).to(torch.float64)
        ri_pos = torch.from_numpy(ri_pos[ri_pos >= 0])

        # mean-center the rating array
        if self.center:
            assert self.item_means_ is not None
            ri_vals -= self.item_means_[ri_pos]

        _log.debug("user %s: %d of %d rated items in model", user, len(ri_pos), len(ratings))

        # now compute the predictions
        agg = _predictors[self.aggregate]
        sims = agg(
            self.sim_matrix_,
            (self.min_nbrs, self.nnbrs),
            ri_vals,
            ri_pos,
        )

        if self.center and self.aggregate in self.RATING_AGGS:
            assert self.item_means_ is not None
            sims += self.item_means_

        results = pd.Series(sims.numpy(), index=self.item_index_)
        results = results.reindex(items, fill_value=np.nan)

        _log.debug("user %s: predicted for %d of %d items", user, results.notna().sum(), len(items))

        return results

    def __str__(self):
        return "ItemItem(nnbrs={}, msize={})".format(self.nnbrs, self.save_nbrs)


@torch.jit.ignore  # type: ignore
def _msg(level, msg):
    # type: (int, str) -> None
    _log.log(level, msg)


@torch.jit.script
def _sim_row(
    item: int, matrix: torch.Tensor, row: torch.Tensor, min_sim: float, max_nbrs: Optional[int]
) -> tuple[int, torch.Tensor, torch.Tensor]:
    nitems, nusers = matrix.shape
    if len(row.indices()) == 0:
        return 0, torch.zeros((0,), dtype=torch.int32), torch.zeros((0,), dtype=torch.float64)

    # _item_dbg(item, f"comparing item with {row.indices().shape[1]} users")
    # _item_dbg(item, f"row norm {torch.linalg.vector_norm(row.values()).item()}")
    row = row.to_dense()
    sim = torch.mv(matrix, row.to(torch.float64))
    sim[item] = 0

    mask = sim >= min_sim
    cols = torch.nonzero(mask)[:, 0].to(torch.int32)
    vals = sim[mask]
    # _item_dbg(item, f"found {len(vals)} acceptable similarities")
    assert len(cols) == torch.sum(mask)

    if max_nbrs is not None and max_nbrs > 0 and max_nbrs < vals.shape[0]:
        # _item_dbg(item, "truncating similarities")
        vals, cis = torch.topk(vals, max_nbrs, sorted=False)
        cols = cols[cis]
        order = torch.argsort(cols)
        cols = cols[order]
        vals = vals[order]

    return len(cols), cols, torch.clamp(vals, -1, 1)


@torch.jit.script
def _sim_block(
    matrix: torch.Tensor, start: int, end: int, min_sim: float, max_nbrs: Optional[int], pbh: str
) -> tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
    "Compute a single block of the similarity matrix"
    bsize = end - start

    counts = torch.zeros(bsize, dtype=torch.int32)
    columns = []
    values = []

    for i in range(start, end):
        c, cs, vs = _sim_row(i, matrix, matrix[i], min_sim, max_nbrs)
        counts[i - start] = c
        columns.append(cs)
        values.append(vs)
        pbh_update(pbh, 1)

    return counts, torch.cat(columns), torch.cat(values).to(torch.float32)


@torch.jit.script
def _sim_blocks(
    matrix: torch.Tensor, min_sim: float, max_nbrs: Optional[int], block_size: int, pbh: str
) -> torch.Tensor:
    "Compute the similarity matrix with blocked matrix-matrix multiplies"
    nitems, nusers = matrix.shape

    jobs: list[torch.jit.Future[tuple[torch.Tensor, torch.Tensor, torch.Tensor]]] = []

    for start in range(0, nitems, block_size):
        end = min(start + block_size, nitems)
        jobs.append(torch.jit.fork(_sim_block, matrix, start, end, min_sim, max_nbrs, pbh))  # type: ignore

    counts = [torch.tensor([0], dtype=torch.int32)]
    columns = []
    values = []

    for job in jobs:
        cts, cis, vs = job.wait()
        counts.append(cts)
        columns.append(cis)
        values.append(vs)

    c_cat = torch.cat(counts)
    crow_indices = torch.cumsum(c_cat, 0, dtype=torch.int32)
    assert len(crow_indices) == nitems + 1
    col_indices = torch.cat(columns)
    c_values = torch.cat(values)
    assert crow_indices[nitems] == len(col_indices)
    assert crow_indices[nitems] == len(c_values)

    return torch.sparse_csr_tensor(
        crow_indices=crow_indices,
        col_indices=col_indices,
        values=c_values,
        size=(nitems, nitems),
    )


def _predict_weighted_average(
    model: torch.Tensor,
    nrange: tuple[int, int],
    rate_v: torch.Tensor,
    rated: torch.Tensor,
) -> torch.Tensor:
    "Weighted average prediction function"
    nitems, _ni = model.shape
    assert nitems == _ni
    min_nbrs, max_nbrs = nrange

    # we proceed rating-by-rating, and accumulate results
    scores = torch.zeros(nitems)
    t_sims = torch.zeros(nitems)
    counts = torch.zeros(nitems, dtype=torch.int32)
    # these store the similarities and values for neighbors, so we can un-count
    nbr_sims = torch.empty((nitems, max_nbrs))
    nbr_vals = torch.empty((nitems, max_nbrs))
    # and this stores the smallest similarity so far for each item
    nbr_min = torch.full((nitems,), torch.finfo().max)

    for i, iidx in enumerate(rated):
        row = model[int(iidx)]
        row_is = row.indices()[0]
        row_vs = row.values()
        assert row_is.shape == row_vs.shape

        row_avs = torch.abs(row_vs)
        fast = counts[row_is] < max_nbrs

        # save the fast-path items
        if torch.any(fast):
            ris_fast = row_is[fast]
            vs_fast = row_vs[fast]
            avs_fast = row_avs[fast]
            vals_fast = vs_fast * rate_v[i]
            nbr_sims[ris_fast, counts[ris_fast]] = vs_fast
            nbr_vals[ris_fast, counts[ris_fast]] = vals_fast
            counts[ris_fast] += 1
            t_sims[ris_fast] += avs_fast
            scores[ris_fast] += vals_fast
            nbr_min[ris_fast] = torch.minimum(nbr_min[ris_fast], vs_fast)

        # skip early if we're done
        if torch.all(fast):
            continue

        # now we have the slow-path items
        slow = torch.logical_not(fast)
        ris_slow = row_is[slow]
        rvs_slow = row_vs[slow]
        # which slow items might actually need an update?
        exc = rvs_slow > nbr_min[ris_slow]
        if not torch.any(exc):
            continue

        ris_slow = ris_slow[exc]
        rvs_slow = rvs_slow[exc]

        # this is brute-force linear search for simplicity right now
        # for each, find the neighbor that's the smallest:
        min_sims, mins = torch.min(nbr_sims[ris_slow], dim=1)
        assert torch.all(min_sims < rvs_slow)

        # now we need to update values: add in new and remove old
        min_vals = nbr_vals[ris_slow, mins]
        ravs_slow = row_avs[slow][exc]
        slow_vals = rvs_slow * rate_v[i]
        t_sims[ris_slow] += ravs_slow - min_sims.abs()
        scores[ris_slow] += slow_vals - min_vals
        # and save
        nbr_sims[ris_slow, mins] = ravs_slow
        nbr_vals[ris_slow, mins] = slow_vals
        # and now we need to update the saved minimums
        nm_sims, _nm_is = torch.min(nbr_sims[ris_slow], dim=1)
        nbr_min[ris_slow] = nm_sims

    # compute averages for items that pass match the threshold
    mask = counts >= min_nbrs
    scores[mask] /= t_sims[mask]
    scores[torch.logical_not(mask)] = torch.nan

    return scores


def _predict_sum(
    model: torch.Tensor,
    nrange: tuple[int, int],
    rate_v: torch.Tensor,
    rated: torch.Tensor,
) -> torch.Tensor:
    "Sum-of-similarities prediction function"
    nitems, _ni = model.shape
    assert nitems == _ni
    min_nbrs, max_nbrs = nrange
    _msg(logging.DEBUG, f"sum-scoring with {len(rated)} items")

    # we proceed rating-by-rating, and accumulate results
    t_sims = torch.zeros(nitems)
    counts = torch.zeros(nitems, dtype=torch.int32)
    nbr_sims = torch.zeros((nitems, max_nbrs))
    # and this stores the smallest similarity so far for each item
    nbr_min = torch.full((nitems,), torch.finfo().max)

    for i, iidx in enumerate(rated):
        iidx = int(iidx)
        row = model[iidx]
        row_is = row.indices()[0]
        row_vs = row.values()
        assert row_is.shape == row_vs.shape

        fast = counts[row_is] < max_nbrs

        # save the fast-path items
        if torch.any(fast):
            ris_fast = row_is[fast]
            vs_fast = row_vs[fast]
            nbr_sims[ris_fast, counts[ris_fast]] = vs_fast
            counts[ris_fast] += 1
            t_sims[ris_fast] += vs_fast
            nbr_min[ris_fast] = torch.minimum(nbr_min[ris_fast], vs_fast)

        # skip early if we're done
        if torch.all(fast):
            continue

        # now we have the slow-path items
        slow = torch.logical_not(fast)
        ris_slow = row_is[slow]
        rvs_slow = row_vs[slow]
        # which slow items might actually need an update?
        exc = rvs_slow > nbr_min[ris_slow]
        if not torch.any(exc):
            continue

        ris_slow = ris_slow[exc]
        rvs_slow = rvs_slow[exc]

        # this is brute-force linear search for simplicity right now
        # for each, find the neighbor that's the smallest:
        min_sims, mins = torch.min(nbr_sims[ris_slow], dim=1)

        # now we need to update values: add in new and remove old
        # anywhere our new neighbor is grater than smallest, replace smallest
        t_sims[ris_slow] -= min_sims
        t_sims[ris_slow] += rvs_slow
        # and save
        nbr_sims[ris_slow, mins] = rvs_slow
        # save the minimums
        nm_sims, _nm_is = torch.min(nbr_sims[ris_slow], dim=1)
        nbr_min[ris_slow] = nm_sims

    # compute averages for items that pass match the threshold
    t_sims[counts < min_nbrs] = torch.nan

    return t_sims


AggFun: TypeAlias = Callable[
    [
        torch.Tensor,
        tuple[int, int],
        torch.Tensor,
        torch.Tensor,
    ],
    torch.Tensor,
]

_predictors: dict[str, AggFun] = {
    "weighted-average": _predict_weighted_average,
    "sum": _predict_sum,
}
