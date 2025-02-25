# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2025 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
Tests for the Dataset class.
"""

import numpy as np
import pandas as pd

from pytest import approx

from lenskit.data import Dataset, from_interactions_df
from lenskit.testing import ml_ds, ml_ratings  # noqa: F401

# re-running the stat tests are a good exercise of the lazy dataset code


def test_item_stats(ml_ratings: pd.DataFrame):
    ml_ds = Dataset(lambda: from_interactions_df(ml_ratings, item_col="item"))
    stats = ml_ds.item_stats()
    stats.info()

    assert len(stats) == ml_ds.item_count
    assert np.all(stats.index == ml_ds.items.index)

    assert np.all(stats["count"] == ml_ratings["item_id"].value_counts().reindex(ml_ds.items))
    assert np.all(stats["user_count"] == ml_ratings["item_id"].value_counts().reindex(ml_ds.items))
    assert np.all(
        stats["rating_count"] == ml_ratings["item_id"].value_counts().reindex(ml_ds.items)
    )

    assert stats["mean_rating"].values == approx(
        ml_ratings.groupby("item_id")["rating"].mean().reindex(ml_ds.items).values
    )

    ts = ml_ratings.groupby("item_id")["timestamp"].min().reindex(ml_ds.items)
    bad = stats["first_time"] != ts
    nbad = np.sum(bad)
    if nbad:
        df = stats[["first_time"]].assign(expected=ts)
        bdf = df[bad]
        raise AssertionError(f"timestamps mismatch:\n{bdf}")


def test_user_stats(ml_ratings: pd.DataFrame):
    ml_ds = Dataset(lambda: from_interactions_df(ml_ratings, item_col="item"))
    stats = ml_ds.user_stats()
    stats.info()

    assert len(stats) == ml_ds.user_count
    assert np.all(stats.index == ml_ds.users.index)

    assert np.all(stats["count"] == ml_ratings["user_id"].value_counts().reindex(ml_ds.users))
    assert np.all(stats["item_count"] == ml_ratings["user_id"].value_counts().reindex(ml_ds.users))
    assert np.all(
        stats["rating_count"] == ml_ratings["user_id"].value_counts().reindex(ml_ds.users)
    )

    assert stats["mean_rating"].values == approx(
        ml_ratings.groupby("user_id")["rating"].mean().reindex(ml_ds.users).values
    )
    assert np.all(
        stats["first_time"] == ml_ratings.groupby("user_id")["timestamp"].min().reindex(ml_ds.users)
    )
    assert np.all(
        stats["last_time"] == ml_ratings.groupby("user_id")["timestamp"].max().reindex(ml_ds.users)
    )
