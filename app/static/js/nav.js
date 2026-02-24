(() => {
  let navInitialized = false;

  function notifyHeaderContrastEngine() {
    if (typeof window.requestHeaderContrastUpdate === "function") {
      window.requestHeaderContrastUpdate();
    }
  }

  function initSiteNav() {
    if (navInitialized) {
      return;
    }
    navInitialized = true;

    const toggle = document.querySelector(".nav-toggle");
    const nav = document.getElementById("site-nav");
    const header = document.querySelector(".site-header");

    const setCollapsed = (collapsed) => {
      nav.dataset.collapsed = collapsed ? "true" : "false";
      if (header) {
        header.dataset.mobileMenuOpen = collapsed ? "false" : "true";
      }
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
      notifyHeaderContrastEngine();
    };

    handleBreakpoint(mq);
    if (typeof mq.addEventListener === "function") {
      mq.addEventListener("change", handleBreakpoint);
    } else if (typeof mq.addListener === "function") {
      mq.addListener(handleBreakpoint);
    }

    toggle.addEventListener("click", () => {
      const isCollapsed = nav.dataset.collapsed !== "false";
      setCollapsed(!isCollapsed);
      notifyHeaderContrastEngine();
    });

    const collapseIfMobile = () => {
      if (!mq.matches && nav.dataset.collapsed === "false") {
        setCollapsed(true);
      }
    };

    document.addEventListener("click", (event) => {
      const target = event.target;
      if (!(target instanceof Element)) return;

      const clickedInsideNav = nav.contains(target) || toggle.contains(target);
      if (!clickedInsideNav) {
        collapseIfMobile();
      }
    });

    document.addEventListener(
      "scroll",
      () => {
        collapseIfMobile();
        notifyHeaderContrastEngine();
      },
      { passive: true }
    );

    nav.addEventListener("click", (event) => {
      if (event.target instanceof Element && event.target.matches("a")) {
        if (!mq.matches) {
          setCollapsed(true);
        }
      }
      notifyHeaderContrastEngine();
    });

    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && nav.dataset.collapsed === "false") {
        setCollapsed(true);
      }
      notifyHeaderContrastEngine();
    });

    window.addEventListener("load", notifyHeaderContrastEngine, { once: true });
  }

  window.initSiteNav = initSiteNav;
})();
