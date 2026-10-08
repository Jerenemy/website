// The motion of every page built on templates/layout.html (the homepage has its own). Two jobs:
//
// 1. Arrival. Everything marked data-reveal rises into place: what is on screen at load in
//    reading order, a beat apart (--i), the rest as it scrolls into view. The timings are the
//    theme's (static/site/tokens.css); without this script nothing is hidden.
// 2. Leaving. Browsers that cross documents with View Transitions (site.css, @view-transition)
//    hold the frame still and fade the old page themselves. Elsewhere, a link to another page of
//    this site fades the page out first (--t-fast), then is followed.
(function () {
  'use strict';
  var root = document.documentElement;
  var reduced = matchMedia('(prefers-reduced-motion: reduce)');
  var seconds = function (name, fallback) {
    var v = getComputedStyle(root).getPropertyValue(name).trim();
    var n = parseFloat(v);
    return isNaN(n) ? fallback : (/ms$/.test(v) ? n : n * 1000);
  };

  // ---------------------------------------------------------------- arrival
  function arrive() {
    var items = Array.prototype.slice.call(document.querySelectorAll('[data-reveal]'));
    if (!items.length) return;
    if (reduced.matches || !('IntersectionObserver' in window)) {
      items.forEach(function (el) { el.classList.add('is-in'); });
      return;
    }
    var h = innerHeight, first = 0;
    var later = [];
    items.forEach(function (el) {
      var r = el.getBoundingClientRect();
      if (r.top < h && r.bottom > 0) el.style.setProperty('--i', first++);
      else later.push(el);
    });
    // Two frames: the hidden state is painted once, so the arrival is a transition and not a cut.
    requestAnimationFrame(function () {
      requestAnimationFrame(function () {
        items.forEach(function (el) { if (later.indexOf(el) < 0) el.classList.add('is-in'); });
      });
    });
    if (!later.length) return;
    // Pieces that enter together (a row of points) still arrive one after another.
    var io = new IntersectionObserver(function (entries) {
      var n = 0;
      entries.forEach(function (e) {
        if (!e.isIntersecting) return;
        e.target.style.setProperty('--i', n++);
        e.target.classList.add('is-in');
        io.unobserve(e.target);
      });
    }, { rootMargin: '0px 0px -8% 0px' });
    later.forEach(function (el) { io.observe(el); });
  }

  // ---------------------------------------------------------------- leaving
  var crossDocument = 'onpagereveal' in window;   // the browser runs @view-transition itself
  function leave(e) {
    if (crossDocument || reduced.matches || e.defaultPrevented || e.button !== 0) return;
    if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    var a = e.target.closest && e.target.closest('a[href]');
    if (!a || a.target && a.target !== '_self' || a.hasAttribute('download')) return;
    var to = new URL(a.href, location.href);
    if (to.origin !== location.origin) return;
    if (to.pathname === location.pathname && to.search === location.search) return;   // a hash on this page
    if (/\.(pdf|zip|dmg|jar|png|jpe?g|svg)$/i.test(to.pathname) || a.dataset.noTransition !== undefined) return;
    e.preventDefault();
    root.classList.add('is-leaving');
    setTimeout(function () { location.href = to.href; }, seconds('--t-fast', 160));
  }
  // Back to a page kept in memory: it comes back as it was, not faded.
  addEventListener('pageshow', function (e) { if (e.persisted) root.classList.remove('is-leaving', 'from-void'); });

  document.addEventListener('click', leave);
  // The browser's own chrome (Safari's tab bar, a phone's status bar) takes the theme's ground.
  var tint = document.querySelector('meta[name="theme-color"]');
  var bg = getComputedStyle(root).getPropertyValue('--bg').trim();
  if (tint && bg) tint.setAttribute('content', bg);
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', arrive);
  else arrive();
})();
