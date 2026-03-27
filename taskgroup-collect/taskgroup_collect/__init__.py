"""TaskGroup variant that collects all errors instead of aborting on the first.

Standard asyncio.TaskGroup cancels all remaining tasks when any task raises.
CollectorTaskGroup lets all tasks run to completion, then raises a combined
BaseExceptionGroup if any failed.

See: https://github.com/python/cpython/issues/101581
"""

from taskgroup_collect._collector import CollectorTaskGroup

__all__ = ["CollectorTaskGroup"]
