"""
Implementation of a Jax-accelerated pendulum environment.
"""
from os import path
from typing import Optional, Tuple, Union

import jax
import jax.numpy as jnp
import numpy as np
from jax.random import PRNGKey

import gymnasium as gym
from gymnasium.error import DependencyNotInstalled
from gymnasium.experimental.func2env import FunctionalJaxCompatibilityEnv
from gymnasium.experimental.functional import ActType, FuncEnv, StateType
from gymnasium.utils import EzPickle

RenderStateType = Tuple["pygame.Surface", "pygame.time.Clock", Optional[float]]  # type: ignore  # noqa: F821


class PendulumFunctional(
    FuncEnv[jnp.ndarray, jnp.ndarray, int, float, bool, RenderStateType]
):
    """Pendulum but in jax and functional."""

    max_speed = 8
    max_torque = 2.0
    dt = 0.05
    g = 10.0
    m = 1.0
    l = 1.0
    high_x = jnp.pi
    high_y = 1.0

    screen_dim = 500

    observation_space = gym.spaces.Box(-np.inf, np.inf, shape=(3,), dtype=np.float32)
    action_space = gym.spaces.Box(-max_torque, max_torque, shape=(1,), dtype=np.float32)

    def initial(self, rng: PRNGKey):
        """Initial state generation."""
        high = jnp.array([self.high_x, self.high_y])
        return jax.random.uniform(key=rng, minval=-high, maxval=high, shape=high.shape)

    def transition(
        self, state: jnp.ndarray, action: Union[int, jnp.ndarray], rng: None = None
    ) -> jnp.ndarray:
        """Pendulum transition."""
        th, thdot = state  # th := theta
        u = action

        g = self.g
        m = self.m
        l = self.l
        dt = self.dt

        u = jnp.clip(u, -self.max_torque, self.max_torque)[0]

        newthdot = thdot + (3 * g / (2 * l) * jnp.sin(th) + 3.0 / (m * l**2) * u) * dt
        newthdot = jnp.clip(newthdot, -self.max_speed, self.max_speed)
        newth = th + newthdot * dt

        new_state = jnp.array([newth, newthdot])
        return new_state

    def observation(self, state: jnp.ndarray) -> jnp.ndarray:
        theta, thetadot = state
        return jnp.array([jnp.cos(theta), jnp.sin(theta), thetadot])

    def reward(self, state: StateType, action: ActType, next_state: StateType) -> float:
        th, thdot = state  # th := theta
        u = action

        u = jnp.clip(u, -self.max_torque, self.max_torque)[0]

        th_normalized = ((th + jnp.pi) % (2 * jnp.pi)) - jnp.pi
        costs = th_normalized**2 + 0.1 * thdot**2 + 0.001 * (u**2)

        return -costs

    def terminal(self, state: StateType) -> bool:
        return False

    def render_image(
        self,
        state: StateType,
        render_state: Tuple["pygame.Surface", "pygame.time.Clock", Optional[float]],  # type: ignore  # noqa: F821
    ) -> Tuple[RenderStateType, np.ndarray]:
        try:
            import pygame
            from pygame import gfxdraw
        except ImportError:
            raise DependencyNotInstalled(
                "pygame is not installed, run `pip install gymnasium[classic_control]`"
            )
        screen, clock, last_u = render_state

        surf = pygame.Surface((self.screen_dim, self.screen_dim))
        surf.fill((255, 255, 255))

        bound = 2.2
        scale = self.screen_dim / (bound * 2)
        offset = self.screen_dim // 2

        rod_length = 1 * scale
        rod_width = 0.2 * scale
        l, r, t, b = 0, rod_length, rod_width / 2, -rod_width / 2
        coords = [(l, b), (l, t), (r, t), (r, b)]
        transformed_coords = []
        for c in coords:
            c = pygame.math.Vector2(c).rotate_rad(state[0] + np.pi / 2)
            c = (c[0] + offset, c[1] + offset)
            transformed_coords.append(c)
        gfxdraw.aapolygon(surf, transformed_coords, (204, 77, 77))
        gfxdraw.filled_polygon(surf, transformed_coords, (204, 77, 77))

        gfxdraw.aacircle(surf, offset, offset, int(rod_width / 2), (204, 77, 77))
        gfxdraw.filled_circle(surf, offset, offset, int(rod_width / 2), (204, 77, 77))

        rod_end = (rod_length, 0)
        rod_end = pygame.math.Vector2(rod_end).rotate_rad(state[0] + np.pi / 2)
        rod_end = (int(rod_end[0] + offset), int(rod_end[1] + offset))
        gfxdraw.aacircle(
            surf, rod_end[0], rod_end[1], int(rod_width / 2), (204, 77, 77)
        )
        gfxdraw.filled_circle(
            surf, rod_end[0], rod_end[1], int(rod_width / 2), (204, 77, 77)
        )

        fname = path.join(path.dirname(__file__), "assets/clockwise.png")
        img = pygame.image.load(fname)
        if last_u is not None:
            scale_img = pygame.transform.smoothscale(
                img,
                (scale * np.abs(last_u) / 2, scale * np.abs(last_u) / 2),
            )
            is_flip = bool(last_u > 0)
            scale_img = pygame.transform.flip(scale_img, is_flip, True)
            surf.blit(
                scale_img,
                (
                    offset - scale_img.get_rect().centerx,
                    offset - scale_img.get_rect().centery,
                ),
            )

        # drawing axle
        gfxdraw.aacircle(surf, offset, offset, int(0.05 * scale), (0, 0, 0))
        gfxdraw.filled_circle(surf, offset, offset, int(0.05 * scale), (0, 0, 0))

        surf = pygame.transform.flip(surf, False, True)
        screen.blit(surf, (0, 0))

        return (screen, clock, last_u), np.transpose(
            np.array(pygame.surfarray.pixels3d(screen)), axes=(1, 0, 2)
        )

    def render_init(
        self, screen_width: int = 600, screen_height: int = 400
    ) -> RenderStateType:
        try:
            import pygame
        except ImportError:
            raise DependencyNotInstalled(
                "pygame is not installed, run `pip install gymnasium[classic_control]`"
            )

        pygame.init()
        screen = pygame.Surface((screen_width, screen_height))
        clock = pygame.time.Clock()

        return screen, clock, None

    def render_close(self, render_state: RenderStateType) -> None:
        try:
            import pygame
        except ImportError:
            raise DependencyNotInstalled(
                "pygame is not installed, run `pip install gymnasium[classic_control]`"
            )
        pygame.display.quit()
        pygame.quit()


class PendulumEnv(FunctionalJaxCompatibilityEnv, EzPickle):

    metadata = {"render_modes": ["rgb_array"], "render_fps": 30}

    def __init__(self, render_mode: Optional[str] = None, **kwargs):
        EzPickle.__init__(self, render_mode=render_mode, **kwargs)
        env = PendulumFunctional(**kwargs)
        env.transform(jax.jit)
        action_space = env.action_space
        observation_space = env.observation_space
        metadata = {"render_modes": ["rgb_array"], "render_fps": 30}

        super().__init__(
            env,
            observation_space=observation_space,
            action_space=action_space,
            metadata=metadata,
            render_mode=render_mode,
        )
