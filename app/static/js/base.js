document.documentElement.setAttribute("data-theme", "light");

window.addEventListener("DOMContentLoaded", () => {
  if (typeof window.initHeaderContrast === "function") {
    window.initHeaderContrast();
  }

  if (typeof window.initSiteNav === "function") {
    window.initSiteNav();
  }
});
