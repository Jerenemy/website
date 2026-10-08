// Content access. In production the works and the person come from the page itself: Flask
// renders them from app/data/portfolio.json into <script type="application/json" id="site-data">
// (templates/home.html), next to the rail it renders from the same items. The standalone demo
// (design/homepage-demo) has no such element and imports its data.js instead; production has
// no data.js, so it is only ever fetched there. This module also applies the ?n=<int>
// scale-test override (slice, or cycle with suffixed ids/titles), clamped to N_MAX so that a
// shared link cannot ask a visitor's machine for thousands of steps.
async function load() {
  const node = document.getElementById('site-data');
  if (!node) return import('../data.js');
  try {
    return JSON.parse(node.textContent);
  } catch (err) {
    // No works: main.js builds no scene, and the server-rendered list stands as the page.
    console.error('site-data is not valid JSON; the scene stays off', err);
    return { person: { name: '', links: [] }, works: [] };
  }
}
const { person, works: allWorks } = await load();

const params = new URLSearchParams(location.search);
const N_MAX = 64;   // the scale tests go to 40

function scaled(list, n) {
  if (!Number.isFinite(n) || n < 1 || !list.length) return list;
  const out = [];
  for (let i = 0; i < n; i++) {
    const src = list[i % list.length];
    const lap = Math.floor(i / list.length);
    out.push(lap === 0 ? src : { ...src, id: `${src.id}-${lap + 1}`, title: `${src.title} ${lap + 1}` });
  }
  return out;
}

const n = Math.min(N_MAX, parseInt(params.get('n') ?? '', 10));
export const works = scaled(allWorks, n);
export { person };
export const flags = {
  scaled: Number.isFinite(n) && n >= 1,       // the ?n= test: the server's rail is expected not to match
  skipIntro: params.get('skipIntro') === '1',
  noGL: params.get('nogl') === '1',
  // Motion QA. ?slow=k plays every integrated motion k times slower (CSS transitions are
  // not slowed); ?stay=1 lets the light go through a door without the link being followed.
  slow: Math.max(1, parseFloat(params.get('slow') ?? '') || 1),
  stay: params.get('stay') === '1',
};
