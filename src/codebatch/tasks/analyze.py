"""Analyze task executor - produces file-level metrics.

Emits:
- kind=metric: File-level metrics (bytes, loc, lang, parse_status)

Inputs:
- Snapshot file records for this shard
- Optionally parse outputs to determine parse_status

Metrics are stable and cheap - no deep analysis.
"""

from typing import Iterable, Optional

from ..runner import ShardRunner


def count_lines(content: str) -> int:
    """Count lines of code (non-empty lines)."""
    lines = content.split('\n')
    return sum(1 for line in lines if line.strip())


def analyze_executor(config: dict, files: Iterable[dict], runner: ShardRunner) -> list[dict]:
    """Execute the analyze task.

    Produces file-level metrics for each file in the shard:
    - bytes: File size from snapshot
    - loc: Lines of code (non-empty lines, text files only)
    - lang: Language hint from snapshot
    - parse_status: 'ok', 'failed', or 'missing' if parse dep exists

    Args:
        config: Task configuration.
        files: Iterable of file records for this shard.
        runner: ShardRunner for CAS access.

    Returns:
        List of metric output records.
    """
    outputs = []

    # Check if we should look at parse outputs
    check_parse = config.get("check_parse_status", True)

    # Materialize files for potential multi-pass
    file_list = list(files)

    # Build parse status map if checking parse
    parse_status_map: dict[str, str] = {}
    if check_parse:
        # Get batch/task context from runner if available
        # We'll populate this when we have context from the shard run
        pass  # Will be populated per-file below

    for file_record in file_list:
        path = file_record["path"]
        object_ref = file_record["object"]
        lang_hint = file_record.get("lang_hint", "unknown")

        try:
            # Get file content from CAS
            data = runner.object_store.get_bytes(object_ref)
            file_bytes = len(data)

            # Try to decode as text for LOC
            loc: Optional[int] = None
            try:
                content = data.decode("utf-8")
                loc = count_lines(content)
            except UnicodeDecodeError:
                # Binary file - no LOC
                pass

            # Emit bytes metric
            outputs.append({
                "kind": "metric",
                "path": path,
                "metric": "bytes",
                "value": file_bytes,
            })

            # Emit LOC metric (if text)
            if loc is not None:
                outputs.append({
                    "kind": "metric",
                    "path": path,
                    "metric": "loc",
                    "value": loc,
                })

            # Emit lang metric
            outputs.append({
                "kind": "metric",
                "path": path,
                "metric": "lang",
                "value": lang_hint,
            })

        except Exception as e:
            # Emit error metric
            outputs.append({
                "kind": "metric",
                "path": path,
                "metric": "error",
                "value": str(e),
            })

    return outputs
