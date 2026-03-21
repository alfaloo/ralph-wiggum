"""Shared utility helpers for Ralph Wiggum.

This module collects small, reusable helpers extracted from commands.py and
run.py to reduce duplication across the codebase.
"""

from __future__ import annotations

import re
import subprocess
import sys


def _read_validation_rating(validation_path: str) -> str | None:
    """Return the rating string from a validation.md file, or None if not found.

    Opens *validation_path*, scans each line for a ``# rating: …`` heading
    (case-insensitive), and returns the first match stripped and lowercased.
    Returns ``None`` if no match is found or if the file cannot be read.
    """
    try:
        with open(validation_path) as f:
            for line in f:
                m = re.match(r"#\s*rating:\s*(.+)", line.strip(), re.IGNORECASE)
                if m:
                    return m.group(1).strip().lower()
    except OSError:
        pass
    return None


def _git_checkout(branch: str) -> None:
    """Checkout *branch*, printing a Ralph-style error and exiting on failure."""
    result = subprocess.run(["git", "checkout", branch], capture_output=True, text=True)
    if result.returncode != 0:
        print(
            f"[ralph] I couldn't get to branch '{branch}': {result.stderr.strip()}",
            file=sys.stderr,
        )
        sys.exit(1)


def _git_branch_exists(branch: str) -> bool:
    """Return True if *branch* exists in the local repository, False otherwise."""
    result = subprocess.run(["git", "branch", "--list", branch], capture_output=True, text=True)
    return bool(result.stdout.strip())
