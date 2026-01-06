from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock

DEFAULT_HOME_DESCRIPTION = (
    "I am an undergraduate student at Wesleyan University, pursuing a triple-major in "
    "Computer Science, Mathematics, and College of Integrative Sciences. My research in "
    "the Thayer Lab focuses on using machine learning techniques, including diffusion, "
    "to design small drug-like molecules aimed at restoring mutant p53."
)

_STORE_LOCK = Lock()


def _default_settings() -> dict:
    return {
        "home_description": DEFAULT_HOME_DESCRIPTION,
        "home_bg": "img/home-bg.jpg",
        "resume_filename": "resume.pdf",
        "theme": {
            "bg": "#555555",
            "fg": "#111111",
            "accent": "#4fc3f7",
        },
    }


def _merge_defaults(data: dict) -> dict:
    merged = _default_settings()
    if not isinstance(data, dict):
        return merged

    home_description = data.get("home_description")
    if isinstance(home_description, str) and home_description.strip():
        merged["home_description"] = home_description

    home_bg = data.get("home_bg")
    if isinstance(home_bg, str) and home_bg.strip():
        merged["home_bg"] = home_bg

    resume_filename = data.get("resume_filename")
    if isinstance(resume_filename, str) and resume_filename.strip():
        merged["resume_filename"] = resume_filename

    theme = data.get("theme")
    if isinstance(theme, dict):
        for key in ("bg", "fg", "accent"):
            value = theme.get(key)
            if isinstance(value, str) and value.strip():
                merged["theme"][key] = value

    updated_at = data.get("updated_at")
    if isinstance(updated_at, str) and updated_at.strip():
        merged["updated_at"] = updated_at

    return merged


class SiteSettingsStore:
    def __init__(self, data_path: str) -> None:
        self._path = Path(data_path)
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def get_settings(self) -> dict:
        data = self._read()
        return _merge_defaults(data)

    def update_settings(self, updates: dict) -> dict:
        with _STORE_LOCK:
            current = self.get_settings()

            if "home_description" in updates and updates["home_description"] is not None:
                current["home_description"] = str(updates["home_description"])
            if "home_bg" in updates and updates["home_bg"] is not None:
                current["home_bg"] = str(updates["home_bg"])
            if "resume_filename" in updates and updates["resume_filename"] is not None:
                current["resume_filename"] = str(updates["resume_filename"])

            if "theme" in updates and isinstance(updates["theme"], dict):
                theme = current.get("theme", {})
                for key in ("bg", "fg", "accent"):
                    if key in updates["theme"] and updates["theme"][key] is not None:
                        theme[key] = str(updates["theme"][key])
                current["theme"] = theme

            current["updated_at"] = _timestamp()
            self._write(current)
            return current

    def _ensure_data_file(self) -> None:
        if not self._path.exists():
            self._write(_default_settings())

    def _read(self) -> dict:
        self._ensure_data_file()
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return _default_settings()

    def _write(self, data: dict) -> None:
        serialized = json.dumps(data, indent=2, ensure_ascii=True)
        temp_path = self._path.with_suffix(".tmp")
        temp_path.write_text(serialized, encoding="utf-8")
        temp_path.replace(self._path)


def _timestamp() -> str:
    return datetime.now(timezone.utc).isoformat()
