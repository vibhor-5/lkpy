import zlib
import numpy as np
from lenskit.util import random

from pytest import mark

new_gen = mark.skipif(not random._have_gen, reason="requires NumPy with generators")
old_gen = mark.skipif(random._have_gen, reason="only for legacy NumPy")


@new_gen
def test_generator():
    rng = random.rng()
    assert isinstance(rng, np.random.Generator)


@new_gen
def test_generator_seed():
    rng = random.rng(42)
    assert isinstance(rng, np.random.Generator)


@new_gen
def test_generator_seed_seq():
    seq = np.random.SeedSequence(42)
    rng = random.rng(seq)
    assert isinstance(rng, np.random.Generator)


def test_generator_legacy():
    rng = random.rng(legacy=True)
    assert isinstance(rng, np.random.RandomState)


def test_generator_legacy_seed():
    rng = random.rng(42, legacy=True)
    assert isinstance(rng, np.random.RandomState)


def test_generator_legacy_passthrough():
    rng1 = random.rng(legacy=True)
    rng = random.rng(rng1)
    assert isinstance(rng, np.random.RandomState)


@new_gen
def test_generator_legacy_ss():
    seq = np.random.SeedSequence(42)
    rng = random.rng(seq, legacy=True)
    assert isinstance(rng, np.random.RandomState)


@new_gen
def test_generator_convert_to_legacy():
    rng1 = random.rng()
    rng = random.rng(rng1, legacy=True)
    assert isinstance(rng, np.random.RandomState)


@new_gen
def test_generator_passthrough():
    rng1 = random.rng()
    rng = random.rng(rng1)
    assert isinstance(rng, np.random.Generator)
    assert rng is rng1


@old_gen
def test_random_state():
    rng = random.rng()
    assert isinstance(rng, np.random.RandomState)
    rng2 = random.rng()
    assert rng2 is rng  # we use the same random state multiple times


@old_gen
def test_random_state_int_seed():
    rng = random.rng(42)
    assert isinstance(rng, np.random.RandomState)
    rng2 = random.rng()
    assert rng is not rng2


@new_gen
def test_initialize():
    random.init_rng(42)
    assert random._rng_impl.seed.entropy == 42
    assert len(random._rng_impl.seed.spawn_key) == 0


@old_gen
def test_initialize_legacy():
    random.init_rng(42)
    assert random._rng_impl.seed == 42


@new_gen
def test_initialize_key():
    random.init_rng(42, 'wombat')
    assert random._rng_impl.seed.entropy == 42
    assert random._rng_impl.seed.spawn_key == (zlib.crc32(b'wombat'),)


@new_gen
def test_derive_seed():
    random.init_rng(42, propagate=False)
    s2 = random.derive_seed()
    assert s2.entropy == 42
    assert s2.spawn_key == (0,)


@new_gen
def test_derive_seed_intkey():
    random.init_rng(42, propagate=False)
    s2 = random.derive_seed(10, 7)
    assert s2.entropy == 42
    assert s2.spawn_key == (10, 7)


@new_gen
def test_derive_seed_str():
    random.init_rng(42, propagate=False)
    s2 = random.derive_seed(b'wombat')
    assert s2.entropy == 42
    assert s2.spawn_key == (zlib.crc32(b'wombat'),)
