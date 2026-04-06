"""OTP-inspired actor primitives for Python asyncio.

Provides:
- :class:`Actor` / :class:`ActorRef` — base actor with inbox and lifecycle hooks
- :class:`ActorSystem` — spawn and supervise actors with automatic restarts
- :class:`Inbox` / :class:`OverflowPolicy` / :class:`InboxFull` — bounded queue
- :class:`SupervisionStrategy` / :class:`RestartPolicy` — supervision configuration
- :class:`PersistentBridge` — async-sync bridge for monitor-thread patterns
- :class:`Supervisor` / :class:`ChildSpec` — hierarchical supervision
- :class:`CircuitBreaker` / :class:`CircuitState` — failure management
- :class:`DispatchActor` — actor with type-based message dispatch
"""

from asyncio_actors.actor import Actor, ActorRef, Envelope
from asyncio_actors.system import ActorSystem
from asyncio_actors.inbox import Inbox, OverflowPolicy, InboxFull
from asyncio_actors.supervision import SupervisionStrategy, RestartPolicy
from asyncio_actors.bridge import PersistentBridge
from asyncio_actors.supervisor import (
    Supervisor, ChildSpec, SupervisorStrategy, RestartType,
)
from asyncio_actors.circuit_breaker import CircuitBreaker, CircuitState, CircuitOpenError
from asyncio_actors.dispatch_actor import DispatchActor

__all__ = [
    "Actor",
    "ActorRef",
    "ActorSystem",
    "Envelope",
    "Inbox",
    "OverflowPolicy",
    "InboxFull",
    "SupervisionStrategy",
    "RestartPolicy",
    "PersistentBridge",
    "Supervisor",
    "ChildSpec",
    "SupervisorStrategy",
    "RestartType",
    "CircuitBreaker",
    "CircuitState",
    "CircuitOpenError",
    "DispatchActor",
]

__version__ = "0.1.0"
