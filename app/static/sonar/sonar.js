// Sonar's page (templates/works/sonar/sonar.html): the live rater, Sonar's five dots with
// half-steps (each dot is two points of ten), and the profile numbers counting up into view.
(function () {
  'use strict';
  var WORDS = ['Not rated', 'Skip it', 'Rough', 'Meh', 'Not for me', 'Fine', 'Decent', 'Really good', 'Great', 'Loved it', 'All-timer'];
  var reduced = matchMedia('(prefers-reduced-motion: reduce)').matches;

  document.querySelectorAll('.sn-rater').forEach(function (rater) {
    var dots = Array.prototype.slice.call(rater.querySelectorAll('.sn-rater__dot'));
    var out = rater.parentNode.querySelector('.sn-try__out');
    var value = Number(rater.dataset.value) || 0;

    function paint(v, pop) {
      dots.forEach(function (dot, i) {
        var fill = Math.max(0, Math.min(1, (v - i * 2) / 2));
        dot.style.setProperty('--fill', fill);
        dot.classList.toggle('is-on', fill > 0);
      });
      if (pop && !reduced) {
        var d = dots[Math.max(0, Math.ceil(v / 2) - 1)];
        d.classList.add('is-pop');
        setTimeout(function () { d.classList.remove('is-pop'); }, 160);
      }
      if (out) out.innerHTML = '<b>' + v + '</b><span>/10</span> <em>' + WORDS[v] + '</em>';
    }
    function set(v, pop) {
      v = Math.max(0, Math.min(10, v));
      if (v === value) return;
      value = v;
      rater.setAttribute('aria-valuenow', v);
      rater.setAttribute('aria-valuetext', v + ' out of 10, ' + WORDS[v].toLowerCase());
      paint(v, pop);
    }
    // Which half of which dot the pointer is over: the left half is the odd point, the right the even.
    function at(x) {
      for (var i = 0; i < dots.length; i++) {
        var r = dots[i].getBoundingClientRect();
        if (x < r.right + 6) return i * 2 + (x < r.left + r.width / 2 ? 1 : 2);
      }
      return 10;
    }
    var dragging = false;
    rater.addEventListener('pointerdown', function (e) { dragging = true; rater.setPointerCapture(e.pointerId); set(at(e.clientX), true); });
    rater.addEventListener('pointermove', function (e) { if (dragging) set(at(e.clientX), true); });
    rater.addEventListener('pointerup', function () { dragging = false; });
    rater.addEventListener('pointercancel', function () { dragging = false; });
    rater.addEventListener('keydown', function (e) {
      var step = { ArrowRight: 1, ArrowUp: 1, ArrowLeft: -1, ArrowDown: -1 }[e.key];
      if (e.key === 'Home') step = -value; else if (e.key === 'End') step = 10 - value;
      if (step === undefined) return;
      e.preventDefault();
      set(value + step, true);
    });
    paint(value, false);
  });

  // Numbers that count up the first time they are seen.
  var counts = document.querySelectorAll('[data-count]');
  if (!counts.length || reduced || !('IntersectionObserver' in window)) return;
  var io = new IntersectionObserver(function (entries) {
    entries.forEach(function (e) {
      if (!e.isIntersecting) return;
      io.unobserve(e.target);
      var el = e.target, end = Number(el.dataset.count), t0 = performance.now(), dur = 1100;
      (function tick(now) {
        var p = Math.min(1, (now - t0) / dur);
        el.textContent = Math.round(end * (1 - Math.pow(1 - p, 3)));
        if (p < 1) requestAnimationFrame(tick);
      })(t0);
    });
  }, { threshold: 0.6 });
  counts.forEach(function (el) { el.textContent = '0'; io.observe(el); });
})();
