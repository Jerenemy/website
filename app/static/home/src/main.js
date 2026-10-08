// The entry. The theme's world first, then the scene: src/theme.js loads the active theme's
// scene module (the page's <html data-scene>, or ?theme=<name> on the standalone demo) and lays
// its config over src/config.js, and only then is src/app.js (the composition root) imported, so
// every module that reads the config at evaluation time, shader constants included, reads the
// themed values. A theme that cannot be loaded leaves the scene's own world (a warning in the
// console, never a broken page); index.html's error listener withdraws the scene's layout for
// any error that escapes before window.__demo exists.
import { loadTheme } from './theme.js';

await loadTheme();
await import('./app.js');
