from __future__ import annotations

import json
import re
import shutil
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

_STORE_LOCK = Lock()
# The words of an item, which `flask portfolio-copy` brings over from the seed.
COPY_FIELDS = ("title", "line", "short_desc", "long_desc", "image_alt")

# What a work is, for the homepage's caption and the screen reader ("Title, Kind, line").
KINDS = ("about", "research", "engineering", "product", "play")   # "about": the page about the person, not a work
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def normalize_kind(value) -> str:
    """One of KINDS, or "" when missing or unknown (older items carry no kind)."""
    kind = str(value or "").strip().lower()
    return kind if kind in KINDS else ""


@dataclass
class PortfolioItem:
    id: str
    title: str
    short_desc: str
    long_desc: str
    image_full: str
    image_thumb: str
    image_alt: str
    sort_order: int
    is_published: bool = True
    created_at: str = ""
    updated_at: str = ""
    # The homepage (templates/home.html): what kind of work it is, one short plain-text
    # sentence, and where the work lives (a site path like /zaychess or an https:// URL).
    # Defaults keep items saved before these fields existed loading as they were.
    kind: str = ""
    line: str = ""
    href: str = ""

    @classmethod
    def from_dict(cls, data: dict) -> "PortfolioItem":
        return cls(
            id=str(data.get("id", "")),
            title=str(data.get("title", "")),
            short_desc=str(data.get("short_desc", "")),
            long_desc=str(data.get("long_desc", "")),
            image_full=str(data.get("image_full", "")),
            image_thumb=str(data.get("image_thumb", "")),
            image_alt=str(data.get("image_alt", "")),
            sort_order=int(data.get("sort_order", 0)),
            is_published=bool(data.get("is_published", True)),
            created_at=str(data.get("created_at", "")),
            updated_at=str(data.get("updated_at", "")),
            kind=normalize_kind(data.get("kind")),
            line=str(data.get("line") or ""),
            href=str(data.get("href") or ""),
        )

    def to_dict(self) -> dict:
        return asdict(self)


class PortfolioStore:
    # The live file is the server's own (written by /admin/portfolio, never tracked); a missing
    # one starts as a copy of the seed that ships in the repository.
    def __init__(self, data_path: str, seed_path: str | None = None) -> None:
        self._path = Path(data_path)
        self._seed = Path(seed_path) if seed_path else None
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def list_items(self, include_unpublished: bool = False) -> list[dict]:
        data = self._read()
        items = [PortfolioItem.from_dict(item) for item in data.get("items", [])]
        if not include_unpublished:
            items = [item for item in items if item.is_published]
        items.sort(key=lambda item: item.sort_order)
        return [item.to_dict() for item in items]

    def get_item(self, item_id: str) -> dict | None:
        data = self._read()
        for item in data.get("items", []):
            if item.get("id") == item_id:
                return PortfolioItem.from_dict(item).to_dict()
        return None

    def create_item(self, payload: dict) -> dict:
        with _STORE_LOCK:
            data = self._read()
            items = data.get("items", [])

            sort_order = payload.get("sort_order")
            if sort_order is None:
                sort_order = self._next_sort_order(items)

            now = _timestamp()
            item = PortfolioItem(
                id=self._new_id(payload.get("title", ""), items),
                title=payload.get("title", ""),
                short_desc=payload.get("short_desc", ""),
                long_desc=payload.get("long_desc", ""),
                image_full=payload.get("image_full", ""),
                image_thumb=payload.get("image_thumb", ""),
                image_alt=payload.get("image_alt", ""),
                sort_order=int(sort_order),
                is_published=bool(payload.get("is_published", True)),
                created_at=now,
                updated_at=now,
                kind=normalize_kind(payload.get("kind")),
                line=payload.get("line", ""),
                href=payload.get("href", ""),
            ).to_dict()

            items.append(item)
            data["items"] = _rerank(items, item["id"], item["sort_order"])
            self._write(data)
            return next(i for i in data["items"] if i["id"] == item["id"])

    def update_item(self, item_id: str, payload: dict) -> dict | None:
        with _STORE_LOCK:
            data = self._read()
            items = data.get("items", [])
            updated_item = None

            for idx, raw in enumerate(items):
                if raw.get("id") != item_id:
                    continue

                current = PortfolioItem.from_dict(raw)
                current.title = payload.get("title", current.title)
                current.short_desc = payload.get("short_desc", current.short_desc)
                current.long_desc = payload.get("long_desc", current.long_desc)
                current.image_full = payload.get("image_full", current.image_full)
                current.image_thumb = payload.get("image_thumb", current.image_thumb)
                current.image_alt = payload.get("image_alt", current.image_alt)
                if payload.get("kind") is not None:
                    current.kind = normalize_kind(payload.get("kind"))
                current.line = payload.get("line", current.line)
                current.href = payload.get("href", current.href)
                if payload.get("sort_order") is not None:
                    current.sort_order = int(payload.get("sort_order"))
                if payload.get("is_published") is not None:
                    current.is_published = bool(payload.get("is_published"))
                current.updated_at = _timestamp()

                updated_item = current.to_dict()
                items[idx] = updated_item
                break

            if updated_item is None:
                return None

            if payload.get("sort_order") is not None:
                items = _rerank(items, item_id, updated_item["sort_order"])
                updated_item = next(i for i in items if i["id"] == item_id)
            data["items"] = items
            self._write(data)
            return updated_item

    def delete_item(self, item_id: str) -> bool:
        with _STORE_LOCK:
            data = self._read()
            items = data.get("items", [])
            filtered = [item for item in items if item.get("id") != item_id]
            if len(filtered) == len(items):
                return False
            data["items"] = _rerank(filtered)
            self._write(data)
            return True

    def _new_id(self, title: str, items: list[dict]) -> str:
        """A readable, unique id from the title (it names the work in the homepage's URL,
        /#curve-explorer); a random one when the title has no letters or digits."""
        base = _SLUG_RE.sub("-", str(title).lower()).strip("-")[:48].strip("-")
        if not base:
            return uuid.uuid4().hex
        taken = {str(item.get("id", "")) for item in items}
        candidate, n = base, 2
        while candidate in taken:
            candidate, n = f"{base}-{n}", n + 1
        return candidate

    def import_copy(self, seed_path: str, dry_run: bool = False) -> list[tuple[str, str]]:
        """Copies the words (COPY_FIELDS) of every seed item into the live item with its id, and
        nothing else: order, publishing, images and the admin's other edits stay as they are.
        Returns the (id, field) pairs that changed."""
        seed = {item.get("id"): item for item in json.loads(Path(seed_path).read_text(encoding="utf-8")).get("items", [])}
        with _STORE_LOCK:
            data = self._read()
            changed = []
            for item in data.get("items", []):
                source = seed.get(item.get("id"))
                if not source:
                    continue
                for field in COPY_FIELDS:
                    if field in source and source[field] != item.get(field):
                        item[field] = source[field]
                        changed.append((item["id"], field))
            if changed and not dry_run:
                self._write(data)
            return changed

    def _next_sort_order(self, items: list[dict]) -> int:
        return len(items)

    def _ensure_data_file(self) -> None:
        if self._path.exists():
            return
        if self._seed and self._seed.exists():
            shutil.copyfile(self._seed, self._path)
        else:
            self._write({"items": []})

    def _read(self) -> dict:
        self._ensure_data_file()
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {"items": []}

    def _write(self, data: dict) -> None:
        serialized = json.dumps(data, indent=2, ensure_ascii=True)
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(self._path)


def _rerank(items: list[dict], moved_id: str | None = None, position: int = 0) -> list[dict]:
    """Every item gets a distinct rank 0..n-1 in its current order. The moved item lands at
    `position` (clamped to the ends) and the others shift around it, so no two share a rank."""
    order = sorted(range(len(items)), key=lambda i: (int(items[i].get("sort_order", 0)), i))
    ordered = [items[i] for i in order if items[i].get("id") != moved_id]
    if moved_id is not None:
        moved = next(item for item in items if item.get("id") == moved_id)
        ordered.insert(max(0, min(int(position), len(ordered))), moved)
    for rank, item in enumerate(ordered):
        item["sort_order"] = rank
    return ordered


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
