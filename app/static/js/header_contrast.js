(() => {
  const HEADER_CONTRAST = {
    STRATEGY: "blend", // "threshold" | "blend"
    PROBE_X_RATIOS: [0.2, 0.5, 0.8],
    PROBE_Y_RATIOS: [0.35, 0.65],
    // 0.0 -> switch to light text very easily, 1.0 -> only switch on near-black backgrounds.
    DARKNESS_ON_THRESHOLD: 0.34,
    SWITCH_HYSTERESIS: 0.01,
    MIN_BG_ALPHA_FOR_TONE: 0.02,
    // Blend mode: text color on very light backgrounds (set near black for maximum contrast).
    BLEND_LIGHT_BG_TEXT_RGB: [0, 0, 0],
    // Blend mode: text color on very dark backgrounds.
    BLEND_DARK_BG_TEXT_RGB: [247, 250, 252],
  };

  const BG_IMAGE_URL_RE = /url\((['"]?)(.*?)\1\)/i;
  const bgImageDarknessCache = new Map();

  let headerContrastTicking = false;
  let headerContrastInitialized = false;

  function clamp(value, min = 0, max = 1) {
    return Math.max(min, Math.min(max, value));
  }

  function parseColorToRgba(value) {
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
        a: rgbMatch[4] !== undefined ? clamp(Number.parseFloat(rgbMatch[4])) : 1,
      };
    }

    return null;
  }

  function relativeLuminance({ r, g, b }) {
    const toLinear = (channel) => {
      const c = channel / 255;
      return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4;
    };

    const R = toLinear(r);
    const G = toLinear(g);
    const B = toLinear(b);
    return 0.2126 * R + 0.7152 * G + 0.0722 * B;
  }

  function darknessFromRgba(rgba) {
    return clamp(1 - relativeLuminance(rgba));
  }

  function darknessToGrayRgba(darkness, alpha = 1) {
    const luminance = clamp(1 - darkness);
    const channel = Math.round(luminance * 255);
    return { r: channel, g: channel, b: channel, a: clamp(alpha) };
  }

  function shouldUseBlendContrast() {
    return HEADER_CONTRAST.STRATEGY === "blend";
  }

  function headerDarknessThreshold() {
    return clamp(HEADER_CONTRAST.DARKNESS_ON_THRESHOLD);
  }

  function applyGlassContrastTokens() {
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
  }

  function getConfiguredPageBackground() {
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
  }

  function normalizeRgbTuple(value, fallback) {
    if (!Array.isArray(value) || value.length !== 3) {
      return fallback;
    }
    return value.map((channel) => clamp(Math.round(Number(channel)), 0, 255));
  }

  function blendHeaderInkFromDarkness(useLightInk) {
    const darkInk = normalizeRgbTuple(HEADER_CONTRAST.BLEND_LIGHT_BG_TEXT_RGB, [0, 0, 0]);
    const lightInk = normalizeRgbTuple(HEADER_CONTRAST.BLEND_DARK_BG_TEXT_RGB, [247, 250, 252]);
    const ink = useLightInk ? lightInk : darkInk;
    return `rgb(${ink[0]} ${ink[1]} ${ink[2]})`;
  }

  function compositeRgba(fg, bg) {
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
  }

  function getCachedImageDarkness(imageUrl) {
    if (!imageUrl) {
      return null;
    }
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

        // 1x1 draw approximates average brightness cheaply.
        ctx.drawImage(img, 0, 0, 1, 1);
        const pixel = ctx.getImageData(0, 0, 1, 1).data;
        entry.value = darknessFromRgba({ r: pixel[0], g: pixel[1], b: pixel[2], a: 1 });
        entry.status = "ready";
        requestHeaderContrastUpdate();
      } catch (_err) {
        entry.status = "error";
      }
    });

    img.addEventListener("error", () => {
      entry.status = "error";
    });

    img.src = imageUrl;
    return null;
  }

  function getBackgroundImageDarkness(styles) {
    const bgImage = (styles.backgroundImage || "").trim();
    if (!bgImage || bgImage === "none") {
      return null;
    }

    const match = bgImage.match(BG_IMAGE_URL_RE);
    if (!match || !match[2]) {
      return null;
    }

    return getCachedImageDarkness(match[2]);
  }

  function getElementContentDarkness(element) {
    if (element instanceof HTMLImageElement) {
      const source = (element.currentSrc || element.src || "").trim();
      return getCachedImageDarkness(source);
    }

    if (element instanceof HTMLVideoElement) {
      const poster = (element.poster || "").trim();
      if (poster) {
        return getCachedImageDarkness(poster);
      }
    }

    return null;
  }

  function toneOverrideFromElement(element) {
    const toneOverride = element.closest("[data-header-tone]");
    if (!(toneOverride instanceof Element)) {
      return null;
    }
    const tone = toneOverride.getAttribute("data-header-tone");
    if (tone === "dark" || tone === "light") {
      return tone;
    }
    return null;
  }

  function sampleDarknessAtPoint(probeX, probeY, header) {
    const stack = document
      .elementsFromPoint(probeX, probeY)
      .filter((element) => element instanceof Element && element.closest(".site-header") !== header);

    if (stack.length === 0) {
      return darknessFromRgba(getConfiguredPageBackground());
    }

    // Topmost tone override wins.
    for (const element of stack) {
      const forcedTone = toneOverrideFromElement(element);
      if (forcedTone === "dark") return 1;
      if (forcedTone === "light") return 0;
    }

    // Composite all visible layers at this point from back to front.
    let effectiveColor = getConfiguredPageBackground();
    for (let idx = stack.length - 1; idx >= 0; idx -= 1) {
      const element = stack[idx];
      const styles = getComputedStyle(element);
      const elementOpacity = clamp(Number.parseFloat(styles.opacity || "1"));

      const bgImageDarkness = getBackgroundImageDarkness(styles);
      if (bgImageDarkness !== null && elementOpacity > 0) {
        const imageColor = darknessToGrayRgba(bgImageDarkness, elementOpacity);
        effectiveColor = compositeRgba(imageColor, effectiveColor);
      }

      const elementContentDarkness = getElementContentDarkness(element);
      if (elementContentDarkness !== null && elementOpacity > 0) {
        const contentColor = darknessToGrayRgba(elementContentDarkness, elementOpacity);
        effectiveColor = compositeRgba(contentColor, effectiveColor);
      }

      const bg = parseColorToRgba(styles.backgroundColor);
      if (bg && bg.a > HEADER_CONTRAST.MIN_BG_ALPHA_FOR_TONE && elementOpacity > 0) {
        const visibleBg = { ...bg, a: clamp(bg.a * elementOpacity) };
        effectiveColor = compositeRgba(visibleBg, effectiveColor);
      }
    }

    return darknessFromRgba(effectiveColor);
  }

  function detectHeaderBackdropDarkness(header) {
    const rect = header.getBoundingClientRect();
    const probeYs = HEADER_CONTRAST.PROBE_Y_RATIOS.map((ratio) =>
      Math.min(window.innerHeight - 1, Math.max(0, Math.round(rect.top + rect.height * ratio)))
    );

    header.classList.add("site-header--hit-test-pass-through");
    const darknessValues = (() => {
      try {
        return HEADER_CONTRAST.PROBE_X_RATIOS.flatMap((ratio) => {
          const probeX = Math.min(
            window.innerWidth - 1,
            Math.max(0, Math.round(window.innerWidth * ratio))
          );
          return probeYs.map((probeY) => sampleDarknessAtPoint(probeX, probeY, header));
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
  }

  function requestHeaderContrastUpdate() {
    // No-op: dynamic scroll updating is disabled by user request.
    // This empty function remains so that other scripts (like nav.js) don't throw an undefined error.
  }

  function initHeaderContrast() {
    if (headerContrastInitialized) {
      return;
    }
    headerContrastInitialized = true;

    applyGlassContrastTokens();

    // We only need to compute the initial contrast once based on the page background
    // Removing the aggressive scroll listeners entirely removes the "scroll jank".
    let header = document.querySelector(".site-header");
    if (header instanceof HTMLElement) {
      // Since we are no longer dynamically checking scroll depth, we can just use the static configured page background:
      let bgConfig = getConfiguredPageBackground();
      let darkness = darknessFromRgba(bgConfig);

      const onThreshold = headerDarknessThreshold();
      const shouldBeDark = darkness >= onThreshold;

      if (shouldUseBlendContrast()) {
        header.classList.add("site-header--blend-contrast");
        header.classList.toggle("site-header--on-dark", shouldBeDark);
        header.style.setProperty("--header-ink", blendHeaderInkFromDarkness(shouldBeDark));
      } else {
        header.classList.remove("site-header--blend-contrast");
        header.style.removeProperty("--header-ink");
        header.classList.toggle("site-header--on-dark", shouldBeDark);
      }
    }
  }

  window.initHeaderContrast = initHeaderContrast;
  window.requestHeaderContrastUpdate = requestHeaderContrastUpdate;
})();
