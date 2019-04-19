"""
Miscellaneous utility functions.
"""

import logging
from copy import deepcopy

from ..algorithms import Algorithm
from .files import *
from .accum import Accumulator
from .timing import Stopwatch
from .data import read_df_detect, write_parquet, load_ml_ratings

_log = logging.getLogger(__name__)


def clone(algo):
    """
    Clone an algorithm, but not its fitted data.  This is like
    :py:func:`scikit.base.clone`, but may not work on arbitrary SciKit estimators.
    LensKit algorithms are compatible with SciKit clone, however, so feel free
    to use that if you need more general capabilities.

    This function is somewhat derived from the SciKit one.

    >>> from lenskit.algorithms.basic import Bias
    >>> orig = Bias()
    >>> copy = clone(orig)
    >>> copy is orig
    False
    >>> copy.damping == orig.damping
    True
    """
    _log.debug('cloning %s', algo)
    if isinstance(algo, Algorithm) or hasattr(algo, 'get_params'):
        params = algo.get_params(deep=False)

        sps = dict([(k, clone(v)) for (k, v) in params.items()])
        return algo.__class__(**sps)
    elif isinstance(algo, list) or isinstance(algo, tuple):
        return [clone(a) for a in algo]
    else:
        return deepcopy(algo)


class LastMemo:
    def __init__(self, func, check_type='identity'):
        self.function = func
        self.check = check_type
        self.memory = None
        self.result = None

    def __call__(self, arg):
        if not self._arg_is_last(arg):
            self.result = self.function(arg)
            self.memory = arg

        return self.result

    def _arg_is_last(self, arg):
        if self.check == 'identity':
            return arg is self.memory
        elif self.check == 'equality':
            return arg == self.memory


def last_memo(func=None, check_type='identity'):
    if func is None:
        return lambda f: LastMemo(f, check_type)
    else:
        return LastMemo(func, check_type)


def no_progress(obj, **kwargs):
    return obj
