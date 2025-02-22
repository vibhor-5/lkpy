# This file is part of LensKit.
# Copyright (C) 2018-2023 Boise State University
# Copyright (C) 2023-2025 Drexel University
# Licensed under the MIT license, see LICENSE.md for details.
# SPDX-License-Identifier: MIT

from pathlib import Path

from numpy.random import Generator, SeedSequence

from hypothesis import assume, given
from hypothesis import strategies as st
from pytest import skip

from lenskit.data.query import RecQuery
from lenskit.random import derivable_rng, load_seed, make_seed


@given(
    st.one_of(
        st.integers(min_value=0),
        st.binary(),
        st.uuids(),
        st.text(),
        st.lists(st.integers(min_value=0)),
    )
)
def test_make_seed(seed):
    ss = make_seed(seed)
    assert isinstance(ss, SeedSequence)
    state = ss.generate_state(1)
    assert len(state) == 1
    assert state[0]


@given(st.integers(min_value=0), st.emails(), st.emails())
def test_derivable_fixed(seed: int, uid1: str, uid2: str):
    assume(uid1 != uid2)

    drng = derivable_rng(seed)

    v1a = drng(RecQuery.create(uid1)).integers(1_000_000)
    v1b = drng(RecQuery.create(uid1)).integers(1_000_000)
    v2 = drng(RecQuery.create(uid2)).integers(1_000_000)

    assert v1a != v2
    assert v1a != v1b


@given(st.integers(min_value=0), st.emails(), st.emails())
def test_derivable_user(seed: int, uid1: str, uid2: str):
    assume(uid1 != uid2)

    drng = derivable_rng((seed, "user"))

    v1a = drng(RecQuery.create(uid1)).integers(1_000_000)
    v1b = drng(RecQuery.create(uid1)).integers(1_000_000)
    v2 = drng(RecQuery.create(uid2)).integers(1_000_000)

    assert v1a != v2
    assert v1a == v1b

    vnone = drng(None).integers(1_000_000)
    assert vnone != v1a
    assert vnone != v2


def test_load_seed_json():
    file = Path(__file__).parent / "config.json"
    seed = load_seed(file)
    assert seed.entropy == [20250205]


def test_load_seed_yaml():
    try:
        import yaml
    except ImportError:
        skip("pyyaml not installed")

    file = Path(__file__).parent / "config.yaml"
    seed = load_seed(file, "random_seed")
    assert seed.entropy == [20250205]


def test_load_seed_toml():
    file = Path(__file__).parent / "config.toml"
    seed = load_seed(file, "rng.seed")
    assert seed.entropy == [20250201]
