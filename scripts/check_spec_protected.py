#!/usr/bin/env python3
"""CI Rule A: SPEC stability guard.

Fails if protected regions of SPEC.md have changed.

Uses a committed baseline hash file (.spec_baseline_hash) as the source of truth.
This ensures enforcement works even without git history access.

Usage:
    python scripts/check_spec_protected.py [--bootstrap]

Arguments:
    --bootstrap: Create/update the baseline hash file (run once to lock)

Exit codes:
    0: No protected changes (or bootstrap succeeded)
    1: Protected region modified OR baseline missing
    2: Error (missing file, etc.)
"""

import hashlib
import sys
import re
from pathlib import Path


SPEC_FILE = Path("SPEC.md")
BASELINE_FILE = Path(".spec_baseline_hash")
BEGIN_MARKER = "<!-- SPEC_PROTECTED_BEGIN -->"
END_MARKER = "<!-- SPEC_PROTECTED_END -->"


def extract_protected_region(content: str) -> str:
    """Extract content between protected markers."""
    begin_match = re.search(re.escape(BEGIN_MARKER), content)
    end_match = re.search(re.escape(END_MARKER), content)

    if not begin_match or not end_match:
        return ""

    start = begin_match.end()
    end = end_match.start()
    return content[start:end].strip()


def compute_hash(content: str) -> str:
    """Compute SHA256 hash of content."""
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def bootstrap_baseline(protected_region: str) -> None:
    """Create or update the baseline hash file."""
    region_hash = compute_hash(protected_region)
    BASELINE_FILE.write_text(f"{region_hash}\n", encoding="utf-8")
    print(f"OK: Baseline hash written to {BASELINE_FILE}")
    print(f"    Hash: {region_hash[:16]}...")
    print(f"    Commit this file to lock the protected region.")


def main():
    bootstrap_mode = "--bootstrap" in sys.argv

    # Get current SPEC file
    if not SPEC_FILE.exists():
        print(f"ERROR: {SPEC_FILE} not found")
        sys.exit(2)

    current_content = SPEC_FILE.read_text(encoding="utf-8")
    current_protected = extract_protected_region(current_content)

    if not current_protected:
        print(f"ERROR: Protected region markers missing from {SPEC_FILE}")
        print(f"       Expected markers: {BEGIN_MARKER} ... {END_MARKER}")
        sys.exit(1)

    current_hash = compute_hash(current_protected)

    # Bootstrap mode: create baseline
    if bootstrap_mode:
        bootstrap_baseline(current_protected)
        sys.exit(0)

    # Normal mode: compare against baseline
    if not BASELINE_FILE.exists():
        print(f"ERROR: Baseline file {BASELINE_FILE} not found")
        print(f"       Run with --bootstrap to create it (once, then commit)")
        print(f"       This is required to enforce SPEC stability.")
        sys.exit(1)

    baseline_hash = BASELINE_FILE.read_text(encoding="utf-8").strip()

    if current_hash != baseline_hash:
        print(f"ERROR: Protected region of {SPEC_FILE} has been modified")
        print(f"\n  Baseline hash: {baseline_hash[:16]}...")
        print(f"  Current hash:  {current_hash[:16]}...")
        print(f"\nChanges detected in sections 2-8 (store layout, shard rules, truth separation).")
        print(f"These changes require Phase 3+ and a schema version bump.")
        print(f"\nAllowed changes:")
        print(f"  - Adding output kinds (section 9)")
        print(f"  - Clarifying plan deps (section 7)")
        print(f"  - Adding new schema files")
        print(f"\nIf this change is intentional (Phase 3+):")
        print(f"  1. Bump schema_version in common.py")
        print(f"  2. Run: python scripts/check_spec_protected.py --bootstrap")
        print(f"  3. Commit the updated {BASELINE_FILE}")
        sys.exit(1)

    print(f"OK: Protected region unchanged (hash: {current_hash[:16]}...)")
    sys.exit(0)


if __name__ == "__main__":
    main()
