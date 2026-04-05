"""ActorSystem — spawn and supervise actors."""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

from asyncio_actors.actor import Actor, ActorRef

logger = logging.getLogger(__name__)

# Backoff constants
_BACKOFF_BASE = 0.1     # 100ms initial backoff
_BACKOFF_MAX = 5.0      # 5s max backoff
_BACKOFF_FACTOR = 2.0   # Exponential factor


class ActorSystem:
    """Manages actor lifecycles with automatic supervision and restart.

    Usage::

        async with ActorSystem() as system:
            ref = await system.spawn(MyActor, name="my-actor")
            await ref.send("hello")
            result = await ref.ask("question")
            same_ref = system.get("my-actor")
    """

    def __init__(self) -> None:
        self._actors: dict[Actor, asyncio.Task[None]] = {}
        self._registry: dict[str, ActorRef] = {}
        self._running = False

    async def __aenter__(self) -> ActorSystem:
        self._running = True
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: Any,
    ) -> None:
        self._running = False
        # Signal all actors to stop.
        for actor in list(self._actors):
            await actor.stop()
        # Await all supervision tasks so we don't leave dangling tasks.
        if self._actors:
            tasks = list(self._actors.values())
            await asyncio.gather(*tasks, return_exceptions=True)
        self._actors.clear()
        self._registry.clear()

    async def spawn(
        self,
        actor_cls: type[Actor],
        *args: Any,
        name: str | None = None,
        **kwargs: Any,
    ) -> ActorRef:
        """Instantiate *actor_cls* and start its supervised run loop.

        Args:
            actor_cls: The actor class to instantiate.
            *args: Positional arguments forwarded to the actor constructor.
            name: Optional name for the actor.  Must be unique within this
                system; raises :class:`ValueError` if a name is reused while
                the original actor is still registered.
            **kwargs: Keyword arguments forwarded to the actor constructor.

        Returns an :class:`~asyncio_actors.actor.ActorRef` handle immediately.
        ``on_start`` will have had one event-loop iteration to begin running by
        the time this coroutine returns.
        """
        if not self._running:
            raise RuntimeError("ActorSystem must be entered before spawning actors")
        if name is not None and name in self._registry:
            raise ValueError(f"An actor named {name!r} is already registered")
        actor = actor_cls(*args, **kwargs)
        task: asyncio.Task[None] = asyncio.create_task(
            self._supervise(actor_cls, args, kwargs, actor, name=name),
            name=f"actor-{type(actor).__name__}",
        )
        self._actors[actor] = task
        ref = actor.ref()
        if name is not None:
            self._registry[name] = ref
        # Yield control so that on_start() has a chance to run before the
        # caller proceeds.
        await asyncio.sleep(0)
        return ref

    def get(self, name: str) -> ActorRef | None:
        """Look up a named actor by name.

        Returns the :class:`~asyncio_actors.actor.ActorRef` registered under
        *name*, or ``None`` if no actor with that name exists (or it has been
        removed after stopping).
        """
        return self._registry.get(name)

    async def _supervise(
        self,
        actor_cls: type[Actor],
        args: tuple[Any, ...],
        kwargs: dict[str, Any],
        actor: Actor,
        name: str | None = None,
    ) -> None:
        """Supervision loop: restart the actor according to its restart policy."""
        policy = actor.restart_policy
        consecutive_failures = 0
        while self._running:
            try:
                await actor._run()
                consecutive_failures = 0  # Reset on successful run
                break  # Clean / intentional shutdown — do not restart.
            except Exception as e:
                consecutive_failures += 1
                logger.error("Actor %s crashed: %s", type(actor).__name__, e, exc_info=True)
                if policy.should_restart(time.monotonic()):
                    logger.info("Restarting actor %s", type(actor).__name__)

                    # Exponential backoff before restart
                    delay = min(
                        _BACKOFF_BASE * (_BACKOFF_FACTOR ** (consecutive_failures - 1)),
                        _BACKOFF_MAX,
                    )
                    await asyncio.sleep(delay)

                    if not self._running:
                        break

                    new_actor = actor_cls(*args, **kwargs)
                    new_actor.restart_policy = policy
                    if not actor._inbox._closed:
                        new_actor._inbox = actor._inbox
                    actor._ref_target = new_actor
                    task = self._actors.pop(actor, None)
                    if task is not None:
                        self._actors[new_actor] = task
                    actor = new_actor
                    continue
                else:
                    logger.error(
                        "Actor %s exceeded restart limit — giving up",
                        type(actor).__name__,
                    )
                    break
        # Remove from the system registry once definitively done.
        self._actors.pop(actor, None)
        if name is not None:
            self._registry.pop(name, None)
