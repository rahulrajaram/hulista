"""Hierarchical supervision for actors.

Implements OTP-style supervision strategies:
- OneForOne: restart only the failed child
- OneForAll: restart all children when one fails
- RestForOne: restart the failed child and all children started after it
"""
from __future__ import annotations

import logging
import asyncio
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from asyncio_actors.actor import Actor, ActorRef

logger = logging.getLogger(__name__)

# Backoff constants (shared with system.py)
_BACKOFF_BASE = 0.1
_BACKOFF_MAX = 5.0
_BACKOFF_FACTOR = 2.0


async def _sleep(delay: float) -> None:
    """Wrapper for backoff sleeps so tests can patch timing deterministically."""
    await asyncio.sleep(delay)


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
    actor_cls: type[Actor]
    restart: RestartType = RestartType.PERMANENT
    args: tuple[Any, ...] = ()
    kwargs: dict[str, Any] = field(default_factory=dict)


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
        # Copy class-level children_specs to avoid shared mutable state
        self.children_specs = list(type(self).children_specs)
        self._children: list[tuple[ChildSpec, Actor, asyncio.Task]] = []
        self._consecutive_failures: dict[int, int] = {
            id(spec): 0 for spec in self.children_specs
        }

    async def on_start(self) -> None:
        """Start all children defined in children_specs."""
        for spec in self.children_specs:
            await self._start_child(spec)

    async def _start_child(
        self,
        spec: ChildSpec,
        *,
        previous_actor: Actor | None = None,
        preserve_inbox: bool = False,
    ) -> Actor:
        """Create and start a single child actor."""
        actor = spec.actor_cls(*spec.args, **spec.kwargs)
        if previous_actor is not None:
            if preserve_inbox and not previous_actor._inbox._closed:
                actor._inbox = previous_actor._inbox
            else:
                previous_actor._inbox.drain_into(actor._inbox)
            previous_actor._ref_target = actor
        task = asyncio.create_task(
            self._watch_child(spec, actor),
            name=f"child-{spec.actor_cls.__name__}",
        )
        if previous_actor is None:
            self._children.append((spec, actor, task))
        else:
            for i, (_, existing_actor, _) in enumerate(self._children):
                if existing_actor is previous_actor:
                    self._children[i] = (spec, actor, task)
                    break
            else:
                self._children.append((spec, actor, task))
        # Give child on_start a chance to run
        await asyncio.sleep(0)
        return actor

    async def _watch_child(self, spec: ChildSpec, actor: Actor) -> None:
        """Run a child actor and handle its exit with backoff and drain."""
        key = id(spec)
        while True:
            try:
                await actor._run()
                self._consecutive_failures[key] = 0
                # Clean exit
                if spec.restart == RestartType.PERMANENT:
                    logger.info("Restarting permanent child %s after clean exit",
                                spec.actor_cls.__name__)
                    await self._handle_child_exit(spec, actor, normal=True)
                return
            except Exception as e:
                self._consecutive_failures[key] += 1
                logger.error("Child %s crashed: %s", spec.actor_cls.__name__, e)
                if spec.restart == RestartType.TEMPORARY:
                    logger.info("Not restarting temporary child %s",
                                spec.actor_cls.__name__)
                    return

                # Exponential backoff before restart
                delay = min(
                    _BACKOFF_BASE * (_BACKOFF_FACTOR ** (self._consecutive_failures[key] - 1)),
                    _BACKOFF_MAX,
                )
                await _sleep(delay)

                await self._handle_child_exit(spec, actor, normal=False)
                return  # _handle_child_exit creates a new watcher task

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
        await self._start_child(
            spec,
            previous_actor=old_actor,
            preserve_inbox=not old_actor._inbox._closed,
        )

    async def _restart_all(self) -> None:
        """Stop all children and restart them."""
        children = list(self._children)
        # Stop all
        current_task = asyncio.current_task()
        for _, actor, task in children:
            await actor.stop()
            if task is not current_task:
                task.cancel()
        # Restart all
        for spec, old_actor, _ in children:
            await self._start_child(spec, previous_actor=old_actor)

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
        rest = list(self._children[idx:])
        current_task = asyncio.current_task()
        for spec, actor, task in rest:
            await actor.stop()
            if task is not current_task:
                task.cancel()
        # Restart
        for spec, old_actor, _ in rest:
            await self._start_child(
                spec,
                previous_actor=old_actor,
                preserve_inbox=(spec is failed_spec and not old_actor._inbox._closed),
            )

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
