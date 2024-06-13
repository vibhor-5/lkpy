Hierarchical Poisson Factorization
==================================

.. module:: lenskit.hpf

This module provides a LensKit bridge to the hpfrec_ library implementing hierarchical Poisson
factorization :cite:p:`gopalanScalableRecommendationPoisson2013a`.

To install, run::

    pip install lenskit-hpf

We do **not** provide a Conda package, because hpfrec_ is not packaged for Conda.  You can
use ``pip`` to install this package in your Anaconda environment after installing LensKit
itself with ``conda``.

.. _hpfrec: https://hpfrec.readthedocs.io/en/latest/

.. autoclass:: HPF
    :members:
