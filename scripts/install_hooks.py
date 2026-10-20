#!/usr/bin/env python3
"""Enable this repository's local Git hooks for the current checkout."""

import subprocess
from pathlib import Path


root = Path(
    subprocess.check_output(["git", "rev-parse", "--show-toplevel"], text=True).strip()
)
subprocess.run(
    ["git", "config", "--local", "core.hooksPath", ".githooks"],
    cwd=root,
    check=True,
)
print("Repository hooks enabled.")
