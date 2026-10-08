// Single source of truth for the homepage. In production this object is rendered by Flask
// from app/data/portfolio.json (+ site settings); in the demo it is static.
// Adding a work = appending one object here. Nothing else may need to change.
export const person = {
  name: 'Jeremy Zay',
  links: [
    { id: 'resume',   label: 'Résumé',   href: 'https://jeremyzay.com/resume' },
    { id: 'writing',  label: 'Writing',  href: 'https://jeremyzay.com/blog' },
    { id: 'github',   label: 'GitHub',   href: 'https://github.com/Jerenemy' },
    { id: 'linkedin', label: 'LinkedIn', href: 'https://www.linkedin.com/in/jeremy-zay/' },
    { id: 'contact',  label: 'Contact',  href: 'https://jeremyzay.com/contact' },   // a route of its own: the section it anchored to is on the page this one replaces
  ],
};

// kind is one of: 'research' | 'engineering' | 'product' | 'play'
export const works = [
  { id: 'diffusion',  title: 'Diffusion',              kind: 'research',    line: 'Diffusion models that design molecules for mutant p53', href: 'https://jeremyzay.com/poster-diffusion-2025', image: 'img/diffusion.png' },
  { id: 'reinforcement-learning', title: 'Reinforcement Learning', kind: 'research', line: 'RL-guided molecule generation for p53 Y220C', href: 'https://jeremyzay.com/poster-rl-2024', image: 'img/reinforcement-learning.jpg' },
  { id: 'curve-explorer', title: 'Curve Explorer',     kind: 'engineering', line: 'Curve workflow in ONYX Pro at Chatham Financial',       href: 'https://jeremyzay.com/blog/chatham-financial-internship', image: null },
  { id: 'karchive',   title: 'KArchive',               kind: 'product',     line: 'Searchable video archive with cited answers',           href: 'https://karchive.dad', image: 'img/karchive.svg' },
  { id: 'zaychess',   title: 'Zaychess',               kind: 'product',     line: 'A chess app built to feel good to play',                href: 'https://jeremyzay.com/zaychess', image: 'img/zaychess.png' },
  { id: 'zaybot',     title: 'ZayBot',                 kind: 'engineering', line: 'An AlphaZero-style chess engine',                       href: 'https://jeremyzay.com/blog/zaybot', image: null },
  { id: 'polydiff',   title: 'Polydiff',               kind: 'research',    line: 'A diffusion model that draws polygons',                 href: 'https://jeremyzay.com/blog/polydiff', image: null },
  { id: 'sonar',      title: 'Sonar',                  kind: 'product',     line: 'Podcast ratings and reviews for iOS',                   href: 'https://jeremyzay.com/sonar', image: 'img/sonar.png' },
  { id: 'ear',        title: 'EAR',                    kind: 'research',    line: 'Audio-visual retrieval',                                href: 'https://jeremyzay.com/ear/', image: null },
  { id: 'asteroids',  title: 'Asteroids',              kind: 'play',        line: 'The arcade classic, rebuilt in PyGame',                 href: 'https://jeremyzay.com/game', image: 'img/asteroids.png' },
];
