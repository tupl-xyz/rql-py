"""Factory for creating the TaskExecutor."""

from ..ast import TaskInvocation
from ...runtime.session import RQLSession
from .task import TaskExecutor


# Global executor instance
_task_executor = TaskExecutor()


def create_executor(task_invocation: TaskInvocation, session: RQLSession) -> TaskExecutor:
    """Create the TaskExecutor for TASK invocation."""
    # All execution goes through TaskExecutor in the task-based architecture
    return _task_executor