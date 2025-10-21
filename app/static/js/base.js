document.documentElement.setAttribute("data-theme", "dark");

window.addEventListener("DOMContentLoaded", () => {
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
