# Python recommendation tools

![Test Suite](https://github.com/lenskit/lkpy/workflows/Test%20Suite/badge.svg)
[![codecov](https://codecov.io/gh/lenskit/lkpy/branch/master/graph/badge.svg)](https://codecov.io/gh/lenskit/lkpy)

LensKit is a set of Python tools for experimenting with and studying recommender
systems.  It provides support for training, running, and evaluating recommender
algorithms in a flexible fashion suitable for research and education.

LensKit for Python (LKPY) is the successor to the Java-based LensKit project.

> [!IMPORTANT]
> If you use LensKit for Python in published research, please cite:
>
> > Michael D. Ekstrand. 2020.
> > LensKit for Python: Next-Generation Software for Recommender Systems Experiments.
> > In <cite>Proceedings of the 29th ACM International Conference on Information and Knowledge Management</cite> (CIKM '20).
> > DOI:[10.1145/3340531.3412778](https://dx.doi.org/10.1145/3340531.3412778).
> > arXiv:[1809.03125](https://arxiv.org/abs/1809.03125) [cs.IR].

> [!WARNING]
> This is the `main` branch of LensKit, following new development in preparation
> for the 2024 release.  It will be changing frequently and incompatibly. You
> probably want to use a [stable release][release].

[release]: https://lkpy.lenskit.org/en/stable/

## Installing

To install the current release with Anaconda (recommended):

    conda install -c conda-forge lenskit

Or you can use `pip`:

    pip install lenskit

To use the latest development version, install directly from GitHub:

    pip install -U git+https://github.com/lenskit/lkpy

Then see [Getting Started](https://lkpy.lenskit.org/en/latest/GettingStarted.html)

## Developing

[issues]: https://github.com/lenskit/lkpy/issues
[workflow]: https://github.com/lenskit/lkpy/wiki/DevWorkflow

To contribute to LensKit, clone or fork the repository, get to work, and submit
a pull request.  We welcome contributions from anyone; if you are looking for a
place to get started, see the [issue tracker][issues].

Our development workflow is documented in [the wiki][workflow]; the wiki also
contains other information on *developing* LensKit. User-facing documentation is
at <https://lkpy.lenskit.org>.

[conda-lock]: https://github.com/conda-incubator/conda-lock
[lkbuild]: https://github.com/lenskit/lkbuild

We recommend using an Anaconda environment for developing LensKit.  We provide a
tool to automate setting up Conda environments from the LensKit dependencies; to
create a dev environment, checkout LensKit, then run:

    pipx ./utils/conda-tool.py --env -n lkpy pyproject.toml dev-requirements.txt
    conda activate lkpy

That will create and activate an environment named `lkpy` with all the LensKit
dependencies. You will also need to install LensKit in editable mode to do
things like run the tests:

    pip install -e lenskit

Each LensKit subpackage you want to work on will also need to be installed.

### Developing with Standard Virtual Environments

[uv]: https://github.com/astral-sh/uv

You can also use a standard virtual environment and vanilla Python to develop LensKit.
To do this, the easiest way is to use [uv][]:

    uv venv -p python3.11
    uv pip install -r full-dev-requirements.txt

You can also use traditional Pip:

    python -m venv .venv
    . .venv/bin/activate
    python -m pip install -r full-dev-requirements.txt

## Testing Changes

You should always test your changes by running the LensKit test suite:

    python -m pytest

If you want to use your changes in a LensKit experiment, you can locally install
your modified LensKit into your experiment's environment.  We recommend using
separate environments for LensKit development and for each experiment; you will
need to install the modified LensKit into your experiment's repository:

    conda activate my-exp
    conda install -c conda-forge
    cd /path/to/lkpy
    pip install -e . --no-deps

You may need to first uninstall LensKit from your experiment repo; make sure that
LensKit's dependencies are all still installed.

Once you have pushed your code to a GitHub branch, you can use a Git repository as
a Pip dependency in an `environment.yml` for your experiment, to keep using the
correct modified version of LensKit until your changes make it in to a release.

## Resources

- [Documentation](https://lkpy.lenskit.org)
- [Mailing list, etc.](https://lenskit.org/connect)

## Acknowledgements

This material is based upon work supported by the National Science Foundation
under Grant No. IIS 17-51278. Any opinions, findings, and conclusions or
recommendations expressed in this material are those of the author(s) and do not
necessarily reflect the views of the National Science Foundation.
