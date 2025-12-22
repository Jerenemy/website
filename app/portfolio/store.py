from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

_STORE_LOCK = Lock()


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
        )

    def to_dict(self) -> dict:
        return asdict(self)


class PortfolioStore:
    def __init__(self, data_path: str) -> None:
        self._path = Path(data_path)
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
                id=uuid.uuid4().hex,
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
            ).to_dict()

            items.append(item)
            data["items"] = items
            self._write(data)
            return item

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
            data["items"] = filtered
            self._write(data)
            return True

    def _next_sort_order(self, items: list[dict]) -> int:
        if not items:
            return 0
        return max(int(item.get("sort_order", 0)) for item in items) + 1

    def _ensure_data_file(self) -> None:
        if not self._path.exists():
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


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
