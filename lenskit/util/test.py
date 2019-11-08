"""
Test utilities for LKPY tests.
"""

import os
import os.path
import logging
from contextlib import contextmanager

import numpy as np
from .. import matrix

import pytest

from lenskit.datasets import MovieLens, ML100K

_log = logging.getLogger(__name__)

ml_test = MovieLens('ml-latest-small')
ml100k = ML100K()


def ml_sample():
    ratings = ml_test.ratings
    icounts = ratings.groupby('item').rating.count()
    top = icounts.nlargest(500)
    ratings = ratings.set_index('item')
    top_rates = ratings.loc[top.index, :]
    _log.info('top 500 items yield %d of %d ratings', len(top_rates), len(ratings))
    return top_rates.reset_index()


def rand_csr(nrows=100, ncols=50, nnz=1000, values=True):
    "Generate a random CSR for testing."
    coords = np.random.choice(np.arange(ncols * nrows, dtype=np.int32), nnz, False)
    rows = np.mod(coords, nrows, dtype=np.int32)
    cols = np.floor_divide(coords, nrows, dtype=np.int32)
    if values:
        vals = np.random.randn(nnz)
    else:
        vals = None
    return matrix.CSR.from_coo(rows, cols, vals, (nrows, ncols))


@contextmanager
def rand_seed(seed):
    state = np.random.get_state()
    try:
        np.random.seed(seed)
        yield
    finally:
        np.random.set_state(state)


def repeated(n=50):
    """
    Decorator to run a test multiple times. Useful for randomized tests.

    Example::
        @repeated
        def test_something_with_random_values():
            pass

    Args:
        n(int):
            The number of iterations.  If the decorator is used without
            parentheses, this will be the function itself, which will be
            run the default number of times (50).

    Environment Variables:
        LK_TEST_ITERATION_MULT(float):
            A multiplier for the number of test iterations.  This is useful
            when debugging tests, to cause a test to be run more times than
            the default.
    """
    mult = os.environ.get('LK_TEST_ITERATION_MULT', '1')
    mult = float(mult)

    def wrap(proc):
        def run(*args, **kwargs):
            _log.info('running %s for %d iterations', proc.__name__, n * mult)
            for i in range(int(n * mult)):
                proc(*args, **kwargs)
        return run

    if hasattr(n, '__call__'):
        proc = n
        n = 50
        return wrap(proc)
    else:
        return wrap


wantjit = pytest.mark.skipif('NUMBA_DISABLE_JIT' in os.environ,
                             reason='JIT required')
