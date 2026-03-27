"""Hierarchical supervision for actors.

Implements OTP-style supervision strategies:
- OneForOne: restart only the failed child
- OneForAll: restart all children when one fails
- RestForOne: restart the failed child and all children started after it
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from asyncio_actors.actor import Actor, ActorRef

logger = logging.getLogger(__name__)


class SupervisorStrategy(Enum):
    ONE_FOR_ONE = "one_for_one"
    ONE_FOR_ALL = "one_for_all"
    REST_FOR_ONE = "rest_for_one"


class RestartType(Enum):
    PERMANENT = "permanent"    # Always restart
    TRANSIENT = "transient"    # Restart only if abnormal exit
    TEMPORARY = "temporary"    # Never restart


@dataclass(frozen=True)
class ChildSpec:
    """Specification for a child actor managed by a Supervisor."""
    actor_cls: type
    restart: RestartType = RestartType.PERMANENT
    args: tuple = ()
    kwargs: dict = field(default_factory=dict)


class Supervisor(Actor):
    """Actor that manages child actors with configurable restart strategies.

    Usage::

        class MyApp(Supervisor):
            strategy = SupervisorStrategy.ONE_FOR_ONE
            children_specs = [
                ChildSpec(WorkerA),
                ChildSpec(WorkerB, restart=RestartType.TRANSIENT),
            ]
    """

    strategy: SupervisorStrategy = SupervisorStrategy.ONE_FOR_ONE
    children_specs: list[ChildSpec] = []

    def __init__(self) -> None:
        super().__init__()
        self._children: list[tuple[ChildSpec, Actor, asyncio.Task]] = []

    async def on_start(self) -> None:
        """Start all children defined in children_specs."""
        for spec in self.children_specs:
            await self._start_child(spec)

    async def _start_child(self, spec: ChildSpec) -> Actor:
        """Create and start a single child actor."""
        actor = spec.actor_cls(*spec.args, **spec.kwargs)
        task = asyncio.create_task(
            self._watch_child(spec, actor),
            name=f"child-{spec.actor_cls.__name__}",
        )
        self._children.append((spec, actor, task))
        # Give child on_start a chance to run
        await asyncio.sleep(0)
        return actor

    async def _watch_child(self, spec: ChildSpec, actor: Actor) -> None:
        """Run a child actor and handle its exit."""
        try:
            await actor._run()
            # Clean exit
            if spec.restart == RestartType.PERMANENT:
                logger.info("Restarting permanent child %s after clean exit",
                            spec.actor_cls.__name__)
                await self._handle_child_exit(spec, actor, normal=True)
        except Exception as e:
            logger.error("Child %s crashed: %s", spec.actor_cls.__name__, e)
            if spec.restart == RestartType.TEMPORARY:
                logger.info("Not restarting temporary child %s",
                            spec.actor_cls.__name__)
                return
            await self._handle_child_exit(spec, actor, normal=False)

    async def _handle_child_exit(self, spec: ChildSpec, actor: Actor, normal: bool) -> None:
        """Apply the supervisor strategy when a child exits."""
        if spec.restart == RestartType.TEMPORARY:
            return
        if spec.restart == RestartType.TRANSIENT and normal:
            return

        if self.strategy == SupervisorStrategy.ONE_FOR_ONE:
            await self._restart_child(spec, actor)
        elif self.strategy == SupervisorStrategy.ONE_FOR_ALL:
            await self._restart_all()
        elif self.strategy == SupervisorStrategy.REST_FOR_ONE:
            await self._restart_rest(spec)

    async def _restart_child(self, spec: ChildSpec, old_actor: Actor) -> None:
        """Restart a single child."""
        # Remove old entry
        self._children = [
            (s, a, t) for s, a, t in self._children if a is not old_actor
        ]
        await self._start_child(spec)

    async def _restart_all(self) -> None:
        """Stop all children and restart them."""
        specs = [s for s, _, _ in self._children]
        # Stop all
        for _, actor, task in self._children:
            await actor.stop()
            task.cancel()
        self._children.clear()
        # Restart all
        for spec in specs:
            await self._start_child(spec)

    async def _restart_rest(self, failed_spec: ChildSpec) -> None:
        """Restart the failed child and all children started after it."""
        idx = None
        for i, (spec, _, _) in enumerate(self._children):
            if spec is failed_spec:
                idx = i
                break
        if idx is None:
            return

        # Stop and collect specs from idx onwards
        rest = self._children[idx:]
        self._children = self._children[:idx]
        for _, actor, task in rest:
            await actor.stop()
            task.cancel()
        # Restart
        for spec, _, _ in rest:
            await self._start_child(spec)

    async def on_message(self, message: Any) -> Any:
        """Forward messages to children or handle supervisor commands."""
        return None

    async def on_stop(self) -> None:
        """Stop all children."""
        for _, actor, task in self._children:
            await actor.stop()
            task.cancel()
        self._children.clear()

    def child_refs(self) -> list[ActorRef]:
        """Return ActorRefs for all managed children."""
        return [actor.ref() for _, actor, _ in self._children]
