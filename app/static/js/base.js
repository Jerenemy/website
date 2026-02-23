document.documentElement.setAttribute("data-theme", "light");

const parseColorToRgba = (value) => {
  if (!value) return null;
  const input = value.trim();

  const hexMatch = input.match(/^#([0-9a-f]{3}|[0-9a-f]{6})$/i);
  if (hexMatch) {
    const hex = hexMatch[1];
    if (hex.length === 3) {
      return {
        r: parseInt(hex[0] + hex[0], 16),
        g: parseInt(hex[1] + hex[1], 16),
        b: parseInt(hex[2] + hex[2], 16),
        a: 1,
      };
    }
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
      a: 1,
    };
  }

  const rgbMatch = input.match(
    /^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})(?:\s*,\s*([0-9.]+)\s*)?\)$/i
  );
  if (rgbMatch) {
    return {
      r: Math.min(255, parseInt(rgbMatch[1], 10)),
      g: Math.min(255, parseInt(rgbMatch[2], 10)),
      b: Math.min(255, parseInt(rgbMatch[3], 10)),
      a:
        rgbMatch[4] !== undefined
          ? Math.max(0, Math.min(1, Number.parseFloat(rgbMatch[4])))
          : 1,
    };
  }

  return null;
};

const relativeLuminance = ({ r, g, b }) => {
  const toLinear = (channel) => {
    const c = channel / 255;
    return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
  };
  const R = toLinear(r);
  const G = toLinear(g);
  const B = toLinear(b);
  return 0.2126 * R + 0.7152 * G + 0.0722 * B;
};

const applyGlassContrastTokens = () => {
  const root = document.documentElement;
  const styles = getComputedStyle(root);
  const bgValue = styles.getPropertyValue("--bg").trim() || styles.backgroundColor;
  const rgba = parseColorToRgba(bgValue);
  if (!rgba) return;

  const isDarkBackground = relativeLuminance(rgba) < 0.35;
  if (isDarkBackground) {
    root.style.setProperty("--on-glass", "#f7fafc");
    root.style.setProperty("--on-glass-muted", "rgba(247, 250, 252, 0.82)");
  } else {
    root.style.setProperty("--on-glass", "#111111");
    root.style.setProperty("--on-glass-muted", "rgba(17, 17, 17, 0.78)");
  }
};

const HEADER_PROBE_X_RATIOS = [0.2, 0.5, 0.8];
const HEADER_PROBE_Y_RATIOS = [0.35, 0.65];
// 0.0 -> switch to light text very easily, 1.0 -> only switch on near-black backgrounds.
const HEADER_DARKNESS_ON_THRESHOLD = 0.45;
const HEADER_SWITCH_HYSTERESIS = 0.01;
const HEADER_MIN_BG_ALPHA_FOR_TONE = 0.02;
const BG_IMAGE_URL_RE = /url\((['"]?)(.*?)\1\)/i;
const bgImageDarknessCache = new Map();

const headerDarknessThreshold = () =>
  Math.max(0, Math.min(1, HEADER_DARKNESS_ON_THRESHOLD));

const getConfiguredPageBackground = () => {
  const rootStyles = getComputedStyle(document.documentElement);
  const fromThemeVar = parseColorToRgba(rootStyles.getPropertyValue("--bg").trim());
  if (fromThemeVar) {
    return { ...fromThemeVar, a: 1 };
  }

  const bodyColor = parseColorToRgba(getComputedStyle(document.body).backgroundColor);
  if (bodyColor) {
    return { ...bodyColor, a: 1 };
  }

  return { r: 255, g: 255, b: 255, a: 1 };
};

const compositeRgba = (fg, bg) => {
  const a = fg.a + bg.a * (1 - fg.a);
  if (a <= 0) {
    return { r: 0, g: 0, b: 0, a: 0 };
  }
  return {
    r: Math.round((fg.r * fg.a + bg.r * bg.a * (1 - fg.a)) / a),
    g: Math.round((fg.g * fg.a + bg.g * bg.a * (1 - fg.a)) / a),
    b: Math.round((fg.b * fg.a + bg.b * bg.a * (1 - fg.a)) / a),
    a,
  };
};

const darknessFromRgba = (rgba) => {
  const luminance = relativeLuminance(rgba);
  return Math.max(0, Math.min(1, 1 - luminance));
};

const getBackgroundImageDarkness = (styles) => {
  const bgImage = (styles.backgroundImage || "").trim();
  if (!bgImage || bgImage === "none") {
    return null;
  }

  const match = bgImage.match(BG_IMAGE_URL_RE);
  if (!match || !match[2]) {
    return null;
  }

  const imageUrl = match[2];
  if (bgImageDarknessCache.has(imageUrl)) {
    const cached = bgImageDarknessCache.get(imageUrl);
    return cached.status === "ready" ? cached.value : null;
  }

  const entry = { status: "loading", value: null };
  bgImageDarknessCache.set(imageUrl, entry);

  const img = new Image();
  img.decoding = "async";
  img.addEventListener("load", () => {
    try {
      const canvas = document.createElement("canvas");
      canvas.width = 1;
      canvas.height = 1;
      const ctx = canvas.getContext("2d");
      if (!ctx) {
        entry.status = "error";
        return;
      }

      // Draw to 1x1 to approximate image average color quickly.
      ctx.drawImage(img, 0, 0, 1, 1);
      const pixel = ctx.getImageData(0, 0, 1, 1).data;
      entry.value = darknessFromRgba({ r: pixel[0], g: pixel[1], b: pixel[2], a: 1 });
      entry.status = "ready";
      scheduleHeaderContrastUpdate();
    } catch (_err) {
      entry.status = "error";
    }
  });
  img.addEventListener("error", () => {
    entry.status = "error";
  });
  img.src = imageUrl;

  return null;
};

const elementDarknessFromBackground = (element) => {
  const chain = [];
  let current = element;
  while (current && current instanceof Element) {
    chain.push(current);
    if (current === document.documentElement) {
      break;
    }
    current = current.parentElement;
  }

  let effectiveColor = getConfiguredPageBackground();
  let imageDarkness = 0;
  for (let idx = chain.length - 1; idx >= 0; idx -= 1) {
    const node = chain[idx];
    const styles = getComputedStyle(node);

    const bgImageDarkness = getBackgroundImageDarkness(styles);
    if (bgImageDarkness !== null) {
      imageDarkness = Math.max(imageDarkness, bgImageDarkness);
    }

    const bg = parseColorToRgba(styles.backgroundColor);
    if (bg && bg.a > HEADER_MIN_BG_ALPHA_FOR_TONE) {
      effectiveColor = compositeRgba(bg, effectiveColor);
    }
  }

  return Math.max(darknessFromRgba(effectiveColor), imageDarkness);
};

const resolveDarknessFromHit = (hit, header) => {
  if (!(hit instanceof Element)) {
    return darknessFromRgba(getConfiguredPageBackground());
  }

  if (header && hit.closest(".site-header") === header) {
    return darknessFromRgba(getConfiguredPageBackground());
  }

  const toneOverride = hit.closest("[data-header-tone]");
  if (toneOverride instanceof Element) {
    const tone = toneOverride.getAttribute("data-header-tone");
    if (tone === "dark" || tone === "light") {
      return tone === "dark" ? 1 : 0;
    }
  }

  return elementDarknessFromBackground(hit);
};

const detectHeaderBackdropDarkness = (header) => {
  const rect = header.getBoundingClientRect();
  const probeYs = HEADER_PROBE_Y_RATIOS.map((ratio) =>
    Math.min(
      window.innerHeight - 1,
      Math.max(0, Math.round(rect.top + rect.height * ratio))
    )
  );

  header.classList.add("site-header--hit-test-pass-through");
  const darknessValues = (() => {
    try {
      return HEADER_PROBE_X_RATIOS.flatMap((ratio) => {
        const probeX = Math.min(
          window.innerWidth - 1,
          Math.max(0, Math.round(window.innerWidth * ratio))
        );
        return probeYs.map((probeY) =>
          resolveDarknessFromHit(document.elementFromPoint(probeX, probeY), header)
        );
      });
    } finally {
      header.classList.remove("site-header--hit-test-pass-through");
    }
  })();

  if (darknessValues.length === 0) {
    return darknessFromRgba(getConfiguredPageBackground());
  }
  const total = darknessValues.reduce((sum, value) => sum + value, 0);
  return total / darknessValues.length;
};

const applyHeaderContrastFromBackdrop = () => {
  const header = document.querySelector(".site-header");
  if (!(header instanceof HTMLElement)) {
    return;
  }

  // `threshold` is the exact darkness needed to switch into light header text.
  // Hysteresis only applies when switching back to dark text to avoid flicker.
  const onThreshold = headerDarknessThreshold();
  const hysteresis = Math.max(0, Math.min(0.2, HEADER_SWITCH_HYSTERESIS));
  const offThreshold = Math.max(0, onThreshold - hysteresis);
  const darkness = detectHeaderBackdropDarkness(header);

  const isCurrentlyDark = header.classList.contains("site-header--on-dark");
  const shouldBeDark = isCurrentlyDark
    ? darkness >= offThreshold
    : darkness >= onThreshold;
  header.classList.toggle("site-header--on-dark", shouldBeDark);
};

let headerContrastTicking = false;
const scheduleHeaderContrastUpdate = () => {
  if (headerContrastTicking) {
    return;
  }
  headerContrastTicking = true;
  window.requestAnimationFrame(() => {
    headerContrastTicking = false;
    applyHeaderContrastFromBackdrop();
  });
};

window.addEventListener("DOMContentLoaded", () => {
  applyGlassContrastTokens();
  scheduleHeaderContrastUpdate();

  const toggle = document.querySelector(".nav-toggle");
  const nav = document.getElementById("site-nav");

  if (!toggle || !nav) {
    return;
  }

  const setCollapsed = (collapsed) => {
    nav.dataset.collapsed = collapsed ? "true" : "false";
    toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
  };

  const mq = window.matchMedia("(min-width: 769px)");
  const handleBreakpoint = (event) => {
    if (event.matches) {
      toggle.setAttribute("aria-expanded", "false");
      nav.dataset.collapsed = "false";
    } else {
      setCollapsed(true);
    }
  };

  // initialize state based on current viewport
  handleBreakpoint(mq);
  if (typeof mq.addEventListener === "function") {
    mq.addEventListener("change", handleBreakpoint);
  } else if (typeof mq.addListener === "function") {
    mq.addListener(handleBreakpoint);
  }

  toggle.addEventListener("click", () => {
    const isCollapsed = nav.dataset.collapsed !== "false";
    setCollapsed(!isCollapsed);
  });

  const collapseIfMobile = () => {
    if (!mq.matches && nav.dataset.collapsed === "false") {
      setCollapsed(true);
    }
  };

  // click outside nav/toggle collapses on mobile
  document.addEventListener("click", (event) => {
    const target = event.target;
    if (!(target instanceof Element)) return;
    const clickedInsideNav = nav.contains(target) || toggle.contains(target);
    if (!clickedInsideNav) {
      collapseIfMobile();
    }
  });

  // scrolling collapses on mobile
  document.addEventListener("scroll", () => {
    collapseIfMobile();
    scheduleHeaderContrastUpdate();
  }, { passive: true });

  window.addEventListener("resize", scheduleHeaderContrastUpdate, { passive: true });

  nav.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.matches("a")) {
      if (!mq.matches) {
        setCollapsed(true);
      }
    }
    scheduleHeaderContrastUpdate();
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.dataset.collapsed === "false") {
      setCollapsed(true);
    }
    scheduleHeaderContrastUpdate();
  });

  window.addEventListener("load", scheduleHeaderContrastUpdate, { once: true });
});
