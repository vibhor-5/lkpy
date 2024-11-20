# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
k-NN recommender models.
"""

from .item import ItemKNNScorer
from .user import UserKNNScorer

__all__ = ["ItemKNNScorer", "UserKNNScorer"]
