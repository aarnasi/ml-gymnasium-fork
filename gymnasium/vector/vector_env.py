"""Base class for vectorized environments."""
from __future__ import annotations

from typing import TYPE_CHECKING, Any, Generic, TypeVar

import numpy as np

import gymnasium as gym
from gymnasium.utils import seeding

if TYPE_CHECKING:
    from gymnasium.envs.registration import EnvSpec

__all__ = ["VectorEnv"]

VectorObsType = TypeVar("VectorObsType")
VectorActType = TypeVar("VectorActType")
VectorArrayType = TypeVar("VectorArrayType")


class VectorEnv(Generic[VectorObsType, VectorActType, VectorArrayType]):
    """Base class for vectorized environments to run multiple independent copies of the same environment in parallel.

    Vector environments can provide a linear speed-up in the steps taken per second through sampling multiple
    sub-environments at the same time. To prevent terminated environments waiting until all sub-environments have
    terminated or truncated, the vector environments autoreset sub-environments after they terminate or truncated.
    As a result, the final step's observation and info are overwritten by the reset's observation and info.
    Therefore, the observation and info for the final step of a sub-environment is stored in the info parameter,
    using `"final_observation"` and `"final_info"` respectively. See :meth:`step` for more information.

    The vector environments batch `observations`, `rewards`, `terminations`, `truncations` and `info` for each
    parallel environment. In addition, :meth:`step` expects to receive a batch of actions for each parallel environment.

    Gymnasium contains two types of Vector environments: :class:`AsyncVectorEnv` and :class:`SyncVectorEnv`.

    The Vector Environments have the additional attributes for users to understand the implementation

    - :attr:`num_envs` - The number of sub-environment in the vector environment
    - :attr:`observation_space` - The batched observation space of the vector environment
    - :attr:`action_space` - The batched action space of the vector environment

    Note:
        The info parameter of :meth:`reset` and :meth:`step` was originally implemented before OpenAI Gym v25 was a list
        of dictionary for each sub-environment. However, this was modified in OpenAI Gym v25+ and in Gymnasium to a
        dictionary with a NumPy array for each key. To use the old info style using the :class:`VectorListInfo`.

    Note:
        To render the sub-environments, use :meth:`call` with "render" arguments. Remember to set the `render_modes`
        for all the sub-environments during initialization.

    Note:
        All parallel environments should share the identical observation and action spaces.
        In other words, a vector of multiple different environments is not supported.
    """

    metadata: dict[str, Any] = {}
    spec: EnvSpec | None = None
    render_mode: str | None = None
    closed: bool = False

    observation_space: gym.Space[VectorObsType]
    action_space: gym.Space[VectorActType]
    num_envs: int

    _np_random: np.random.Generator | None = None

    def reset(
        self,
        *,
        seed: int | list[int] | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[VectorObsType, dict[str, Any]]:  # type: ignore
        """Reset all parallel environments and return a batch of initial observations and info.

        Args:
            seed: The environment reset seeds
            options: If to return the options

        Returns:
            A batch of observations and info from the vectorized environment.
        """
        if seed is not None:
            self._np_random, seed = seeding.np_random(seed)

    def step(
        self, actions: VectorActType
    ) -> tuple[
        VectorObsType, VectorArrayType, VectorArrayType, VectorArrayType, dict[str, Any]
    ]:
        """Take an action for each parallel environment.

        Args:
            actions: element of :attr:`action_space` Batch of actions.

        Returns:
            Batch of (observations, rewards, terminations, truncations, infos)

        Note:
            As the vector environments autoreset for a terminating and truncating sub-environments,
            the returned observation and info is not the final step's observation or info which is instead stored in
            info as `"final_observation"` and `"final_info"`.
        """
        pass

    def close(self, **kwargs: Any):
        """Close all parallel environments and release resources.

        It also closes all the existing image viewers, then calls :meth:`close_extras` and set
        :attr:`closed` as ``True``.

        Warnings:
            This function itself does not close the environments, it should be handled
            in :meth:`close_extras`. This is generic for both synchronous and asynchronous
            vectorized environments.

        Note:
            This will be automatically called when garbage collected or program exited.

        Args:
            **kwargs: Keyword arguments passed to :meth:`close_extras`
        """
        self.closed = True

    @property
    def np_random(self) -> np.random.Generator:
        """Returns the environment's internal :attr:`_np_random` that if not set will initialise with a random seed.

        Returns:
            Instances of `np.random.Generator`
        """
        if self._np_random is None:
            self._np_random, seed = seeding.np_random()
        return self._np_random

    @np_random.setter
    def np_random(self, value: np.random.Generator):
        self._np_random = value

    @property
    def unwrapped(self) -> VectorEnv[VectorObsType, VectorActType, VectorArrayType]:
        """Return the base environment."""
        return self

    def _add_info(self, infos: dict, info: dict, env_num: int) -> dict:
        """Add env info to the info dictionary of the vectorized environment.

        Given the `info` of a single environment add it to the `infos` dictionary
        which represents all the infos of the vectorized environment.
        Every `key` of `info` is paired with a boolean mask `_key` representing
        whether or not the i-indexed environment has this `info`.

        Args:
            infos (dict): the infos of the vectorized environment
            info (dict): the info coming from the single environment
            env_num (int): the index of the single environment

        Returns:
            infos (dict): the (updated) infos of the vectorized environment

        """
        for k in info.keys():
            if k not in infos:
                info_array, array_mask = self._init_info_arrays(type(info[k]))
            else:
                info_array, array_mask = infos[k], infos[f"_{k}"]

            info_array[env_num], array_mask[env_num] = info[k], True
            infos[k], infos[f"_{k}"] = info_array, array_mask
        return infos

    def _init_info_arrays(self, dtype: type) -> tuple[np.ndarray, np.ndarray]:
        """Initialize the info array.

        Initialize the info array. If the dtype is numeric
        the info array will have the same dtype, otherwise
        will be an array of `None`. Also, a boolean array
        of the same length is returned. It will be used for
        assessing which environment has info data.

        Args:
            dtype (type): data type of the info coming from the env.

        Returns:
            array (np.ndarray): the initialized info array.
            array_mask (np.ndarray): the initialized boolean array.

        """
        if dtype in [int, float, bool] or issubclass(dtype, np.number):
            array = np.zeros(self.num_envs, dtype=dtype)
        else:
            array = np.zeros(self.num_envs, dtype=object)
            array[:] = None
        array_mask = np.zeros(self.num_envs, dtype=bool)
        return array, array_mask

    def __del__(self):
        """Closes the vector environment."""
        if not getattr(self, "closed", True):
            self.close()

    def __repr__(self) -> str:
        """Returns a string representation of the vector environment.

        Returns:
            A string containing the class name, number of environments and environment spec id
        """
        if self.spec is None:
            return f"{self.__class__.__name__}({self.num_envs})"
        else:
            return f"{self.__class__.__name__}({self.spec.id}, {self.num_envs})"


VectorWrapperObsType = TypeVar("VectorWrapperObsType")
VectorWrapperActType = TypeVar("VectorWrapperActType")
VectorWrapperArrayType = TypeVar("VectorWrapperArrayType")


class VectorWrapper(
    VectorEnv[VectorWrapperObsType, VectorWrapperActType, VectorWrapperArrayType]
):
    """Wraps the vectorized environment to allow a modular transformation.

    This class is the base class for all wrappers for vectorized environments. The subclass
    could override some methods to change the behavior of the original vectorized environment
    without touching the original code.

    Note:
        Don't forget to call ``super().__init__(env)`` if the subclass overrides :meth:`__init__`.
    """

    def __init__(self, env: VectorEnv[VectorObsType, VectorActType, VectorArrayType]):
        super().__init__()

        assert isinstance(env, VectorEnv)
        self.env = env

    def reset(
        self,
        *,
        seed: int | list[int] | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[VectorWrapperObsType, dict[str, Any]]:
        return self.env.reset(seed=seed, options=options)

    def step(
        self, actions: VectorWrapperActType
    ) -> tuple[
        VectorWrapperObsType,
        VectorWrapperArrayType,
        VectorWrapperArrayType,
        VectorWrapperArrayType,
        dict[str, Any],
    ]:
        return self.env.step(actions)

    def close(self, **kwargs: Any):
        return self.env.close(**kwargs)

    # implicitly forward all other methods and attributes to self.env
    def __getattr__(self, name: str) -> Any:
        if name.startswith("_"):
            raise AttributeError(f"attempted to get missing private attribute '{name}'")
        return getattr(self.env, name)

    @property
    def unwrapped(self) -> VectorEnv[VectorObsType, VectorActType, VectorArrayType]:
        return self.env.unwrapped

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__}, {self.env}>"

    def __del__(self):
        self.env.__del__()


class VectorObservationWrapper(
    VectorWrapper[VectorWrapperObsType, VectorActType, VectorArrayType]
):
    """Wraps the vectorized environment to allow a modular transformation of the observation. Equivalent to :class:`gym.ObservationWrapper` for vectorized environments."""

    def reset(
        self,
        *,
        seed: int | list[int] | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[VectorWrapperObsType, dict[str, Any]]:
        observation = self.env.reset(seed=seed, options=options)
        return self.observation(observation)

    def step(
        self, actions: VectorActType
    ) -> tuple[
        VectorWrapperObsType,
        VectorArrayType,
        VectorArrayType,
        VectorArrayType,
        dict[str, Any],
    ]:
        observation, reward, termination, truncation, info = self.env.step(actions)
        return (
            self.observation(observation),
            reward,
            termination,
            truncation,
            info,
        )

    def observation(self, observation: VectorActType) -> VectorWrapperObsType:
        """Defines the observation transformation.

        Args:
            observation (object): the observation from the environment

        Returns:
            observation (object): the transformed observation
        """
        raise NotImplementedError


class VectorActionWrapper(
    VectorWrapper[VectorObsType, VectorWrapperActType, VectorArrayType]
):
    """Wraps the vectorized environment to allow a modular transformation of the actions. Equivalent of :class:`~gym.ActionWrapper` for vectorized environments."""

    def step(
        self, actions: VectorWrapperActType
    ) -> tuple[
        VectorObsType, VectorArrayType, VectorArrayType, VectorArrayType, dict[str, Any]
    ]:
        return self.env.step(self.action(actions))

    def actions(self, actions: VectorWrapperActType) -> VectorActType:
        """Transform the actions before sending them to the environment.

        Args:
            actions (ActType): the actions to transform

        Returns:
            ActType: the transformed actions
        """
        raise NotImplementedError


class VectorRewardWrapper(VectorWrapper[VectorObsType, VectorActType, VectorArrayType]):
    """Wraps the vectorized environment to allow a modular transformation of the reward. Equivalent of :class:`~gym.RewardWrapper` for vectorized environments."""

    def step(
        self, actions: VectorActType
    ) -> tuple[
        VectorObsType, VectorArrayType, VectorArrayType, VectorArrayType, dict[str, Any]
    ]:
        observation, reward, termination, truncation, info = self.env.step(actions)
        return observation, self.reward(reward), termination, truncation, info

    def reward(self, reward: VectorArrayType) -> VectorArrayType:
        """Transform the reward before returning it.

        Args:
            reward (array): the reward to transform

        Returns:
            array: the transformed reward
        """
        raise NotImplementedError
