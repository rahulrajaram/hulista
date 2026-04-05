"""Base Actor class with inbox, lifecycle hooks, and supervision."""
from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any

from asyncio_actors.inbox import Inbox, OverflowPolicy
from asyncio_actors.supervision import SupervisionStrategy, RestartPolicy

logger = logging.getLogger(__name__)


def _get_result_types():
    """Lazily import Result, Ok, Err from fp-combinators.

    Raises ImportError with a helpful message if fp-combinators is not installed.
    """
    try:
        from fp_combinators import Result, Ok, Err
        return Result, Ok, Err
    except ImportError:
        raise ImportError(
            "ask_result() requires fp-combinators. Install with: pip install fp-combinators"
        )


# ---------------------------------------------------------------------------
# Envelope — wraps every message with metadata
# ---------------------------------------------------------------------------

@dataclass
class Envelope:
    """Metadata wrapper applied to every message in transit.

    The actor's ``on_message`` still receives the *unwrapped* payload; use
    ``self.envelope`` inside ``on_message`` to access these fields.
    """
    message: Any
    sender: ActorRef | None = None
    correlation_id: str | None = None
    timestamp: float = field(default_factory=time.time)


class ActorRef:
    """Handle to a running actor for message passing."""
    __slots__ = ('_actor',)

    def __init__(self, actor: Actor) -> None:
        self._actor = actor

    def _target(self) -> Actor:
        """Resolve the latest live actor for this logical ref chain."""
        actor = self._actor
        chain: list[Actor] = []
        while actor._ref_target is not actor:
            chain.append(actor)
            actor = actor._ref_target
        for previous in chain:
            previous._ref_target = actor
        return actor

    async def send(
        self,
        message: Any,
        *,
        sender: ActorRef | None = None,
        correlation_id: str | None = None,
    ) -> None:
        """Fire-and-forget message delivery.

        The message is wrapped in an :class:`Envelope`; the actor's
        ``on_message`` receives the unwrapped payload and ``self.envelope``
        holds the metadata.
        """
        envelope = Envelope(message=message, sender=sender, correlation_id=correlation_id)
        await self._target()._inbox.put(envelope)

    async def ask(
        self,
        message: Any,
        timeout: float = 5.0,
        *,
        sender: ActorRef | None = None,
        correlation_id: str | None = None,
    ) -> Any:
        """Send a message and await the actor's reply.

        The actor must call ``await self.reply(value)`` or return a value from
        ``on_message`` to resolve the future.
        """
        reply_future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        env = Envelope(message=message, sender=sender, correlation_id=correlation_id)
        ask_env = _AskEnvelope(env, reply_future)
        await self._target()._inbox.put(ask_env)
        return await asyncio.wait_for(reply_future, timeout=timeout)

    async def ask_result(
        self,
        message: Any,
        timeout: float = 5.0,
        *,
        sender: ActorRef | None = None,
        correlation_id: str | None = None,
    ) -> Any:
        """Send a message and await the actor's reply, returning a Result.

        Unlike :meth:`ask`, this method never raises on failure or timeout.
        Instead it returns:

        - ``Ok(value)`` on success
        - ``Err(TimeoutError(...))`` when the reply exceeds *timeout* seconds
        - ``Err(exc)`` when the actor raises an exception during handling

        Requires the ``fp-combinators`` package to be installed.
        """
        _Result, Ok, Err = _get_result_types()
        try:
            value = await self.ask(message, timeout=timeout)
            return Ok(value)
        except asyncio.TimeoutError:
            return Err(
                TimeoutError(
                    f"ask_result() timed out after {timeout}s waiting for reply"
                )
            )
        except Exception as exc:
            return Err(exc)

    async def stop(self) -> None:
        """Request a graceful shutdown of the actor.

        Triggers the actor's ``on_stop()`` lifecycle hook.
        """
        await self._target().stop()

    async def watch(self) -> asyncio.Future[None]:
        """Return a :class:`asyncio.Future` that resolves when the actor stops.

        Callers can ``await`` the returned future to be notified of termination::

            done = await ref.watch()
            await done
        """
        target = self._target()
        fut: asyncio.Future[None] = asyncio.get_running_loop().create_future()
        target._watchers.append(fut)
        # If the actor is already stopped, resolve immediately.
        if not target._running and target._task is None:
            if not fut.done():
                fut.set_result(None)
        return fut

    @property
    def is_alive(self) -> bool:
        return self._target()._running


class _AskEnvelope:
    __slots__ = ('envelope', 'reply_future')

    def __init__(self, envelope: Envelope, reply_future: asyncio.Future[Any]) -> None:
        self.envelope = envelope
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
        self._ref_target: Actor = self
        self._task: asyncio.Task[None] | None = None
        self._reply_future: asyncio.Future[Any] | None = None
        # Current envelope — populated before each on_message call.
        self.envelope: Envelope | None = None
        # Watchers — futures to resolve when the actor stops.
        self._watchers: list[asyncio.Future[None]] = []
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

    async def receive(
        self,
        match: type | None = None,
        timeout: float | None = None,
    ) -> Any:
        """Selective receive: wait for and return the next matching message.

        Non-matching messages remain in the inbox for later processing.

        Args:
            match: If provided, only return messages that are instances of
                this type.  If ``None``, return the next message regardless
                of type.
            timeout: Optional timeout in seconds.  Raises
                :class:`asyncio.TimeoutError` if no matching message arrives
                in time.

        Returns:
            The (unwrapped) message payload.
        """
        if match is None:
            # Fast-path: just get the next message.
            raw = await self._inbox.get(timeout=timeout)
            return self._unwrap_raw(raw)

        # Use the inbox's selective-receive, but we need to handle the
        # Envelope wrapping: scan for Envelopes whose .message is an
        # instance of match, and also handle _AskEnvelopes.
        # Because the inbox's receive() matches on the container type, we
        # do a manual loop using the inbox's internal API.
        return await self._selective_receive(match, timeout)

    async def _selective_receive(
        self, match: type, timeout: float | None
    ) -> Any:
        """Internal: poll inbox for a message matching *match*, respecting timeout."""
        deadline: float | None = None
        if timeout is not None:
            deadline = time.monotonic() + timeout

        # First scan what's already queued.
        found = self._scan_inbox_for_match(match)
        if found is not _SENTINEL:
            return found

        # Wait for new messages.
        while True:
            remaining: float | None = None
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise asyncio.TimeoutError()

            raw = await self._inbox._await_queued_message(timeout=remaining)
            unwrapped = self._unwrap_raw(raw)
            if isinstance(unwrapped, match):
                return unwrapped
            # Stash the raw item so it is not lost.
            self._inbox._stash.append(raw)

    def _scan_inbox_for_match(self, match: type) -> object:
        """Scan stash and queue for a matching message (envelope-aware)."""
        for store in (self._inbox._stash, self._inbox._queue):
            for i, raw in enumerate(store):
                unwrapped = self._unwrap_raw(raw)
                if isinstance(unwrapped, match):
                    del store[i]
                    return unwrapped
        return _SENTINEL

    @staticmethod
    def _unwrap_raw(raw: Any) -> Any:
        """Unwrap an Envelope or _AskEnvelope to its payload."""
        if isinstance(raw, _AskEnvelope):
            return raw.envelope.message
        if isinstance(raw, Envelope):
            return raw.message
        # Legacy: bare message (should not occur after migration but be safe)
        return raw

    async def stop(self) -> None:
        """Request a graceful shutdown of this actor."""
        self._running = False
        self._inbox.close()
        task = self._task
        current = asyncio.current_task()
        if task is not None and task is not current and not task.done():
            task.cancel()

    def ref(self) -> ActorRef:
        """Return an :class:`ActorRef` handle for message passing."""
        return ActorRef(self)

    # ------------------------------------------------------------------
    # Internal run loop — managed by ActorSystem
    # ------------------------------------------------------------------

    async def _run(self) -> None:
        """Main actor loop.  Called (and potentially restarted) by the system."""
        self._running = True
        self._task = asyncio.current_task()
        try:
            await self.on_start()
            while self._running:
                try:
                    raw = await asyncio.wait_for(self._inbox.get(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                except RuntimeError:
                    # Inbox closed — exit cleanly.
                    break

                # Unwrap ask() envelopes so on_message sees the real payload.
                if isinstance(raw, _AskEnvelope):
                    self._reply_future = raw.reply_future
                    self.envelope = raw.envelope
                    actual_msg = raw.envelope.message
                elif isinstance(raw, Envelope):
                    self._reply_future = None
                    self.envelope = raw
                    actual_msg = raw.message
                else:
                    # Legacy bare message — kept for safety
                    self._reply_future = None
                    self.envelope = None
                    actual_msg = raw

                try:
                    result = await self.on_message(actual_msg)
                    # Auto-reply if on_message returned a value and no explicit
                    # reply() call was made yet.
                    if self._reply_future and not self._reply_future.done():
                        self._reply_future.set_result(result)
                except asyncio.CancelledError:
                    if self._running:
                        raise
                    break
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
        except asyncio.CancelledError:
            if self._running:
                raise
        finally:
            self._running = False
            self._task = None
            await self.on_stop()
            self._notify_watchers()

    def _notify_watchers(self) -> None:
        """Resolve all watch() futures when the actor stops."""
        watchers = self._watchers
        self._watchers = []
        for fut in watchers:
            if not fut.done():
                fut.set_result(None)


_SENTINEL = object()
