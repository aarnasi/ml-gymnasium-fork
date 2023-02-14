"""Testing suite for the experimental vector utility functions for spaces."""

import copy
import re
from typing import Iterable

import pytest

from gymnasium import Space
from gymnasium.experimental.vector.utils import (
    batch_space,
    concatenate,
    create_empty_array,
    iterate,
)
from gymnasium.utils.env_checker import data_equivalence
from tests.experimental.vector.utils.utils import is_rng_equal
from tests.spaces.utils import TESTING_BASE_SPACE, TESTING_SPACES, TESTING_SPACES_IDS


@pytest.mark.parametrize("space", TESTING_SPACES, ids=TESTING_SPACES_IDS)
@pytest.mark.parametrize("n", [1, 4], ids=[f"n={n}" for n in [1, 4]])
def test_batch_space_concatenate_iterate_create_empty_array(space: Space, n: int):
    """Test all space_utils functions using them together."""
    # Batch the space and create a sample
    batched_space = batch_space(space, n)
    assert isinstance(batched_space, Space)
    batched_sample = batched_space.sample()
    assert batched_sample in batched_space

    # Check the batched samples are within the original space
    iterated_samples = iterate(batched_space, batched_sample)
    assert isinstance(iterated_samples, Iterable)
    unbatched_samples = list(iterated_samples)
    assert len(unbatched_samples) == n
    assert all(item in space for item in unbatched_samples)

    # Create an empty array and check that space is within the batch space
    array = create_empty_array(space, n)
    # We do not check that the generated array is within the batched_space.
    # assert array in batched_space
    unbatched_array = list(iterate(batched_space, array))
    assert len(unbatched_array) == n
    # assert all(item in space for item in unbatched_array)

    # Generate samples from the original space and concatenate using array into a single object
    space_samples = [space.sample() for _ in range(n)]
    assert all(item in space for item in space_samples)
    concatenated_samples_array = concatenate(space, space_samples, array)
    # `concatenate` does not necessarily use the out object as the returned object
    # assert out is concatenated_samples_array
    assert concatenated_samples_array in batched_space

    # Iterate over the samples and check that the concatenated samples == original samples
    iterated_samples = iterate(batched_space, concatenated_samples_array)
    assert isinstance(iterated_samples, Iterable)
    unbatched_samples = list(iterated_samples)
    assert len(unbatched_samples) == n
    for unbatched_sample, original_sample in zip(unbatched_samples, space_samples):
        assert data_equivalence(unbatched_sample, original_sample)


@pytest.mark.parametrize("space", TESTING_SPACES, ids=TESTING_SPACES_IDS)
@pytest.mark.parametrize("n", [1, 2, 5], ids=[f"n={n}" for n in [1, 2, 5]])
@pytest.mark.parametrize(
    "base_seed", [123, 456], ids=[f"seed={base_seed}" for base_seed in [123, 456]]
)
def test_batch_space_deterministic(space: Space, n: int, base_seed: int):
    """Tests the batched spaces are deterministic by using a copied version."""
    # Copy the spaces and check that the np_random are not reference equal
    space_a = space
    space_a.seed(base_seed)
    space_b = copy.deepcopy(space_a)
    is_rng_equal(space_a.np_random, space_b.np_random)
    assert space_a.np_random is not space_b.np_random

    # Batch the spaces and check that the np_random are not reference equal
    space_a_batched = batch_space(space_a, n)
    space_b_batched = batch_space(space_b, n)
    is_rng_equal(space_a_batched.np_random, space_b_batched.np_random)
    assert space_a_batched.np_random is not space_b_batched.np_random
    # Create that the batched space is not reference equal to the origin spaces
    assert space_a.np_random is not space_a_batched.np_random

    # Check that batched space a and b random number generator are not effected by the original space
    space_a.sample()
    space_a_batched_sample = space_a_batched.sample()
    space_b_batched_sample = space_b_batched.sample()
    for a_sample, b_sample in zip(
        iterate(space_a_batched, space_a_batched_sample),
        iterate(space_b_batched, space_b_batched_sample),
    ):
        assert data_equivalence(a_sample, b_sample)


@pytest.mark.parametrize("space", TESTING_SPACES, ids=TESTING_SPACES_IDS)
@pytest.mark.parametrize("n", [4, 5], ids=[f"n={n}" for n in [4, 5]])
@pytest.mark.parametrize(
    "base_seed", [123, 456], ids=[f"seed={base_seed}" for base_seed in [123, 456]]
)
def test_batch_space_different_samples(space: Space, n: int, base_seed: int):
    """Tests that the rng values produced at each index are different to prevent if the rng is copied for each subspace."""
    space.seed(base_seed)

    batched_space = batch_space(space, n)
    assert space.np_random is not batched_space.np_random
    is_rng_equal(space.np_random, batched_space.np_random)

    batched_sample = batched_space.sample()
    unbatched_samples = list(iterate(batched_space, batched_sample))
    assert len(unbatched_samples) == n
    assert all(item in space for item in unbatched_samples)
    assert not all(
        data_equivalence(element, unbatched_samples[0]) for element in unbatched_samples
    ), unbatched_samples


@pytest.mark.parametrize(
    "func, n_args",
    [(batch_space, 1), (concatenate, 2), (iterate, 1), (create_empty_array, 2)],
)
def test_unknown_spaces(func, n_args):
    """Test spaces for vector utility functions on the error produced with unknown spaces."""
    args = [None for _ in range(n_args)]
    func_name = func.__name__
    with pytest.raises(
        TypeError,
        match=re.escape(
            f"The space provided to `{func_name}` is not a gymnasium Space instance, type: <class 'str'>, space"
        ),
    ):
        func("space", *args)

    with pytest.raises(
        ValueError,
        match=re.escape(
            f"Space of type `<class 'gymnasium.spaces.space.Space'>` doesn't have an registered `{func_name}` function."
        ),
    ):
        func(TESTING_BASE_SPACE, *args)
