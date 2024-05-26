"""Test suite of HumanRendering wrapper."""
import re

import pytest

import gymnasium as gym
from gymnasium.wrappers import HumanRendering


def test_human_rendering():
    for mode in ["rgb_array", "rgb_array_list"]:
        env = HumanRendering(
            gym.make("CartPole-v1", render_mode=mode, disable_env_checker=True)
        )
        assert env.render_mode == "human"
        env.reset()

        for _ in range(75):
            _, _, terminated, truncated, _ = env.step(env.action_space.sample())
            if terminated or truncated:
                env.reset()

        env.close()


def test_builtin_human_rendering():
    """Directly requesting builtin human rendering."""
    env = gym.make("CartPole-v1", render_mode="human")

    assert env.render_mode == "human", f"Unexpected render mode {env.render_mode}"

    env.reset()
    for _ in range(75):
        _, _, terminated, truncated, _ = env.step(env.action_space.sample())
        if terminated or truncated:
            env.reset()

    # HumanRenderer on human renderer should not work
    with pytest.raises(
        AssertionError,
        match=re.escape(
            "Expected env.render_mode to be one of ['rgb_array', 'rgb_array_list', 'depth_array', 'depth_array_list'] but got 'human'"
        ),
    ):
        HumanRendering(env)
    env.close()
