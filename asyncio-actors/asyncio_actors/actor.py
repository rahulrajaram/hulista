"""Base Actor class with inbox, lifecycle hooks, and supervision."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

from asyncio_actors.inbox import Inbox, OverflowPolicy
from asyncio_actors.supervision import SupervisionStrategy, RestartPolicy

logger = logging.getLogger(__name__)


class ActorRef:
    """Handle to a running actor for message passing."""
    __slots__ = ('_actor', '_inbox')

    def __init__(self, actor: Actor, inbox: Inbox[Any]) -> None:
        self._actor = actor
        self._inbox = inbox

    async def send(self, message: Any) -> None:
        """Fire-and-forget message delivery."""
        await self._inbox.put(message)

    async def ask(self, message: Any, timeout: float = 5.0) -> Any:
        """Send a message and await the actor's reply.

        The actor must call ``await self.reply(value)`` or return a value from
        ``on_message`` to resolve the future.
        """
        reply_future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        envelope = _AskEnvelope(message, reply_future)
        await self._inbox.put(envelope)
        return await asyncio.wait_for(reply_future, timeout=timeout)

    @property
    def is_alive(self) -> bool:
        return self._actor._running


class _AskEnvelope:
    __slots__ = ('message', 'reply_future')

    def __init__(self, message: Any, reply_future: asyncio.Future[Any]) -> None:
        self.message = message
        self.reply_future = reply_future


class Actor:
    """Base actor class. Subclass and implement ``on_message()``.

    Lifecycle::

        on_start() -> message loop -> on_stop()

    ``on_error()`` is called on unhandled exceptions from ``on_message()``.
    The return value of ``on_error()`` controls the supervision decision for
    that individual error; the :class:`~asyncio_actors.supervision.RestartPolicy`
    on the actor controls how many times the system will restart after a crash.
    """

    inbox_size: int = 100
    overflow_policy: OverflowPolicy = OverflowPolicy.BLOCK

    def __init__(self) -> None:
        self._inbox: Inbox[Any] = Inbox(
            maxsize=self.inbox_size, policy=self.overflow_policy
        )
        self._running = False
        self._task: asyncio.Task[None] | None = None
        self._reply_future: asyncio.Future[Any] | None = None
        # Per-instance restart policy to avoid shared mutable state.
        # If the subclass defined its own restart_policy as a class attribute,
        # we clone it so _restart_times is not shared across instances.
        if 'restart_policy' not in self.__dict__:
            cls_policy = type(self).__dict__.get('restart_policy', None)
            if cls_policy is not None:
                self.restart_policy = RestartPolicy(
                    max_restarts=cls_policy.max_restarts,
                    restart_window_seconds=cls_policy.restart_window_seconds,
                )
            else:
                self.restart_policy = RestartPolicy()

    # ------------------------------------------------------------------
    # Lifecycle hooks — override in subclasses
    # ------------------------------------------------------------------

    async def on_start(self) -> None:
        """Called once when the actor starts. Override to initialise state."""

    async def on_message(self, message: Any) -> Any:
        """Called for each received message. Must be overridden."""
        raise NotImplementedError("Subclass must implement on_message()")

    async def on_stop(self) -> None:
        """Called on graceful shutdown. Override to release resources."""

    async def on_error(self, error: Exception) -> SupervisionStrategy:
        """Called on an unhandled error in ``on_message``.

        Return a :class:`~asyncio_actors.supervision.SupervisionStrategy` to
        direct the actor's own handling of the error within the current run.
        Note that :attr:`restart_policy` governs system-level restarts when the
        actor raises from its run loop.
        """
        logger.error(
            "Actor %s error: %s", type(self).__name__, error, exc_info=True
        )
        return SupervisionStrategy.RESTART

    # ------------------------------------------------------------------
    # API available inside on_message
    # ------------------------------------------------------------------

    async def reply(self, response: Any) -> None:
        """Reply to the current ``ask()`` call from within ``on_message``."""
        if self._reply_future and not self._reply_future.done():
            self._reply_future.set_result(response)

    async def stop(self) -> None:
        """Request a graceful shutdown of this actor."""
        self._running = False
        self._inbox.close()

    def ref(self) -> ActorRef:
        """Return an :class:`ActorRef` handle for message passing."""
        return ActorRef(self, self._inbox)

    # ------------------------------------------------------------------
    # Internal run loop — managed by ActorSystem
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main actor loop.  Called (and potentially restarted) by the system."""
        self._running = True
        try:
            await self.on_start()
            while self._running:
                try:
                    msg = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except RuntimeError:
                    # Inbox closed — exit cleanly.
                    break

                # Unwrap ask() envelopes so on_message sees the real payload.
                if isinstance(msg, _AskEnvelope):
                    self._reply_future = msg.reply_future
                    actual_msg = msg.message
                else:
                    self._reply_future = None
                    actual_msg = msg

                try:
                    result = await self.on_message(actual_msg)
                    # Auto-reply if on_message returned a value and no explicit
                    # reply() call was made yet.
                    if self._reply_future and not self._reply_future.done():
                        self._reply_future.set_result(result)
                except Exception as e:
                    if self._reply_future and not self._reply_future.done():
                        self._reply_future.set_exception(e)
                    strategy = await self.on_error(e)
                    if strategy == SupervisionStrategy.STOP:
                        break
                    elif strategy == SupervisionStrategy.ESCALATE:
                        raise
                    # RESTART strategy: continue the loop.  The on_error hook
                    # can reset internal state if needed.
        finally:
            self._running = False
            await self.on_stop()
