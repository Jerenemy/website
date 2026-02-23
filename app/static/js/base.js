document.documentElement.setAttribute("data-theme", "light");

const parseColorToRgb = (value) => {
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
      };
    }
    return {
      r: parseInt(hex.slice(0, 2), 16),
      g: parseInt(hex.slice(2, 4), 16),
      b: parseInt(hex.slice(4, 6), 16),
    };
  }

  const rgbMatch = input.match(
    /^rgba?\(\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})\s*,\s*([0-9]{1,3})(?:\s*,\s*[0-9.]+\s*)?\)$/i
  );
  if (rgbMatch) {
    return {
      r: Math.min(255, parseInt(rgbMatch[1], 10)),
      g: Math.min(255, parseInt(rgbMatch[2], 10)),
      b: Math.min(255, parseInt(rgbMatch[3], 10)),
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
  const rgb = parseColorToRgb(bgValue);
  if (!rgb) return;

  const isDarkBackground = relativeLuminance(rgb) < 0.35;
  if (isDarkBackground) {
    root.style.setProperty("--on-glass", "#f7fafc");
    root.style.setProperty("--on-glass-muted", "rgba(247, 250, 252, 0.82)");
  } else {
    root.style.setProperty("--on-glass", "#111111");
    root.style.setProperty("--on-glass-muted", "rgba(17, 17, 17, 0.78)");
  }
};

window.addEventListener("DOMContentLoaded", () => {
  applyGlassContrastTokens();

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
  }, { passive: true });

  nav.addEventListener("click", (event) => {
    if (event.target instanceof Element && event.target.matches("a")) {
      if (!mq.matches) {
        setCollapsed(true);
      }
    }
  });

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.dataset.collapsed === "false") {
      setCollapsed(true);
    }
  });
});
