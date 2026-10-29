// Booking links. Every "Zarezerwuj" link already points at the expert's Zencal page (or a pre-filled
// e-mail while the expert has no Zencal link yet). This script only handles an expert's own link:
// a visitor arriving with ?link=<kod_linku> books through that expert's unlisted Zencal type.
// Nothing is stored in the browser: the code stays in the address and is carried to other pages
// of the site through their links (privacy policy, section 6, says so).
(function () {
  var cfg = window.AICH_BOOKING || {};
  var code = null, own = null;
  try { code = new URLSearchParams(window.location.search).get('link'); } catch (e) { return; }
  if (!code) return;
  Object.keys(cfg).forEach(function (slug) {
    if (cfg[slug].ownCode && cfg[slug].ownCode === code) own = slug;
  });
  if (!own || !cfg[own].zencalOwn) return;
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('a[data-ekspert="' + own + '"]').forEach(function (a) { a.href = cfg[own].zencalOwn; });
    document.querySelectorAll('a[href]').forEach(function (a) {
      var href = a.getAttribute('href');
      if (!href || href.charAt(0) === '#' || a.hasAttribute('data-ekspert')) return;
      var u;
      try { u = new URL(href, window.location.href); } catch (e) { return; }
      if (u.origin !== window.location.origin || !/(\.html|\/)$/.test(u.pathname)) return;
      u.searchParams.set('link', code);
      a.href = u.toString();
    });
  });
})();
