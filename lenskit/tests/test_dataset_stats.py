"""
Tests for the Dataset class.
"""

import numpy as np
import pandas as pd
from pytest import approx

from lenskit.data import Dataset
from lenskit.data.tables import NumpyUserItemTable, TorchUserItemTable
from lenskit.util.test import ml_ds, ml_ratings  # noqa: F401


def test_item_stats(ml_ratings: pd.DataFrame, ml_ds: Dataset):
    stats = ml_ds.item_stats()
    stats.info()

    assert len(stats) == ml_ds.item_count
    assert np.all(stats.index == ml_ds.items.index)

    assert np.all(stats["count"] == ml_ratings["item"].value_counts().reindex(ml_ds.items))
    assert np.all(stats["user_count"] == ml_ratings["item"].value_counts().reindex(ml_ds.items))
    assert np.all(stats["rating_count"] == ml_ratings["item"].value_counts().reindex(ml_ds.items))

    assert stats["mean_rating"].values == approx(
        ml_ratings.groupby("item")["rating"].mean().reindex(ml_ds.items).values
    )

    ts = ml_ratings.groupby("item")["timestamp"].min().reindex(ml_ds.items)
    bad = stats["first_time"] != ts
    nbad = np.sum(bad)
    if nbad:
        df = stats[["first_time"]].assign(expected=ts)
        bdf = df[bad]
        raise AssertionError(f"timestamps mismatch:\n{bdf}")


def test_user_stats(ml_ratings: pd.DataFrame, ml_ds: Dataset):
    stats = ml_ds.user_stats()
    stats.info()

    assert len(stats) == ml_ds.user_count
    assert np.all(stats.index == ml_ds.users.index)

    assert np.all(stats["count"] == ml_ratings["user"].value_counts().reindex(ml_ds.users))
    assert np.all(stats["user_count"] == ml_ratings["user"].value_counts().reindex(ml_ds.users))
    assert np.all(stats["rating_count"] == ml_ratings["user"].value_counts().reindex(ml_ds.users))

    assert stats["mean_rating"].values == approx(
        ml_ratings.groupby("user")["rating"].mean().reindex(ml_ds.users).values
    )
    assert np.all(
        stats["first_time"] == ml_ratings.groupby("user")["timestamp"].min().reindex(ml_ds.users)
    )
    assert np.all(
        stats["last_time"] == ml_ratings.groupby("user")["timestamp"].max().reindex(ml_ds.users)
    )
