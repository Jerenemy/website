"""Path and runtime config resolution for attack-target Dash apps."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class RuntimePaths:
    project_dir: Path
    analysis_root: Path
    edges_path: Path
    nodes_path: Path
    mentions_path: Path
    harmonized_path: Path
    base_path: str


def normalize_base_path(path: str) -> str:
    normalized = (path or "/").strip()
    if not normalized.startswith("/"):
        normalized = f"/{normalized}"
    if not normalized.endswith("/"):
        normalized = f"{normalized}/"
    return normalized


def detect_analysis_root(project_dir: Path) -> Path:
    cwd = Path.cwd().resolve()
    candidates = [cwd, project_dir, project_dir.parent, cwd.parent]

    seen: set[Path] = set()
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in seen:
            continue
        seen.add(resolved)
        if (resolved / "outputs").exists() and (resolved / "data").exists():
            return resolved
    return cwd


def resolve_path(path_str: str, root: Path) -> Path:
    path = Path(path_str).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (root / path).resolve()


def resolve_first_existing_path(candidates: list[Path]) -> Path:
    attempted: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.resolve()
        if path in seen:
            continue
        seen.add(path)
        attempted.append(path)
        if path.exists():
            return path

    attempted_paths = "\n".join(f"- {p}" for p in attempted)
    raise FileNotFoundError(f"None of the candidate input paths exist:\n{attempted_paths}")


def build_input_candidates(
    relative_paths: list[str],
    analysis_root: Path,
    project_dir: Path,
) -> list[Path]:
    candidates: list[Path] = []

    data_root_env = os.getenv("DELTA_DATA_ROOT", "").strip()
    if data_root_env:
        data_root = Path(data_root_env).expanduser().resolve()
        for relative_path in relative_paths:
            candidates.extend(
                [
                    resolve_path(relative_path, data_root),
                    (data_root / Path(relative_path).name).resolve(),
                ]
            )

    for root in [project_dir, analysis_root]:
        for relative_path in relative_paths:
            candidates.append(resolve_path(relative_path, root))
    return candidates


def resolve_runtime_paths() -> RuntimePaths:
    project_dir = Path(__file__).resolve().parent
    analysis_root = detect_analysis_root(project_dir)
    base_path = normalize_base_path(os.getenv("DELTA_BASE_PATH", "/"))

    edges_path = resolve_first_existing_path(
        build_input_candidates(
            relative_paths=[
                "outputs/week3/attack_target_edges_v1_2.csv",
                "data_inputs/attack_target_edges_v1_2.csv",
                "outputs/week3/attack_target_edges_v1_1.csv",
                "data_inputs/attack_target_edges_v1_1.csv",
            ],
            analysis_root=analysis_root,
            project_dir=project_dir,
        )
    )
    nodes_path = resolve_first_existing_path(
        build_input_candidates(
            relative_paths=[
                "outputs/week3/attack_target_nodes_v1_2.csv",
                "data_inputs/attack_target_nodes_v1_2.csv",
                "outputs/week3/attack_target_nodes_v1_1.csv",
                "data_inputs/attack_target_nodes_v1_1.csv",
            ],
            analysis_root=analysis_root,
            project_dir=project_dir,
        )
    )
    mentions_path = resolve_first_existing_path(
        build_input_candidates(
            relative_paths=[
                "outputs/week3/entity_mentions_week3_cleaned_v1_1.csv.gz",
                "data_inputs/entity_mentions_week3_cleaned_v1_1.csv.gz",
            ],
            analysis_root=analysis_root,
            project_dir=project_dir,
        )
    )
    harmonized_path = resolve_first_existing_path(
        build_input_candidates(
            relative_paths=[
                "outputs/week1/harmonized_sample_week1.csv.gz",
                "data_inputs/harmonized_sample_week1.csv.gz",
            ],
            analysis_root=analysis_root,
            project_dir=project_dir,
        )
    )

    return RuntimePaths(
        project_dir=project_dir,
        analysis_root=analysis_root,
        edges_path=edges_path,
        nodes_path=nodes_path,
        mentions_path=mentions_path,
        harmonized_path=harmonized_path,
        base_path=base_path,
    )
