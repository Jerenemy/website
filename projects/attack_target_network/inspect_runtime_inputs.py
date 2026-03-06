#!/usr/bin/env python3
"""Print resolved runtime input paths and CSV headers for the Dash app."""

from __future__ import annotations

import pandas as pd

try:
    from .week3_runtime_paths import resolve_runtime_paths
except ImportError:
    try:
        from week3_runtime_paths import resolve_runtime_paths
    except ImportError:
        from projects.attack_target_network.week3_runtime_paths import resolve_runtime_paths


def print_columns(label: str, path: str, *, compression: str | None = None) -> None:
    frame = pd.read_csv(path, nrows=1, compression=compression)
    print(f"{label}: {path}")
    print(f"columns: {frame.columns.tolist()}")


def main() -> None:
    paths = resolve_runtime_paths()
    print_columns("edges", str(paths.edges_path))
    print_columns("nodes", str(paths.nodes_path))
    print_columns("mentions", str(paths.mentions_path), compression="gzip")
    print_columns("harmonized", str(paths.harmonized_path), compression="gzip")


if __name__ == "__main__":
    main()
