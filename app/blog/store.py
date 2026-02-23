from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import markdown as markdown_lib

_MARKDOWN_EXTENSIONS = ["extra", "sane_lists", "smarty"]
_HEADING_RE = re.compile(r"^\s*#\s+(.+?)\s*$", re.MULTILINE)


@dataclass
class BlogPost:
    slug: str
    title: str
    summary: str
    date_label: str
    sort_date: datetime
    html: str
    source_path: str

    def to_summary_dict(self) -> dict:
        return {
            "slug": self.slug,
            "title": self.title,
            "summary": self.summary,
            "date_label": self.date_label,
        }

    def to_detail_dict(self) -> dict:
        payload = self.to_summary_dict()
        payload.update({"html": self.html, "source_path": self.source_path})
        return payload


class BlogStore:
    def __init__(self, posts_dir: str) -> None:
        self._posts_dir = Path(posts_dir)

    def list_posts(self) -> list[dict]:
        posts = self._load_posts(include_html=False)
        return [post.to_summary_dict() for post in posts]

    def get_post(self, slug: str) -> dict | None:
        posts = self._load_posts(include_html=True)
        for post in posts:
            if post.slug == slug:
                return post.to_detail_dict()
        return None

    def _load_posts(self, include_html: bool) -> list[BlogPost]:
        if not self._posts_dir.exists():
            return []

        posts: list[BlogPost] = []
        seen_slugs: set[str] = set()

        for path in sorted(self._posts_dir.glob("*.md")):
            if not path.is_file():
                continue

            text = path.read_text(encoding="utf-8", errors="replace")
            metadata, body = _split_front_matter(text)

            slug = _build_unique_slug(path.stem, seen_slugs)
            title = _resolve_title(path.stem, metadata, body)
            summary = _resolve_summary(metadata, body)
            sort_date, date_label = _resolve_dates(metadata.get("date"), path)
            render_body = _strip_duplicate_leading_h1(body, title)
            html = _render_markdown(render_body) if include_html else ""

            posts.append(
                BlogPost(
                    slug=slug,
                    title=title,
                    summary=summary,
                    date_label=date_label,
                    sort_date=sort_date,
                    html=html,
                    source_path=str(path),
                )
            )

        posts.sort(key=lambda item: item.sort_date, reverse=True)
        return posts


def _split_front_matter(text: str) -> tuple[dict[str, str], str]:
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}, text

    metadata: dict[str, str] = {}
    end_idx = -1
    for idx, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            end_idx = idx
            break
        if ":" not in line:
            continue
        key, value = line.split(":", 1)
        key = key.strip().lower()
        value = value.strip().strip("'").strip('"')
        if key:
            metadata[key] = value

    if end_idx == -1:
        return {}, text

    body = "\n".join(lines[end_idx + 1 :]).lstrip("\n")
    return metadata, body


def _build_unique_slug(stem: str, seen_slugs: set[str]) -> str:
    base = _slugify(stem) or "post"
    slug = base
    suffix = 2
    while slug in seen_slugs:
        slug = f"{base}-{suffix}"
        suffix += 1
    seen_slugs.add(slug)
    return slug


def _slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return slug


def _resolve_title(stem: str, metadata: dict[str, str], body: str) -> str:
    title = metadata.get("title", "").strip()
    if title:
        return title

    heading_match = _HEADING_RE.search(body)
    if heading_match:
        return _strip_markdown_inline(heading_match.group(1))

    return stem.replace("-", " ").replace("_", " ").strip().title() or "Untitled Post"


def _resolve_summary(metadata: dict[str, str], body: str) -> str:
    summary = metadata.get("summary", "").strip()
    if summary:
        return summary
    return _extract_summary(body)


def _resolve_dates(raw_date: str | None, path: Path) -> tuple[datetime, str]:
    parsed = _parse_date(raw_date)
    if parsed is not None:
        return parsed, _format_date_label(parsed)

    file_date = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc)
    return file_date, _format_date_label(file_date)


def _parse_date(raw_date: str | None) -> datetime | None:
    if not raw_date:
        return None

    candidate = raw_date.strip()
    if not candidate:
        return None

    if candidate.endswith("Z"):
        candidate = f"{candidate[:-1]}+00:00"

    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _format_date_label(value: datetime) -> str:
    return value.strftime("%B %d, %Y").replace(" 0", " ")


def _extract_summary(body: str) -> str:
    lines = body.splitlines()
    in_fence = False

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
            continue
        if in_fence or not stripped:
            continue
        if stripped.startswith("#"):
            continue

        summary = _strip_markdown_inline(stripped)
        if summary:
            if len(summary) > 200:
                return f"{summary[:197].rstrip()}..."
            return summary

    return "Read this post."


def _strip_markdown_inline(text: str) -> str:
    cleaned = text
    cleaned = re.sub(r"!\[[^\]]*]\([^)]+\)", "", cleaned)
    cleaned = re.sub(r"\[([^\]]+)]\([^)]+\)", r"\1", cleaned)
    cleaned = re.sub(r"`([^`]+)`", r"\1", cleaned)
    cleaned = re.sub(r"[*_~>#]", "", cleaned)
    cleaned = re.sub(r"\s+", " ", cleaned)
    return cleaned.strip()


def _strip_duplicate_leading_h1(body: str, title: str) -> str:
    lines = body.splitlines()
    idx = 0

    while idx < len(lines) and not lines[idx].strip():
        idx += 1

    if idx >= len(lines):
        return body

    stripped = lines[idx].strip()
    if not stripped.startswith("# "):
        return body

    heading_text = stripped[2:].strip()
    heading_text = re.sub(r"\s+#+\s*$", "", heading_text)
    if _normalize_for_match(heading_text) != _normalize_for_match(title):
        return body

    new_lines = lines[:idx] + lines[idx + 1 :]
    while idx < len(new_lines) and not new_lines[idx].strip():
        del new_lines[idx]
    return "\n".join(new_lines).lstrip("\n")


def _normalize_for_match(text: str) -> str:
    value = _strip_markdown_inline(text).lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def _render_markdown(body: str) -> str:
    if not body.strip():
        return "<p>This post is empty.</p>"
    return markdown_lib.markdown(body, extensions=_MARKDOWN_EXTENSIONS, output_format="html5")
