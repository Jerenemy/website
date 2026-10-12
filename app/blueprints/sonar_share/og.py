"""Open Graph preview images (1200x630 PNG) for Sonar share links.

The landscape cousins of the in-app share cards (Sonar/Components/ShareCardViews.swift): the
cool ink canvas with a soft wash of the artwork's colour, the artwork with its one shadow,
quiet type, five rating dots and the loved heart, and the lowercase ``sonar.`` wordmark.

Everything is drawn at 2x and downsampled, so circles and rounded corners come out smooth.
Type is Nunito (SIL OFL, bundled in static/sonar/fonts), the closest open rounded face to SF
Pro Rounded. Rendered PNGs are cached in-process (LRU) and on disk under instance/ with a TTL.

Failure handling: no data (missing/private/unreadable, or a lookup error) gives the brand-only
image; artwork that can't be fetched gives the card with a placeholder tile. Either way the
result is cached only briefly, so a transient failure doesn't stick.
"""

import colorsys
import hashlib
import io
import ipaddress
import os
import random
import socket
import threading
import time
from collections import OrderedDict
from urllib.parse import urljoin, urlsplit

import requests
from flask import current_app
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# Bump to invalidate every cached image after a design change.
RENDER_VERSION = "1"

W, H = 1200, 630
S = 2  # supersampling factor
PAD = 64

INK = (12, 16, 20)            # #0C1014 canvas
CARD = (22, 27, 33)           # #161B21
LABEL = (243, 245, 247)       # #F3F5F7
GRAY = (152, 162, 173)        # #98A2AD
TEAL = (47, 203, 189)         # #2FCBBD
LOVE = (255, 92, 122)         # #FF5C7A

FONT_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", "static", "sonar", "fonts"))
FONT_FILES = {
    "regular": "Nunito-Regular.otf",
    "semibold": "Nunito-SemiBold.otf",
    "bold": "Nunito-Bold.otf",
}

ARTWORK_TIMEOUT = (3, 4)          # connect, read (seconds)
ARTWORK_DEADLINE = 6              # whole download, seconds
ARTWORK_MAX_BYTES = 6 * 1024 * 1024
ARTWORK_MAX_PIXELS = 36_000_000
ARTWORK_MAX_REDIRECTS = 3

MEMORY_ITEMS = 64
GOOD_TTL = 3600                   # in-process, seconds
DISK_TTL = 6 * 3600
DEGRADED_TTL = 300

CACHE_CONTROL_GOOD = "public, max-age=86400, stale-while-revalidate=604800"
CACHE_CONTROL_SHORT = "public, max-age=300"


def alpha(rgb, a):
    return (*rgb, int(round(a * 255)))


def s(value):
    return int(round(value * S))


# --- Fonts and text ------------------------------------------------------------------------

_fonts = {}
_missing = {}
_font_lock = threading.Lock()


def font(weight, size):
    key = (weight, size)
    with _font_lock:
        if key not in _fonts:
            _fonts[key] = ImageFont.truetype(os.path.join(FONT_DIR, FONT_FILES[weight]), s(size))
        return _fonts[key]


def _supported(text, weight):
    """Drops characters the font has no glyph for (emoji, CJK), rather than drawing boxes."""
    probe = font(weight, 20)
    with _font_lock:
        if weight not in _missing:
            _missing[weight] = (bytes(probe.getmask("\U0010fffd")), {})
        notdef, known = _missing[weight]
        out = []
        for char in text:
            if char.isspace() or char.isascii():
                out.append(char)
                continue
            if char not in known:
                known[char] = bytes(probe.getmask(char)) != notdef
            if known[char]:
                out.append(char)
    return "".join(out)


def clean(text, weight="regular"):
    return " ".join(_supported(text or "", weight).split())


def wrap(text, weight, size, max_width, max_lines):
    """Word-wraps to at most max_lines, ending with an ellipsis when it had to cut."""
    face = font(weight, size)
    limit = s(max_width)
    words = clean(text, weight).split(" ")
    lines, current, cut = [], "", False
    for index, word in enumerate(words):
        if not word:
            continue
        trial = f"{current} {word}".strip()
        if face.getlength(trial) <= limit:
            current = trial
            continue
        if current:
            lines.append(current)
            current = ""
            if len(lines) == max_lines:
                cut = True
                break
        while face.getlength(word) > limit:  # a single overlong word: break it by character
            end = len(word)
            while end > 1 and face.getlength(word[:end]) > limit:
                end -= 1
            lines.append(word[:end])
            word = word[end:]
            if len(lines) == max_lines:
                cut = True
                break
        if cut:
            break
        current = word
    if not cut and current:
        if len(lines) < max_lines:
            lines.append(current)
        else:
            cut = True
    if cut and lines:
        last = lines[-1]
        while last and face.getlength(last + "…") > limit:
            last = last[:-1]
        lines[-1] = last.rstrip(" ,.;:-") + "…"
    return lines


def one_line(text, weight, size, max_width):
    lines = wrap(text, weight, size, max_width, 1)
    return lines[0] if lines else ""


# --- Drawing -------------------------------------------------------------------------------

class Card:
    def __init__(self, glow=None):
        self.image = Image.new("RGB", (s(W), s(H)), INK)
        if glow is not None:
            self._glow(glow)
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def _glow(self, artwork):
        """The artwork's colour bleeding in from the top, as on the in-app cards."""
        small = artwork.convert("RGB").resize((48, 48), Image.BILINEAR)
        small = small.filter(ImageFilter.GaussianBlur(6))
        wash = small.resize((s(W), s(H)), Image.BICUBIC)
        # As ShareCardCanvas: the wash covers the top 75% at 50% opacity, fading 1 -> .55
        # (at 45% of its height) -> 0.
        ramp = []
        for row in range(256):
            t = row / 255 / 0.75
            strength = 0 if t >= 1 else (1 - 0.45 * t / 0.45 if t < 0.45 else 0.55 * (1 - (t - 0.45) / 0.55))
            ramp.append(int(255 * 0.5 * strength))
        mask = Image.linear_gradient("L").point(ramp).resize((s(W), s(H)))
        self.image.paste(wash, (0, 0), mask)

    def teal_wash(self):
        """A faint teal wash from the top, like the marketing pages' background, for cards without artwork."""
        wash = Image.new("RGB", (s(W), s(H)), (12, 30, 32))
        mask = Image.radial_gradient("L").resize((s(W) * 2, s(H) * 2))
        mask = mask.crop((s(W) // 2, s(H) * 3 // 4, s(W) * 3 // 2, s(H) * 7 // 4))
        mask = mask.point(lambda v: int((255 - v) * 0.9))
        self.image.paste(wash, (0, 0), mask)
        self.draw = ImageDraw.Draw(self.image, "RGBA")

    def text(self, xy, value, weight, size, fill, anchor="la"):
        self.draw.text((s(xy[0]), s(xy[1])), value, font=font(weight, size), fill=fill, anchor=anchor)

    def text_width(self, value, weight, size):
        return font(weight, size).getlength(value) / S

    def lines(self, x, y, lines, weight, size, fill, line_height):
        for index, line in enumerate(lines):
            self.text((x, y + index * line_height), line, weight, size, fill)
        return y + len(lines) * line_height

    def divider(self, x0, x1, y):
        self.draw.rectangle((s(x0), s(y), s(x1), s(y) + 1), fill=alpha(LABEL, 0.1))

    def artwork(self, image, x, y, size, shadow=True):
        px = side = s(size)
        radius = s(size * 0.09)
        if shadow:
            pad = s(60)
            shade = Image.new("L", (side + 2 * pad, side + 2 * pad), 0)
            ImageDraw.Draw(shade).rounded_rectangle((pad, pad, pad + side, pad + side), radius, fill=int(255 * 0.45))
            shade = shade.filter(ImageFilter.GaussianBlur(s(20)))
            black = Image.new("RGB", shade.size, (0, 0, 0))
            self.image.paste(black, (s(x) - pad, s(y) + s(14) - pad), shade)
        mask = Image.new("L", (px, px), 0)
        ImageDraw.Draw(mask).rounded_rectangle((0, 0, px - 1, px - 1), radius, fill=255)
        if image is not None:
            tile = _cover(image, px)
        else:
            tile = Image.new("RGB", (px, px), CARD)
            mark = Image.new("RGBA", (px, px), (0, 0, 0, 0))
            _brand_mark(ImageDraw.Draw(mark), px / 2, px / 2, px * 0.34, LABEL, 0.14)
            tile.paste(mark, (0, 0), mark)
        self.image.paste(tile, (s(x), s(y)), mask)
        self.draw = ImageDraw.Draw(self.image, "RGBA")
        self.draw.rounded_rectangle(
            (s(x), s(y), s(x) + px - 1, s(y) + px - 1), radius, outline=alpha(LABEL, 0.08), width=max(1, S)
        )

    def dots(self, x, y_center, rating, diameter=22):
        """Five rating dots for a 0...5 rating, half points fill half a dot. Returns the end x."""
        d = s(diameter)
        gap = max(2, diameter * 0.32)
        for level in range(5):
            fill = min(max(rating - level, 0), 1)
            left = s(x + level * (diameter + gap))
            top = s(y_center) - d // 2
            self.draw.ellipse((left, top, left + d, top + d), fill=alpha(LABEL, 0.16))
            if fill > 0:
                mask = Image.new("L", (d, d), 0)
                ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
                if fill < 1:
                    ImageDraw.Draw(mask).rectangle((int(d * fill), 0, d, d), fill=0)
                self.image.paste(Image.new("RGB", (d, d), TEAL), (left, top), mask)
        self.draw = ImageDraw.Draw(self.image, "RGBA")
        return x + 5 * diameter + 4 * gap

    def heart(self, x, y_center, size, color=LOVE):
        """A filled heart, size points wide."""
        h = s(size)
        left, top = s(x), s(y_center) - int(h * 0.46)
        r = h * 0.27
        for cx in (0.27, 0.73):
            self.draw.ellipse((left + h * cx - r, top + h * 0.3 - r, left + h * cx + r, top + h * 0.3 + r), fill=color)
        self.draw.polygon(
            [(left + h * 0.015, top + h * 0.38), (left + h * 0.5, top + h * 0.9), (left + h * 0.985, top + h * 0.38),
             (left + h * 0.5, top + h * 0.3)],
            fill=color,
        )
        return x + size

    def avatar(self, username, x, y, size):
        top, bottom = avatar_colors(username)
        d = s(size)
        vertical = Image.linear_gradient("L").resize((d, d))
        gradient = ImageChops.add(vertical, vertical.transpose(Image.Transpose.ROTATE_90), scale=2.0)
        tile = Image.composite(Image.new("RGB", (d, d), bottom), Image.new("RGB", (d, d), top), gradient)
        mask = Image.new("L", (d, d), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
        self.image.paste(tile, (s(x), s(y)), mask)
        self.draw = ImageDraw.Draw(self.image, "RGBA")
        self.draw.ellipse((s(x), s(y), s(x) + d - 1, s(y) + d - 1), outline=alpha(LABEL, 0.08), width=max(1, S))
        initial = avatar_initial(username)
        self.text((x + size / 2, y + size / 2), initial, "semibold", size * 0.42, alpha(LABEL, 0.95), anchor="mm")

    def photo(self, image, x, y, size):
        """A round profile photo."""
        d = s(size)
        tile = _cover(image, d)
        mask = Image.new("L", (d, d), 0)
        ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
        self.image.paste(tile, (s(x), s(y)), mask)
        self.draw = ImageDraw.Draw(self.image, "RGBA")
        self.draw.ellipse((s(x), s(y), s(x) + d - 1, s(y) + d - 1), outline=alpha(LABEL, 0.08), width=max(1, S))

    def wordmark(self, right, y_center, size=30):
        """The mark and the lowercase wordmark, right-aligned at `right`."""
        word = "sonar"
        word_w = self.text_width(word, "semibold", size)
        dot_w = self.text_width(".", "semibold", size)
        mark = size * 0.95
        left = right - (mark + size * 0.3 + word_w + dot_w)
        _brand_mark(self.draw, s(left + mark / 2), s(y_center), s(mark), TEAL)
        text_x = left + mark + size * 0.3
        self.text((text_x, y_center), word, "semibold", size, LABEL, anchor="lm")
        self.text((text_x + word_w, y_center), ".", "semibold", size, TEAL, anchor="lm")

    def footer(self, x0, x1, y_divider):
        self.divider(x0, x1, y_divider)
        row = y_divider + (H - PAD + 10 - y_divider) / 2
        self.wordmark(x1, row)
        return row

    def png(self):
        final = self.image.resize((W, H), Image.LANCZOS)
        out = io.BytesIO()
        final.save(out, "PNG", optimize=True)
        return out.getvalue()


def _brand_mark(draw, cx, cy, diameter, color, opacity=1.0):
    """SonarBrandMark: an outer ring at 45%, an inner ring and the ping dot."""
    def ring(d, width, a):
        r = d / 2
        draw.ellipse((cx - r, cy - r, cx + r, cy + r), outline=alpha(color, a * opacity), width=max(1, int(round(width))))
    ring(diameter * 0.816 + diameter * 0.047, diameter * 0.047, 0.45)
    ring(diameter * 0.512 + diameter * 0.0625, diameter * 0.0625, 1.0)
    r = diameter * 0.115
    draw.ellipse((cx - r, cy - r, cx + r, cy + r), fill=alpha(color, opacity))


def _cover(image, side):
    """Center-crops to a square and scales to side x side."""
    w, h = image.size
    edge = min(w, h)
    box = ((w - edge) // 2, (h - edge) // 2, (w - edge) // 2 + edge, (h - edge) // 2 + edge)
    return image.convert("RGB").crop(box).resize((side, side), Image.LANCZOS)


def avatar_colors(username):
    """The app's per-username avatar gradient (AvatarView): a stable, calm hue."""
    total = 0
    for char in username or "":
        total = (total * 31 + ord(char)) & 0xFFFF
    hue = (total % 360) / 360
    top = tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(hue, 0.42, 0.52))
    bottom = tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(hue, 0.5, 0.34))
    return top, bottom


def avatar_initial(username):
    first = (username or "")[:1]
    return first.upper() if first.isalnum() else "?"


# --- Artwork -------------------------------------------------------------------------------

class ArtworkError(Exception):
    pass


def _check_host(host):
    """Refuses hosts that resolve to private, loopback or otherwise internal addresses."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except socket.gaierror as error:
        raise ArtworkError(f"cannot resolve {host}") from error
    for info in infos:
        address = ipaddress.ip_address(info[4][0].split("%")[0])
        if not address.is_global:
            raise ArtworkError(f"refusing internal address for {host}")


def fetch_artwork(url):
    """Downloads and decodes an artwork image, or raises ArtworkError. Bounded in time and size."""
    if not url:
        raise ArtworkError("no artwork")
    started = time.monotonic()
    for _ in range(ARTWORK_MAX_REDIRECTS + 1):
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.hostname:
            raise ArtworkError("unsupported artwork url")
        _check_host(parts.hostname)
        try:
            response = requests.get(
                url,
                stream=True,
                timeout=ARTWORK_TIMEOUT,
                allow_redirects=False,
                headers={"User-Agent": "SonarShare/1.0 (jeremyzay.com)", "Accept": "image/*"},
            )
        except requests.RequestException as error:
            raise ArtworkError(str(error)) from error
        with response:
            if response.is_redirect:
                url = urljoin(url, response.headers.get("Location", ""))
                continue
            if response.status_code != 200:
                raise ArtworkError(f"artwork status {response.status_code}")
            declared = response.headers.get("Content-Length", "")
            if declared.isdigit() and int(declared) > ARTWORK_MAX_BYTES:
                raise ArtworkError("artwork too large")
            body = bytearray()
            try:
                for chunk in response.iter_content(64 * 1024):
                    body.extend(chunk)
                    if len(body) > ARTWORK_MAX_BYTES:
                        raise ArtworkError("artwork too large")
                    if time.monotonic() - started > ARTWORK_DEADLINE:
                        raise ArtworkError("artwork too slow")
            except requests.RequestException as error:
                raise ArtworkError(str(error)) from error
        return _decode(bytes(body))
    raise ArtworkError("too many redirects")


def _decode(body):
    try:
        image = Image.open(io.BytesIO(body))
        if image.width * image.height > ARTWORK_MAX_PIXELS:
            raise ArtworkError("artwork has too many pixels")
        image.draft("RGB", (1000, 1000))  # JPEG: decode at a reduced size, much faster
        image = image.convert("RGB")
        image.thumbnail((1000, 1000))
        return image
    except ArtworkError:
        raise
    except Exception as error:  # Pillow raises a variety of errors on bad input
        raise ArtworkError(f"undecodable artwork: {error}") from error


def load_artwork(*urls):
    """The first artwork that loads, or None. Records the failure on the current render."""
    for url in urls:
        if not url:
            continue
        try:
            return fetch_artwork(url)
        except ArtworkError as error:
            current_app.logger.info("sonar og artwork failed: %s (%s)", url, error)
            _render_state.degraded = True
    return None


_render_state = threading.local()


def mark_degraded():
    """Keeps the image being rendered out of the long caches (a stand-in that may change soon)."""
    _render_state.degraded = True


# --- Cards ---------------------------------------------------------------------------------

ART = 440
ART_Y = (H - ART) // 2
COL_X = PAD + ART + 56
COL_W = W - PAD - COL_X
DIVIDER_Y = H - PAD - 52


def brand_card():
    card = Card()
    card.teal_wash()
    mark = 150
    _brand_mark(card.draw, s(W / 2), s(205), s(mark), TEAL)
    size = 104
    word_w = card.text_width("sonar", "semibold", size)
    dot_w = card.text_width(".", "semibold", size)
    x = (W - word_w - dot_w) / 2
    card.text((x, 380), "sonar", "semibold", size, LABEL, anchor="ls")
    card.text((x + word_w, 380), ".", "semibold", size, TEAL, anchor="ls")
    card.text((W / 2, 452), "Rate, review and remember the episodes you love", "regular", 32, GRAY, anchor="ms")
    return card


def review_card(review):
    episode = review.episode
    artwork_url = episode.artwork if episode else None
    fallback = episode.podcast.artwork if episode and episode.podcast else None
    art = load_artwork(artwork_url, fallback if fallback != artwork_url else None)
    card = Card(glow=art)
    card.artwork(art, PAD, ART_Y, ART)

    y = PAD + 8
    show = episode.podcast.name if episode and episode.podcast else None
    if show:
        card.text((COL_X, y), one_line(show, "regular", 26, COL_W), "regular", 26, GRAY)
        y += 38
    title = episode.title if episode else "A podcast episode"
    y = card.lines(COL_X, y, wrap(title, "bold", 38, COL_W, 2), "bold", 38, LABEL, 48)

    if review.rating or review.is_loved:
        y += 18
        row = y + 13
        x = COL_X
        if review.rating:
            x = card.dots(COL_X, row, review.rating / 2, 24) + 12
        if review.is_loved:
            card.heart(x, row, 26)
        y += 26

    y += 24
    room = DIVIDER_Y - 22 - y
    if review.text:
        length = len(review.text)
        size, line_height = (34, 46) if length < 90 else (29, 40) if length < 200 else (25, 35)
        lines = wrap(review.text, "regular", size, COL_W, max(1, int(room // line_height)))
        card.lines(COL_X, y, lines, "regular", size, alpha(LABEL, 0.92), line_height)
    else:
        card.text((COL_X, y), "Rated this episode" if review.rating else "Logged this episode", "regular", 26, GRAY)

    row = card.footer(COL_X, W - PAD, DIVIDER_Y)
    _byline(card, review.username, row)
    return card


def _byline(card, username, row, suffix=" on Sonar"):
    name = f"@{username}" if username else "Someone"
    card.avatar(username or "?", COL_X, row - 18, 36)
    x = COL_X + 48
    room = W - PAD - 220 - x
    name = one_line(name, "semibold", 24, room)
    card.text((x, row), name, "semibold", 24, LABEL, anchor="lm")
    x += card.text_width(name, "semibold", 24)
    card.text((x, row), suffix, "regular", 24, GRAY, anchor="lm")


def episode_card(episode, average):
    art = load_artwork(episode.artwork, episode.podcast.artwork if episode.podcast else None)
    card = Card(glow=art)
    card.artwork(art, PAD, ART_Y, ART)
    y = PAD + 8
    if episode.podcast:
        card.text((COL_X, y), one_line(episode.podcast.name, "regular", 26, COL_W), "regular", 26, GRAY)
        y += 40
    y = card.lines(COL_X, y, wrap(episode.title, "bold", 44, COL_W, 4), "bold", 44, LABEL, 54)
    y += 26
    if average:
        end = card.dots(COL_X, y + 13, average, 24)
        card.text((end + 14, y + 13), f"{average:g}", "bold", 28, LABEL, anchor="lm")
        card.text((COL_X, y + 42), "Community", "regular", 22, GRAY)
    else:
        card.text((COL_X, y), "Be the first to rate it", "regular", 26, GRAY)
    row = card.footer(COL_X, W - PAD, DIVIDER_Y)
    card.text((COL_X, row), "Listen, rate, review", "regular", 24, GRAY, anchor="lm")
    return card


def podcast_card(podcast):
    art = load_artwork(podcast.artwork)
    card = Card(glow=art)
    card.artwork(art, PAD, ART_Y, ART)
    y = PAD + 8
    if podcast.author:
        card.text((COL_X, y), one_line(podcast.author, "regular", 26, COL_W), "regular", 26, GRAY)
        y += 40
    y = card.lines(COL_X, y, wrap(podcast.name, "bold", 48, COL_W, 3), "bold", 48, LABEL, 58)
    if podcast.description:
        y += 18
        room = DIVIDER_Y - 24 - y
        lines = wrap(podcast.description, "regular", 25, COL_W, max(0, min(4, int(room // 35))))
        card.lines(COL_X, y, lines, "regular", 25, GRAY, 35)
    row = card.footer(COL_X, W - PAD, DIVIDER_Y)
    card.text((COL_X, row), "Rate its episodes on Sonar", "regular", 24, GRAY, anchor="lm")
    return card


def profile_card(profile, avatar_url=None):
    card = Card()
    card.teal_wash()
    size = 168
    photo = load_artwork(avatar_url) if avatar_url else None
    if photo is not None:
        card.photo(photo, (W - size) / 2, 70, size)
    else:
        card.avatar(profile.username, (W - size) / 2, 70, size)
    name = one_line(f"@{profile.username}", "bold", 56, W - 2 * PAD)
    card.text((W / 2, 318), name, "bold", 56, LABEL, anchor="ms")
    if profile.logged_count:
        count = f"{profile.logged_count:,}"
        label = " episode logged" if profile.logged_count == 1 else " episodes logged"
        total = card.text_width(count, "bold", 30) + card.text_width(label, "regular", 30)
        x = (W - total) / 2
        card.text((x, 372), count, "bold", 30, LABEL, anchor="ls")
        card.text((x + card.text_width(count, "bold", 30), 372), label, "regular", 30, GRAY, anchor="ls")
    row = card.footer(PAD, W - PAD, DIVIDER_Y)
    card.text((PAD, row), "Follow me on Sonar", "regular", 24, GRAY, anchor="lm")
    return card


def list_card(sonar_list):
    urls = [item.artwork for item in sonar_list.items if item.artwork]
    unique = list(dict.fromkeys(urls))
    tiles = []
    for url in unique:
        if len(tiles) == 4:
            break
        image = load_artwork(url)
        if image is not None:
            tiles.append(image)
    card = Card(glow=tiles[0] if tiles else None)
    if len(tiles) >= 4:
        gap = 12
        half = (ART - gap) / 2
        for index, image in enumerate(tiles[:4]):
            card.artwork(image, PAD + (index % 2) * (half + gap), ART_Y + (index // 2) * (half + gap), half, shadow=False)
    else:
        card.artwork(tiles[0] if tiles else None, PAD, ART_Y, ART)

    y = PAD + 8
    card.text((COL_X, y), "A list on Sonar", "regular", 26, GRAY)
    y += 40
    y = card.lines(COL_X, y, wrap(sonar_list.title, "bold", 48, COL_W, 3), "bold", 48, LABEL, 58)
    if sonar_list.description:
        y += 16
        room = DIVIDER_Y - 70 - y
        lines = wrap(sonar_list.description, "regular", 25, COL_W, max(0, min(3, int(room // 35))))
        y = card.lines(COL_X, y, lines, "regular", 25, GRAY, 35)
    if sonar_list.item_count:
        y += 18
        noun = "entry" if sonar_list.item_count == 1 else "entries"
        card.text((COL_X, y), f"{sonar_list.item_count} {noun}", "semibold", 25, LABEL)
    row = card.footer(COL_X, W - PAD, DIVIDER_Y)
    _byline(card, sonar_list.username, row, suffix="")
    return card


def invite_card(page):
    """"@name invited you to Sonar": their photo (or initial), the invitation, and a 2x2 of the
    artwork they love or reviewed lately. `page` None is the generic invitation."""
    username = page.username if page else None
    art = []
    for url in (page.artwork if page else [])[:6]:
        if len(art) == 4:
            break
        image = load_artwork(url)
        if image is not None:
            art.append(image)

    card = Card(glow=art[0] if art else None)
    if not art:
        card.teal_wash()
    grid_x = W - PAD - ART
    if len(art) >= 4:
        gap = 12
        half = (ART - gap) / 2
        for index, image in enumerate(art[:4]):
            card.artwork(image, grid_x + (index % 2) * (half + gap), ART_Y + (index // 2) * (half + gap), half, shadow=False)
    elif art:
        card.artwork(art[0], grid_x, ART_Y, ART)
    else:
        _brand_mark(card.draw, s(grid_x + ART / 2), s(ART_Y + ART / 2 - 10), s(300), TEAL)

    col_w = grid_x - 56 - PAD
    y = PAD + 8
    size = 112
    photo = load_artwork(page.avatar_url) if page and page.avatar_url else None
    if photo is not None:
        card.photo(photo, PAD, y, size)
    elif username:
        card.avatar(username, PAD, y, size)
    else:
        card.artwork(None, PAD, y, size, shadow=False)
    y += size + 62
    if username:
        name = one_line(f"@{username}", "bold", 52, col_w)
        card.text((PAD, y), name, "bold", 52, LABEL, anchor="ls")
        y += 58
        card.text((PAD, y), "invited you to Sonar", "semibold", 40, TEAL, anchor="ls")
    else:
        card.text((PAD, y), "You're invited", "bold", 52, LABEL, anchor="ls")
        y += 58
        card.text((PAD, y), "to Sonar", "semibold", 40, TEAL, anchor="ls")
    y += 30
    # Broken by hand: wrapped to the column, "love" would sit alone on the second line.
    card.lines(PAD, y, ["Rate, review and remember", "the episodes you love"], "regular", 28, GRAY, 38)
    card.footer(PAD, PAD + col_w, DIVIDER_Y)
    return card


# --- Cache and response --------------------------------------------------------------------

_memory = OrderedDict()
_memory_lock = threading.Lock()
_brand_png = None


def brand_png():
    global _brand_png
    if _brand_png is None:
        _brand_png = brand_card().png()
    return _brand_png


def _cache_dir():
    configured = current_app.config.get("SONAR_OG_CACHE_DIR")
    return configured or os.path.join(current_app.instance_path, "sonar_og")


def _key_name(key):
    return hashlib.sha256(repr((RENDER_VERSION, key)).encode()).hexdigest()


def _memory_get(name):
    with _memory_lock:
        hit = _memory.get(name)
        if hit is None:
            return None
        expires, png = hit
        if time.monotonic() > expires:
            del _memory[name]
            return None
        _memory.move_to_end(name)
        return png


def _memory_put(name, png, ttl):
    with _memory_lock:
        _memory[name] = (time.monotonic() + ttl, png)
        _memory.move_to_end(name)
        while len(_memory) > MEMORY_ITEMS:
            _memory.popitem(last=False)


def _disk_get(name):
    path = os.path.join(_cache_dir(), f"{name}.png")
    try:
        if time.time() - os.path.getmtime(path) > DISK_TTL:
            return None
        with open(path, "rb") as handle:
            return handle.read()
    except OSError:
        return None


def _disk_put(name, png):
    directory = _cache_dir()
    try:
        os.makedirs(directory, exist_ok=True)
        temp = os.path.join(directory, f".{name}.{os.getpid()}.{threading.get_ident()}.tmp")
        with open(temp, "wb") as handle:
            handle.write(png)
        os.replace(temp, os.path.join(directory, f"{name}.png"))
        if random.random() < 0.02:
            _prune(directory)
    except OSError:
        current_app.logger.warning("sonar og: could not write the disk cache", exc_info=True)


def _prune(directory):
    cutoff = time.time() - DISK_TTL
    for entry in os.scandir(directory):
        try:
            if entry.is_file() and entry.stat().st_mtime < cutoff:
                os.remove(entry.path)
        except OSError:
            pass


def clear_memory_cache():
    with _memory_lock:
        _memory.clear()


def render(key, build):
    """Returns (png, cache_control). `build` returns a Card, or None when there's nothing to show."""
    name = _key_name(key)
    png = _memory_get(name)
    if png is not None:
        return png, CACHE_CONTROL_GOOD
    png = _disk_get(name)
    if png is not None:
        _memory_put(name, png, GOOD_TTL)
        return png, CACHE_CONTROL_GOOD

    _render_state.degraded = False
    try:
        card = build()
    except Exception:
        current_app.logger.warning("sonar og render failed: %s", key, exc_info=True)
        card = None
    if card is None:
        return brand_png(), CACHE_CONTROL_SHORT

    png = card.png()
    if _render_state.degraded:
        _memory_put(name, png, DEGRADED_TTL)
        return png, CACHE_CONTROL_SHORT
    _memory_put(name, png, GOOD_TTL)
    _disk_put(name, png)
    return png, CACHE_CONTROL_GOOD
