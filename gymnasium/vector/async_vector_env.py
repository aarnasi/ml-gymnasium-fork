"""An async vector environment."""
from __future__ import annotations

import multiprocessing
import sys
import time
from copy import deepcopy
from enum import Enum
from multiprocessing import Queue
from multiprocessing.connection import Connection
from typing import Any, Callable, Sequence

import numpy as np

from gymnasium import logger
from gymnasium.core import Env, ObsType
from gymnasium.error import (
    AlreadyPendingCallError,
    ClosedEnvironmentError,
    CustomSpaceError,
    NoAsyncCallError,
)
from gymnasium.vector.utils import (
    CloudpickleWrapper,
    batch_space,
    clear_mpi_env_vars,
    concatenate,
    create_empty_array,
    create_shared_memory,
    iterate,
    read_from_shared_memory,
    write_to_shared_memory,
)
from gymnasium.vector.vector_env import VectorEnv


__all__ = ["AsyncVectorEnv", "AsyncState"]


class AsyncState(Enum):
    """The AsyncVectorEnv possible states given the different actions."""
    DEFAULT = "default"
    WAITING_RESET = "reset"
    WAITING_STEP = "step"
    WAITING_CALL = "call"


class AsyncVectorEnv(VectorEnv):
    """Vectorized environment that runs multiple environments in parallel.

    It uses ``multiprocessing`` processes, and pipes for communication.

    Example:
        >>> import gymnasium as gym
        >>> envs = gym.vector.AsyncVectorEnv([
        ...     lambda: gym.make("Pendulum-v1", g=9.81),
        ...     lambda: gym.make("Pendulum-v1", g=1.62)
        ... ])
        >>> observations, infos = envs.reset(seed=42)
        >>> observations
        array([[-0.14995256,  0.9886932 , -0.12224312],
               [ 0.5760367 ,  0.8174238 , -0.91244936]], dtype=float32)
        >>> infos
        {}
        >>> _ = envs.action_space.seed(123)
        >>> observations, rewards, terminations, truncations, infos = envs.step(envs.action_space.sample())
        >>> observations
        array([[-0.1851753 ,  0.98270553,  0.714599  ],
               [ 0.6193494 ,  0.7851154 , -1.0808398 ]], dtype=float32)
        >>> rewards
        array([-2.96495728, -1.00214607])
        >>> terminations
        array([False, False])
        >>> truncations
        array([False, False])
        >>> infos
        {}
    """

    def __init__(
        self,
        env_fns: Sequence[Callable[[], Env]],
        shared_memory: bool = True,
        copy: bool = True,
        context: str | None = None,
        daemon: bool = True,
        worker: callable | None = None,
    ):
        """Vectorized environment that runs multiple environments in parallel.

        Args:
            env_fns: Functions that create the environments.
            shared_memory: If ``True``, then the observations from the worker processes are communicated back through
                shared variables. This can improve the efficiency if the observations are large (e.g. images).
            copy: If ``True``, then the :meth:`~AsyncVectorEnv.reset` and :meth:`~AsyncVectorEnv.step` methods
                return a copy of the observations.
            context: Context for `multiprocessing`. If ``None``, then the default context is used.
            daemon: If ``True``, then subprocesses have ``daemon`` flag turned on; that is, they will quit if
                the head process quits. However, ``daemon=True`` prevents subprocesses to spawn children,
                so for some environments you may want to have it set to ``False``.
            worker: If set, then use that worker in a subprocess instead of a default one.
                Can be useful to override some inner vector env logic, for instance, how resets on termination or truncation are handled.

        Warnings:
            worker is an advanced mode option. It provides a high degree of flexibility and a high chance
            to shoot yourself in the foot; thus, if you are writing your own worker, it is recommended to start
            from the code for ``_worker`` (or ``_worker_shared_memory``) method, and add changes.

        Raises:
            RuntimeError: If the observation space of some sub-environment does not match observation_space
                (or, by default, the observation space of the first sub-environment).
            ValueError: If observation_space is a custom space (i.e. not a default space in Gym,
                such as gymnasium.spaces.Box, gymnasium.spaces.Discrete, or gymnasium.spaces.Dict) and shared_memory is True.
        """
        self.env_fns = env_fns
        self.shared_memory = shared_memory
        self.copy = copy

        self.num_envs = len(env_fns)

        # This would be nice to get rid of, but without it there's a deadlock between shared memory and pipes
        # Create a dummy environment to gather the metadata and observation / action space of the environment
        dummy_env = env_fns[0]()
        self.metadata = dummy_env.metadata

        self.single_observation_space = dummy_env.observation_space
        self.single_action_space = dummy_env.action_space

        self.observation_space = batch_space(
            self.single_observation_space, self.num_envs
        )
        self.action_space = batch_space(self.single_action_space, self.num_envs)

        dummy_env.close()
        del dummy_env

        # Generate the multiprocessing context for the observation buffer
        ctx = multiprocessing.get_context(context)
        if self.shared_memory:
            try:
                _obs_buffer = create_shared_memory(
                    self.single_observation_space, n=self.num_envs, ctx=ctx
                )
                self.observations = read_from_shared_memory(
                    self.single_observation_space, _obs_buffer, n=self.num_envs
                )
            except CustomSpaceError as e:
                raise ValueError(
                    "Using `shared_memory=True` in `AsyncVectorEnv` is incompatible with non-standard Gymnasium observation spaces (i.e. custom spaces inheriting from `gymnasium.Space`), "
                    "and is only compatible with default Gymnasium spaces (e.g. `Box`, `Tuple`, `Dict`) for batching. "
                    "Set `shared_memory=False` if you use custom observation spaces."
                ) from e
        else:
            _obs_buffer = None
            self.observations = create_empty_array(
                self.single_observation_space, n=self.num_envs, fn=np.zeros
            )

        self.parent_pipes, self.processes = [], []
        self.error_queue = ctx.Queue()
        target = worker or _worker
        with clear_mpi_env_vars():
            for idx, env_fn in enumerate(self.env_fns):
                parent_pipe, child_pipe = ctx.Pipe()
                process = ctx.Process(
                    target=target,
                    name=f"Worker<{type(self).__name__}>-{idx}",
                    args=(
                        idx,
                        CloudpickleWrapper(env_fn),
                        child_pipe,
                        parent_pipe,
                        _obs_buffer,
                        self.error_queue,
                    ),
                )

                self.parent_pipes.append(parent_pipe)
                self.processes.append(process)

                process.daemon = daemon
                process.start()
                child_pipe.close()

        self._state = AsyncState.DEFAULT
        self._check_spaces()

    def reset(
        self,
        *,
        seed: int | list[int] | None = None,
        options: dict | None = None,
    ):
        """Resets all sub-environments in parallel and return a batch of concatenated observations and info.

        Args:
            seed: The environment reset seeds
            options: If to return the options

        Returns:
            A batch of observations and info from the vectorized environment.
        """
        self.reset_async(seed=seed, options=options)
        return self.reset_wait()

    def reset_async(
        self,
        seed: int | list[int] | None = None,
        options: dict | None = None,
    ):
        """Send calls to the :obj:`reset` methods of the sub-environments.

        To get the results of these calls, you may invoke :meth:`reset_wait`.

        Args:
            seed: List of seeds for each environment
            options: The reset option

        Raises:
            ClosedEnvironmentError: If the environment was closed (if :meth:`close` was previously called).
            AlreadyPendingCallError: If the environment is already waiting for a pending call to another
                method (e.g. :meth:`step_async`). This can be caused by two consecutive
                calls to :meth:`reset_async`, with no call to :meth:`reset_wait` in between.
        """
        self._assert_is_running()

        if seed is None:
            seed = [None for _ in range(self.num_envs)]
        elif isinstance(seed, int):
            seed = [seed + i for i in range(self.num_envs)]
        assert len(seed) == self.num_envs

        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError(
                f"Calling `reset_async` while waiting for a pending call to `{self._state.value}` to complete",
                str(self._state.value),
            )

        for pipe, env_seed in zip(self.parent_pipes, seed):
            env_kwargs = {"seed": env_seed, "options": options}
            pipe.send(("reset", env_kwargs))
        self._state = AsyncState.WAITING_RESET

    def reset_wait(
        self,
        timeout: int | float | None = None,
    ) -> tuple[ObsType, dict[str, Any]]:
        """Waits for the calls triggered by :meth:`reset_async` to finish and returns the results.

        Args:
            timeout: Number of seconds before the call to `reset_wait` times out. If `None`, the call to `reset_wait` never times out.

        Returns:
            A tuple of batched observations and list of dictionaries

        Raises:
            ClosedEnvironmentError: If the environment was closed (if :meth:`close` was previously called).
            NoAsyncCallError: If :meth:`reset_wait` was called without any prior call to :meth:`reset_async`.
            TimeoutError: If :meth:`reset_wait` timed out.
        """
        self._assert_is_running()
        if self._state != AsyncState.WAITING_RESET:
            raise NoAsyncCallError(
                "Calling `reset_wait` without any prior " "call to `reset_async`.",
                AsyncState.WAITING_RESET.value,
            )

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise multiprocessing.TimeoutError(
                f"The call to `reset_wait` has timed out after {timeout} second(s)."
            )

        results, successes = zip(*[pipe.recv() for pipe in self.parent_pipes])
        self._raise_if_errors(successes)

        infos = {}
        results, info_data = zip(*results)
        for i, info in enumerate(info_data):
            infos = self._add_info(infos, info, i)

        if not self.shared_memory:
            self.observations = concatenate(
                self.single_observation_space, results, self.observations
            )

        self._state = AsyncState.DEFAULT
        return (deepcopy(self.observations) if self.copy else self.observations), infos

    def step(self, actions):
        """Take an action for each parallel environment.

        Args:
            actions: element of :attr:`action_space` batch of actions.

        Returns:
            Batch of (observations, rewards, terminations, truncations, infos)
        """
        self.step_async(actions)
        return self.step_wait()

    def step_async(self, actions: np.ndarray):
        """Send the calls to :obj:`step` to each sub-environment.

        Args:
            actions: Batch of actions. element of :attr:`~VectorEnv.action_space`

        Raises:
            ClosedEnvironmentError: If the environment was closed (if :meth:`close` was previously called).
            AlreadyPendingCallError: If the environment is already waiting for a pending call to another
                method (e.g. :meth:`reset_async`). This can be caused by two consecutive
                calls to :meth:`step_async`, with no call to :meth:`step_wait` in
                between.
        """
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError(
                f"Calling `step_async` while waiting for a pending call to `{self._state.value}` to complete.",
                str(self._state.value),
            )

        iter_actions = iterate(self.action_space, actions)
        for pipe, action in zip(self.parent_pipes, iter_actions):
            pipe.send(("step", action))
        self._state = AsyncState.WAITING_STEP

    def step_wait(
        self, timeout: int | float | None = None
    ) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, dict]:
        """Wait for the calls to :obj:`step` in each sub-environment to finish.

        Args:
            timeout: Number of seconds before the call to :meth:`step_wait` times out. If ``None``, the call to :meth:`step_wait` never times out.

        Returns:
             The batched environment step information, (obs, reward, terminated, truncated, info)

        Raises:
            ClosedEnvironmentError: If the environment was closed (if :meth:`close` was previously called).
            NoAsyncCallError: If :meth:`step_wait` was called without any prior call to :meth:`step_async`.
            TimeoutError: If :meth:`step_wait` timed out.
        """
        self._assert_is_running()
        if self._state != AsyncState.WAITING_STEP:
            raise NoAsyncCallError(
                "Calling `step_wait` without any prior call " "to `step_async`.",
                AsyncState.WAITING_STEP.value,
            )

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise multiprocessing.TimeoutError(
                f"The call to `step_wait` has timed out after {timeout} second(s)."
            )

        observations, rewards, terminations, truncations, infos = [], [], [], [], {}
        successes = []
        for env_idx, pipe in enumerate(self.parent_pipes):
            env_step_return, success = pipe.recv()

            successes.append(success)
            if success:
                env_obs, env_reward, env_terminated, env_truncated, env_info = env_step_return

                observations.append(env_obs)
                rewards.append(env_reward)
                terminations.append(env_terminated)
                truncations.append(env_truncated)
                infos = self._add_info(infos, env_info, env_idx)

        self._raise_if_errors(successes)

        if not self.shared_memory:
            self.observations = concatenate(
                self.single_observation_space,
                observations,
                self.observations,
            )

        self._state = AsyncState.DEFAULT
        return (
            deepcopy(self.observations) if self.copy else self.observations,
            np.array(rewards, dtype=np.float64),
            np.array(terminations, dtype=np.bool_),
            np.array(truncations, dtype=np.bool_),
            infos,
        )

    def call(self, name: str, *args, **kwargs) -> list[Any]:
        """Call a method, or get a property, from each parallel environment.

        Args:
            name (str): Name of the method or property to call.
            *args: Arguments to apply to the method call.
            **kwargs: Keyword arguments to apply to the method call.

        Returns:
            List of the results of the individual calls to the method or property for each environment.
        """
        self.call_async(name, *args, **kwargs)
        return self.call_wait()

    def call_async(self, name: str, *args, **kwargs):
        """Calls the method with name asynchronously and apply args and kwargs to the method.

        Args:
            name: Name of the method or property to call.
            *args: Arguments to apply to the method call.
            **kwargs: Keyword arguments to apply to the method call.

        Raises:
            ClosedEnvironmentError: If the environment was closed (if :meth:`close` was previously called).
            AlreadyPendingCallError: Calling `call_async` while waiting for a pending call to complete
        """
        self._assert_is_running()
        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError(
                f"Calling `call_async` while waiting for a pending call to `{self._state.value}` to complete.",
                str(self._state.value),
            )

        for pipe in self.parent_pipes:
            pipe.send(("_call", (name, args, kwargs)))
        self._state = AsyncState.WAITING_CALL

    def call_wait(self, timeout: int | float | None = None) -> list:
        """Calls all parent pipes and waits for the results.

        Args:
            timeout: Number of seconds before the call to `step_wait` times out.
                If `None` (default), the call to `step_wait` never times out.

        Returns:
            List of the results of the individual calls to the method or property for each environment.

        Raises:
            NoAsyncCallError: Calling `call_wait` without any prior call to `call_async`.
            TimeoutError: The call to `call_wait` has timed out after timeout second(s).
        """
        self._assert_is_running()
        if self._state != AsyncState.WAITING_CALL:
            raise NoAsyncCallError(
                "Calling `call_wait` without any prior call to `call_async`.",
                AsyncState.WAITING_CALL.value,
            )

        if not self._poll(timeout):
            self._state = AsyncState.DEFAULT
            raise multiprocessing.TimeoutError(
                f"The call to `call_wait` has timed out after {timeout} second(s)."
            )

        results, successes = zip(*[pipe.recv() for pipe in self.parent_pipes])
        self._raise_if_errors(successes)
        self._state = AsyncState.DEFAULT

        return results

    def get_attr(self, name: str):
        """Get a property from each parallel environment.

        Args:
            name (str): Name of the property to be get from each individual environment.

        Returns:
            The property with name
        """
        return self.call(name)

    def set_attr(self, name: str, values: list[Any] | tuple[Any] | object):
        """Sets an attribute of the sub-environments.

        Args:
            name: Name of the property to be set in each individual environment.
            values: Values of the property to be set to. If ``values`` is a list or
                tuple, then it corresponds to the values for each individual
                environment, otherwise a single value is set for all environments.

        Raises:
            ValueError: Values must be a list or tuple with length equal to the number of environments.
            AlreadyPendingCallError: Calling `set_attr` while waiting for a pending call to complete.
        """
        self._assert_is_running()
        if not isinstance(values, (list, tuple)):
            values = [values for _ in range(self.num_envs)]
        if len(values) != self.num_envs:
            raise ValueError(
                "Values must be a list or tuple with length equal to the number of environments. "
                f"Got `{len(values)}` values for {self.num_envs} environments."
            )

        if self._state != AsyncState.DEFAULT:
            raise AlreadyPendingCallError(
                f"Calling `set_attr` while waiting for a pending call to `{self._state.value}` to complete.",
                str(self._state.value),
            )

        for pipe, value in zip(self.parent_pipes, values):
            pipe.send(("_setattr", (name, value)))
        _, successes = zip(*[pipe.recv() for pipe in self.parent_pipes])
        self._raise_if_errors(successes)

    def close_extras(self, timeout: int | float | None = None, terminate: bool = False):
        """Close the environments & clean up the extra resources (processes and pipes).

        Args:
            timeout: Number of seconds before the call to :meth:`close` times out. If ``None``,
                the call to :meth:`close` never times out. If the call to :meth:`close`
                times out, then all processes are terminated.
            terminate: If ``True``, then the :meth:`close` operation is forced and all processes are terminated.

        Raises:
            TimeoutError: If :meth:`close` timed out.
        """
        timeout = 0 if terminate else timeout
        try:
            if self._state != AsyncState.DEFAULT:
                logger.warn(
                    f"Calling `close` while waiting for a pending call to `{self._state.value}` to complete."
                )
                function = getattr(self, f"{self._state.value}_wait")
                function(timeout)
        except multiprocessing.TimeoutError:
            terminate = True

        if terminate:
            for process in self.processes:
                if process.is_alive():
                    process.terminate()
        else:
            for pipe in self.parent_pipes:
                if (pipe is not None) and (not pipe.closed):
                    pipe.send(("close", None))
            for pipe in self.parent_pipes:
                if (pipe is not None) and (not pipe.closed):
                    pipe.recv()

        for pipe in self.parent_pipes:
            if pipe is not None:
                pipe.close()
        for process in self.processes:
            process.join()

    def _poll(self, timeout=None):
        self._assert_is_running()
        if timeout is None:
            return True
        end_time = time.perf_counter() + timeout
        delta = None
        for pipe in self.parent_pipes:
            delta = max(end_time - time.perf_counter(), 0)
            if pipe is None:
                return False
            if pipe.closed or (not pipe.poll(delta)):
                return False
        return True

    def _check_spaces(self):
        self._assert_is_running()
        spaces = (self.single_observation_space, self.single_action_space)
        for pipe in self.parent_pipes:
            pipe.send(("_check_spaces", spaces))
        results, successes = zip(*[pipe.recv() for pipe in self.parent_pipes])
        self._raise_if_errors(successes)
        same_observation_spaces, same_action_spaces = zip(*results)
        if not all(same_observation_spaces):
            raise RuntimeError(
                f"Some environments have an observation space different from `{self.single_observation_space}`. "
                "In order to batch observations, the observation spaces from all environments must be equal."
            )
        if not all(same_action_spaces):
            raise RuntimeError(
                f"Some environments have an action space different from `{self.single_action_space}`. "
                "In order to batch actions, the action spaces from all environments must be equal."
            )

    def _assert_is_running(self):
        if self.closed:
            raise ClosedEnvironmentError(
                f"Trying to operate on `{type(self).__name__}`, after a call to `close()`."
            )

    def _raise_if_errors(self, successes: list[bool]):
        if all(successes):
            return

        num_errors = self.num_envs - sum(successes)
        assert num_errors > 0
        for i in range(num_errors):
            index, exctype, value = self.error_queue.get()
            logger.error(
                f"Received the following error from Worker-{index}: {exctype.__name__}: {value}"
            )
            logger.error(f"Shutting down Worker-{index}.")
            self.parent_pipes[index].close()
            self.parent_pipes[index] = None

            if i == num_errors - 1:
                logger.error("Raising the last exception back to the main process.")
                raise exctype(value)

    def __del__(self):
        """On deleting the object, checks that the vector environment is closed."""
        if not getattr(self, "closed", True) and hasattr(self, "_state"):
            self.close(terminate=True)


def _worker(
    index: int,
    env_fn: callable,
    pipe: Connection,
    parent_pipe: Connection,
    shared_memory: bool,
    error_queue: Queue,
):
    env = env_fn()
    observation_space = env.observation_space
    action_space = env.action_space
    parent_pipe.close()
    try:
        while True:
            command, data = pipe.recv()

            if command == "reset":
                observation, info = env.reset(**data)
                if shared_memory:
                    write_to_shared_memory(
                        observation_space, index, observation, shared_memory
                    )
                    observation = None
                pipe.send(((observation, info), True))

            elif command == "step":
                (
                    observation,
                    reward,
                    terminated,
                    truncated,
                    info,
                ) = env.step(data)
                if terminated or truncated:
                    old_observation, old_info = observation, info
                    observation, info = env.reset()
                    info["final_observation"] = old_observation
                    info["final_info"] = old_info

                if shared_memory:
                    write_to_shared_memory(
                        observation_space, index, observation, shared_memory
                    )
                    observation = None

                pipe.send(((observation, reward, terminated, truncated, info), True))
            elif command == "seed":
                env.seed(data)
                pipe.send((None, True))
            elif command == "close":
                pipe.send((None, True))
                break
            elif command == "_call":
                name, args, kwargs = data
                if name in ["reset", "step", "seed", "close"]:
                    raise ValueError(
                        f"Trying to call function `{name}` with "
                        f"`_call`. Use `{name}` directly instead."
                    )
                function = env.get_wrapper_attr(name)
                if callable(function):
                    pipe.send((function(*args, **kwargs), True))
                else:
                    pipe.send((function, True))
            elif command == "_setattr":
                name, value = data
                setattr(env, name, value)
                pipe.send((None, True))
            elif command == "_check_spaces":
                pipe.send(
                    (
                        (data[0] == observation_space, data[1] == action_space),
                        True,
                    )
                )
            else:
                raise RuntimeError(
                    f"Received unknown command `{command}`. Must be one of [`reset`, `step`, `seed`, `close`, `_call`, `_setattr`, `_check_spaces`]."
                )
    except (KeyboardInterrupt, Exception):
        error_queue.put((index,) + sys.exc_info()[:2])
        pipe.send((None, False))
    finally:
        env.close()
