"""Task executors registry."""

from typing import Callable

from ..runner import ShardRunner


# Task executor type: (config, files, runner) -> list[output_records]
TaskExecutor = Callable[[dict, list[dict], ShardRunner], list[dict]]


def get_executor(task_id: str) -> TaskExecutor:
    """Get the executor function for a task.

    Args:
        task_id: Task ID (e.g., '01_parse').

    Returns:
        Executor function.

    Raises:
        ValueError: If task executor not found.
    """
    if task_id == "01_parse":
        from .parse import parse_executor
        return parse_executor
    elif task_id == "02_analyze":
        from .analyze import analyze_executor
        return analyze_executor
    elif task_id == "03_symbols":
        from .symbols import symbols_executor
        return symbols_executor
    elif task_id == "04_lint":
        from .lint import lint_executor
        return lint_executor
    else:
        raise ValueError(f"Unknown task: {task_id}")
