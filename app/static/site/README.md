# The site's design system

One look for every page. The homepage scene is the reference; every other page speaks its
language: near-black ground, neutral greys, one family in two voices, hairlines instead of
boxes, numbers for order, and **one point of colour per page that means "you are here"**.

## Where everything lives

| File | What it holds | Change it to… |
| --- | --- | --- |
| `static/site/tokens.css` | **Every value**: colour, type, space, radii, motion. | change the feel of the whole site, homepage included. |
| `static/site/themes/<name>/` | A theme: `theme.css` (only the tokens it overrides) and, when it changes the homepage's world, `scene.js` (its material, air, light and dust: `static/home/src/theme.js` is the contract), with any fonts or textures it ships. | add a look (a `theme.css` alone is enough for a tokens-only theme). |
| `static/site/site.css` | Every piece (head, sections, lists, actions, devices, forms, tables, pager, motion). No values of its own. | change how a piece is built. |
| `static/site/site.js` | Arrival (reveal) and leaving (page fade where View Transitions are missing). | change the motion's logic (timings are tokens). |
| `static/site/works/<work>.css` | A work's *rendering of itself* (an app screen), scoped to `.app-<work>`. | draw a product. |
| `templates/layout.html` | The page: head, frame, main, pager, foot. | change every page's skeleton. |
| `templates/partials/_ui.html` | The pieces as Jinja macros. | add a piece. |
| `templates/partials/_theme.html` | The icon, the tokens and the active theme, for any `<head>`. | — |
| `templates/partials/_themes.html` | The theme switcher: every theme on disk, the current one marked; in every page's foot and the homepage's corner. | — |
| `app/design.py` | The active theme, the switcher's rows, the frame's links, the page's place in the works loop. | — |

### Themes

* Default: `SITE_THEME` in the environment (`void` = `tokens.css` alone, and the scene's own world).
* Switching: the switcher in every page's frame, or `?theme=<name>` on any URL; a cookie keeps it for
  the visit, `?theme=void` clears it. The standalone demo (`design/homepage-demo`) takes the same
  `?theme=<name>`.
* New theme: a folder `themes/<name>/` with a `theme.css` whose `:root { … }` overrides only what
  changes; it appears in the switcher at once (an empty file named `hidden` beside it keeps it
  out of the switcher while `?theme=<name>` still shows it). The homepage's interface is drawn in `--world-*`
  over the scene's air, so a theme whose air is bright sets them dark (`--world-bg` is also what
  the canvas fades from and to, so it should sit near the air's tone), and the light in the scene
  is `--accent`.
* A theme that changes the **world** (the blocks, the air, the light, the dust) adds a `scene.js`
  beside its `theme.css`: a plain ES module with no imports, exporting `{ config, glsl }`.
  `config` lays values over `static/home/src/config.js` by name (the key light, the mist, the halo,
  the motes…); `glsl` holds up to four shader chunks, `surface` (the blocks' material, and optionally
  `surfaceCover`, which carves the blocks' outline: rounded corners, a lumpy edge), `air`, `light`
  and `mote`, each a function of a documented struct. The contract, the structs and
  the void's own implementations (the reference for each hook) are in `static/home/src/theme.js`.
  Fonts and textures a theme needs live in its folder and ship with it (the repository's
  `.gitignore` allowlists `themes/**`). What a theme must keep: the paradox rule (no surface may
  depend on distance along the view), the three face tones, one light.

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
{% import "partials/_ui.html" as ui with context %}  {# with context: the pieces read work_nav #}
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
* `.figure` with `figcaption` (`<span class="no">FIG 01</span><span class="t">…</span>`); `.figure--photo`
  keeps a photograph within the screen's height (its `img` gives `style="--ratio: 3 / 2"`).
* `.pair`: a large figure with its words beside it (`<div class="pair"><figure>…</figure><div>…</div></div>`); the words stay in view.
* `ui.pdf_figure(pdf, image, alt, …)`: a figure drawn from its PDF's first page by pdf.js, sharp at any
  density and zoom, its image standing in until then; the page loads `site/pdf-figure.js` as a module.
* `.actions`: a row of `ui.open` actions inside a section.
* `.note`, `.small`, `.link` (an inline link outside `.prose`).

Mark anything that should rise into place with `data-reveal` (the macros already do).

## Motion

Between pages the frame (name and links) holds still while the rest of the old page fades
(`--t-fast`) and the new one arrives in reading order, each piece rising `--rise` a
`--stagger` apart (`--t-slow`). Browsers with cross-document View Transitions do the leaving
themselves; others get the same fade from `site.js`. A page reached through the homepage's door
rises out of the void. Under reduced motion nothing moves.
