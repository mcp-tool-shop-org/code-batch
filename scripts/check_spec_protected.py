#!/usr/bin/env python3
"""CI Rule A: SPEC stability guard.

Fails if protected regions of SPEC.md have changed.

Usage:
    python scripts/check_spec_protected.py [base_ref]

Arguments:
    base_ref: Git ref to compare against (default: origin/main)

Exit codes:
    0: No protected changes
    1: Protected region modified
    2: Error (missing file, git error, etc.)
"""

import subprocess
import sys
import re


SPEC_FILE = "SPEC.md"
BEGIN_MARKER = "<!-- SPEC_PROTECTED_BEGIN -->"
END_MARKER = "<!-- SPEC_PROTECTED_END -->"


def get_file_at_ref(filepath: str, ref: str) -> str:
    """Get file contents at a git ref."""
    try:
        result = subprocess.run(
            ["git", "show", f"{ref}:{filepath}"],
            capture_output=True,
            text=True,
            check=True,
        )
        return result.stdout
    except subprocess.CalledProcessError:
        return ""  # File doesn't exist at ref


def extract_protected_region(content: str) -> str:
    """Extract content between protected markers."""
    begin_match = re.search(re.escape(BEGIN_MARKER), content)
    end_match = re.search(re.escape(END_MARKER), content)

    if not begin_match or not end_match:
        return ""

    start = begin_match.end()
    end = end_match.start()
    return content[start:end].strip()


def main():
    base_ref = sys.argv[1] if len(sys.argv) > 1 else "origin/main"

    # Get current file
    try:
        with open(SPEC_FILE, "r", encoding="utf-8") as f:
            current_content = f.read()
    except FileNotFoundError:
        print(f"ERROR: {SPEC_FILE} not found")
        sys.exit(2)

    # Get file at base ref
    base_content = get_file_at_ref(SPEC_FILE, base_ref)
    if not base_content:
        print(f"INFO: {SPEC_FILE} not found at {base_ref}, skipping check")
        sys.exit(0)

    # Extract protected regions
    current_protected = extract_protected_region(current_content)
    base_protected = extract_protected_region(base_content)

    if not base_protected:
        print(f"INFO: No protected region in {base_ref}, skipping check")
        sys.exit(0)

    if not current_protected:
        print(f"ERROR: Protected region markers missing from current {SPEC_FILE}")
        sys.exit(1)

    # Compare
    if current_protected != base_protected:
        print(f"ERROR: Protected region of {SPEC_FILE} has been modified")
        print(f"\nChanges detected in sections 2-8 (store layout, shard rules, truth separation).")
        print(f"These changes require Phase 3+ and a schema version bump.")
        print(f"\nAllowed changes:")
        print(f"  - Adding output kinds (section 9)")
        print(f"  - Clarifying plan deps (section 7)")
        print(f"  - Adding new schema files")
        sys.exit(1)

    print(f"OK: Protected region unchanged")
    sys.exit(0)


if __name__ == "__main__":
    main()
