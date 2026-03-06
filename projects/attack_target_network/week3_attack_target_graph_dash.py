#!/usr/bin/env python3
"""Week 3 interactive attack-target graph app (Dash)."""

from __future__ import annotations

import json
import os
import hmac
import math
from pathlib import Path
import secrets
import time
from threading import Lock
from collections import deque
from datetime import timedelta

import dash
from dash import Input, Output, State, ctx, dcc, html
from dash.exceptions import PreventUpdate
from dotenv import load_dotenv
from flask import request as flask_request, session
import networkx as nx
import pandas as pd
import plotly.graph_objects as go
from werkzeug.security import check_password_hash

try:
    from .week3_runtime_paths import RuntimePaths, resolve_runtime_paths
except ImportError:
    try:
        from week3_runtime_paths import RuntimePaths, resolve_runtime_paths
    except ImportError:
        from projects.attack_target_network.week3_runtime_paths import RuntimePaths, resolve_runtime_paths

THIS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = THIS_DIR.parent.parent
load_dotenv(PROJECT_ROOT / ".env", override=False)
load_dotenv(THIS_DIR / ".env.deltalab", override=False)

PARTY_COLORS = {
    "REP": "#d62728",
    "DEM": "#1f77b4",
    "IND": "#2ca02c",
    "OTHER": "#7f7f7f",
    "UNKNOWN": "#9e9e9e",
}

TARGET_PARTY_COLORS = {
    # Target nodes now store the inferred target party directly.
    "REP": "#d62728",
    "DEM": "#1f77b4",
    "IND": "#2ca02c",
    "OTHER": "#7f7f7f",
    "UNKNOWN": "#9e9e9e",
}

LABEL_COLORS = {
    "PERSON": "#1f77b4",
    "ORG": "#d62728",
    "GPE": "#2ca02c",
    "SPONSOR": "#636363",
    "UNKNOWN": "#9e9e9e",
}

CANONICAL_ENTITY_COL = "canonical_entity"
IS_TARGET_COL = "is_target"
TARGET_PARTY_MODE_MONEY = "money"
TARGET_PARTY_MODE_MENTIONS = "mentions"
DEFAULT_TARGET_PARTY_MODE = TARGET_PARTY_MODE_MONEY

ADMIN_SESSION_AUTH_KEY = "delta_admin_authenticated"
ADMIN_SESSION_USER_KEY = "delta_admin_user"
ADMIN_SESSION_EXPIRES_AT_KEY = "delta_admin_expires_at"


def env_int(name: str, default: int, minimum: int, maximum: int) -> int:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = int(raw_value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw_value = os.getenv(name, "").strip()
    if not raw_value:
        return default
    try:
        parsed = float(raw_value)
    except ValueError:
        return default
    return max(minimum, min(maximum, parsed))


def env_bool(name: str, default: bool) -> bool:
    raw_value = os.getenv(name, "").strip().lower()
    if not raw_value:
        return default
    if raw_value in {"1", "true", "yes", "on"}:
        return True
    if raw_value in {"0", "false", "no", "off"}:
        return False
    return default


ADMIN_SESSION_TTL_SECONDS = env_int("DELTA_ADMIN_SESSION_TTL_SECONDS", default=1800, minimum=300, maximum=43200)
ADMIN_RATE_LIMIT_MAX_ATTEMPTS = env_int("DELTA_ADMIN_RATE_LIMIT_MAX_ATTEMPTS", default=5, minimum=2, maximum=20)
ADMIN_RATE_LIMIT_WINDOW_SECONDS = env_int("DELTA_ADMIN_RATE_LIMIT_WINDOW_SECONDS", default=300, minimum=30, maximum=3600)
ADMIN_LOCKOUT_BASE_SECONDS = env_int("DELTA_ADMIN_LOCKOUT_BASE_SECONDS", default=300, minimum=30, maximum=7200)
ADMIN_LOCKOUT_MAX_SECONDS = env_int("DELTA_ADMIN_LOCKOUT_MAX_SECONDS", default=3600, minimum=60, maximum=86400)
ADMIN_FAILED_DELAY_SECONDS = env_float("DELTA_ADMIN_FAILED_DELAY_SECONDS", default=0.35, minimum=0.0, maximum=2.0)
ADMIN_COOKIE_SECURE = env_bool("DELTA_SESSION_COOKIE_SECURE", default=True)
MAX_ADMIN_CRED_LENGTH = 256


class LoginAttemptLimiter:
    """In-memory sliding-window limiter with lockouts for failed login attempts."""

    def __init__(
        self,
        max_attempts: int,
        window_seconds: int,
        base_lock_seconds: int,
        max_lock_seconds: int,
    ) -> None:
        self.max_attempts = max_attempts
        self.window_seconds = window_seconds
        self.base_lock_seconds = base_lock_seconds
        self.max_lock_seconds = max_lock_seconds
        self._state: dict[str, dict[str, object]] = {}
        self._lock = Lock()

    def _cleanup(self, now: float) -> None:
        stale_after = max(self.window_seconds, self.max_lock_seconds) * 2
        stale_keys = [
            key
            for key, state in self._state.items()
            if float(state.get("lock_until", 0.0)) < (now - stale_after)
            and not state.get("attempts")
        ]
        for key in stale_keys:
            self._state.pop(key, None)

    def _get_state(self, key: str) -> dict[str, object]:
        if key not in self._state:
            self._state[key] = {"attempts": deque(), "lock_until": 0.0}
        return self._state[key]

    def _trim_attempts(self, attempts: deque[float], now: float) -> None:
        while attempts and now - attempts[0] > self.window_seconds:
            attempts.popleft()

    def check_wait_seconds(self, keys: list[str]) -> int:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            max_wait = 0
            for key in keys:
                state = self._get_state(key)
                lock_until = float(state.get("lock_until", 0.0))
                if lock_until > now:
                    max_wait = max(max_wait, int(lock_until - now) + 1)
            return max_wait

    def register_failure(self, keys: list[str]) -> int:
        now = time.monotonic()
        with self._lock:
            self._cleanup(now)
            lock_seconds = 0
            for key in keys:
                state = self._get_state(key)
                attempts = state["attempts"]
                if not isinstance(attempts, deque):
                    attempts = deque()
                    state["attempts"] = attempts
                self._trim_attempts(attempts, now)
                attempts.append(now)
                if len(attempts) >= self.max_attempts:
                    overflow = len(attempts) - self.max_attempts
                    applied_lock = min(self.max_lock_seconds, self.base_lock_seconds * (2 ** overflow))
                    state["lock_until"] = now + applied_lock
                    attempts.clear()
                    lock_seconds = max(lock_seconds, int(applied_lock))
            return lock_seconds

    def register_success(self, keys: list[str]) -> None:
        with self._lock:
            for key in keys:
                self._state.pop(key, None)


LOGIN_ATTEMPT_LIMITER = LoginAttemptLimiter(
    max_attempts=ADMIN_RATE_LIMIT_MAX_ATTEMPTS,
    window_seconds=ADMIN_RATE_LIMIT_WINDOW_SECONDS,
    base_lock_seconds=ADMIN_LOCKOUT_BASE_SECONDS,
    max_lock_seconds=ADMIN_LOCKOUT_MAX_SECONDS,
)


def admin_username() -> str:
    return (
        os.getenv("DELTA_ADMIN_USERNAME", "").strip()
        or os.getenv("ADMIN_USERNAME", "").strip()
    )


def admin_password_hash() -> str:
    return (
        os.getenv("DELTA_ADMIN_PASSWORD_HASH", "").strip()
        or os.getenv("ADMIN_PASSWORD_HASH", "").strip()
    )


def admin_password_plain() -> str:
    return (
        os.getenv("DELTA_ADMIN_PASSWORD", "").strip()
        or os.getenv("ADMIN_PASSWORD", "").strip()
    )


def admin_auth_configured() -> bool:
    return bool(admin_username() and (admin_password_hash() or admin_password_plain()))


def verify_admin_credentials(username: str, password: str) -> bool:
    expected_username = admin_username()
    if not expected_username:
        return False
    username = (username or "").strip()
    password = password or ""
    if len(username) > MAX_ADMIN_CRED_LENGTH or len(password) > MAX_ADMIN_CRED_LENGTH:
        return False
    if not hmac.compare_digest(username, expected_username):
        return False

    configured_hash = admin_password_hash()
    if configured_hash:
        try:
            return check_password_hash(configured_hash, password)
        except ValueError:
            return False

    configured_plain = admin_password_plain()
    if configured_plain:
        return hmac.compare_digest(password, configured_plain)
    return False


def clear_admin_session() -> None:
    session.pop(ADMIN_SESSION_AUTH_KEY, None)
    session.pop(ADMIN_SESSION_USER_KEY, None)
    session.pop(ADMIN_SESSION_EXPIRES_AT_KEY, None)


def set_admin_session(username: str) -> None:
    now = int(time.time())
    session[ADMIN_SESSION_AUTH_KEY] = True
    session[ADMIN_SESSION_USER_KEY] = username
    session[ADMIN_SESSION_EXPIRES_AT_KEY] = now + ADMIN_SESSION_TTL_SECONDS
    session.permanent = True


def is_admin_session_authenticated() -> bool:
    if not session.get(ADMIN_SESSION_AUTH_KEY):
        clear_admin_session()
        return False

    expires_at_raw = session.get(ADMIN_SESSION_EXPIRES_AT_KEY)
    try:
        expires_at = int(expires_at_raw)
    except (TypeError, ValueError):
        clear_admin_session()
        return False

    now = int(time.time())
    if now >= expires_at:
        clear_admin_session()
        return False

    # Sliding expiration while the admin session is actively used.
    session[ADMIN_SESSION_EXPIRES_AT_KEY] = now + ADMIN_SESSION_TTL_SECONDS
    session.modified = True
    return True


def client_ip() -> str:
    x_forwarded_for = flask_request.headers.get("X-Forwarded-For", "")
    if x_forwarded_for:
        ip = x_forwarded_for.split(",")[0].strip()
        if ip:
            return ip[:64]
    remote_addr = (flask_request.remote_addr or "").strip()
    if remote_addr:
        return remote_addr[:64]
    return "unknown"


def login_rate_limit_keys(username: str) -> list[str]:
    ip = client_ip()
    username_key = (username or "").strip().lower()[:MAX_ADMIN_CRED_LENGTH] or "_"
    return [f"ip:{ip}", f"ip-user:{ip}:{username_key}"]


def auth_ui_style(is_admin: bool, is_error: bool = False) -> dict[str, str]:
    color = "#555555"
    if is_admin:
        color = "#0d7a28"
    elif is_error:
        color = "#a31621"
    return {"marginTop": "6px", "fontSize": "0.9rem", "fontWeight": "600", "color": color}


def auth_ui_payload(is_admin: bool) -> dict[str, object]:
    return {"is_admin": is_admin, "updated_at": int(time.time())}


def mode(series: pd.Series, default: str = "UNKNOWN") -> str:
    s = series.dropna().astype(str)
    if s.empty:
        return default
    m = s.mode()
    if m.empty:
        return default
    return str(m.iloc[0]).strip() or default


def opposing_party(party: str) -> str:
    party = str(party).strip().upper()
    if party == "REP":
        return "DEM"
    if party == "DEM":
        return "REP"
    if party in {"IND", "OTHER", "UNKNOWN"}:
        return party
    return "UNKNOWN"


def target_party_column(target_party_mode: str) -> str:
    if target_party_mode == TARGET_PARTY_MODE_MENTIONS:
        return "target_party_inferred_mentions"
    return "target_party_inferred_money"


def resolve_node_party(meta: dict, target_party_mode: str) -> str:
    if str(meta.get("node_type", "")) == "target":
        return str(meta.get(target_party_column(target_party_mode), meta.get("party", "UNKNOWN")))
    return str(meta.get("party", "UNKNOWN"))


def resolve_first_available_column(
    frame: pd.DataFrame,
    candidates: list[str],
    dataset_name: str,
    path: Path,
) -> str:
    for candidate in candidates:
        if candidate in frame.columns:
            return candidate

    available = ", ".join(frame.columns.astype(str).tolist())
    expected = ", ".join(candidates)
    raise ValueError(
        f"{dataset_name} at {path} is missing any of [{expected}]. "
        f"Available columns: {available}"
    )


def require_columns(
    frame: pd.DataFrame,
    required: list[str],
    dataset_name: str,
    path: Path,
) -> None:
    missing = [column for column in required if column not in frame.columns]
    if not missing:
        return

    available = ", ".join(frame.columns.astype(str).tolist())
    raise ValueError(
        f"{dataset_name} at {path} is missing required columns {missing}. "
        f"Available columns: {available}"
    )


def normalize_runtime_frames(
    edges: pd.DataFrame,
    nodes: pd.DataFrame,
    mentions: pd.DataFrame,
    harmonized: pd.DataFrame,
    paths: RuntimePaths,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    edges = edges.rename(
        columns={
            resolve_first_available_column(
                edges,
                ["canonical_entity", "canonical_entity_v1_2", "canonical_entity_v1_1"],
                "edges",
                paths.edges_path,
            ): CANONICAL_ENTITY_COL,
        }
    )
    nodes = nodes.rename(
        columns={
            resolve_first_available_column(
                nodes,
                ["canonical_entity", "canonical_entity_v1_2", "canonical_entity_v1_1"],
                "nodes",
                paths.nodes_path,
            ): CANONICAL_ENTITY_COL,
        }
    )
    mentions = mentions.rename(
        columns={
            resolve_first_available_column(
                mentions,
                ["canonical_entity", "canonical_entity_v1_2", "canonical_entity_v1_1"],
                "mentions",
                paths.mentions_path,
            ): CANONICAL_ENTITY_COL,
            resolve_first_available_column(
                mentions,
                ["is_target", "is_target_v1_2", "is_target_v1_1"],
                "mentions",
                paths.mentions_path,
            ): IS_TARGET_COL,
        }
    )

    require_columns(
        edges,
        [CANONICAL_ENTITY_COL, "sponsor_name", "mention_count", "ad_count", "party_mode", "tone_mode"],
        "edges",
        paths.edges_path,
    )
    require_columns(
        nodes,
        [CANONICAL_ENTITY_COL, "mention_count", "ad_count", "sponsor_count", "platform_count", "label_mode"],
        "nodes",
        paths.nodes_path,
    )
    require_columns(
        mentions,
        [CANONICAL_ENTITY_COL, IS_TARGET_COL, "platform", "ad_id", "sponsor_name", "party_std"],
        "mentions",
        paths.mentions_path,
    )
    require_columns(
        harmonized,
        ["platform", "ad_id", "spend_proxy"],
        "harmonized",
        paths.harmonized_path,
    )

    return edges, nodes, mentions, harmonized


def infer_target_party(frame: pd.DataFrame, weight_col: str) -> pd.Series:
    grouped = (
        frame.groupby([CANONICAL_ENTITY_COL, "sponsor_party"], as_index=False)[weight_col]
        .sum()
        .sort_values([CANONICAL_ENTITY_COL, weight_col], ascending=[True, False])
    )
    out: dict[str, str] = {}
    for target, g in grouped.groupby(CANONICAL_ENTITY_COL):
        top_weight = g[weight_col].max()
        winners = g[g[weight_col] == top_weight]["sponsor_party"].tolist()
        out[target] = opposing_party(winners[0]) if len(winners) == 1 else "UNKNOWN"
    return pd.Series(out, name="target_party_inferred")


def scale_series(values: pd.Series, lo: float = 8, hi: float = 42) -> pd.Series:
    if values.empty:
        return values
    vmin = float(values.min())
    vmax = float(values.max())
    if vmax == vmin:
        return pd.Series([(lo + hi) / 2.0] * len(values), index=values.index)
    return lo + (values - vmin) * (hi - lo) / (vmax - vmin)


def normalized_axis_positions(count: int) -> list[float]:
    if count <= 0:
        return []
    if count == 1:
        return [0.0]
    step = 2.0 / float(count - 1)
    return [1.0 - (idx * step) for idx in range(count)]


def normalize_positions(pos: dict[str, tuple[float, float] | list[float]]) -> dict[str, tuple[float, float]]:
    if not pos:
        return {}

    xs = [float(coords[0]) for coords in pos.values()]
    ys = [float(coords[1]) for coords in pos.values()]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    span_x = max(max_x - min_x, 1e-9)
    span_y = max(max_y - min_y, 1e-9)
    mid_x = (max_x + min_x) / 2.0
    mid_y = (max_y + min_y) / 2.0

    return {
        node: (
            (float(coords[0]) - mid_x) / span_x * 2.0,
            (float(coords[1]) - mid_y) / span_y * 2.0,
        )
        for node, coords in pos.items()
    }


def sorted_nodes_for_layout(
    graph: nx.DiGraph,
    base_graph: nx.DiGraph,
    node_type: str,
    target_party_mode: str = DEFAULT_TARGET_PARTY_MODE,
) -> list[str]:
    nodes = [node for node in graph.nodes() if base_graph.nodes[node]["node_type"] == node_type]
    if node_type == "sponsor":
        key_fn = lambda node: (-graph.out_degree(node), str(base_graph.nodes[node].get("party", "UNKNOWN")), node.lower())
    else:
        key_fn = lambda node: (
            -graph.in_degree(node),
            resolve_node_party(base_graph.nodes[node], target_party_mode),
            node.lower(),
        )
    return sorted(nodes, key=key_fn)


def compute_bipartite_positions(
    graph: nx.DiGraph,
    base_graph: nx.DiGraph,
    target_party_mode: str,
) -> dict[str, tuple[float, float]]:
    sponsors = sorted_nodes_for_layout(graph, base_graph, "sponsor", target_party_mode)
    targets = sorted_nodes_for_layout(graph, base_graph, "target", target_party_mode)
    positions: dict[str, tuple[float, float]] = {}

    if sponsors and targets:
        for node, y in zip(sponsors, normalized_axis_positions(len(sponsors))):
            positions[node] = (-1.0, y)
        for node, y in zip(targets, normalized_axis_positions(len(targets))):
            positions[node] = (1.0, y)
        return positions

    lone_nodes = sponsors or targets
    x = -0.2 if sponsors else 0.2
    for node, y in zip(lone_nodes, normalized_axis_positions(len(lone_nodes))):
        positions[node] = (x, y)
    return positions


def compute_layout_positions(
    graph: nx.DiGraph,
    base_graph: nx.DiGraph,
    layout_mode: str,
    target_party_mode: str,
) -> dict[str, tuple[float, float]]:
    if layout_mode == "bipartite":
        return compute_bipartite_positions(graph, base_graph, target_party_mode)

    layout_graph = nx.Graph(graph)
    if layout_mode == "radial":
        shells: list[list[str]] = []
        sponsors = sorted_nodes_for_layout(graph, base_graph, "sponsor", target_party_mode)
        targets = sorted_nodes_for_layout(graph, base_graph, "target", target_party_mode)
        if sponsors:
            shells.append(sponsors)
        if targets:
            shells.append(targets)
        return normalize_positions(nx.shell_layout(layout_graph, nlist=shells or [list(graph.nodes())]))

    try:
        k = min(0.9, max(0.24, 5.0 / math.sqrt(max(graph.number_of_nodes(), 1))))
        return normalize_positions(nx.spring_layout(layout_graph, seed=42, k=k))
    except ModuleNotFoundError as exc:
        if exc.name != "scipy":
            raise
        return normalize_positions(nx.random_layout(layout_graph, seed=42))


def build_visible_graph(
    runtime: dict[str, object],
    sponsor_party_filter: list[str],
    target_party_filter: list[str],
    target_party_mode: str,
    node_type_visible: list[str],
    min_edge_mentions: int,
    top_n_edges: int,
) -> tuple[nx.DiGraph, nx.DiGraph]:
    edges: pd.DataFrame = runtime["edges"]  # type: ignore[assignment]
    base_graph: nx.DiGraph = runtime["graph"]  # type: ignore[assignment]
    target_party_col = target_party_column(target_party_mode)

    ef = edges.copy()
    ef = ef[ef["mention_count"] >= int(min_edge_mentions)]
    if sponsor_party_filter:
        ef = ef[ef["sponsor_party"].isin(sponsor_party_filter)]
    if target_party_filter:
        ef = ef[ef[target_party_col].isin(target_party_filter)]
    ef = ef.sort_values("mention_count", ascending=False)
    ef = ef.head(int(top_n_edges))

    sponsors_visible = "sponsor" in node_type_visible
    targets_visible = "target" in node_type_visible

    graph = nx.DiGraph()
    for row in ef.itertuples(index=False):
        graph.add_edge(
            row.sponsor_name,
            row.canonical_entity,
            mention_count=int(row.mention_count),
            ad_count=int(row.ad_count),
            edge_attack_spend=float(row.edge_attack_spend),
            sponsor_party=str(row.sponsor_party),
            target_party_inferred=str(getattr(row, target_party_col)),
        )

    if not sponsors_visible or not targets_visible:
        to_drop: list[str] = []
        for node in graph.nodes():
            node_type = base_graph.nodes[node]["node_type"] if node in base_graph.nodes else "unknown"
            if node_type == "sponsor" and not sponsors_visible:
                to_drop.append(node)
            if node_type == "target" and not targets_visible:
                to_drop.append(node)
        if to_drop:
            graph.remove_nodes_from(to_drop)

    return graph, base_graph


def encode_node_search_value(node_name: str, node_type: str) -> str:
    return json.dumps({"name": node_name, "type": node_type}, separators=(",", ":"))


def decode_node_search_value(value: str | None) -> tuple[str, str] | None:
    if not value:
        return None
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return None
    node_name = decoded.get("name")
    node_type = decoded.get("type")
    if not node_name or node_type not in {"sponsor", "target"}:
        return None
    return str(node_name), str(node_type)


def build_node_search_options(
    graph: nx.DiGraph,
    base_graph: nx.DiGraph,
    target_party_mode: str,
) -> list[dict[str, str]]:
    options: list[dict[str, str]] = []
    for node_type in ["sponsor", "target"]:
        for node in sorted_nodes_for_layout(graph, base_graph, node_type, target_party_mode):
            meta = base_graph.nodes[node]
            party = resolve_node_party(meta, target_party_mode)
            options.append(
                {
                    "label": f"{node} ({node_type.title()}, {party})",
                    "value": encode_node_search_value(node, node_type),
                }
            )
    return options


def filter_visible_ad_records(
    runtime: dict[str, object],
    sponsor_party_filter: list[str],
    target_party_filter: list[str],
    target_party_mode: str,
    node_type_visible: list[str],
    min_edge_mentions: int,
    top_n_edges: int,
) -> pd.DataFrame:
    graph, _ = build_visible_graph(
        runtime=runtime,
        sponsor_party_filter=sponsor_party_filter,
        target_party_filter=target_party_filter,
        target_party_mode=target_party_mode,
        node_type_visible=node_type_visible,
        min_edge_mentions=min_edge_mentions,
        top_n_edges=top_n_edges,
    )
    if graph.number_of_edges() == 0:
        ad_records: pd.DataFrame = runtime["ad_records"]  # type: ignore[assignment]
        return ad_records.iloc[0:0].copy()

    visible_edges = pd.DataFrame(
        [(u, v) for u, v in graph.edges()],
        columns=["sponsor_name", CANONICAL_ENTITY_COL],
    ).drop_duplicates()
    ad_records = runtime["ad_records"]  # type: ignore[assignment]
    return ad_records.merge(visible_edges, on=["sponsor_name", CANONICAL_ENTITY_COL], how="inner")


def build_ad_table_rows(
    rows: pd.DataFrame,
    counterpart_label: str,
) -> list:
    grouped = (
        rows.groupby(["platform", "ad_id"], as_index=False)
        .agg(
            spend_proxy=("spend_proxy", "max"),
            counterpart=("counterpart", lambda s: ", ".join(sorted({str(v) for v in s if str(v).strip()}))),
            transcript=(
                "text_main",
                lambda s: next((str(v).strip() for v in s if str(v).strip()), ""),
            ),
        )
        .sort_values(["spend_proxy", "platform", "ad_id"], ascending=[False, True, True])
    )

    max_rows = 200
    rendered_rows = grouped.head(max_rows)
    table_rows = [
        html.Tr(
            [
                html.Td(str(row.platform)),
                html.Td(str(row.ad_id)),
                html.Td(f"${float(row.spend_proxy):,.2f}"),
                html.Td(str(row.counterpart)),
                html.Td(
                    html.Details(
                        [
                            html.Summary("Show transcript"),
                            html.Div(
                                str(row.transcript) if str(row.transcript).strip() else "No transcript available.",
                                style={"whiteSpace": "pre-wrap", "paddingTop": "8px", "maxWidth": "640px"},
                            ),
                        ]
                    )
                ),
            ]
        )
        for row in rendered_rows.itertuples(index=False)
    ]
    if len(grouped) > max_rows:
        table_rows.append(
            html.Tr(
                [
                    html.Td(
                        f"Showing first {max_rows:,} of {len(grouped):,} visible ads",
                        colSpan=5,
                        style={"fontStyle": "italic", "color": "#555"},
                    )
                ]
            )
        )
    return [
        html.Table(
            [
                html.Thead(
                    html.Tr(
                        [
                            html.Th("Platform"),
                            html.Th("Ad ID"),
                            html.Th("Spend"),
                            html.Th(counterpart_label),
                            html.Th("Transcript"),
                        ]
                    )
                ),
                html.Tbody(table_rows),
            ],
            style={"width": "100%", "borderCollapse": "collapse"},
        )
    ]


def build_selected_ad_details(
    runtime: dict[str, object],
    sponsor_party_filter: list[str],
    target_party_filter: list[str],
    target_party_mode: str,
    node_type_visible: list[str],
    min_edge_mentions: int,
    top_n_edges: int,
    selected_nodes: list[dict[str, str]] | None,
):
    selected_nodes = list(selected_nodes or [])
    if not selected_nodes:
        return html.Div(
            "Select a sponsor or target to inspect visible ad IDs.",
            style={"color": "#666"},
        )

    visible_ad_records = filter_visible_ad_records(
        runtime=runtime,
        sponsor_party_filter=sponsor_party_filter,
        target_party_filter=target_party_filter,
        target_party_mode=target_party_mode,
        node_type_visible=node_type_visible,
        min_edge_mentions=min_edge_mentions,
        top_n_edges=top_n_edges,
    )
    if visible_ad_records.empty:
        return html.Div(
            "No visible ad IDs match the current graph filters.",
            style={"color": "#666"},
        )

    panels: list = []
    for seed in selected_nodes:
        node_name = str(seed.get("name", "")).strip()
        node_type = str(seed.get("type", "")).strip()
        if not node_name or node_type not in {"sponsor", "target"}:
            continue

        if node_type == "sponsor":
            rows = visible_ad_records.loc[visible_ad_records["sponsor_name"] == node_name].copy()
            counterpart_label = "Targets"
            rows["counterpart"] = rows[CANONICAL_ENTITY_COL]
        else:
            rows = visible_ad_records.loc[visible_ad_records[CANONICAL_ENTITY_COL] == node_name].copy()
            counterpart_label = "Sponsors"
            rows["counterpart"] = rows["sponsor_name"]

        if rows.empty:
            panels.append(
                html.Details(
                    [
                        html.Summary(f"{node_name} ({node_type})"),
                        html.Div(
                            "No visible ad IDs for this selection under the current filters.",
                            style={"paddingTop": "8px", "color": "#666"},
                        ),
                    ]
                )
            )
            continue

        unique_ad_count = int(rows[["platform", "ad_id"]].drop_duplicates().shape[0])
        panels.append(
            html.Details(
                [
                    html.Summary(f"{node_name} ({node_type}) - {unique_ad_count:,} visible ad IDs"),
                    html.Div(
                        [
                            html.Div(
                                "Ad IDs below reflect the currently visible graph only.",
                                style={"padding": "8px 0", "color": "#555", "fontSize": "0.92rem"},
                            ),
                            html.Div(
                                build_ad_table_rows(rows, counterpart_label),
                                style={
                                    "maxHeight": "320px",
                                    "overflowY": "auto",
                                    "border": "1px solid #ddd",
                                    "borderRadius": "6px",
                                    "padding": "8px",
                                    "backgroundColor": "#fff",
                                },
                            ),
                        ],
                        style={"paddingTop": "8px"},
                    ),
                ]
            )
        )

    if not panels:
        return html.Div(
            "Select a sponsor or target to inspect visible ad IDs.",
            style={"color": "#666"},
        )
    return html.Div(panels, style={"display": "grid", "gap": "10px"})


def load_runtime_data(paths: RuntimePaths) -> dict[str, object]:
    edges = pd.read_csv(paths.edges_path).copy()
    nodes = pd.read_csv(paths.nodes_path).copy()
    mentions = pd.read_csv(paths.mentions_path, compression="gzip").copy()
    harmonized = pd.read_csv(
        paths.harmonized_path,
        compression="gzip",
        usecols=["platform", "ad_id", "spend_proxy", "text_main"],
    ).copy()
    edges, nodes, mentions, harmonized = normalize_runtime_frames(edges, nodes, mentions, harmonized, paths)

    sponsor_party = (
        mentions.groupby("sponsor_name", as_index=False)
        .agg(sponsor_party=("party_std", lambda s: mode(s, default="UNKNOWN")))
    )
    sponsor_party["sponsor_party"] = sponsor_party["sponsor_party"].replace("", "UNKNOWN")
    edges = edges.merge(sponsor_party, on="sponsor_name", how="left")
    edges["sponsor_party"] = edges["sponsor_party"].fillna("UNKNOWN")
    target_party_mentions = infer_target_party(edges, weight_col="mention_count")

    target_mentions = mentions[mentions[IS_TARGET_COL]].copy()
    target_mentions = target_mentions[
        ["platform", "ad_id", "sponsor_name", CANONICAL_ENTITY_COL, "party_std"]
    ].drop_duplicates()

    spend_ads = harmonized[["platform", "ad_id", "spend_proxy", "text_main"]].copy()
    spend_ads["spend_proxy"] = pd.to_numeric(spend_ads["spend_proxy"], errors="coerce").fillna(0.0)
    target_mentions = target_mentions.merge(spend_ads, on=["platform", "ad_id"], how="left")
    target_mentions["spend_proxy"] = target_mentions["spend_proxy"].fillna(0.0)
    target_mentions = target_mentions.merge(sponsor_party, on="sponsor_name", how="left")
    target_mentions["sponsor_party"] = target_mentions["sponsor_party"].fillna("UNKNOWN")

    target_spend_by_edge = target_mentions.drop_duplicates(
        subset=["sponsor_name", CANONICAL_ENTITY_COL, "platform", "ad_id"]
    )
    target_party_money = infer_target_party(target_spend_by_edge, weight_col="spend_proxy")
    edges["target_party_inferred_mentions"] = edges[CANONICAL_ENTITY_COL].map(target_party_mentions).fillna("UNKNOWN")
    edges["target_party_inferred_money"] = edges[CANONICAL_ENTITY_COL].map(target_party_money).fillna("UNKNOWN")
    edges["target_party_inferred"] = edges[target_party_column(DEFAULT_TARGET_PARTY_MODE)]

    sponsor_attack_spend = (
        target_mentions.drop_duplicates(subset=["sponsor_name", "platform", "ad_id"])
        .groupby("sponsor_name")["spend_proxy"]
        .sum()
    )

    target_received_spend = (
        target_mentions.drop_duplicates(subset=[CANONICAL_ENTITY_COL, "platform", "ad_id"])
        .groupby(CANONICAL_ENTITY_COL)["spend_proxy"]
        .sum()
    )

    edge_attack_spend = (
        target_spend_by_edge
        .groupby(["sponsor_name", CANONICAL_ENTITY_COL])["spend_proxy"]
        .sum()
        .rename("edge_attack_spend")
        .reset_index()
    )
    edges = edges.merge(edge_attack_spend, on=["sponsor_name", CANONICAL_ENTITY_COL], how="left")
    edges["edge_attack_spend"] = edges["edge_attack_spend"].fillna(0.0)

    target_node_meta = (
        nodes.groupby(CANONICAL_ENTITY_COL, as_index=False)
        .agg(
            target_label=("label_mode", lambda s: mode(s, default="UNKNOWN")),
            target_mentions=("mention_count", "max"),
            target_ads=("ad_count", "max"),
            target_sponsors=("sponsor_count", "max"),
            target_platforms=("platform_count", "max"),
        )
        .set_index(CANONICAL_ENTITY_COL)
    )

    full_graph = nx.DiGraph()
    for row in edges.itertuples(index=False):
        full_graph.add_edge(
            row.sponsor_name,
            row.canonical_entity,
            mention_count=int(row.mention_count),
            ad_count=int(row.ad_count),
            party_mode=str(row.party_mode),
            tone_mode=str(row.tone_mode),
            sponsor_party=str(row.sponsor_party),
            target_party_inferred_mentions=str(row.target_party_inferred_mentions),
            target_party_inferred_money=str(row.target_party_inferred_money),
            target_party_inferred=str(row.target_party_inferred),
            edge_attack_spend=float(row.edge_attack_spend),
        )

    for node in list(full_graph.nodes()):
        if node in target_node_meta.index:
            meta = target_node_meta.loc[node]
            full_graph.nodes[node]["node_type"] = "target"
            full_graph.nodes[node]["label_mode"] = str(meta["target_label"])
            full_graph.nodes[node]["target_party_inferred_mentions"] = str(target_party_mentions.get(node, "UNKNOWN"))
            full_graph.nodes[node]["target_party_inferred_money"] = str(target_party_money.get(node, "UNKNOWN"))
            full_graph.nodes[node]["party"] = str(target_party_money.get(node, "UNKNOWN"))
            full_graph.nodes[node]["mention_count"] = int(meta["target_mentions"])
            full_graph.nodes[node]["ad_count"] = int(meta["target_ads"])
            full_graph.nodes[node]["sponsor_count"] = int(meta["target_sponsors"])
            full_graph.nodes[node]["platform_count"] = int(meta["target_platforms"])
            full_graph.nodes[node]["target_received_spend"] = float(target_received_spend.get(node, 0.0))
            full_graph.nodes[node]["sponsor_attack_spend"] = 0.0
        else:
            full_graph.nodes[node]["node_type"] = "sponsor"
            full_graph.nodes[node]["label_mode"] = "SPONSOR"
            full_graph.nodes[node]["party"] = str(sponsor_party.set_index("sponsor_name").get("sponsor_party", pd.Series()).get(node, "UNKNOWN"))
            full_graph.nodes[node]["mention_count"] = 0
            full_graph.nodes[node]["ad_count"] = 0
            full_graph.nodes[node]["sponsor_count"] = 0
            full_graph.nodes[node]["platform_count"] = 0
            full_graph.nodes[node]["target_received_spend"] = 0.0
            full_graph.nodes[node]["sponsor_attack_spend"] = float(sponsor_attack_spend.get(node, 0.0))

    return {
        "edges": edges,
        "graph": full_graph,
        "ad_records": target_spend_by_edge.copy(),
        "sponsor_parties": sorted(edges["sponsor_party"].dropna().unique().tolist()),
        "target_parties": sorted(edges["target_party_inferred"].dropna().unique().tolist()),
        "target_parties_by_mode": {
            TARGET_PARTY_MODE_MENTIONS: sorted(edges["target_party_inferred_mentions"].dropna().unique().tolist()),
            TARGET_PARTY_MODE_MONEY: sorted(edges["target_party_inferred_money"].dropna().unique().tolist()),
        },
    }


def build_figure(
    runtime: dict[str, object],
    sponsor_party_filter: list[str],
    target_party_filter: list[str],
    target_party_mode: str,
    node_type_visible: list[str],
    layout_mode: str,
    color_mode: str,
    size_mode: str,
    interaction_mode: str,
    min_edge_mentions: int,
    top_n_edges: int,
    selected_nodes: list[dict[str, str]] | None,
) -> tuple[go.Figure, str]:
    graph, base_graph = build_visible_graph(
        runtime=runtime,
        sponsor_party_filter=sponsor_party_filter,
        target_party_filter=target_party_filter,
        target_party_mode=target_party_mode,
        node_type_visible=node_type_visible,
        min_edge_mentions=min_edge_mentions,
        top_n_edges=top_n_edges,
    )

    if graph.number_of_nodes() == 0:
        fig = go.Figure()
        fig.update_layout(
            template="plotly_white",
            title="No nodes match current filters",
            xaxis=dict(visible=False),
            yaxis=dict(visible=False),
        )
        return fig, "No visible nodes. Relax filters."

    pos = compute_layout_positions(graph, base_graph, layout_mode, target_party_mode)

    highlight_nodes: set[str] = set(graph.nodes())
    highlight_edges: set[tuple[str, str]] = set(graph.edges())
    active_seeds: list[dict[str, str]] = list(selected_nodes or [])
    if interaction_mode == "highlight" and active_seeds:
        active_seeds = active_seeds[:1]

    has_active_selection = False
    visible_seed_count = 0
    if interaction_mode in {"highlight", "accumulate"} and active_seeds:
        selected_nodes_union: set[str] = set()
        selected_edges_union: set[tuple[str, str]] = set()
        for seed in active_seeds:
            selected_name = seed.get("name")
            selected_type = seed.get("type")
            if not selected_name or selected_name not in graph.nodes():
                continue
            has_active_selection = True
            visible_seed_count += 1
            if selected_type == "sponsor":
                neighbors = set(graph.successors(selected_name))
                selected_nodes_union |= {selected_name} | neighbors
                selected_edges_union |= {(selected_name, n) for n in neighbors if graph.has_edge(selected_name, n)}
            elif selected_type == "target":
                neighbors = set(graph.predecessors(selected_name))
                selected_nodes_union |= {selected_name} | neighbors
                selected_edges_union |= {(n, selected_name) for n in neighbors if graph.has_edge(n, selected_name)}
        if has_active_selection:
            highlight_nodes = selected_nodes_union
            highlight_edges = selected_edges_union

    sponsor_out_degree = pd.Series({n: graph.out_degree(n) for n in graph.nodes()})
    target_in_degree = pd.Series({n: graph.in_degree(n) for n in graph.nodes()})

    size_raw: dict[str, float] = {}
    for n in graph.nodes():
        meta = base_graph.nodes[n]
        ntype = meta["node_type"]
        if size_mode == "topology":
            if ntype == "sponsor":
                size_raw[n] = float(sponsor_out_degree.get(n, 0))
            else:
                size_raw[n] = float(target_in_degree.get(n, 0))
        else:
            if ntype == "sponsor":
                size_raw[n] = float(meta.get("sponsor_attack_spend", 0.0))
            else:
                size_raw[n] = float(meta.get("target_received_spend", 0.0))

    size_series = pd.Series(size_raw)
    size_scaled = scale_series(size_series, lo=10, hi=46).to_dict()

    edge_x_dim, edge_y_dim, edge_x_hi, edge_y_hi = [], [], [], []
    edge_hover_x, edge_hover_y, edge_hover_text = [], [], []
    for u, v in graph.edges():
        x0, y0 = pos[u]
        x1, y1 = pos[v]
        edge_meta = graph.edges[u, v]
        is_hi = (u, v) in highlight_edges
        if interaction_mode in {"highlight", "accumulate"} and has_active_selection and not is_hi:
            edge_x_dim.extend([x0, x1, None])
            edge_y_dim.extend([y0, y1, None])
        else:
            edge_x_hi.extend([x0, x1, None])
            edge_y_hi.extend([y0, y1, None])

        if not has_active_selection or is_hi:
            # Hover anchor at edge midpoint so edge details are discoverable.
            edge_hover_x.append((x0 + x1) / 2.0)
            edge_hover_y.append((y0 + y1) / 2.0)
            edge_hover_text.append(
                f"{u} -> {v}<br>"
                f"attacks (mention_count)={int(edge_meta.get('mention_count', 0)):,}<br>"
                f"ads={int(edge_meta.get('ad_count', 0)):,}<br>"
                f"attack_spend=${float(edge_meta.get('edge_attack_spend', 0.0)):,.2f}"
            )

    edge_dim_trace = go.Scatter(
        x=edge_x_dim,
        y=edge_y_dim,
        mode="lines",
        hoverinfo="none",
        line=dict(width=0.6, color="rgba(120,120,120,0.08)"),
        showlegend=False,
    )
    edge_hi_trace = go.Scatter(
        x=edge_x_hi,
        y=edge_y_hi,
        mode="lines",
        hoverinfo="none",
        line=dict(width=0.9, color="rgba(120,120,120,0.42)"),
        showlegend=False,
    )
    edge_hover_trace = go.Scatter(
        x=edge_hover_x,
        y=edge_hover_y,
        mode="markers",
        hoverinfo="text",
        text=edge_hover_text,
        showlegend=False,
        marker=dict(
            size=10,
            color="rgba(0,0,0,0.001)",
            line=dict(width=0),
        ),
    )

    sponsor_x, sponsor_y, sponsor_size, sponsor_color, sponsor_text, sponsor_cd, sponsor_opacity = ([] for _ in range(7))
    target_x, target_y, target_size, target_color, target_text, target_cd, target_opacity = ([] for _ in range(7))

    for n in graph.nodes():
        meta = base_graph.nodes[n]
        ntype = meta["node_type"]
        x, y = pos[n]
        is_hi_node = n in highlight_nodes
        opacity = 0.98 if (interaction_mode not in {"highlight", "accumulate"} or not has_active_selection or is_hi_node) else 0.14

        if color_mode == "party":
            party = resolve_node_party(meta, target_party_mode)
            if ntype == "sponsor":
                color = PARTY_COLORS.get(party, PARTY_COLORS["UNKNOWN"])
            else:
                color = TARGET_PARTY_COLORS.get(party, TARGET_PARTY_COLORS["UNKNOWN"])
        else:
            color = LABEL_COLORS.get(str(meta.get("label_mode", "UNKNOWN")), LABEL_COLORS["UNKNOWN"])

        if ntype == "sponsor":
            sponsor_x.append(x)
            sponsor_y.append(y)
            sponsor_size.append(float(size_scaled.get(n, 12)))
            sponsor_color.append(color)
            sponsor_opacity.append(opacity)
            sponsor_cd.append([n, "sponsor"])
            sponsor_text.append(
                f"sponsor={n}<br>"
                f"party={resolve_node_party(meta, target_party_mode)}<br>"
                f"outgoing_edges={int(sponsor_out_degree.get(n, 0)):,}<br>"
                f"attack_spend_total=${float(meta.get('sponsor_attack_spend', 0.0)):,.2f}"
            )
        else:
            target_x.append(x)
            target_y.append(y)
            target_size.append(float(size_scaled.get(n, 12)))
            target_color.append(color)
            target_opacity.append(opacity)
            target_cd.append([n, "target"])
            target_text.append(
                f"target={n}<br>"
                f"label={meta.get('label_mode','UNKNOWN')}<br>"
                f"inferred_party ({target_party_mode})={resolve_node_party(meta, target_party_mode)}<br>"
                f"incoming_edges={int(target_in_degree.get(n, 0)):,}<br>"
                f"received_attack_spend=${float(meta.get('target_received_spend', 0.0)):,.2f}"
            )

    sponsor_trace = go.Scatter(
        x=sponsor_x,
        y=sponsor_y,
        mode="markers",
        name="Sponsors",
        customdata=sponsor_cd,
        hoverinfo="text",
        text=sponsor_text,
        marker=dict(size=sponsor_size, color=sponsor_color, line=dict(width=0.8, color="white"), opacity=sponsor_opacity),
    )

    target_trace = go.Scatter(
        x=target_x,
        y=target_y,
        mode="markers",
        name="Targets",
        customdata=target_cd,
        hoverinfo="text",
        text=target_text,
        marker=dict(size=target_size, color=target_color, line=dict(width=0.8, color="white"), opacity=target_opacity),
    )

    # Strong role cue independent of color:
    # sponsors are square markers, targets are circles.
    sponsor_trace.marker.symbol = "square"
    sponsor_trace.marker.line = dict(width=1.6, color="#111111")
    target_trace.marker.symbol = "circle"
    target_trace.marker.line = dict(width=0.9, color="#ffffff")

    fig = go.Figure(data=[edge_dim_trace, edge_hi_trace, edge_hover_trace, sponsor_trace, target_trace])
    fig.update_layout(
        template="plotly_white",
        title=f"Week 3 Attack-Target Interactive Graph ({graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges)",
        hovermode="closest",
        clickmode="event",
        margin=dict(l=20, r=20, t=56, b=20),
        legend=dict(orientation="h", yanchor="top", y=-0.08, x=0),
        xaxis=dict(showgrid=False, zeroline=False, visible=False),
        yaxis=dict(showgrid=False, zeroline=False, visible=False),
    )

    status = (
        f"Visible: {graph.number_of_nodes():,} nodes, {graph.number_of_edges():,} edges | "
        f"Mode: target_party={target_party_mode}, layout={layout_mode}, color={color_mode}, size={size_mode}, interaction={interaction_mode}"
    )
    if interaction_mode in {"highlight", "accumulate"} and has_active_selection:
        if interaction_mode == "accumulate":
            status += f" | Active seed nodes: {visible_seed_count}"
        else:
            seed = active_seeds[0]
            status += f" | Highlight selection: {seed.get('name')} ({seed.get('type')})"
    return fig, status


PATHS = resolve_runtime_paths()
RUNTIME = load_runtime_data(PATHS)
BASE_PATH = PATHS.base_path
DEFAULT_NODE_TYPES = ["sponsor", "target"]
DEFAULT_MIN_EDGE_MENTIONS = 2
DEFAULT_TOP_N_EDGES = 900
DEFAULT_VISIBLE_GRAPH, DEFAULT_BASE_GRAPH = build_visible_graph(
    runtime=RUNTIME,
    sponsor_party_filter=RUNTIME["sponsor_parties"],  # type: ignore[arg-type]
    target_party_filter=RUNTIME["target_parties_by_mode"][DEFAULT_TARGET_PARTY_MODE],  # type: ignore[index]
    target_party_mode=DEFAULT_TARGET_PARTY_MODE,
    node_type_visible=DEFAULT_NODE_TYPES,
    min_edge_mentions=DEFAULT_MIN_EDGE_MENTIONS,
    top_n_edges=DEFAULT_TOP_N_EDGES,
)
DEFAULT_NODE_SEARCH_OPTIONS = build_node_search_options(
    DEFAULT_VISIBLE_GRAPH,
    DEFAULT_BASE_GRAPH,
    DEFAULT_TARGET_PARTY_MODE,
)

app = dash.Dash(
    __name__,
    requests_pathname_prefix=BASE_PATH,
    routes_pathname_prefix=BASE_PATH,
)
app.title = "Week 3 Attack-Target Graph"
server = app.server
server.secret_key = (
    os.getenv("DELTA_SECRET_KEY", "").strip()
    or os.getenv("SECRET_KEY", "").strip()
    or server.secret_key
    or secrets.token_hex(32)
)
server.config.update(
    SESSION_COOKIE_HTTPONLY=True,
    SESSION_COOKIE_SAMESITE="Lax",
    SESSION_COOKIE_SECURE=ADMIN_COOKIE_SECURE,
    PERMANENT_SESSION_LIFETIME=timedelta(seconds=ADMIN_SESSION_TTL_SECONDS),
)
EDGE_Q95 = int(pd.Series(RUNTIME["edges"]["mention_count"]).quantile(0.95))  # type: ignore[index]
SLIDER_MAX = max(2, EDGE_Q95)
SLIDER_STEP = 5 if SLIDER_MAX >= 20 else 1
SLIDER_MARKS = {v: str(v) for v in range(2, SLIDER_MAX + 1, SLIDER_STEP)}
if SLIDER_MAX not in SLIDER_MARKS:
    SLIDER_MARKS[SLIDER_MAX] = str(SLIDER_MAX)

app.layout = html.Div(
    [
        dcc.Location(id="page-location", refresh=False),
        dcc.Store(id="admin-auth-store", data={"is_admin": False, "updated_at": 0}),
        html.Div(
            [
                html.Div(
                    [
                        html.Strong("Admin Mode"),
                        dcc.Input(
                            id="admin-username-input",
                            type="text",
                            placeholder="Admin username",
                            maxLength=MAX_ADMIN_CRED_LENGTH,
                            autoComplete="username",
                            style={"minWidth": "180px"},
                        ),
                        dcc.Input(
                            id="admin-password-input",
                            type="password",
                            placeholder="Admin password",
                            maxLength=MAX_ADMIN_CRED_LENGTH,
                            autoComplete="current-password",
                            style={"minWidth": "220px"},
                        ),
                        html.Button("Enter Admin Mode", id="admin-login-button", n_clicks=0),
                        html.Button(
                            "Exit Admin Mode",
                            id="admin-logout-button",
                            n_clicks=0,
                            style={"display": "none"},
                        ),
                    ],
                    style={"display": "flex", "alignItems": "center", "gap": "8px", "flexWrap": "wrap"},
                ),
                html.Div(
                    id="admin-auth-status",
                    children="Admin mode is off. Log in to view ad IDs.",
                    style=auth_ui_style(is_admin=False, is_error=False),
                ),
            ],
            style={
                "marginBottom": "12px",
                "padding": "10px",
                "border": "1px solid #d7d7d7",
                "borderRadius": "8px",
                "backgroundColor": "#fafafa",
            },
        ),
        html.H3("Week 3 Attack-Target Graph (Interactive)", style={"margin": "0 0 12px 0"}),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Sponsor Party Filter"),
                        dcc.Dropdown(
                            id="sponsor-party-filter",
                            options=[{"label": p, "value": p} for p in RUNTIME["sponsor_parties"]],
                            value=RUNTIME["sponsor_parties"],
                            multi=True,
                        ),
                    ],
                    style={"width": "24%", "display": "inline-block", "paddingRight": "1%"},
                ),
                html.Div(
                    [
                        html.Label("Target Party Inference"),
                        dcc.RadioItems(
                            id="target-party-mode",
                            options=[
                                {"label": " Money", "value": TARGET_PARTY_MODE_MONEY},
                                {"label": " Mentions", "value": TARGET_PARTY_MODE_MENTIONS},
                            ],
                            value=DEFAULT_TARGET_PARTY_MODE,
                            inline=True,
                        ),
                    ],
                    style={"width": "24%", "display": "inline-block", "paddingRight": "1%"},
                ),
                html.Div(
                    [
                        html.Label("Target Party Filter (Inferred)"),
                        dcc.Dropdown(
                            id="target-party-filter",
                            options=[
                                {"label": p, "value": p}
                                for p in RUNTIME["target_parties_by_mode"][DEFAULT_TARGET_PARTY_MODE]
                            ],
                            value=RUNTIME["target_parties_by_mode"][DEFAULT_TARGET_PARTY_MODE],
                            multi=True,
                        ),
                    ],
                    style={"width": "24%", "display": "inline-block", "paddingRight": "1%"},
                ),
                html.Div(
                    [
                        html.Label("Show Node Types"),
                        dcc.Checklist(
                            id="node-type-visible",
                            options=[
                                {"label": " Sponsors", "value": "sponsor"},
                                {"label": " Targets", "value": "target"},
                            ],
                            value=["sponsor", "target"],
                            inline=True,
                        ),
                    ],
                    style={"width": "16%", "display": "inline-block", "paddingRight": "1%"},
                ),
                html.Div(
                    [
                        html.Label("Min Edge Mentions"),
                        dcc.Slider(
                            id="min-edge-mentions",
                            min=2,
                            max=SLIDER_MAX,
                            step=1,
                            value=2,
                            marks=SLIDER_MARKS,
                            tooltip={"placement": "bottom", "always_visible": False},
                        ),
                    ],
                    style={"width": "34%", "display": "inline-block"},
                ),
            ],
            style={"marginBottom": "10px"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Search Sponsor Party"),
                        dcc.Dropdown(
                            id="sponsor-party-search",
                            options=[{"label": p, "value": p} for p in RUNTIME["sponsor_parties"]],
                            placeholder="Type to isolate a sponsor party",
                            clearable=True,
                        ),
                    ],
                    style={"width": "20%", "display": "inline-block", "paddingRight": "1%"},
                ),
                html.Div(
                    [
                        html.Label("Search Target Party"),
                        dcc.Dropdown(
                            id="target-party-search",
                            options=[
                                {"label": p, "value": p}
                                for p in RUNTIME["target_parties_by_mode"][DEFAULT_TARGET_PARTY_MODE]
                            ],
                            placeholder="Type to isolate a target party",
                            clearable=True,
                        ),
                    ],
                    style={"width": "20%", "display": "inline-block", "paddingRight": "1%"},
                ),
                html.Div(
                    [
                        html.Label("Search Visible Node"),
                        dcc.Dropdown(
                            id="node-search",
                            options=DEFAULT_NODE_SEARCH_OPTIONS,
                            placeholder="Type a sponsor or target name",
                            clearable=True,
                        ),
                    ],
                    style={"width": "58%", "display": "inline-block"},
                ),
            ],
            style={"marginBottom": "10px"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Layout"),
                        dcc.RadioItems(
                            id="layout-mode",
                            options=[
                                {"label": " Bipartite", "value": "bipartite"},
                                {"label": " Force Directed", "value": "spring"},
                                {"label": " Radial", "value": "radial"},
                            ],
                            value="spring",
                            inline=True,
                        ),
                    ],
                    style={"width": "34%", "display": "inline-block", "paddingRight": "2%"},
                ),
                html.Div(
                    [
                        html.Label("Color Mode"),
                        dcc.RadioItems(
                            id="color-mode",
                            options=[
                                {"label": " Party Colors", "value": "party"},
                                {"label": " Entity Label Colors", "value": "entity_label"},
                            ],
                            value="party",
                            inline=True,
                        ),
                    ],
                    style={"width": "22%", "display": "inline-block", "paddingRight": "2%"},
                ),
                html.Div(
                    [
                        html.Label("Size Mode"),
                        dcc.RadioItems(
                            id="size-mode",
                            options=[
                                {"label": " Topology", "value": "topology"},
                                {"label": " Money", "value": "money"},
                            ],
                            value="topology",
                            inline=True,
                        ),
                    ],
                    style={"width": "18%", "display": "inline-block", "paddingRight": "2%"},
                ),
                html.Div(
                    [
                        html.Label("Interaction Mode"),
                        dcc.RadioItems(
                            id="interaction-mode",
                            options=[
                                {"label": " Accumulate Highlight", "value": "accumulate"},
                                {"label": " Neighbor Highlight", "value": "highlight"},
                            ],
                            value="highlight",
                            inline=True,
                        ),
                    ],
                    style={"width": "24%", "display": "inline-block"},
                ),
            ],
            style={"marginBottom": "10px"},
        ),
        html.Div(
            [
                html.Div(
                    [
                        html.Label("Top N Edges"),
                        dcc.Input(id="top-n-edges", type="number", min=50, max=5000, step=50, value=900),
                        html.Button("Clear Selection", id="clear-selection", n_clicks=0, style={"marginLeft": "8px"}),
                    ],
                    style={"width": "100%", "display": "inline-block"},
                ),
            ],
            style={"marginBottom": "10px"},
        ),
        dcc.Store(id="selected-seeds", data=[]),
        html.Div(id="status-text", style={"marginBottom": "8px", "fontWeight": "600"}),
        dcc.Graph(id="attack-target-graph", style={"height": "80vh"}, config={"displaylogo": False}),
        html.Div(
            [
                html.H4("Selected Ad IDs", style={"margin": "12px 0 8px 0"}),
                html.Div(id="selected-ad-ids-panel"),
            ],
            id="selected-ad-ids-container",
            style={"display": "none", "marginTop": "8px"},
        ),
        html.Div(
            "Bipartite layout places sponsors on the left and targets on the right. "
            "Target party inference can be based on money or mentions; the default is money. "
            "Party search fields isolate a single sponsor or target party. "
            "Node search only lists nodes currently visible under the active filters and selects them like a click. "
            "Accumulate mode: each click adds that node's neighborhood to the highlighted network (click again to remove). "
            "Neighbor Highlight mode: one selected node at a time. Visual cue: sponsors are squares, targets are circles.",
            style={"color": "#555", "fontSize": "0.9rem", "marginTop": "6px"},
        ),
    ],
    style={"padding": "12px 16px"},
)


def apply_node_selection(node_name: str, node_type: str, interaction_mode: str, selected_seeds):
    selected_seeds = list(selected_seeds or [])
    if interaction_mode == "accumulate":
        exists = any(seed.get("name") == node_name and seed.get("type") == node_type for seed in selected_seeds)
        if exists:
            return [
                seed
                for seed in selected_seeds
                if not (seed.get("name") == node_name and seed.get("type") == node_type)
            ]
        selected_seeds.append({"name": node_name, "type": node_type})
        return selected_seeds

    if selected_seeds and selected_seeds[0].get("name") == node_name and selected_seeds[0].get("type") == node_type:
        return []
    return [{"name": node_name, "type": node_type}]


@app.callback(
    Output("admin-auth-store", "data"),
    Output("admin-auth-status", "children"),
    Output("admin-auth-status", "style"),
    Output("admin-password-input", "value"),
    Output("admin-login-button", "style"),
    Output("admin-logout-button", "style"),
    Input("page-location", "pathname"),
    Input("admin-login-button", "n_clicks"),
    Input("admin-logout-button", "n_clicks"),
    State("admin-username-input", "value"),
    State("admin-password-input", "value"),
)
def update_admin_auth_state(
    _pathname,
    _login_clicks,
    _logout_clicks,
    username_value,
    password_value,
):
    login_button_style = {}
    logout_button_style = {"display": "none"}
    trigger = ctx.triggered_id

    if trigger == "admin-logout-button":
        clear_admin_session()
        return (
            auth_ui_payload(is_admin=False),
            "Admin mode is off. Log in to view ad IDs.",
            auth_ui_style(is_admin=False, is_error=False),
            "",
            login_button_style,
            logout_button_style,
        )

    if trigger == "admin-login-button":
        username = (username_value or "").strip()
        password = password_value or ""
        if not admin_auth_configured():
            return (
                auth_ui_payload(is_admin=False),
                "Admin login is not configured. Set DELTA_ADMIN_USERNAME and DELTA_ADMIN_PASSWORD_HASH.",
                auth_ui_style(is_admin=False, is_error=True),
                "",
                login_button_style,
                logout_button_style,
            )

        keys = login_rate_limit_keys(username)
        wait_seconds = LOGIN_ATTEMPT_LIMITER.check_wait_seconds(keys)
        if wait_seconds > 0:
            return (
                auth_ui_payload(is_admin=False),
                f"Too many login attempts. Try again in {wait_seconds} seconds.",
                auth_ui_style(is_admin=False, is_error=True),
                "",
                login_button_style,
                logout_button_style,
            )

        if verify_admin_credentials(username, password):
            LOGIN_ATTEMPT_LIMITER.register_success(keys)
            set_admin_session(username)
            return (
                auth_ui_payload(is_admin=True),
                f"Admin mode enabled for {username}.",
                auth_ui_style(is_admin=True, is_error=False),
                "",
                {"display": "none"},
                {},
            )

        lock_seconds = LOGIN_ATTEMPT_LIMITER.register_failure(keys)
        if ADMIN_FAILED_DELAY_SECONDS > 0:
            time.sleep(ADMIN_FAILED_DELAY_SECONDS)
        message = "Invalid username or password."
        if lock_seconds > 0:
            message = f"Too many failed attempts. Login locked for {lock_seconds} seconds."
        return (
            auth_ui_payload(is_admin=False),
            message,
            auth_ui_style(is_admin=False, is_error=True),
            "",
            login_button_style,
            logout_button_style,
        )

    if is_admin_session_authenticated():
        username = str(session.get(ADMIN_SESSION_USER_KEY, admin_username() or "admin"))
        return (
            auth_ui_payload(is_admin=True),
            f"Admin mode enabled for {username}.",
            auth_ui_style(is_admin=True, is_error=False),
            "",
            {"display": "none"},
            {},
        )

    clear_admin_session()
    return (
        auth_ui_payload(is_admin=False),
        "Admin mode is off. Log in to view ad IDs.",
        auth_ui_style(is_admin=False, is_error=False),
        "",
        login_button_style,
        logout_button_style,
    )


@app.callback(
    Output("selected-seeds", "data"),
    Input("attack-target-graph", "clickData"),
    State("interaction-mode", "value"),
    State("selected-seeds", "data"),
)
def update_selected_seeds(click_data, interaction_mode, selected_seeds):
    if not click_data or "points" not in click_data or not click_data["points"]:
        return selected_seeds or []
    customdata = click_data["points"][0].get("customdata")
    if not customdata or len(customdata) != 2:
        return selected_seeds or []

    node_name, node_type = customdata[0], customdata[1]
    return apply_node_selection(node_name, node_type, interaction_mode, selected_seeds)


@app.callback(
    Output("sponsor-party-filter", "value"),
    Output("sponsor-party-search", "value"),
    Input("sponsor-party-search", "value"),
    prevent_initial_call=True,
)
def quick_select_sponsor_party(party_value):
    if not party_value:
        raise PreventUpdate
    return [party_value], None


@app.callback(
    Output("target-party-filter", "value", allow_duplicate=True),
    Output("target-party-search", "value", allow_duplicate=True),
    Input("target-party-search", "value"),
    prevent_initial_call=True,
)
def quick_select_target_party(party_value):
    if not party_value:
        raise PreventUpdate
    return [party_value], None


@app.callback(
    Output("target-party-filter", "options"),
    Output("target-party-filter", "value"),
    Output("target-party-search", "options"),
    Output("target-party-search", "value"),
    Input("target-party-mode", "value"),
)
def sync_target_party_controls(target_party_mode):
    mode = target_party_mode or DEFAULT_TARGET_PARTY_MODE
    parties = RUNTIME["target_parties_by_mode"].get(mode, RUNTIME["target_parties_by_mode"][DEFAULT_TARGET_PARTY_MODE])  # type: ignore[index]
    options = [{"label": party, "value": party} for party in parties]
    return options, parties, options, None


@app.callback(
    Output("node-search", "options"),
    Input("sponsor-party-filter", "value"),
    Input("target-party-filter", "value"),
    Input("target-party-mode", "value"),
    Input("node-type-visible", "value"),
    Input("min-edge-mentions", "value"),
    Input("top-n-edges", "value"),
)
def update_node_search_options(
    sponsor_party_filter,
    target_party_filter,
    target_party_mode,
    node_type_visible,
    min_edge_mentions,
    top_n_edges,
):
    graph, base_graph = build_visible_graph(
        runtime=RUNTIME,
        sponsor_party_filter=sponsor_party_filter or [],
        target_party_filter=target_party_filter or [],
        target_party_mode=target_party_mode or DEFAULT_TARGET_PARTY_MODE,
        node_type_visible=node_type_visible or [],
        min_edge_mentions=int(min_edge_mentions or DEFAULT_MIN_EDGE_MENTIONS),
        top_n_edges=int(top_n_edges or DEFAULT_TOP_N_EDGES),
    )
    return build_node_search_options(graph, base_graph, target_party_mode or DEFAULT_TARGET_PARTY_MODE)


@app.callback(
    Output("selected-seeds", "data", allow_duplicate=True),
    Output("node-search", "value"),
    Input("node-search", "value"),
    State("interaction-mode", "value"),
    State("selected-seeds", "data"),
    prevent_initial_call=True,
)
def select_node_from_search(node_search_value, interaction_mode, selected_seeds):
    decoded = decode_node_search_value(node_search_value)
    if decoded is None:
        raise PreventUpdate
    node_name, node_type = decoded
    return apply_node_selection(node_name, node_type, interaction_mode, selected_seeds), None


@app.callback(
    Output("attack-target-graph", "clickData", allow_duplicate=True),
    Input("selected-seeds", "data"),
    prevent_initial_call=True,
)
def reset_click_data_after_selection(_selected_seeds):
    # Force the next click (even on the same node) to produce a fresh event.
    return None


@app.callback(
    Output("selected-seeds", "data", allow_duplicate=True),
    Output("attack-target-graph", "clickData"),
    Input("clear-selection", "n_clicks"),
    prevent_initial_call=True,
)
def clear_selection(_n_clicks):
    return [], None


@app.callback(
    Output("selected-ad-ids-container", "style"),
    Output("selected-ad-ids-panel", "children"),
    Input("admin-auth-store", "data"),
    Input("sponsor-party-filter", "value"),
    Input("target-party-filter", "value"),
    Input("target-party-mode", "value"),
    Input("node-type-visible", "value"),
    Input("min-edge-mentions", "value"),
    Input("top-n-edges", "value"),
    Input("selected-seeds", "data"),
)
def update_selected_ad_ids_panel(
    _admin_auth_state,
    sponsor_party_filter,
    target_party_filter,
    target_party_mode,
    node_type_visible,
    min_edge_mentions,
    top_n_edges,
    selected_seeds,
):
    if not is_admin_session_authenticated():
        return {"display": "none", "marginTop": "8px"}, []

    panel = build_selected_ad_details(
        runtime=RUNTIME,
        sponsor_party_filter=sponsor_party_filter or [],
        target_party_filter=target_party_filter or [],
        target_party_mode=target_party_mode or DEFAULT_TARGET_PARTY_MODE,
        node_type_visible=node_type_visible or [],
        min_edge_mentions=int(min_edge_mentions or DEFAULT_MIN_EDGE_MENTIONS),
        top_n_edges=int(top_n_edges or DEFAULT_TOP_N_EDGES),
        selected_nodes=selected_seeds or [],
    )
    return {"display": "block", "marginTop": "8px"}, panel


@app.callback(
    Output("attack-target-graph", "figure"),
    Output("status-text", "children"),
    Input("sponsor-party-filter", "value"),
    Input("target-party-filter", "value"),
    Input("target-party-mode", "value"),
    Input("node-type-visible", "value"),
    Input("layout-mode", "value"),
    Input("color-mode", "value"),
    Input("size-mode", "value"),
    Input("interaction-mode", "value"),
    Input("min-edge-mentions", "value"),
    Input("top-n-edges", "value"),
    Input("selected-seeds", "data"),
)
def update_graph(
    sponsor_party_filter,
    target_party_filter,
    target_party_mode,
    node_type_visible,
    layout_mode,
    color_mode,
    size_mode,
    interaction_mode,
    min_edge_mentions,
    top_n_edges,
    selected_seeds,
):
    fig, status = build_figure(
        runtime=RUNTIME,
        sponsor_party_filter=sponsor_party_filter or [],
        target_party_filter=target_party_filter or [],
        target_party_mode=target_party_mode or DEFAULT_TARGET_PARTY_MODE,
        node_type_visible=node_type_visible or [],
        layout_mode=layout_mode or "spring",
        color_mode=color_mode or "party",
        size_mode=size_mode or "topology",
        interaction_mode=interaction_mode or "highlight",
        min_edge_mentions=int(min_edge_mentions or 2),
        top_n_edges=int(top_n_edges or 900),
        selected_nodes=selected_seeds or [],
    )
    return fig, status


if __name__ == "__main__":
    app.run_server(
        debug=True,
        host=os.getenv("DELTA_HOST", "127.0.0.1"),
        port=int(os.getenv("DELTA_PORT", "8050")),
    )
