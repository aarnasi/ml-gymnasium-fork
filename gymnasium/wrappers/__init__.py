"""Module of wrapper classes.

Wrappers are a convenient way to modify an existing environment without having to alter the underlying code directly.
Using wrappers will allow you to avoid a lot of boilerplate code and make your environment more modular. Wrappers can
also be chained to combine their effects.
Most environments that are generated via :meth:`gymnasium.make` will already be wrapped by default.

In order to wrap an environment, you must first initialize a base environment. Then you can pass this environment along
with (possibly optional) parameters to the wrapper's constructor.

    >>> import gymnasium as gym
    >>> from gymnasium.wrappers import RescaleAction
    >>> base_env = gym.make("BipedalWalker-v3")
    >>> base_env.action_space
    Box([-1. -1. -1. -1.], [1. 1. 1. 1.], (4,), float32)
    >>> wrapped_env = RescaleAction(base_env, min_action=0, max_action=1)
    >>> wrapped_env.action_space
    Box([0. 0. 0. 0.], [1. 1. 1. 1.], (4,), float32)

You can access the environment underneath the **first** wrapper by using the :attr:`gymnasium.Wrapper.env` attribute.
As the :class:`gymnasium.Wrapper` class inherits from :class:`gymnasium.Env` then :attr:`gymnasium.Wrapper.env` can be another wrapper.

    >>> wrapped_env
    <RescaleAction<TimeLimit<OrderEnforcing<BipedalWalker<BipedalWalker-v3>>>>>
    >>> wrapped_env.env
    <TimeLimit<OrderEnforcing<BipedalWalker<BipedalWalker-v3>>>>

If you want to get to the environment underneath **all** of the layers of wrappers, you can use the
:attr:`gymnasium.Wrapper.unwrapped` attribute.
If the environment is already a bare environment, the :attr:`gymnasium.Wrapper.unwrapped` attribute will just return itself.

    >>> wrapped_env
    <RescaleAction<TimeLimit<OrderEnforcing<BipedalWalker<BipedalWalker-v3>>>>>
    >>> wrapped_env.unwrapped
    <gymnasium.envs.box2d.bipedal_walker.BipedalWalker object at 0x7f87d70712d0>

There are three common things you might want a wrapper to do:

- Transform actions before applying them to the base environment
- Transform observations that are returned by the base environment
- Transform rewards that are returned by the base environment

Such wrappers can be easily implemented by inheriting from :class:`gymnasium.ActionWrapper`,
:class:`gymnasium.ObservationWrapper`, or :class:`gymnasium.RewardWrapper` and implementing the respective transformation.
If you need a wrapper to do more complicated tasks, you can inherit from the :class:`gymnasium.Wrapper` class directly.

If you'd like to implement your own custom wrapper, check out `the corresponding tutorial <../../tutorials/implementing_custom_wrappers>`_.
"""
from gymnasium.wrappers.atari_preprocessing import AtariPreprocessing as _AtariPreprocessing
from gymnasium.wrappers.autoreset import AutoResetWrapper as _AutoResetWrapper
from gymnasium.wrappers.clip_action import ClipAction as _ClipAction
from gymnasium.wrappers.compatibility import EnvCompatibility as _EnvCompatibility
from gymnasium.wrappers.env_checker import PassiveEnvChecker as _PassiveEnvChecker
from gymnasium.wrappers.filter_observation import FilterObservation as _FilterObservation
from gymnasium.wrappers.flatten_observation import FlattenObservation as _FlattenObservation
from gymnasium.wrappers.frame_stack import FrameStack as _FrameStack
from gymnasium.wrappers.frame_stack import LazyFrames as _LazyFrames
from gymnasium.wrappers.gray_scale_observation import GrayScaleObservation as _GrayScaleObservation
from gymnasium.wrappers.human_rendering import HumanRendering as _HumanRendering
from gymnasium.wrappers.normalize import NormalizeObservation as _NormalizeObservation
from gymnasium.wrappers.normalize import NormalizeReward as _NormalizeReward
from gymnasium.wrappers.order_enforcing import OrderEnforcing as _OrderEnforcing
from gymnasium.wrappers.pixel_observation import PixelObservationWrapper as _PixelObservationWrapper
from gymnasium.wrappers.record_episode_statistics import RecordEpisodeStatistics as _RecordEpisodeStatistics
from gymnasium.wrappers.record_video import RecordVideo as _RecordVideo
from gymnasium.wrappers.record_video import capped_cubic_video_schedule as _capped_cubic_video_schedule
from gymnasium.wrappers.render_collection import RenderCollection as _RenderCollection
from gymnasium.wrappers.rescale_action import RescaleAction as _RescaleAction
from gymnasium.wrappers.resize_observation import ResizeObservation as _ResizeObservation
from gymnasium.wrappers.step_api_compatibility import StepAPICompatibility as _StepAPICompatibility
from gymnasium.wrappers.time_aware_observation import TimeAwareObservation as _TimeAwareObservation
from gymnasium.wrappers.time_limit import TimeLimit as _TimeLimit
from gymnasium.wrappers.transform_observation import TransformObservation as _TransformObservation
from gymnasium.wrappers.transform_reward import TransformReward as _TransformReward
from gymnasium.wrappers.vector_list_info import VectorListInfo as _VectorListInfo
from gymnasium import logger


def __getattr__(name):
    logger.warn("Wrappers have been replaced in favor of lambda wrappers and they will be deleted soon. "
                "Use the ones in gymnasium.experimental.wrappers, for further details see: ")  # TODO
    return globals()[f"_{name}"]
