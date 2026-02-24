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

    let isMobileMode = false;

    const setCollapsed = (collapsed) => {
      nav.dataset.collapsed = collapsed ? "true" : "false";
      if (header) {
        header.dataset.mobileMenuOpen = collapsed ? "false" : "true";
      }
      toggle.setAttribute("aria-expanded", collapsed ? "false" : "true");
    };

    const updateLayout = () => {
      if (!header || !nav) return;

      // Temporarily disable transitions during measurement to prevent visual bugs
      document.body.classList.add("is-measuring");

      const wasMobileMode = isMobileMode;
      const previouslyOpen = nav.dataset.collapsed === "false";

      // Temporarily revert to desktop to check fit
      document.body.classList.remove("is-mobile-menu");
      header.dataset.mobileMenuOpen = "false";
      nav.dataset.collapsed = "false"; // natural flex row state

      // Set styles to measure true unconstrained width
      const children = Array.from(header.children);
      const originalShrink = children.map(c => c.style.flexShrink);
      children.forEach(c => c.style.flexShrink = "0");
      const originalWhiteSpace = nav.style.whiteSpace;
      nav.style.whiteSpace = "nowrap";

      // Force layout calculation (Synchronous reflow)
      const needsMobile = header.scrollWidth > header.clientWidth;

      // Restore flex shrink and white-space
      children.forEach((c, i) => c.style.flexShrink = originalShrink[i]);
      nav.style.whiteSpace = originalWhiteSpace;

      if (needsMobile) {
        document.body.classList.add("is-mobile-menu");
        isMobileMode = true;
        // If resizing within mobile mode, preserve state. If coming from desktop, start closed.
        const shouldBeOpen = wasMobileMode ? previouslyOpen : false;

        nav.dataset.collapsed = shouldBeOpen ? "false" : "true";
        header.dataset.mobileMenuOpen = shouldBeOpen ? "true" : "false";
        toggle.setAttribute("aria-expanded", shouldBeOpen ? "true" : "false");
      } else {
        isMobileMode = false;
        header.dataset.mobileMenuOpen = "false";
        nav.dataset.collapsed = "false";
        toggle.setAttribute("aria-expanded", "false");
      }

      // Force synchronous layout to apply the correct non-transitioned state
      document.body.offsetHeight;
      document.body.classList.remove("is-measuring");

      notifyHeaderContrastEngine();
    };

    let resizeFrame;
    window.addEventListener("resize", () => {
      if (resizeFrame) cancelAnimationFrame(resizeFrame);
      resizeFrame = requestAnimationFrame(updateLayout);
    });
    // Trigger immediately
    updateLayout();

    toggle.addEventListener("click", () => {
      const isCollapsed = nav.dataset.collapsed !== "false";
      setCollapsed(!isCollapsed);
      notifyHeaderContrastEngine();
    });

    const collapseIfMobile = () => {
      if (isMobileMode && nav.dataset.collapsed === "false") {
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
        if (isMobileMode) {
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

    window.addEventListener("load", () => {
      updateLayout();
      notifyHeaderContrastEngine();
    }, { once: true });
  }

  window.initSiteNav = initSiteNav;
})();
