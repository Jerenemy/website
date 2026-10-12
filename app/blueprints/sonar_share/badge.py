"""Rating badges for podcasters to embed: a compact, shields-style SVG.

    [ (( sonar. | ★ 4.3 · 128 ratings ]

Fixed size (WIDTH x HEIGHT) so an embed never reflows, in the sea-glass palette: dark by
default, ``theme="light"`` for light pages. Every piece of text is XML-escaped, and the SVG has
no scripts, links or external references, so it's safe to drop into any page as an <img>.
"""

from xml.sax.saxutils import escape, quoteattr

WIDTH, HEIGHT = 230, 28
SPLIT = 78  # where the value half starts

THEMES = {
    "dark": {
        "left": "#0C1014", "right": "#161B21", "stroke": "#2A323B",
        "label": "#F3F5F7", "value": "#F3F5F7", "accent": "#2FCBBD",
    },
    "light": {
        "left": "#FFFFFF", "right": "#EEF2F4", "stroke": "#D5DCE1",
        "label": "#0C1014", "value": "#0C1014", "accent": "#0E8F84",
    },
}

FONT = "ui-rounded, 'SF Pro Rounded', Nunito, -apple-system, 'Segoe UI', Verdana, sans-serif"


def theme_name(value):
    return "light" if (value or "").strip().lower() == "light" else "dark"


def compact(count):
    """128 -> "128", 1234 -> "1,234", 12345 -> "12.3k" (the value half has room for ~22 characters)."""
    if count < 10_000:
        return f"{count:,}"
    if count < 1_000_000:
        return f"{count / 1000:.1f}".rstrip("0").rstrip(".") + "k"
    return f"{count / 1_000_000:.1f}".rstrip("0").rstrip(".") + "M"


def rating_text(average, count):
    """(visible value, accessible description)."""
    if not average or not count:
        return "Rate it on Sonar", "Rate it on Sonar"
    noun = "rating" if count == 1 else "ratings"
    return (f"★ {average:.1f} · {compact(count)} {noun}",
            f"Rated {average:.1f} out of 5 from {count:,} {noun} on Sonar")


def svg(value, description, theme="dark"):
    """The badge. `value` and `description` are plain text; they are escaped here."""
    colors = THEMES[theme_name(theme)]
    value_x = SPLIT + (WIDTH - SPLIT) / 2
    star = value.startswith("★ ")
    if star:
        value_body = (f'<tspan fill="{colors["accent"]}">★</tspan> {escape(value[2:])}')
    else:
        value_body = escape(value)
    title = escape(description)
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{HEIGHT}" '
        f'viewBox="0 0 {WIDTH} {HEIGHT}" role="img" aria-label={quoteattr(description)}>'
        f"<title>{title}</title>"
        # No ids (a page may inline several badges): the right half is the whole rounded
        # rectangle, the left half a path with only its left corners rounded.
        f'<rect width="{WIDTH}" height="{HEIGHT}" rx="7" fill="{colors["right"]}"/>'
        f'<path d="M7 0H{SPLIT}V{HEIGHT}H7A7 7 0 0 1 0 {HEIGHT - 7}V7A7 7 0 0 1 7 0Z" fill="{colors["left"]}"/>'
        f'<rect x=".5" y=".5" width="{WIDTH - 1}" height="{HEIGHT - 1}" rx="6.5" fill="none" stroke="{colors["stroke"]}"/>'
        # The ping mark: outer ring at 45%, inner ring, dot (SonarBrandMark).
        f'<g transform="translate(17 14)" fill="none" stroke="{colors["accent"]}">'
        f'<circle r="6.3" stroke-opacity=".45" stroke-width="1.3"/>'
        f'<circle r="3.9" stroke-width="1.6"/>'
        f'<circle r="1.7" fill="{colors["accent"]}" stroke="none"/>'
        f"</g>"
        f'<g font-family="{FONT}" font-size="13" font-weight="600">'
        f'<text x="29" y="18.5" fill="{colors["label"]}">sonar<tspan fill="{colors["accent"]}">.</tspan></text>'
        f"</g>"
        f'<text x="{value_x:g}" y="18.5" text-anchor="middle" font-family="{FONT}" font-size="12" '
        f'font-weight="600" fill="{colors["value"]}">{value_body}</text>'
        f"</svg>"
    )
