Data Set Utilities
==================

.. module:: lenskit.datasets

The :py:mod:`lenskit.datasets` module provides utilities for reading a variety
of commonly-used LensKit data sets.  It does not package or automatically
download them, but loads them from a local directory where you have unpacked
the data set.  Each data set class or function takes a ``path`` parameter
specifying the location of the data set.

The normal mode of operation for these utilities is to provide a class for the
data set; this class then exposes the data set's data as attributes.  These
attributes are cached internally, so e.g. accessing :py:attr:`MovieLens.ratings`
twice will only load the data file once.

These data files have normalized column names to fit with LensKit's general
conventions.  These are the following:

- User ID columns are called ``user``.
- Item ID columns are called ``item``.
- Rating columns are called ``rating``.
- Timestamp columns are called ``timestamp``.

Other column names are unchanged.  Data tables that provide information about
specific things, such as a table of movie titles, are indexed by the relevant
ID (e.g. :py:attr:`MovieLens.ratings` is indexed by ``item``).

MovieLens Data Sets
-------------------

The GroupLens research group provides several data sets extracted from the
MovieLens service [ML]_.  These can be downloaded from https://grouplens.org/datasets/movielens/.

.. autoclass:: MovieLens
    :members:

.. autoclass:: ML100K
    :members:

.. autoclass:: ML1M
    :inherited-members:
    :members:

.. autoclass:: ML10M
    :inherited-members:
    :members:


.. [ML] F. Maxwell Harper and Joseph A. Konstan. 2015.
   The MovieLens Datasets: History and Context.
   *ACM Transactions on Interactive Intelligent Systems* (TiiS) **5**, 4, Article 19 (December 2015),
   19 pages. DOI=http://dx.doi.org/10.1145/2827872
