"""Test suite for TimeAwareObservationV0."""
import numpy as np

from gymnasium.spaces import Box, Dict, Tuple
from gymnasium.wrappers import TimeAwareObservationV0
from tests.testing_env import GenericTestEnv


def test_default_parameters():
    """Test the flatten parameter for the TimeAwareObservation wrapper."""
    env = GenericTestEnv(observation_space=Box(0, 1))
    wrapped_env = TimeAwareObservationV0(env)
    assert isinstance(wrapped_env.observation_space, Box)
    reset_obs, _ = wrapped_env.reset()
    step_obs, _, _, _, _ = wrapped_env.step(None)
    assert reset_obs.shape == (2,) and step_obs.shape == (2,)

    assert reset_obs in wrapped_env.observation_space
    assert step_obs in wrapped_env.observation_space


def test_env_flatten_obs_space():
    """Test the TimeAwareObservation wrapper for three type of observation spaces."""
    env = GenericTestEnv(observation_space=Dict(arm_1=Box(0, 1), arm_2=Box(2, 3)))
    wrapped_env = TimeAwareObservationV0(env, flatten=False)
    assert isinstance(wrapped_env.observation_space, Dict)
    reset_obs, _ = wrapped_env.reset()
    step_obs, _, _, _, _ = wrapped_env.step(None)
    assert "time" in reset_obs and "time" in step_obs, f"{reset_obs}, {step_obs}"

    assert reset_obs in wrapped_env.observation_space
    assert step_obs in wrapped_env.observation_space

    env = GenericTestEnv(observation_space=Tuple((Box(0, 1), Box(2, 3))))
    wrapped_env = TimeAwareObservationV0(env, flatten=False)
    assert isinstance(wrapped_env.observation_space, Tuple)
    reset_obs, _ = wrapped_env.reset()
    step_obs, _, _, _, _ = wrapped_env.step(None)
    assert len(reset_obs) == 3 and len(step_obs) == 3

    assert reset_obs in wrapped_env.observation_space
    assert step_obs in wrapped_env.observation_space

    env = GenericTestEnv(observation_space=Box(0, 1))
    wrapped_env = TimeAwareObservationV0(env, flatten=False)
    assert isinstance(wrapped_env.observation_space, Dict)
    reset_obs, _ = wrapped_env.reset()
    step_obs, _, _, _, _ = wrapped_env.step(None)
    assert isinstance(reset_obs, dict) and isinstance(step_obs, dict)
    assert "obs" in reset_obs and "obs" in step_obs
    assert "time" in reset_obs and "time" in step_obs

    assert reset_obs in wrapped_env.observation_space
    assert step_obs in wrapped_env.observation_space


def test_normalize_time_parameter():
    """Test the normalize time parameter for DelayObservation wrappers."""
    # Tests the normalize_time parameter
    env = GenericTestEnv(observation_space=Box(0, 1))
    wrapped_env = TimeAwareObservationV0(env, flatten=False, normalize_time=False)
    reset_obs, _ = wrapped_env.reset()
    step_obs, _, _, _, _ = wrapped_env.step(None)
    assert reset_obs["time"] == np.array([0], dtype=np.int32) and step_obs[
        "time"
    ] == np.array([1], dtype=np.int32)

    assert reset_obs in wrapped_env.observation_space
    assert step_obs in wrapped_env.observation_space

    env = GenericTestEnv(observation_space=Box(0, 1))
    wrapped_env = TimeAwareObservationV0(env, flatten=False, normalize_time=True)
    reset_obs, _ = wrapped_env.reset()
    step_obs, _, _, _, _ = wrapped_env.step(None)
    assert reset_obs["time"] == 0.0 and step_obs["time"] == 0.01

    assert reset_obs in wrapped_env.observation_space
    assert step_obs in wrapped_env.observation_space
