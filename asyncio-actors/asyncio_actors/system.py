"""ActorSystem — spawn and supervise actors."""
from __future__ import annotations

import asyncio
import time
import logging
from typing import Any

from asyncio_actors.actor import Actor, ActorRef
from asyncio_actors.supervision import RestartPolicy

logger = logging.getLogger(__name__)


class ActorSystem:
    """Manages actor lifecycles with automatic supervision and restart.

    Usage::

        async with ActorSystem() as system:
            ref = await system.spawn(MyActor)
            await ref.send("hello")
            result = await ref.ask("question")
    """

    def __init__(self) -> None:
        self._actors: dict[Actor, asyncio.Task[None]] = {}
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

    async def spawn(self, actor_cls: type[Actor], *args: Any, **kwargs: Any) -> ActorRef:
        """Instantiate *actor_cls* and start its supervised run loop.

        Returns an :class:`~asyncio_actors.actor.ActorRef` handle immediately.
        ``on_start`` will have had one event-loop iteration to begin running by
        the time this coroutine returns.
        """
        actor = actor_cls(*args, **kwargs)
        task: asyncio.Task[None] = asyncio.create_task(
            self._supervise(actor), name=f"actor-{type(actor).__name__}"
        )
        self._actors[actor] = task
        # Yield control so that on_start() has a chance to run before the
        # caller proceeds.
        await asyncio.sleep(0)
        return actor.ref()

    async def _supervise(self, actor: Actor) -> None:
        """Supervision loop: restart the actor according to its restart policy."""
        policy = actor.restart_policy
        while self._running:
            try:
                await actor._run()
                break  # Clean / intentional shutdown — do not restart.
            except Exception as e:
                logger.error("Actor %s crashed: %s", type(actor).__name__, e, exc_info=True)
                if policy.should_restart(time.monotonic()):
                    logger.info("Restarting actor %s", type(actor).__name__)
                    # Reset internal state for a fresh run.
                    actor._running = False
                    actor._inbox = type(actor._inbox)(
                        maxsize=actor.inbox_size,
                        policy=actor.overflow_policy,
                    )
                    continue
                else:
                    logger.error(
                        "Actor %s exceeded restart limit — giving up",
                        type(actor).__name__,
                    )
                    break
        # Remove from the system registry once definitively done.
        self._actors.pop(actor, None)
