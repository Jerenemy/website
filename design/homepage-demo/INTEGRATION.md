# The homepage in Flask

**One copy of the code.** The runtime lives in `app/static/home/`: `src/` (plain ES modules,
no build step), `styles.css` (whose values come from the site's `static/site/tokens.css`, linked here as `site`), `vendor/`, and a `package.json` that marks it ES
modules for Node. Here `src`, `styles.css` and `vendor` are relative symlinks into it, so this
demo, `tools/` (regress, shots, the proofs) and the harness run the production code.

**Data.** Works are the published items of `app/data/portfolio.json`, in `sort_order`, each
with `kind`, `line` and `href` (`app/portfolio/store.py`; older items load with empty
defaults), edited in `/admin/portfolio` (titles up to 24 characters). An eleventh work needs
no code. `data.js` is this demo's copy only (it keeps EAR, which the site ships unpublished
until `/ear/` answers).

**Page.** `GET /` renders `app/templates/home.html`, standalone (not `base.html`): exactly
the markup `src/interface.js` adopts (the body equals this `index.html` with relative links),
plus the works as JSON in `<script type="application/json" id="site-data">`. `src/content.js`
reads it, or imports `../data.js` when it is absent (this demo). `?n=` (at most 64),
`?nogl=1`, `?skipIntro=1` work on both. The head script takes the scene's layout only with
WebGL 2 and import maps, and gives it back to the list on any error before `window.__demo`
exists (a module that failed to load, resolve or evaluate); `/#contact` goes to `/contact`.
`home.html` preloads every module but `src/probe.js`, which the QA hooks import on demand.
If the markup drifts from the data, interface.js rebuilds the rail and warns in the console.
`GET /contact` renders `app/templates/contact.html` in the same type and greys, posting
through `static/js/contact.js` to `/api/contact` (form-encoded without JavaScript).

**three.js.** `vendor/three-r186/three.module.min.js` is npm `three@0.186.1`
(`three.module.js` with `three.core.js` inlined, licence kept), rebuilt byte-identically by
`esbuild vendor/three.module.js --bundle --format=esm --minify --legal-comments=eof`
(esbuild 0.28.2). The unminified sources beside it are its build input and never deploy. A
new revision gets a new folder: nginx caches this one for a year as immutable.

**Shipping.** The repository `.gitignore` is an allowlist; `app/static/home/**`, the
templates, `tests/test_home.py` and this folder (not `shots/`) have entries, and that test
fails if a needed file is ignored. nginx (`deploy/nginx/personal_website.conf`) gzips CSS,
JS, JSON and SVG over HTTP/2. Deploy and rollback: README, "Deploying the homepage".
