// Booking links: the one place to switch "Zarezerwuj" buttons to Zencal.
// Until an expert's Zencal link is filled in, the button opens a pre-filled booking e-mail.
//   zencal     - the expert's public booking link
//   zencalOwn  - the unlisted booking type for clients the expert brings
//   ownCode    - the code in the expert's own link, e.g. piotr-bombol.html?link=<ownCode>
window.AICH_BOOKING = {
  'piotr-bombol':     { zencal: '', zencalOwn: '', ownCode: '' },
  'bartek-lechowski': { zencal: '', zencalOwn: '', ownCode: '' },
  'tomasz-kerber':    { zencal: '', zencalOwn: '', ownCode: '' }
};

(function () {
  var cfg = window.AICH_BOOKING;
  var KEY = 'aich-own-link';
  var code = new URLSearchParams(window.location.search).get('link');
  var own = null;
  try {
    if (code) {
      Object.keys(cfg).forEach(function (slug) {
        if (cfg[slug].ownCode && cfg[slug].ownCode === code) sessionStorage.setItem(KEY, slug);
      });
    }
    own = sessionStorage.getItem(KEY);
  } catch (e) { /* storage blocked: the own-link booking type is then not used */ }

  document.querySelectorAll('a[data-ekspert]').forEach(function (a) {
    var slug = a.getAttribute('data-ekspert');
    var e = cfg[slug];
    if (e && e.zencal) a.href = (own === slug && e.zencalOwn) ? e.zencalOwn : e.zencal;
  });
})();
