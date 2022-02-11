LensKit
=======

LensKit is a set of Python tools for experimenting with and studying recommender
systems.  It provides support for training, running, and evaluating recommender
algorithms in a flexible fashion suitable for research and education.

LensKit for Python (also known as LKPY) is the successor to the Java-based
LensKit toolkit and a part of the LensKit project.

If you use Lenskit in published research, cite [LKPY]_.

.. [LKPY]
    Michael D. Ekstrand. 2020.
    LensKit for Python: Next-Generation Software for Recommender Systems Experiments.
    In <cite>Proceedings of the 29th ACM International Conference on Information and Knowledge Management</cite> (CIKM '20).
    DOI:`10.1145/3340531.3412778 <https://dx.doi.org/10.1145/3340531.3412778>`_.
    arXiv:`1809.03125 <https://arxiv.org/abs/1809.03125>`_ [cs.IR].

Throughout this documentation, we use the notation of :cite:t:`Ekstrand2019-dh`.

Resources
---------

- `Mailing list, etc. <https://lenskit.org/connect>`_
- `Source and issues on GitHub <https://github.com/lenskit/lkpy>`_

.. toctree::
   :maxdepth: 2
   :caption: Overview

   install
   GettingStarted
   examples
   Release Notes <https://github.com/lenskit/lkpy/releases>

.. toctree::
   :maxdepth: 2
   :caption: Running Experiments

   datasets
   crossfold
   batch
   evaluation/index

.. toctree::
    :maxdepth: 1
    :caption: Algorithms

    interfaces
    algorithms
    basic
    ranking
    bias
    knn
    mf
    addons

.. toctree::
    :maxdepth: 2
    :caption: Tips and Tricks

    performance
    diagnostics
    impl-tips

.. toctree::
    :maxdepth: 2
    :caption: Configuration and Internals

    util
    internals

.. toctree::
    :maxdepth: 2
    :caption: Links

    references


Indices and tables
==================

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

Acknowledgements
================

This material is based upon work supported by the National Science Foundation
under Grant No. IIS 17-51278. Any opinions, findings, and conclusions or
recommendations expressed in this material are those of the author(s) and do not
necessarily reflect the views of the National Science Foundation.
