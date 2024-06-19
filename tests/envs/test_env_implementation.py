from typing import Optional

import numpy as np
import pytest

import gymnasium as gym
from gymnasium.envs.box2d import BipedalWalker, CarRacing
from gymnasium.envs.box2d.lunar_lander import demo_heuristic_lander
from gymnasium.envs.toy_text import TaxiEnv, CliffWalkingEnv
from gymnasium.envs.toy_text.frozen_lake import generate_random_map


def test_lunar_lander_heuristics():
    """Tests the LunarLander environment by checking if the heuristic lander works."""
    lunar_lander = gym.make("LunarLander-v3", disable_env_checker=True)
    total_reward = demo_heuristic_lander(lunar_lander, seed=1)
    assert total_reward > 100


@pytest.mark.parametrize("seed", [0, 10, 20, 30, 40])
def test_lunar_lander_random_wind_seed(seed: int):
    """Test that the wind_idx and torque are correctly drawn when setting a seed"""

    lunar_lander = gym.make(
        "LunarLander-v3", disable_env_checker=True, enable_wind=True
    ).unwrapped
    lunar_lander.reset(seed=seed)

    # Test that same seed gives same wind
    w1, t1 = lunar_lander.wind_idx, lunar_lander.torque_idx
    lunar_lander.reset(seed=seed)
    w2, t2 = lunar_lander.wind_idx, lunar_lander.torque_idx
    assert (
        w1 == w2 and t1 == t2
    ), "Setting same seed caused different initial wind or torque index"

    # Test that different seed gives different wind
    # There is a small chance that different seeds causes same number so test
    # 10 times (with different seeds) to make this chance incredibly tiny.
    for i in range(1, 11):
        lunar_lander.reset(seed=seed + i)
        w3, t3 = lunar_lander.wind_idx, lunar_lander.torque_idx
        if w2 != w3 and t1 != t3:  # Found different initial values
            break
    else:  # no break
        raise AssertionError(
            "Setting different seed caused same initial wind or torque index"
        )


def test_carracing_domain_randomize():
    """Tests the CarRacing Environment domain randomization.

    CarRacing DomainRandomize should have different colours at every reset.
    However, it should have same colours when `options={"randomize": False}` is given to reset.
    """
    env: CarRacing = gym.make("CarRacing-v2", domain_randomize=True).unwrapped

    road_color = env.road_color
    bg_color = env.bg_color
    grass_color = env.grass_color

    env.reset(options={"randomize": False})

    assert (
        road_color == env.road_color
    ).all(), f"Have different road color after reset with randomize turned off. Before: {road_color}, after: {env.road_color}."
    assert (
        bg_color == env.bg_color
    ).all(), f"Have different bg color after reset with randomize turned off. Before: {bg_color}, after: {env.bg_color}."
    assert (
        grass_color == env.grass_color
    ).all(), f"Have different grass color after reset with randomize turned off. Before: {grass_color}, after: {env.grass_color}."

    env.reset()

    assert (
        road_color != env.road_color
    ).all(), f"Have same road color after reset. Before: {road_color}, after: {env.road_color}."
    assert (
        bg_color != env.bg_color
    ).all(), (
        f"Have same bg color after reset. Before: {bg_color}, after: {env.bg_color}."
    )
    assert (
        grass_color != env.grass_color
    ).all(), f"Have same grass color after reset. Before: {grass_color}, after: {env.grass_color}."



def test_slippery_cliffwalking():
    """Test that the slippery cliffwalking environment is correctly implemented.
    We check here that there are always 3 possible transitions for each action and
    that there is a 1/3 probability for each.
    """
    envs = CliffWalkingEnv(is_slippery=True)
    for actions_dict in envs.P.values():
        for transitions in actions_dict.values():
            assert len(transitions) == 3
            assert all([r[0] == 1/3 for r in transitions])


def test_cliffwalking():
    env = CliffWalkingEnv(is_slippery=False)
    import json
    with open("new_implementation.json", "w+") as f:
        json.dump(env.P, f, default=str)
    for actions_dict in env.P.values():
        for transitions in actions_dict.values():
            assert len(transitions) == 1
            assert all([r[0] == 1. for r in transitions])

@pytest.mark.parametrize("seed", range(5))
def test_bipedal_walker_hardcore_creation(seed: int):
    """Test BipedalWalker hardcore creation.

    BipedalWalker with `hardcore=True` should have ladders
    stumps and pitfalls. A convenient way to identify if ladders,
    stumps and pitfall are created is checking whether the terrain
    has that particular terrain color.

    Args:
        seed (int): environment seed
    """
    HC_TERRAINS_COLOR1 = (255, 255, 255)
    HC_TERRAINS_COLOR2 = (153, 153, 153)

    env = gym.make("BipedalWalker-v3", disable_env_checker=True).unwrapped
    hc_env = gym.make("BipedalWalkerHardcore-v3", disable_env_checker=True).unwrapped
    assert isinstance(env, BipedalWalker) and isinstance(hc_env, BipedalWalker)
    assert env.hardcore is False and hc_env.hardcore is True

    env.reset(seed=seed)
    hc_env.reset(seed=seed)

    for terrain in env.terrain:
        assert terrain.color1 != HC_TERRAINS_COLOR1
        assert terrain.color2 != HC_TERRAINS_COLOR2

    hc_terrains_color1_count = 0
    hc_terrains_color2_count = 0
    for terrain in hc_env.terrain:
        if terrain.color1 == HC_TERRAINS_COLOR1:
            hc_terrains_color1_count += 1
        if terrain.color2 == HC_TERRAINS_COLOR2:
            hc_terrains_color2_count += 1

    assert hc_terrains_color1_count > 0
    assert hc_terrains_color2_count > 0


@pytest.mark.parametrize("map_size", [5, 10, 16])
def test_frozenlake_dfs_map_generation(map_size: int):
    """Frozenlake has the ability to generate random maps.

    This function checks that the random maps will always be possible to solve for sizes 5, 10, 16,
    currently only 8x8 maps can be generated.
    """
    new_frozenlake = generate_random_map(map_size)
    assert len(new_frozenlake) == map_size
    assert len(new_frozenlake[0]) == map_size

    # Runs a depth first search through the map to find the path.
    directions = [(1, 0), (0, 1), (-1, 0), (0, -1)]
    frontier, discovered = [], set()
    frontier.append((0, 0))
    while frontier:
        row, col = frontier.pop()
        if (row, col) not in discovered:
            discovered.add((row, col))

            for row_direction, col_direction in directions:
                new_row = row + row_direction
                new_col = col + col_direction
                if 0 <= new_row < map_size and 0 <= new_col < map_size:
                    if new_frozenlake[new_row][new_col] == "G":
                        return  # Successful, a route through the map was found
                    if new_frozenlake[new_row][new_col] not in "#H":
                        frontier.append((new_row, new_col))
    raise AssertionError("No path through the frozenlake was found.")


@pytest.mark.parametrize("map_size, seed", [(5, 123), (10, 42), (16, 987)])
def test_frozenlake_map_generation_with_seed(map_size: int, seed: int):
    map1 = generate_random_map(size=map_size, seed=seed)
    map2 = generate_random_map(size=map_size, seed=seed)
    assert map1 == map2
    map1 = generate_random_map(size=map_size, seed=seed)
    map2 = generate_random_map(size=map_size, seed=seed + 1)
    assert map1 != map2


def test_taxi_action_mask():
    env = TaxiEnv()

    for state in env.P:
        mask = env.action_mask(state)
        for action, possible in enumerate(mask):
            _, next_state, _, _ = env.P[state][action][0]
            assert state != next_state if possible else state == next_state


def test_taxi_encode_decode():
    env = TaxiEnv()

    state, info = env.reset()
    for _ in range(100):
        assert (
            env.encode(*env.decode(state)) == state
        ), f"state={state}, encode(decode(state))={env.encode(*env.decode(state))}"
        state, _, _, _, _ = env.step(env.action_space.sample())


@pytest.mark.parametrize(
    "env_name",
    ["Acrobot-v1", "CartPole-v1", "MountainCar-v0", "MountainCarContinuous-v0"],
)
@pytest.mark.parametrize(
    "low_high", [None, (-0.4, 0.4), (np.array(-0.4), np.array(0.4))]
)
def test_customizable_resets(env_name: str, low_high: Optional[list]):
    env = gym.make(env_name)
    env.action_space.seed(0)
    # First ensure we can do a reset.
    if low_high is None:
        env.reset()
    else:
        low, high = low_high
        env.reset(options={"low": low, "high": high})
        assert np.all((env.unwrapped.state >= low) & (env.unwrapped.state <= high))
    # Make sure we can take a step.
    env.step(env.action_space.sample())


# We test Pendulum separately, as the parameters are handled differently.
@pytest.mark.parametrize(
    "low_high",
    [
        None,
        (1.2, 1.0),
        (np.array(1.2), np.array(1.0)),
    ],
)
def test_customizable_pendulum_resets(low_high: Optional[list]):
    env = gym.make("Pendulum-v1")
    env.action_space.seed(0)
    # First ensure we can do a reset and the values are within expected ranges.
    if low_high is None:
        env.reset()
    else:
        low, high = low_high
        # Pendulum is initialized a little differently than the other
        # environments, where we specify the x and y values for the upper
        # limit (and lower limit is just the negative of it).
        env.reset(options={"x_init": low, "y_init": high})
    # Make sure we can take a step.
    env.step(env.action_space.sample())


@pytest.mark.parametrize(
    "env_name",
    ["Acrobot-v1", "CartPole-v1", "MountainCar-v0", "MountainCarContinuous-v0"],
)
@pytest.mark.parametrize(
    "low_high",
    [
        ("x", "y"),
        (10.0, 8.0),
        ([-1.0, -1.0], [1.0, 1.0]),
        (np.array([-1.0, -1.0]), np.array([1.0, 1.0])),
    ],
)
def test_invalid_customizable_resets(env_name: str, low_high: list):
    env = gym.make(env_name)
    low, high = low_high
    with pytest.raises(ValueError):
        # match=re.escape(f"Lower bound ({low}) must be lower than higher bound ({high}).")
        # match=f"An option ({x}) could not be converted to a float."
        env.reset(options={"low": low, "high": high})


def test_cartpole_vector_equiv():
    env = gym.make("CartPole-v1")
    envs = gym.make_vec("CartPole-v1", num_envs=1)

    assert env.action_space == envs.single_action_space
    assert env.observation_space == envs.single_observation_space

    # reset
    seed = np.random.randint(0, 1000)
    obs, info = env.reset(seed=seed)
    vec_obs, vec_info = envs.reset(seed=seed)

    assert obs in env.observation_space
    assert vec_obs in envs.observation_space
    assert np.all(obs == vec_obs[0])
    assert info == vec_info

    assert np.all(env.unwrapped.state == envs.unwrapped.state[:, 0])

    # step
    for i in range(100):
        action = env.action_space.sample()
        assert np.array([action]) in envs.action_space

        obs, reward, term, trunc, info = env.step(action)
        vec_obs, vec_reward, vec_term, vec_trunc, vec_info = envs.step(
            np.array([action])
        )

        assert obs in env.observation_space
        assert vec_obs in envs.observation_space
        assert np.all(obs == vec_obs[0])
        assert reward == vec_reward
        assert term == vec_term
        assert trunc == vec_trunc
        assert info == vec_info

        assert np.all(env.unwrapped.state == envs.unwrapped.state[:, 0])

        if term:
            break

    obs, info = env.reset()
    # the vector action shouldn't matter as autoreset
    vec_obs, vec_reward, vec_term, vec_trunc, vec_info = envs.step(
        envs.action_space.sample()
    )

    assert obs in env.observation_space
    assert vec_obs in envs.observation_space
    assert np.all(obs == vec_obs[0])
    assert vec_reward == np.array([0])
    assert vec_term == np.array([False])
    assert vec_trunc == np.array([False])
    assert info == vec_info

    assert np.all(env.unwrapped.state == envs.unwrapped.state[:, 0])

    env.close()
    envs.close()
