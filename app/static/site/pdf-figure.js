// A figure drawn from its PDF (templates/_ui.html, ui.pdf_figure): the first page is rendered
// by pdf.js from the vector original, at the screen's own resolution, over the image that stands
// in for it until then (and for good, if the PDF or pdf.js cannot be had). Each figure loads its
// PDF only as it nears the screen, and draws again when its width changes.
const VENDOR = new URL('../vendor/pdfjs-6.4.299/', import.meta.url);
const MAX_PIXELS = 16e6;   // a canvas larger than this fails on iOS Safari
const MIN_DENSITY = 3;     // never below 3 device px per CSS px: the type stays sharp when zoomed in

let pdfjs = null;
async function lib() {
  if (!pdfjs) {
    pdfjs = await import(new URL('pdf.min.js', VENDOR).href);
    pdfjs.GlobalWorkerOptions.workerSrc = new URL('pdf.worker.min.js', VENDOR).href;
  }
  return pdfjs;
}

async function draw(figure, state) {
  const frame = figure.querySelector('.figure__frame');
  const width = frame.clientWidth;
  if (!width || width === state.width) return;
  state.width = width;
  if (!state.page) {
    const { getDocument } = await lib();
    const doc = await getDocument({ url: figure.dataset.pdf, standardFontDataUrl: new URL('standard_fonts/', VENDOR).href }).promise;
    state.page = await doc.getPage(1);
  }
  const base = state.page.getViewport({ scale: 1 });
  let density = Math.max(devicePixelRatio || 1, MIN_DENSITY);
  const height = width * base.height / base.width;
  density = Math.min(density, Math.sqrt(MAX_PIXELS / (width * height)));
  const viewport = state.page.getViewport({ scale: (width * density) / base.width });

  // Draw off screen, then swap: the figure never shows a half-drawn page.
  const canvas = document.createElement('canvas');
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  canvas.setAttribute('aria-hidden', 'true');
  state.task?.cancel();
  state.task = state.page.render({ canvas, viewport });
  try { await state.task.promise; } catch (e) { if (e?.name === 'RenderingCancelledException') return; throw e; }
  frame.querySelector('canvas')?.remove();
  frame.append(canvas);
  figure.classList.add('is-drawn');
}

function watch(figure) {
  const state = { width: 0, page: null, task: null };
  const run = () => draw(figure, state).catch((e) => console.warn('PDF figure kept its image:', e));
  let timer = 0;
  new ResizeObserver(() => { if (state.page) { clearTimeout(timer); timer = setTimeout(run, 150); } })
    .observe(figure.querySelector('.figure__frame'));
  return run;
}

const figures = document.querySelectorAll('.figure--pdf[data-pdf]');
if (figures.length) {
  const io = new IntersectionObserver((entries) => {
    for (const e of entries) {
      if (!e.isIntersecting) continue;
      io.unobserve(e.target);
      watch(e.target)();
    }
  }, { rootMargin: '800px 0px' });
  figures.forEach((f) => io.observe(f));
}
