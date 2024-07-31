# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

import functools as ft
import itertools as it
import math

import numpy as np
import pandas as pd

import pytest

from lenskit.data.dataset import Dataset
from lenskit.splitting.records import crossfold_records, sample_records


def test_crossfold_records(ml_ds: Dataset):
    splits = crossfold_records(ml_ds, 5)
    splits = list(splits)
    assert len(splits) == 5

    for s in splits:
        # do we have all the data?
        test_count = sum(len(il) for il in s.test.values())
        assert test_count + s.train.interaction_count == ml_ds.count("pairs")
        test_pairs = set((u, i) for (u, il) in s.test.items() for i in il.ids())
        tdf = s.train.interaction_matrix("pandas", field="rating", original_ids=True)
        train_pairs = set(zip(tdf["user_id"], tdf["item_id"]))

        # no overlap
        assert not (test_pairs & train_pairs)
        # union is complete
        assert len(test_pairs | train_pairs) == ml_ds.count("pairs")

    # the test sets are pairwise disjoint
    for s1, s2 in it.product(splits, splits):
        if s1 is s2:
            continue

        p1 = set((u, i) for (u, il) in s1.test.items() for i in il.ids())
        p2 = set((u, i) for (u, il) in s2.test.items() for i in il.ids())
        assert not (p1 & p2)


def test_sample_records_once(ml_ds):
    train, test = sample_records(ml_ds, size=1000)

    test_count = sum(len(il) for il in test.values())
    assert test_count == 1000
    assert test_count + train.interaction_count == ml_ds.count("pairs")
    test_pairs = set((u, i) for (u, il) in test.items() for i in il.ids())
    tdf = train.interaction_matrix("pandas", field="rating", original_ids=True)
    train_pairs = set(zip(tdf["user_id"], tdf["item_id"]))

    # no overlap
    assert not (test_pairs & train_pairs)
    # union is complete
    assert len(test_pairs | train_pairs) == ml_ds.count("pairs")


def test_sample_records(ml_ds):
    splits = sample_records(ml_ds, size=1000, repeats=5)
    splits = list(splits)
    assert len(splits) == 5

    for s in splits:
        test_count = sum(len(il) for il in s.test.values())
        assert test_count == 1000
        assert test_count + s.train.interaction_count == ml_ds.count("pairs")
        test_pairs = set((u, i) for (u, il) in s.test.items() for i in il.ids())
        tdf = s.train.interaction_matrix("pandas", field="rating", original_ids=True)
        train_pairs = set(zip(tdf["user_id"], tdf["item_id"]))

        # no overlap
        assert not (test_pairs & train_pairs)
        # union is complete
        assert len(test_pairs | train_pairs) == ml_ds.count("pairs")

    for s1, s2 in it.product(splits, splits):
        if s1 is s2:
            continue

        p1 = set((u, i) for (u, il) in s1.test.items() for i in il.ids())
        p2 = set((u, i) for (u, il) in s2.test.items() for i in il.ids())
        assert not (p1 & p2)


def test_sample_rows_more_smaller_parts(ml_ds: Dataset):
    splits = sample_records(ml_ds, 500, repeats=10)
    splits = list(splits)
    assert len(splits) == 10

    for s in splits:
        test_count = sum(len(il) for il in s.test.values())
        assert test_count == 500
        assert test_count + s.train.interaction_count == ml_ds.count("pairs")
        test_pairs = set((u, i) for (u, il) in s.test.items() for i in il.ids())
        tdf = s.train.interaction_matrix("pandas", field="rating", original_ids=True)
        train_pairs = set(zip(tdf["user_id"], tdf["item_id"]))

        # no overlap
        assert not (test_pairs & train_pairs)
        # union is complete
        assert len(test_pairs | train_pairs) == ml_ds.count("pairs")

    for s1, s2 in it.product(splits, splits):
        if s1 is s2:
            continue

        p1 = set((u, i) for (u, il) in s1.test.items() for i in il.ids())
        p2 = set((u, i) for (u, il) in s2.test.items() for i in il.ids())
        assert not (p1 & p2)


def test_sample_non_disjoint(ml_ds: Dataset):
    splits = sample_records(ml_ds, 1000, repeats=10, disjoint=False)
    splits = list(splits)
    assert len(splits) == 10

    for s in splits:
        test_count = sum(len(il) for il in s.test.values())
        assert test_count == 1000
        assert test_count + s.train.interaction_count == ml_ds.count("pairs")
        test_pairs = set((u, i) for (u, il) in s.test.items() for i in il.ids())
        tdf = s.train.interaction_matrix("pandas", field="rating", original_ids=True)
        train_pairs = set(zip(tdf["user_id"], tdf["item_id"]))

        # no overlap
        assert not (test_pairs & train_pairs)
        # union is complete
        assert len(test_pairs | train_pairs) == ml_ds.count("pairs")

    # There are enough splits & items we should pick at least one duplicate
    ipairs = (
        (
            set((u, i) for (u, il) in s1.test.items() for i in il.ids()),
            set((u, i) for (u, il) in s2.test.items() for i in il.ids()),
        )
        for (s1, s2) in it.product(splits, splits)
    )
    isizes = [len(i1.intersection(i2)) for (i1, i2) in ipairs]
    assert any(n > 0 for n in isizes)


@pytest.mark.slow
def test_sample_oversize(ml_ds: Dataset):
    splits = sample_records(ml_ds, 10000, repeats=50)
    splits = list(splits)
    assert len(splits) == 50

    for s in splits:
        test_count = sum(len(il) for il in s.test.values())
        assert test_count + s.train.interaction_count == ml_ds.count("pairs")
        test_pairs = set((u, i) for (u, il) in s.test.items() for i in il.ids())
        tdf = s.train.interaction_matrix("pandas", field="rating", original_ids=True)
        train_pairs = set(zip(tdf["user_id"], tdf["item_id"]))

        # no overlap
        assert not (test_pairs & train_pairs)
        # union is complete
        assert len(test_pairs | train_pairs) == ml_ds.count("pairs")
