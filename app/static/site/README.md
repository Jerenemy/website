# The site's design system

One look for every page. The homepage scene is the reference; every other page speaks its
language: near-black ground, neutral greys, one family in two voices, hairlines instead of
boxes, numbers for order, and **one point of colour per page that means "you are here"**.

## Where everything lives

| File | What it holds | Change it to… |
| --- | --- | --- |
| `static/site/tokens.css` | **Every value**: colour, type, space, radii, motion. | change the feel of the whole site, homepage included. |
| `static/site/themes/<name>.css` | A theme: only the tokens it overrides. | add a look (`paper.css` is the example). |
| `static/site/site.css` | Every piece (head, sections, lists, actions, devices, forms, tables, pager, motion). No values of its own. | change how a piece is built. |
| `static/site/site.js` | Arrival (reveal) and leaving (page fade where View Transitions are missing). | change the motion's logic (timings are tokens). |
| `static/site/works/<work>.css` | A work's *rendering of itself* (an app screen), scoped to `.app-<work>`. | draw a product. |
| `templates/layout.html` | The page: head, frame, main, pager, foot. | change every page's skeleton. |
| `templates/_ui.html` | The pieces as Jinja macros. | add a piece. |
| `templates/_theme.html` | The icon, the tokens and the active theme, for any `<head>`. | — |
| `app/design.py` | The active theme, the frame's links, the page's place in the works loop. | — |

### Themes

* Default: `SITE_THEME` in the environment (`void` = `tokens.css` alone).
* Preview: add `?theme=paper` to any URL; a cookie keeps it for the visit, `?theme=void` clears it.
* New theme: create `themes/<name>.css` with a `:root { … }` that overrides only what changes.
  Keep the `--world-*` values dark: the homepage scene's air is rendered, not styled.
* The homepage reads the tokens too: its interface greys are `--world-*`, its type and curve are
  the site's, and the light in the scene is `--accent` (`static/home/src/config.js`).

## Rules

1. **No raw values outside `tokens.css`.** A page or a piece never writes a colour, a font, a
   size or a duration; it uses a token. (The one exception: a work's rendering of itself.)
2. **Two voices.** The LABEL (`.label`; 11 px, uppercase, tracked) names, numbers and navigates.
   The TEXT (sentence case) is read. Titles are TEXT, large and light (`--title-weight`).
3. **One hue, once.** `--accent` appears only as the `.here` dot in the page's head: the
   homepage's light, carried onto the page it led to. Never on text, never on a button.
4. **Lines, not boxes.** Sections are divided by `--rule`; things to act on sit on a `--hair`.
   No cards, no fills behind text, no shadows except a device's.
5. **Numbers for order.** Sections, points and list rows are numbered `01, 02…` in the label voice.
6. **One action style.** `ui.open(...)` (the homepage's OPEN): a label on a hairline with the
   arrow that leaves. There are no filled buttons.
7. **Every page opens the same way** (`ui.head`): where it sits, the title, its one line, its
   actions. A work's page is placed in the loop automatically (`NN / NN · KIND`).
8. **Nothing without a reason.** No taglines, no decoration, no emoji.

## Showing the work

A page about a product may render the product itself. The rendering sits in a neutral device
(`ui.show(..., device="window" | "phone" | "plain")`) and **inside the device** the product may
wear its own colours and type, styled in `static/site/works/<work>.css` and scoped to
`.app-<work>`. Outside the device, the page is the site's. Screenshots go in the same devices.

## Building a page

```jinja
{% extends "layout.html" %}
{% import "_ui.html" as ui with context %}      {# with context: the pieces read work_nav #}
{% block title %}Name · Jeremy Zay{% endblock %}
{% block description %}One sentence for search and previews.{% endblock %}
{% block content %}
  {% call ui.head("Title", line="The one line.") %}
    {{ ui.open("https://…", "App Store", external=True) }}
  {% endcall %}
  {{ ui.tabs([(url, "Overview", True), (url2, "Support", False)]) }}   {# a work with pages of its own #}

  {% call ui.sect("01", "Section name") %}
    <h2 class="sect__title">A sentence that heads it.</h2>
    <div class="prose"><p>…</p></div>
  {% endcall %}

  {% call ui.show("02", "Feature", "One or two sentences.", device="window", flip=True) %}
    <img src="…" alt="…">
  {% endcall %}
{% endblock %}
{% block foot %}<ul><li><a href="…">Privacy</a></li></ul>{% endblock %}
```

Pieces available inside sections (all in `site.css`):

* `.prose`: reading text (paragraphs, `h2`, `h3`, lists, quotes, code, tables); `.lede` for the
  first paragraph.
* `.points`: three or four numbered claims side by side (`<ol class="points"><li><span class="no">01</span><h3>…</h3><p>…</p></li>`).
* `.index`: a numbered list of rows (`.index__row` > `.index__no`, `.index__title`, `.index__meta`,
  `.index__line`); rows that are links slide on hover. As an FAQ: `<details class="index__item">`
  with the row as its `<summary>` and the answer in `.index__answer`.
* `.facts`: key / value pairs (`<dl class="facts"><div><dt>…</dt><dd>…</dd></div>`).
* `.form` > `.field` (label + input on a hairline), `.open.send` to submit, `.status` for the outcome.
* `.table`: data tables.
* `.figure` with `figcaption` (`<span class="no">FIG 01</span><span class="t">…</span>`).
* `.actions`: a row of `ui.open` actions inside a section.
* `.note`, `.small`, `.link` (an inline link outside `.prose`).

Mark anything that should rise into place with `data-reveal` (the macros already do).

## Motion

Between pages the frame (name and links) holds still while the rest of the old page fades
(`--t-fast`) and the new one arrives in reading order, each piece rising `--rise` a
`--stagger` apart (`--t-slow`). Browsers with cross-document View Transitions do the leaving
themselves; others get the same fade from `site.js`. A page reached through the homepage's door
rises out of the void. Under reduced motion nothing moves.
