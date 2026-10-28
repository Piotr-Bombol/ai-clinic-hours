/* AI Clinic Hours: menu, situation explorer, hero notes, sticky CTA, filters. No dependencies. */
(function () {
  'use strict';
  var d = document;
  var reduce = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var smooth = reduce ? 'auto' : 'smooth';

  /* Menu */
  var mb = d.getElementById('menu-btn'), nav = d.getElementById('main-nav');
  function closeMenu() { nav.classList.remove('open'); mb.setAttribute('aria-expanded', 'false'); }
  if (mb && nav) {
    mb.addEventListener('click', function () {
      var open = nav.classList.toggle('open');
      mb.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    nav.addEventListener('click', function (ev) { if (ev.target.closest('a')) closeMenu(); });
    d.addEventListener('keydown', function (ev) {
      if (ev.key === 'Escape' && nav.classList.contains('open')) { closeMenu(); mb.focus(); }
    });
  }

  /* Header gets a hairline once the page scrolls */
  var hdr = d.querySelector('.site-header');
  function onScroll() { if (hdr) hdr.classList.toggle('is-scrolled', window.scrollY > 8); }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();

  /* Situation explorer: ARIA tabs; without JS every panel stays visible */
  var ex = d.querySelector('[data-explorer]');
  var openSituation = function () { return false; };
  if (ex) {
    var tabs = [].slice.call(ex.querySelectorAll('[role="tab"]'));
    var panels = tabs.map(function (t) { return d.getElementById(t.getAttribute('aria-controls')); });
    var select = function (i, focus) {
      tabs.forEach(function (t, j) {
        var on = i === j;
        t.setAttribute('aria-selected', on ? 'true' : 'false');
        t.tabIndex = on ? 0 : -1;
        panels[j].hidden = !on;
      });
      var p = panels[i];
      p.classList.remove('panel-in'); void p.offsetWidth; p.classList.add('panel-in');
      if (focus) tabs[i].focus({ preventScroll: true });
      var list = tabs[i].parentNode;
      if (list.scrollWidth > list.clientWidth) {
        list.scrollTo({ left: tabs[i].offsetLeft - list.offsetLeft - 16, behavior: smooth });
      }
    };
    tabs.forEach(function (t, i) {
      t.addEventListener('click', function () { select(i, false); });
      t.addEventListener('keydown', function (ev) {
        var n = tabs.length, j = null;
        if (ev.key === 'ArrowDown' || ev.key === 'ArrowRight') j = (i + 1) % n;
        else if (ev.key === 'ArrowUp' || ev.key === 'ArrowLeft') j = (i - 1 + n) % n;
        else if (ev.key === 'Home') j = 0;
        else if (ev.key === 'End') j = n - 1;
        if (j !== null) { ev.preventDefault(); select(j, true); }
      });
    });
    panels.forEach(function (p, j) { p.hidden = j !== 0; });
    openSituation = function (id) {
      for (var i = 0; i < tabs.length; i++) {
        if (tabs[i].id === 'tab-' + id) {
          select(i, false);
          var sec = d.getElementById('sytuacje') || ex;
          sec.scrollIntoView({ behavior: smooth, block: 'start' });
          tabs[i].focus({ preventScroll: true });
          return true;
        }
      }
      return false;
    };
    d.addEventListener('click', function (ev) {
      var a = ev.target.closest('[data-open]');
      if (a && openSituation(a.getAttribute('data-open'))) ev.preventDefault();
    });
    if (location.hash.indexOf('#tab-') === 0) openSituation(location.hash.slice(5));
  }

  /* Hero notes: one example note is "written" at a time; pausable (WCAG 2.2.2) */
  var box = d.querySelector('[data-notes]');
  if (box) {
    var notes = [].slice.call(box.querySelectorAll('[data-note]'));
    var dots = [].slice.call(box.querySelectorAll('.note-dot'));
    var btn = box.querySelector('.note-pause');
    var stage = box.querySelector('.note-stage');
    var MS = 10000, cur = 0, elapsed = 0, last = null;
    var paused = reduce, hover = false, visible = true;
    var show = function (i) {
      cur = i; elapsed = 0;
      notes.forEach(function (n, j) {
        n.hidden = j !== i;
        n.classList.remove('is-writing');
        if (j === i && !reduce) { void n.offsetWidth; n.classList.add('is-writing'); }
      });
      dots.forEach(function (b, j) {
        if (j === i) b.setAttribute('aria-current', 'true'); else b.removeAttribute('aria-current');
        b.style.setProperty('--p', j === i && paused ? 1 : 0);
      });
    };
    var setPaused = function (p) {
      paused = p;
      btn.setAttribute('aria-pressed', p ? 'true' : 'false');
      btn.textContent = p ? btn.getAttribute('data-play') : btn.getAttribute('data-pause');
      if (p) dots[cur].style.setProperty('--p', 1);
    };
    var running = function () { return !paused && !hover && visible && !d.hidden; };
    var tick = function (ts) {
      if (last !== null && running()) {
        elapsed += ts - last;
        var p = Math.min(elapsed / MS, 1);
        dots[cur].style.setProperty('--p', p);
        if (p >= 1) show((cur + 1) % notes.length);
      }
      last = ts;
      window.requestAnimationFrame(tick);
    };
    dots.forEach(function (b, j) {
      b.addEventListener('click', function () { setPaused(true); show(j); });
    });
    btn.addEventListener('click', function () { setPaused(!paused); if (!paused) elapsed = 0; });
    stage.addEventListener('mouseenter', function () { hover = true; });
    stage.addEventListener('mouseleave', function () { hover = false; });
    stage.addEventListener('focusin', function () { hover = true; });
    stage.addEventListener('focusout', function () { hover = false; });
    if ('IntersectionObserver' in window) {
      new IntersectionObserver(function (es) { visible = es[0].isIntersecting; }).observe(box);
    }
    setPaused(paused);
    show(0);
    if (notes.length > 1) window.requestAnimationFrame(tick);
  }

  /* Sticky booking bar on phones: after the first screen, hidden over the footer */
  var sticky = d.querySelector('.sticky-cta');
  var top = d.querySelector('.hero, .xhero, .page-hero, .section');
  if (sticky && top && 'IntersectionObserver' in window) {
    var topOut = false, footIn = false;
    var upd = function () { sticky.classList.toggle('is-on', topOut && !footIn); };
    new IntersectionObserver(function (es) { topOut = !es[0].isIntersecting; upd(); }).observe(top);
    var ft = d.querySelector('.site-footer');
    if (ft) new IntersectionObserver(function (es) { footIn = es[0].isIntersecting; upd(); }).observe(ft);
  }

  /* Expert filters (rendered only when there are enough experts) */
  var fl = d.querySelector('.filters');
  if (fl) {
    fl.addEventListener('click', function (ev) {
      var b = ev.target.closest('[data-filter]');
      if (!b) return;
      var f = b.getAttribute('data-filter');
      [].forEach.call(fl.querySelectorAll('[data-filter]'), function (x) { x.setAttribute('aria-pressed', x === b ? 'true' : 'false'); });
      [].forEach.call(d.querySelectorAll('.xcard'), function (c) { c.hidden = !!f && c.getAttribute('data-obszar') !== f; });
    });
  }
})();
