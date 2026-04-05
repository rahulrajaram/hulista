"""TaskGroup variant that collects all errors instead of aborting on the first.

Standard asyncio.TaskGroup cancels all remaining tasks when any task raises and
interrupts the parent ``async with`` body. CollectorTaskGroup lets sibling
tasks keep running, does not interrupt the active body, and raises a combined
BaseExceptionGroup on exit if any child failed.

See: https://github.com/python/cpython/issues/101581
"""

from taskgroup_collect._collector import CollectorTaskGroup
from taskgroup_collect._outcome import Failure, Success, TaskOutcome

__all__ = ["CollectorTaskGroup", "TaskOutcome", "Success", "Failure"]
