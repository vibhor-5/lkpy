# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

"""
Batch-run recommendation pipelines for evaluation.
"""

from __future__ import annotations

from typing import Mapping, Sequence

from lenskit.data import ID, GenericKey, ItemList, ItemListCollection, UserIDKey
from lenskit.pipeline import Pipeline

from ._results import BatchResults
from ._runner import BatchPipelineRunner, InvocationSpec

__all__ = ["BatchPipelineRunner", "BatchResults", "InvocationSpec", "predict", "recommend"]


def predict(
    pipeline: Pipeline,
    test: ItemListCollection[GenericKey] | Mapping[ID, ItemList],
    *,
    n_jobs: int | None = None,
    **kwargs,
) -> ItemListCollection[GenericKey]:
    """
    Convenience function to batch-generate rating predictions (or other per-item
    scores) from a pipeline.  This is a batch version of :func:`lenskit.predict`.

    Stability:
        Caller
    """

    runner = BatchPipelineRunner(n_jobs=n_jobs)
    runner.predict()
    outs = runner.run(pipeline, test)
    return outs.output("predictions")  # type: ignore


def score(
    pipeline: Pipeline,
    test: ItemListCollection[GenericKey] | Mapping[ID, ItemList],
    *,
    n_jobs: int | None = None,
    **kwargs,
) -> ItemListCollection[GenericKey]:
    """
    Convenience function to batch-generate personalized scores from a pipeline.
    This is a batch version of :func:`lenskit.predict`.

    Stability:
        Caller
    """

    runner = BatchPipelineRunner(n_jobs=n_jobs)
    runner.score()
    outs = runner.run(pipeline, test)
    return outs.output("scores")  # type: ignore


def recommend(
    pipeline: Pipeline,
    users: Sequence[ID | UserIDKey],
    n: int | None = None,
    candidates=None,
    *,
    n_jobs: int | None = None,
    **kwargs,
) -> ItemListCollection[UserIDKey]:
    """
    Convenience function to batch-generate recommendations from a pipeline. This
    is a batch version of :func:`lenskit.recommend`.

    .. todo::

        Support more inputs than just user IDs.

    Stability:
        Caller
    """

    runner = BatchPipelineRunner(n_jobs=n_jobs)
    runner.recommend(n=n)
    outs = runner.run(pipeline, users)
    return outs.output("recommendations")  # type: ignore
