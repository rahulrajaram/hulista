"""OTP-inspired actor primitives for Python asyncio.

Provides:
- :class:`Actor` / :class:`ActorRef` — base actor with inbox and lifecycle hooks
- :class:`ActorSystem` — spawn and supervise actors with automatic restarts
- :class:`Inbox` / :class:`OverflowPolicy` / :class:`InboxFull` — bounded queue
- :class:`SupervisionStrategy` / :class:`RestartPolicy` — supervision configuration
- :class:`PersistentBridge` — async-sync bridge for monitor-thread patterns
"""

from asyncio_actors.actor import Actor, ActorRef
from asyncio_actors.system import ActorSystem
from asyncio_actors.inbox import Inbox, OverflowPolicy, InboxFull
from asyncio_actors.supervision import SupervisionStrategy, RestartPolicy
from asyncio_actors.bridge import PersistentBridge

__all__ = [
    "Actor",
    "ActorRef",
    "ActorSystem",
    "Inbox",
    "OverflowPolicy",
    "InboxFull",
    "SupervisionStrategy",
    "RestartPolicy",
    "PersistentBridge",
]

__version__ = "0.1.0"
