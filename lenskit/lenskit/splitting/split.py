# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT
from __future__ import annotations

from dataclasses import dataclass
from typing import Generic, Literal, TypeAlias, TypeVar

import pandas as pd

from lenskit.data import Dataset, ItemListCollection
from lenskit.data.matrix import MatrixDataset

SplitTable: TypeAlias = Literal["matrix"]
TK = TypeVar("TK", bound=tuple)


@dataclass
class TTSplit(Generic[TK]):
    """
    A train-test set from splitting or other sources.
    """

    train: Dataset
    """
    The training data.
    """

    test: ItemListCollection[TK]
    """
    The test data.
    """

    @property
    def test_size(self) -> int:
        """
        Get the number of test pairs.
        """
        return sum(len(il) for il in self.test.lists())

    @property
    def test_df(self) -> pd.DataFrame:
        """
        Get the test data as a data frame.
        """
        return self.test.to_df()

    @property
    def train_df(self) -> pd.DataFrame:
        """
        Get the training data as a data frame.
        """
        return self.train.interaction_matrix("pandas", field="all")

    @classmethod
    def from_src_and_test(cls, src: Dataset, test: ItemListCollection[TK]) -> TTSplit[TK]:
        """
        Create a split by subtracting test data from a source dataset.
        """
        cols = list(test.key_fields) + ["item_id"]

        test_df = test.to_df().set_index(cols)
        mask = pd.Series(False, index=test_df.index)

        df = src.interaction_matrix("pandas", field="all", original_ids=True).set_index(cols)

        mask = mask.reindex(df.index, fill_value=True)

        train_df = df[mask]
        train = MatrixDataset(src.users, src.items, train_df.reset_index())

        return cls(train, test)
