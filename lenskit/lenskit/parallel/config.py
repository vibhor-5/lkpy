# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2024 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

# pyright: basic
from __future__ import annotations

import logging
import multiprocessing as mp
import os
import warnings
from dataclasses import dataclass
from typing import Optional

import torch
from threadpoolctl import threadpool_limits

_config: Optional[ParallelConfig] = None
_log = logging.getLogger(__name__)


@dataclass
class ParallelConfig:
    processes: int
    threads: int
    backend_threads: int
    child_threads: int


def initialize(
    *,
    processes: int | None = None,
    threads: int | None = None,
    backend_threads: int | None = None,
    child_threads: int | None = None,
):
    """
    Set up and configure LensKit parallelism.  This only needs to be called if
    you want to control when and how parallelism is set up; components using
    parallelism will call :func:`ensure_init`, which will call this function
    with its default arguments if it has not been called.

    Args:
        processes:
            The number of processes to use for multiprocessing evaluations (see
            :envvar:`LK_NUM_PROCS`)
        threads:
            The number of threads to use for parallel model training and similar
            operations (see :envvar:`LK_NUM_THREADS`).
        backend_threads:
            The number of threads underlying computational engines should use
            (see :envvar:`LK_NUM_BACKEND_THREADS`).
        child_threads:
            The number of threads backends are allowed to use in the worker
            processes in multiprocessing operations (see
            :envvar:`LK_NUM_CHILD_THREADS`).
    """
    global _config
    if _config:
        _log.warning("parallelism already initialized")
        return

    # our parallel computation doesn't work with FD sharing
    torch.multiprocessing.set_sharing_strategy("file_system")

    _config = _resolve_parallel_config(processes, threads, backend_threads, child_threads)
    _log.debug("configuring for parallelism: %s", _config)

    threadpool_limits(_config.backend_threads, "blas")
    try:
        torch.set_num_interop_threads(_config.threads)
    except RuntimeError as e:
        _log.warn("failed to configure Pytorch interop threads: %s", e)
        warnings.warn("failed to set interop threads", RuntimeWarning)
    try:
        torch.set_num_threads(_config.backend_threads)
    except RuntimeError as e:
        _log.warn("failed to configure Pytorch intra-op threads: %s", e)
        warnings.warn("failed to set intra-op threads", RuntimeWarning)


def ensure_parallel_init():
    """
    Make sure LensKit parallelism is configured, and configure with defaults if
    it is not.

    Components using parallelism or intensive computations should call this
    function before they begin training.
    """
    if not _config:
        initialize()


def get_parallel_config() -> ParallelConfig:
    """
    Ensure that parallelism is configured and return the configuration.
    """
    ensure_parallel_init()
    assert _config is not None
    return _config


def _resolve_parallel_config(
    processes: int | None = None,
    threads: int | None = None,
    backend_threads: int | None = None,
    child_threads: int | None = None,
) -> ParallelConfig:
    nprocs = os.environ.get("LK_NUM_PROCS", None)
    nthreads = os.environ.get("LK_NUM_THREADS", None)
    nbthreads = os.environ.get("LK_NUM_BACKEND_THREADS", None)
    cthreads = os.environ.get("LK_NUM_CHILD_THREADS", None)
    ncpus = mp.cpu_count()

    if processes is None and nprocs:
        processes = int(nprocs)

    if threads is None and nthreads:
        threads = int(nthreads)

    if backend_threads is None and nbthreads:
        backend_threads = int(nbthreads)

    if child_threads is None and cthreads:
        child_threads = int(cthreads)

    if processes is None:
        processes = min(ncpus, 4)

    if threads is None:
        threads = min(ncpus, 8)

    if backend_threads is None:
        backend_threads = max(min(ncpus // threads, 4), 1)

    if child_threads is None:
        child_threads = max(min(ncpus // processes, 4), 1)

    return ParallelConfig(processes, threads, backend_threads, child_threads)
