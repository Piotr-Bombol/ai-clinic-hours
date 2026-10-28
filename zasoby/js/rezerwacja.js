// Booking links. Every "Zarezerwuj" link already points at the expert's Zencal page (or a pre-filled
// e-mail while the expert has no Zencal link yet). This script only handles an expert's own link:
// a visitor arriving with ?link=<kod_linku> books through that expert's unlisted Zencal type.
(function () {
  var cfg = window.AICH_BOOKING || {};
  var KEY = 'aich-own-link';
  var own = null;
  try {
    var code = new URLSearchParams(window.location.search).get('link');
    if (code) {
      Object.keys(cfg).forEach(function (slug) {
        if (cfg[slug].ownCode && cfg[slug].ownCode === code) sessionStorage.setItem(KEY, slug);
      });
    }
    own = sessionStorage.getItem(KEY);
  } catch (e) { /* storage blocked: the public booking type is used */ }
  if (!own || !cfg[own] || !cfg[own].zencalOwn) return;
  document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('a[data-ekspert="' + own + '"]').forEach(function (a) { a.href = cfg[own].zencalOwn; });
  });
})();
