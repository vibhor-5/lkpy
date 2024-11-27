# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
Test utilities for LKPY tests.
"""

import os
import os.path
from contextlib import contextmanager
from typing import Literal

import numpy as np
import pandas as pd
import scipy.sparse as sps
from pyprojroot import here

import hypothesis.extra.numpy as nph
import hypothesis.strategies as st
import pytest
from hypothesis import assume

from lenskit.basic import PopScorer, SoftmaxRanker
from lenskit.batch import recommend
from lenskit.data import Dataset, ItemList, ItemListCollection, UserIDKey, from_interactions_df
from lenskit.data.lazy import LazyDataset
from lenskit.data.movielens import load_movielens, load_movielens_df
from lenskit.math.sparse import torch_sparse_from_scipy
from lenskit.pipeline import RecPipelineBuilder
from lenskit.splitting import TTSplit, simple_test_pair

ml_test_dir = here("data/ml-latest-small")
ml_100k_zip = here("data/ml-100k.zip")

ml_test: Dataset = LazyDataset(lambda: load_movielens(ml_test_dir))


@pytest.fixture(scope="session")
def ml_ratings():
    """
    Fixture to load the test MovieLens ratings as a data frame. To use this,
    just include it as a parameter in your test::

        def test_thing_with_data(ml_ratings: pd.DataFrame):
            ...

    .. note::
        This is imported in ``conftest.py`` so it is always available in LensKit tests.
    """
    yield load_movielens_df(ml_test_dir)


@pytest.fixture(scope="session")
def ml_ds(ml_ratings: pd.DataFrame):
    """
    Fixture to load the MovieLens test dataset.  To use this, just include it as
    a parameter in your test::

        def test_thing_with_data(ml_ds: Dataset):
            ...

    .. note::
        This is imported in ``conftest.py`` so it is always available in LensKit tests.
    """
    yield from_interactions_df(ml_ratings)


@pytest.fixture
def ml_100k():
    """
    Fixture to load the MovieLens 100K dataset (currently as a data frame).  It skips
    the test if the ML100K data is not available.
    """
    if not ml_100k_zip.exists():
        pytest.skip("ML100K data not available")
    yield load_movielens_df(ml_100k_zip)


@pytest.fixture(scope="session")
def demo_recs(ml_ds: Dataset) -> tuple[TTSplit, ItemListCollection[UserIDKey]]:
    """
    A demo set of train, test, and recommendation data.
    """
    rng = np.random.default_rng(42)
    split = simple_test_pair(ml_ds, f_rates=0.5, rng=rng)

    builder = RecPipelineBuilder()
    builder.scorer(PopScorer())
    builder.ranker(SoftmaxRanker(500))
    pipe = builder.build()
    pipe.train(split.train)

    recs = recommend(pipe, list(split.test.keys()), 500, n_jobs=1, rng=rng)
    return split, recs


@contextmanager
def set_env_var(var, val):
    "Set an environment variable & restore it."
    old_val = os.environ.get(var, None)
    try:
        if val is None:
            if old_val is not None:
                del os.environ[var]
        else:
            os.environ[var] = val
        yield
    finally:
        if old_val is not None:
            os.environ[var] = old_val
        elif val is not None:
            del os.environ[var]


@st.composite
def coo_arrays(
    draw,
    shape=None,
    dtype=nph.floating_dtypes(endianness="=", sizes=[32, 64]),
    elements=st.floats(-1e6, 1e6, allow_nan=False, allow_infinity=False, width=32),
) -> sps.coo_array:
    if shape is None:
        shape = st.tuples(st.integers(1, 100), st.integers(1, 100))

    if isinstance(shape, st.SearchStrategy):
        shape = draw(shape)

    if not isinstance(shape, tuple):
        shape = shape, shape
    rows, cols = shape
    if isinstance(rows, st.SearchStrategy):
        rows = draw(rows)
    if isinstance(cols, st.SearchStrategy):
        cols = draw(cols)

    mask = draw(nph.arrays(np.bool_, (rows, cols)))
    # at least one nonzero value
    assume(np.any(mask))
    nnz = int(np.sum(mask))

    ris, cis = np.nonzero(mask)

    vs = draw(
        nph.arrays(dtype, nnz, elements=elements),
    )

    return sps.coo_array((vs, (ris, cis)), shape=(rows, cols))


@st.composite
def sparse_arrays(draw, *, layout="csr", **kwargs):
    if isinstance(layout, list):
        layout = st.sampled_from(layout)
    if isinstance(layout, st.SearchStrategy):
        layout = draw(layout)

    M: sps.coo_array = draw(coo_arrays(**kwargs))

    match layout:
        case "csr":
            return M.tocsr()
        case "csc":
            return M.tocsc()
        case "coo":
            return M
        case _:
            raise ValueError(f"invalid layout {layout}")


@st.composite
def sparse_tensors(draw, *, layout="csr", **kwargs):
    if isinstance(layout, list):
        layout = st.sampled_from(layout)
    if isinstance(layout, st.SearchStrategy):
        layout = draw(layout)

    M: sps.coo_array = draw(coo_arrays(**kwargs))
    return torch_sparse_from_scipy(M, layout)  # type: ignore


@st.composite
def scored_lists(
    draw: st.DrawFn,
    *,
    n: int | tuple[int, int] | st.SearchStrategy[int] = st.integers(0, 1000),
    scores: st.SearchStrategy[float] | Literal["gaussian"] | None = None,
) -> ItemList:
    """
    Hypothesis generator that produces scored lists.
    """
    if isinstance(n, st.SearchStrategy):
        n = draw(n)
    elif isinstance(n, tuple):
        n = draw(st.integers(*n))

    ids = np.arange(1, n + 1, dtype=np.int32)
    if scores == "gaussian":
        seed = draw(st.integers(0))
        rng = np.random.default_rng(seed)
        xs = np.exp(rng.normal(size=n))
    else:
        xs = draw(
            nph.arrays(nph.floating_dtypes(endianness="=", sizes=[32, 64]), n, elements=scores)
        )
    return ItemList(item_ids=ids, scores=xs)


jit_enabled = True
if "NUMBA_DISABLE_JIT" in os.environ:
    jit_enabled = False
if os.environ.get("PYTORCH_JIT", None) == "0":
    jit_enabled = False

wantjit = pytest.mark.skipif(not jit_enabled, reason="JIT required")
