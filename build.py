#!/usr/bin/env python3
"""Builds the AI Clinic Hours site into docs/ from dane/ (TOML) and zasoby/.

Usage:
  python3 build.py          build pages, images, sitemap, robots.txt
  python3 build.py --og     also render social cards and icons with headless Chrome

Adding an expert: copy dane/eksperci/_wzor.toml to dane/eksperci/<slug>.toml,
put the portrait in zasoby/img/<file>.jpg, link situations in dane/sytuacje.toml,
then build. See README.md.
"""
import datetime
import hashlib
import html
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parent
DANE = Path(os.environ.get("AICH_DANE", ROOT / "dane"))
ZAS = ROOT / "zasoby"
OUT = Path(os.environ.get("AICH_OUT", ROOT / "docs"))
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
TODAY = datetime.date.today().isoformat()
NBSP = " "


# ---------------------------------------------------------------- data

def load(path):
    with open(path, "rb") as f:
        return tomllib.load(f)


S = load(DANE / "strona.toml")
K = S["konfig"]
BASE = K["base_url"].rstrip("/") + "/"
SYT = load(DANE / "sytuacje.toml")["sytuacja"]
EXP = sorted(
    (load(p) for p in (DANE / "eksperci").glob("*.toml") if not p.name.startswith("_")),
    key=lambda x: (x.get("kolejnosc", 99), x["nazwisko"]),
)
BY_SLUG = {x["slug"]: x for x in EXP}
# First names shared by several experts (e.g. two Piotrs): buttons on shared pages use the full name
SHARED_FIRST = {n for n in (x["imie"] for x in EXP) if sum(1 for y in EXP if y["imie"] == n) > 1}
OBSZARY = S["obszary"]
L = S["etykiety"]


def check_data():
    """Fail early on broken references, so a typo never reaches the site."""
    errors = []
    for s in SYT:
        for k in s.get("kto", []):
            if k["ekspert"] not in BY_SLUG:
                errors.append(f"sytuacja {s['id']}: unknown expert {k['ekspert']}")
        if s["obszar"] not in OBSZARY:
            errors.append(f"sytuacja {s['id']}: unknown obszar {s['obszar']}")
    for x in EXP:
        if x["obszar"] not in OBSZARY:
            errors.append(f"{x['slug']}: unknown obszar {x['obszar']}")
        if not (ZAS / "img" / x["zdjecie"]).exists():
            errors.append(f"{x['slug']}: missing photo zasoby/img/{x['zdjecie']}")
        for z in x.get("nie_dla", {}).get("zamiast", []):
            if z not in BY_SLUG:
                errors.append(f"{x['slug']}: nie_dla.zamiast unknown {z}")
    if errors:
        sys.exit("Data errors:\n  " + "\n  ".join(errors))


# ---------------------------------------------------------------- helpers

def e(s):
    return html.escape(str(s), quote=True)


def md(s):
    """Escape, then allow **bold** and [text](url) inside data strings."""
    t = e(s)
    t = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", t)
    t = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', t)
    return t


def zl(n):
    return f"{n:,}".replace(",", NBSP) + NBSP + "zł"


def brutto(n):
    return round(n * (1 + K["vat"]))


def situations_for(slug, primary=True):
    """Situations where the expert is the first choice (primary) or the second one."""
    i = 0 if primary else 1
    return [s for s in SYT if len(s.get("kto", [])) > i and s["kto"][i]["ekspert"] == slug]


def why_for(s, slug):
    for k in s.get("kto", []):
        if k["ekspert"] == slug:
            return k.get("dlaczego", "")
    return ""


def booking_href(x):
    z = x.get("rezerwacja", {}).get("zencal", "")
    if z:
        return z
    subj = f"AI Clinic Hours: rozmowa z {x['narzednik']}"
    body = (f"Dzień dobry,\n\nchcę zarezerwować rozmowę z {x['narzednik']}.\n\n"
            "Moje zdanie (co chcę móc powiedzieć albo zrobić po rozmowie, i komu):\n\n"
            "Dwa, trzy terminy, które mi pasują:\n\nDane do faktury (firma, NIP, adres):\n")
    from urllib.parse import quote
    return f"mailto:{K['kontakt']}?subject={quote(subj)}&body={quote(body)}"


def book_btn(x, text, cls="btn btn-flame"):
    return (f'<a class="{cls}" href="{e(booking_href(x))}" data-ekspert="{e(x["slug"])}">'
            f'{e(text)} <span class="arr" aria-hidden="true">→</span></a>')


def picture(x, widths, sizes, cls="", eager=False, vt=False, alt=None):
    stem = Path(x["zdjecie"]).stem
    w0, h0 = IMG_SIZES[stem]
    ws = [w for w in widths if w <= w0] or [w0]
    largest = ws[-1]
    h = round(h0 * largest / w0)
    src = lambda fmt: ", ".join(f"img/{stem}-{w}.{fmt} {w}w" for w in ws)
    style = f' style="view-transition-name: foto-{e(x["slug"])}"' if vt else ""
    load = 'loading="eager" fetchpriority="high"' if eager else 'loading="lazy" decoding="async"'
    a = x.get("zdjecie_alt", f'{x["imie"]} {x["nazwisko"]}') if alt is None else alt
    return (f'<picture class="{cls}"{style}>'
            f'<source type="image/avif" srcset="{src("avif")}" sizes="{sizes}">'
            f'<source type="image/webp" srcset="{src("webp")}" sizes="{sizes}">'
            f'<img src="img/{stem}-{largest}.jpg" srcset="{src("jpg")}" sizes="{sizes}" '
            f'width="{largest}" height="{h}" alt="{e(a)}" {load}></picture>')


def name(x):
    return f'{x["imie"]} {x["nazwisko"]}'


# ---------------------------------------------------------------- layout

NAV = [("#sytuacje", "nav_sytuacje"), ("#eksperci", "nav_eksperci"),
       ("#jak", "nav_jak"), ("#cena", "nav_cena")]


def header(home, prefix):
    h = "" if home else (prefix or "./")
    links = "".join(f'<a href="{h}{a}">{e(L[k])}</a>' for a, k in NAV)
    return f"""<header class="site-header">
  <div class="wrap header-inner">
    <a href="{prefix or './'}" class="logo" aria-label="AI Clinic Hours, strona główna">
      <span class="logo-main">AI Clinic <em>Hours</em></span>
      <span class="logo-sub">{e(L['prowadzi'])}</span>
    </a>
    <nav class="main-nav" id="main-nav" aria-label="Główna nawigacja">
      <div class="nav-links">{links}<a href="{prefix}dla-ekspertow.html">{e(L['nav_dla_ekspertow'])}</a></div>
      <a href="{h}#sytuacje" class="btn btn-flame btn-sm">{e(L['cta_glowne'])}</a>
    </nav>
    <button class="menu-btn" type="button" aria-expanded="false" aria-controls="main-nav" id="menu-btn">Menu</button>
  </div>
</header>"""


def footer(prefix):
    return f"""<footer class="site-footer">
  <div class="wrap footer-grid">
    <div>
      <p class="logo-main logo-light">AI Clinic <em>Hours</em></p>
      <p class="footer-note">{md(S['stopka']['opis'])}</p>
      <p><a class="footer-mail" href="mailto:{e(K['kontakt'])}">{e(K['kontakt'])}</a></p>
    </div>
    <nav class="footer-links" aria-label="Stopka">
      <a href="{prefix}dla-ekspertow.html">{e(L['nav_dla_ekspertow'])}</a>
      <a href="{prefix}przykladowa-notatka.html">{e(L['nav_notatka'])}</a>
      <a href="{prefix}regulamin.html">Regulamin</a>
      <a href="{prefix}polityka-prywatnosci.html">Polityka prywatności</a>
    </nav>
  </div>
  <div class="wrap footer-base"><p>{e(K['wersja'])}</p></div>
</footer>"""


def head(title, desc, path, og_image, jsonld, og_type="website", prefix=""):
    url = BASE + ("" if path == "index.html" else path)
    robots = "index, follow" if K["indeksowanie"] else "noindex, nofollow"
    ld = ""
    if jsonld:
        ld = ('<script type="application/ld+json">'
              + json.dumps(jsonld, ensure_ascii=False, separators=(",", ":"))
              + "</script>")
    return f"""<!doctype html>
<html lang="pl">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<meta name="robots" content="{robots}">
<link rel="canonical" href="{e(url)}">
<meta property="og:type" content="{og_type}">
<meta property="og:locale" content="pl_PL">
<meta property="og:site_name" content="AI Clinic Hours">
<meta property="og:title" content="{e(title)}">
<meta property="og:description" content="{e(desc)}">
<meta property="og:url" content="{e(url)}">
<meta property="og:image" content="{e(BASE + og_image)}">
<meta property="og:image:width" content="1200">
<meta property="og:image:height" content="630">
<meta name="twitter:card" content="summary_large_image">
<meta name="theme-color" content="#14203B">
<script>document.documentElement.classList.add('js')</script>
<link rel="icon" href="{prefix}favicon.ico" sizes="48x48">
<link rel="icon" href="{prefix}icon.svg" type="image/svg+xml">
<link rel="apple-touch-icon" href="{prefix}apple-touch-icon.png">
<link rel="preload" href="{prefix}fonts/inter-normal-latin.woff2" as="font" type="font/woff2" crossorigin>
<link rel="preload" href="{prefix}fonts/inter-normal-latin-ext.woff2" as="font" type="font/woff2" crossorigin>
<link rel="stylesheet" href="{prefix}css/styles.css?v={ASSET_V}">
{ld}
</head>"""


def page(path, title, desc, main, jsonld=None, og_image="og/strona.jpg", og_type="website",
         home=False, prefix="", sticky=""):
    body_cls = "home" if home else "inner"
    return (head(title, desc, path, og_image, jsonld, og_type, prefix)
            + f'\n<body class="{body_cls}">\n<div class="progress" aria-hidden="true"></div>\n<a href="#main" class="skip-link">Przejdź do treści</a>\n'
            + header(home, prefix)
            + f'\n<main id="main">\n{main}\n</main>\n'
            + footer(prefix)
            + sticky
            + f'\n<script src="{prefix}js/rezerwacja.js?v={ASSET_V}"></script>'
            + f'\n<script src="{prefix}js/app.js?v={ASSET_V}" defer></script>\n</body>\n</html>\n')


def sticky_bar(text_btn, href, attrs=""):
    p = S["cena"]
    return f"""
<div class="sticky-cta" aria-hidden="false">
  <span class="sticky-price"><b>{zl(K['cena_netto'])} netto</b><small>{e(p['za_co'])}</small></span>
  <a class="btn btn-flame btn-sm" href="{e(href)}"{attrs}>{e(text_btn)}</a>
</div>"""


# ---------------------------------------------------------------- shared blocks

def note_card(n, cls="note", label=None, extra=""):
    """A note in the five fixed headings. n: dict with zdanie + punkty[] (naglowek, tresc)."""
    rows = "".join(
        f'<div class="note-row"><dt>{e(p["naglowek"])}</dt><dd>{md(p["tresc"])}</dd></div>'
        for p in n["punkty"])
    lab = label or S["notatka"]["etykieta"]
    return f"""<article class="{cls}"{extra}>
  <header class="note-head"><span class="note-brand">AI Clinic <em>Hours</em></span><span class="note-label">{e(lab)}</span></header>
  <p class="note-q"><span class="note-q-label">{e(S['notatka']['zdanie_etykieta'])}</span>{md(n['zdanie'])}</p>
  <dl class="note-body">{rows}</dl>
</article>"""


def section_head(h, eyebrow="", lead="", cls="", hid=""):
    hid_attr = f' id="{hid}"' if hid else ""
    return (f'<header class="section-head {cls}">'
            + (f'<p class="eyebrow">{e(eyebrow)}</p>' if eyebrow else "")
            + f'<h2{hid_attr}>{md(h)}</h2>'
            + (f'<p class="section-lead">{md(lead)}</p>' if lead else "")
            + "</header>")


def proof_list(x, n=None, cls="proof"):
    items = x["dowody"][:n] if n else x["dowody"]
    return f'<ul class="{cls}">' + "".join(f"<li>{md(d['tekst'])}</li>" for d in items) + "</ul>"


def how_block(cls=""):
    J = S["jak"]
    steps = "".join(
        f'<li class="tl-step"><span class="tl-when">{e(k["kiedy"])}</span>'
        f'<h3 class="tl-title">{e(k["tytul"])}</h3><p>{md(k["tekst"])}</p></li>'
        for k in J["kroki"])
    return f"""<section class="section how {cls}" id="jak" aria-labelledby="jak-h">
  <div class="wrap">
    {section_head(J['tytul'], J.get('nad', ''), J.get('lead', ''), 'on-dark', 'jak-h')}
    <div class="hour-bar" aria-hidden="true">
      <span class="hb-seg hb-talk"><span>{e(J['pasek_rozmowa'])}</span></span>
      <span class="hb-seg hb-note"><span>{e(J['pasek_notatka'])}</span></span>
    </div>
    <ol class="timeline">{steps}</ol>
  </div>
</section>"""


def price_block():
    p = S["cena"]
    inc = "".join(f"<li>{md(i)}</li>" for i in p["w_cenie"])
    exc = "".join(f"<li>{md(i)}</li>" for i in p["poza_cena"])
    pay = "".join(f"<li>{md(i)}</li>" for i in p["platnosc"])
    return f"""<section class="section price" id="cena" aria-labelledby="cena-h">
  <div class="wrap">
    {section_head(p['tytul'], p.get('nad', ''), p.get('lead', ''), '', 'cena-h')}
    <div class="price-grid">
      <div class="price-card">
        <p class="price-big">{zl(K['cena_netto'])}<small> netto</small></p>
        <p class="price-sub">{zl(brutto(K['cena_netto']))} brutto, {e(p['za_co'])}</p>
        <ul class="ticks">{pay}</ul>
        <a class="btn btn-flame" href="#sytuacje">{e(L['cta_glowne'])} <span class="arr" aria-hidden="true">→</span></a>
        <p class="price-own">{md(p['kazdy_ustala'])}</p>
      </div>
      <div class="price-lists">
        <div><h3>{e(p['w_cenie_tytul'])}</h3><ul class="ticks">{inc}</ul></div>
        <div><h3>{e(p['poza_cena_tytul'])}</h3><ul class="dashes">{exc}</ul></div>
      </div>
    </div>
  </div>
</section>"""


def trust_block():
    t = S["zaufanie"]
    items = "".join(f'<li><h3>{e(i["tytul"])}</h3><p>{md(i["tekst"])}</p></li>' for i in t["punkty"])
    return f"""<section class="section trust" aria-labelledby="zaufanie-h">
  <div class="wrap">
    {section_head(t['tytul'], t.get('nad', ''), '', '', 'zaufanie-h')}
    <ul class="trust-grid">{items}</ul>
  </div>
</section>"""


def faq_block():
    f = S["faq"]
    items = "".join(
        f'<details class="faq-item"><summary>{e(q["pytanie"])}</summary><div class="faq-a">{md(q["odpowiedz"])}</div></details>'
        for q in f["pytania"])
    return f"""<section class="section faq" id="faq" aria-labelledby="faq-h">
  <div class="wrap faq-wrap">
    {section_head(f['tytul'], f.get('nad', ''), '', '', 'faq-h')}
    <div class="faq-list">{items}</div>
  </div>
</section>"""


def final_cta(title, text, btn_html, people=None):
    faces = ""
    if people:
        faces = '<div class="faces">' + "".join(
            picture(x, [300], "64px", "face", alt="") for x in people) + "</div>"
    return f"""<section class="section final" aria-labelledby="final-h">
  <div class="wrap final-inner">
    {faces}
    <h2 id="final-h" class="display-2">{md(title)}</h2>
    <p class="section-lead">{md(text)}</p>
    {btn_html}
  </div>
</section>"""


# ---------------------------------------------------------------- home

def home():
    H = S["home"]
    hero_notes = [s for s in SYT if s.get("notatka")][:3]
    notes_html = ""
    for i, s in enumerate(hero_notes):
        x = BY_SLUG[s["kto"][0]["ekspert"]]
        n = {"zdanie": s["cytat"], "punkty": s["notatka"]}
        extra = f' data-note="{i}"' + ("" if i == 0 else ' hidden')
        card = note_card(n, "note note-hero", None, extra)
        foot = (f'<footer class="note-foot">{picture(x, [300], "40px", "note-face", alt="")}'
                f'<span>{e(H["notatka_prowadzi"])} <b>{e(name(x))}</b></span></footer></article>')
        notes_html += card.replace("</article>", foot)
    dots = "".join(
        f'<button type="button" class="note-dot" data-go="{i}" aria-label="{e(H["notatka_przycisk"])} {i + 1}"'
        f'{" aria-current=\"true\"" if i == 0 else ""}></button>' for i in range(len(hero_notes)))
    facts = "".join(f"<li>{md(f)}</li>" for f in H["fakty"])

    hero = f"""<section class="hero" aria-labelledby="hero-h">
  <div class="wrap hero-grid">
    <div class="hero-copy">
      <p class="eyebrow eyebrow-light">{e(H['nad'])}</p>
      <h1 id="hero-h" class="display">{e(H['h1'])} <em>{e(H['h1_akcent'])}</em></h1>
      <p class="lead">{md(H['lead'])}</p>
      <div class="cta-row">
        <a class="btn btn-flame btn-lg" href="#sytuacje">{e(H['cta'])} <span class="arr" aria-hidden="true">→</span></a>
        <a class="btn btn-ghost-light btn-lg" href="#notatka">{e(H['cta2'])}</a>
      </div>
      <ul class="facts">{facts}</ul>
    </div>
    <div class="hero-note" data-notes>
      <p class="hero-note-label">{e(H['notatka_nad'])}</p>
      <div class="note-stage">{notes_html}</div>
      <div class="note-ctrl">
        <div class="note-dots">{dots}</div>
        <button type="button" class="note-pause" aria-pressed="false" data-pause="{e(H['pauza'])}" data-play="{e(H['wznow'])}">{e(H['pauza'])}</button>
      </div>
    </div>
  </div>
</section>"""

    # Situation explorer
    SX = H["sytuacje"]
    tabs, panels = "", ""
    for i, s in enumerate(SYT):
        sel = i == 0
        tabs += (f'<button type="button" role="tab" class="sit-tab" id="tab-{s["id"]}" aria-controls="panel-{s["id"]}" '
                 f'aria-selected="{"true" if sel else "false"}" tabindex="{0 if sel else -1}" data-obszar="{s["obszar"]}">'
                 f'<span class="sit-label">{e(s["etykieta"])}</span>'
                 f'<span class="sit-quote">{e(s["cytat"])}</span></button>')
        kto = s.get("kto", [])
        main_x = BY_SLUG[kto[0]["ekspert"]]
        take = "".join(f"<li>{md(t)}</li>" for t in s["wyjdziesz"])
        # Every further person on the situation gets one line, so a situation can list 2-4 people as the team grows.
        alt = "".join(
            f'<p class="who-alt">{e(SX["druga_osoba"] if j == 1 else SX.get("kolejna_osoba", SX["druga_osoba"]))} '
            f'<a href="{BY_SLUG[k["ekspert"]]["slug"]}.html">{e(name(BY_SLUG[k["ekspert"]]))}</a>'
            f'{", " + md(k["kiedy"]) if k.get("kiedy") else ""}</p>'
            for j, k in enumerate(kto[1:], start=1))
        panels += f"""<section role="tabpanel" class="sit-panel" id="panel-{s['id']}" aria-labelledby="tab-{s['id']}" tabindex="0">
  <p class="panel-tag">{e(OBSZARY[s['obszar']]['etykieta'])}</p>
  <p class="panel-quote">„{e(s['cytat'])}”</p>
  <h3 class="panel-h">{e(SX['wyjdziesz'])}</h3>
  <ol class="takeaways">{take}</ol>
  <div class="who">
    <a class="who-main" href="{main_x['slug']}.html">{picture(main_x, [300], "72px", "who-face", alt="")}
      <span><span class="who-k">{e(SX['z_kim'])}</span><b>{e(name(main_x))}</b><small>{md(kto[0].get('dlaczego', ''))}</small></span></a>
    {book_btn(main_x, SX['zarezerwuj'] + ' ' + main_x['narzednik' if main_x['imie'] in SHARED_FIRST else 'narzednik_imie'])}
  </div>
  {alt}
</section>"""
    # Topic filter above the list once there are enough situations; hidden without JS
    sit_filter = ""
    if len(SYT) >= K.get("filtry_sytuacji_od", 10):
        counts = {k: sum(1 for s in SYT if s["obszar"] == k) for k in OBSZARY}
        opts = "".join(f'<button type="button" class="chip-btn" data-sit-filter="{k}" aria-pressed="false">'
                       f'{e(v["etykieta"])} <span class="chip-n">{counts[k]}</span></button>'
                       for k, v in OBSZARY.items() if counts[k])
        sit_filter = (f'<div class="sit-filter" role="group" aria-label="{e(SX["filtr_aria"])}">'
                      f'<button type="button" class="chip-btn" data-sit-filter="" aria-pressed="true">'
                      f'{e(SX["filtr_wszystkie"])} <span class="chip-n">{len(SYT)}</span></button>{opts}</div>')
    explorer = f"""<section class="section situations" id="sytuacje" aria-labelledby="sytuacje-h">
  <div class="wrap">
    {section_head(SX['tytul'], SX.get('nad', ''), SX.get('lead', ''), '', 'sytuacje-h')}
    {sit_filter}
    <div class="explorer" data-explorer>
      <div class="sit-list" role="tablist" aria-label="{e(SX['lista_aria'])}" aria-orientation="vertical">{tabs}</div>
      <div class="sit-panels">{panels}</div>
    </div>
    <p class="sit-more">{md(SX['nie_ma'])}</p>
  </div>
</section>"""

    # Experts
    EX = H["eksperci"]
    cards = ""
    for x in EXP:
        sits = situations_for(x["slug"])[:3]
        chips = "".join(f'<li><a href="#tab-{s["id"]}" data-open="{s["id"]}">{e(s["etykieta"])}</a></li>' for s in sits)
        cards += f"""<li class="xcard" data-obszar="{x['obszar']}">
  <a class="xcard-photo" href="{x['slug']}.html" tabindex="-1" aria-hidden="true">{picture(x, [300, 570], "(max-width: 700px) 92vw, 380px", "", vt=True, alt="")}
    <span class="xcard-area">{e(OBSZARY[x['obszar']]['etykieta'])}</span></a>
  <div class="xcard-body">
    <h3 class="xcard-name"><a href="{x['slug']}.html">{e(name(x))}</a></h3>
    <p class="xcard-role">{e(x['rola'])}</p>
    <p class="xcard-line">{md(x['jednym_zdaniem'])}</p>
    <p class="mini-h">{e(L['doswiadczenie'])}</p>
    {proof_list(x, 2)}
    <p class="mini-h">{e(L['przyjdz_z'])}</p>
    <ul class="chips">{chips}</ul>
    <div class="xcard-foot">
      <span class="price-inline"><b>{zl(x.get('cena_netto', K['cena_netto']))}</b> netto</span>
      <a class="link-arrow" href="{x['slug']}.html">{e(L['profil'])}<span class="vh"> {e(name(x))}</span></a>
    </div>
    {book_btn(x, L['zarezerwuj'], 'btn btn-flame btn-block')}
  </div>
</li>"""
    filters = ""
    if len(EXP) >= K.get("filtry_od", 6):
        opts = "".join(f'<button type="button" class="chip-btn" data-filter="{k}" aria-pressed="false">{e(v["etykieta"])}</button>'
                       for k, v in OBSZARY.items())
        filters = f'<div class="filters" role="group" aria-label="Obszar"><button type="button" class="chip-btn" data-filter="" aria-pressed="true">Wszyscy</button>{opts}</div>'
    experts = f"""<section class="section experts" id="eksperci" aria-labelledby="eksperci-h">
  <div class="wrap">
    {section_head(EX['tytul'], EX.get('nad', ''), EX.get('lead', ''), '', 'eksperci-h')}
    {filters}
    <ul class="expert-grid">{cards}</ul>
    <p class="join-line">{md(EX['dolaczanie'])}</p>
  </div>
</section>"""

    # Annotated sample note
    N = S["notatka"]
    ann = "".join(
        f'<li><span class="ann-h">{e(p["naglowek"])}</span><span>{md(p["objasnienie"])}</span></li>'
        for p in N["przyklad"]["punkty"])
    note_sec = f"""<section class="section note-sec" id="notatka" aria-labelledby="notatka-h">
  <div class="wrap note-grid">
    <div class="note-copy">
      {section_head(N['tytul'], N.get('nad', ''), N.get('lead', ''), '', 'notatka-h')}
      <ol class="annotations">{ann}</ol>
      <p><a class="link-arrow" href="przykladowa-notatka.html">{e(N['link'])}</a></p>
    </div>
    <div class="note-doc">
      <p class="note-disclaimer">{e(N['zastrzezenie'])}</p>
      {note_card(N['przyklad'], 'note note-paper')}
    </div>
  </div>
</section>"""

    # Stats
    ST = H["liczby"]
    # One headline number per expert (their first "liczby" entry), so the band grows with the team.
    stats = "".join(
        f'<li><span class="stat-v">{e(x["liczby"][0]["wartosc"])}</span><span class="stat-d">{md(x["liczby"][0]["opis"])}</span>'
        f'<a class="stat-who" href="{x["slug"]}.html">{e(name(x))}</a></li>'
        for x in EXP[:6] if x.get("liczby"))
    stats_sec = f"""<section class="section stats" aria-labelledby="liczby-h">
  <div class="wrap">
    {section_head(ST['tytul'], ST.get('nad', ''), '', 'on-dark', 'liczby-h')}
    <ul class="stat-grid">{stats}</ul>
  </div>
</section>"""

    F = H["final"]
    main = "\n".join([
        hero, explorer, experts, how_block(), note_sec, stats_sec, price_block(), trust_block(),
        faq_block(),
        final_cta(F["tytul"], F["tekst"],
                  f'<a class="btn btn-flame btn-lg" href="#sytuacje">{e(F["cta"])} <span class="arr" aria-hidden="true">→</span></a>',
                  EXP),
    ])
    M = S["meta"]["home"]
    org = {
        "@type": "Organization", "@id": BASE + "#org", "name": K["organizacja"],
        "url": BASE, "email": K["kontakt"], "description": S["stopka"]["opis_org"],
        "address": {"@type": "PostalAddress", "addressLocality": "Warszawa", "addressCountry": "PL"},
    }
    if K.get("organizacja_sameas"):
        org["sameAs"] = K["organizacja_sameas"]
    ld = {"@context": "https://schema.org", "@graph": [
        org,
        {"@type": "WebSite", "@id": BASE + "#site", "url": BASE, "name": "AI Clinic Hours",
         "inLanguage": "pl", "publisher": {"@id": BASE + "#org"}},
        service_ld(),
        {"@type": "ItemList", "name": EX["tytul_listy"], "itemListElement": [
            {"@type": "ListItem", "position": i + 1, "url": BASE + x["slug"] + ".html", "name": name(x)}
            for i, x in enumerate(EXP)]},
    ]}
    sticky = sticky_bar(L["cta_glowne"], "#sytuacje")
    return page("index.html", M["title"], M["description"], main, ld, "og/strona.jpg", home=True, sticky=sticky)


def service_ld():
    c = K["cena_netto"]
    return {
        "@type": "Service", "@id": BASE + "#usluga", "name": S["meta"]["usluga_nazwa"],
        "description": S["meta"]["usluga_opis"], "provider": {"@id": BASE + "#org"},
        "areaServed": "PL", "availableLanguage": "pl",
        "audience": {"@type": "BusinessAudience", "audienceType": S["meta"]["usluga_dla"]},
        "offers": {"@type": "Offer", "price": str(c), "priceCurrency": "PLN",
                   "priceSpecification": {"@type": "UnitPriceSpecification", "price": str(c),
                                          "priceCurrency": "PLN", "valueAddedTaxIncluded": False},
                   "url": BASE + "#cena"},
    }


# ---------------------------------------------------------------- expert page

def expert(x):
    P = S["profil"]
    sits = situations_for(x["slug"])
    sit_cards = ""
    for s in sits:
        take = "".join(f"<li>{md(t)}</li>" for t in s["wyjdziesz"])
        why = why_for(s, x["slug"])
        sit_cards += f"""<li class="sit-card">
  <p class="panel-quote">„{e(s['cytat'])}”</p>
  {f'<p class="sit-why">{md(why)}</p>' if why else ''}
  <p class="mini-h">{e(S['home']['sytuacje']['wyjdziesz'])}</p>
  <ol class="takeaways takeaways-sm">{take}</ol>
</li>"""
    stats = "".join(
        f'<li><span class="stat-v">{e(t["wartosc"])}</span><span class="stat-d">{md(t["opis"])}</span></li>'
        for t in x.get("liczby", []))
    second = situations_for(x["slug"], primary=False)
    also = ""
    if second:
        chips = "".join(f'<li><a href="./#tab-{s["id"]}">{e(s["etykieta"])}</a></li>' for s in second)
        also = f'<div class="also"><p class="mini-h">{e(P.get("takze", "Druga osoba przy sprawach"))}</p><ul class="chips">{chips}</ul></div>'
    with_note = [s for s in sits if s.get("notatka")]
    note_sec = ""
    if with_note:
        s0 = with_note[0]
        note_sec = f"""<section class="section x-note" aria-labelledby="xnote-h">
  <div class="wrap note-grid">
    <div class="note-copy">{section_head(P.get('notatka_tytul', 'Tak może wyglądać **Twoja notatka.**'), '', P.get('notatka_lead', ''), '', 'xnote-h')}
      <p><a class="link-arrow" href="przykladowa-notatka.html">{e(S['notatka']['link'])}</a></p></div>
    <div class="note-doc"><p class="note-disclaimer">{e(S['notatka']['zastrzezenie'])}</p>
      {note_card({'zdanie': s0['cytat'], 'punkty': s0['notatka']}, 'note note-paper')}</div>
  </div>
</section>"""
    nd = x.get("nie_dla", {})
    alts = "".join(
        f'<a class="alt-card" href="{z}.html">{picture(BY_SLUG[z], [300], "56px", "alt-face", alt="")}'
        f'<span><b>{e(name(BY_SLUG[z]))}</b><small>{e(OBSZARY[BY_SLUG[z]["obszar"]]["etykieta"])}</small></span></a>'
        for z in nd.get("zamiast", []))
    others = "".join(
        f'<a class="alt-card" href="{o["slug"]}.html">{picture(o, [300], "56px", "alt-face", alt="")}'
        f'<span><b>{e(name(o))}</b><small>{e(OBSZARY[o["obszar"]]["etykieta"])}</small></span></a>'
        for o in EXP if o["slug"] != x["slug"])
    meta_rows = ""
    for key, lab in (("jezyki", P["jezyki"]), ("branze", P["branze"])):
        if x.get(key):
            meta_rows += f'<div><dt>{e(lab)}</dt><dd>{e(", ".join(x[key]))}</dd></div>'
    meta_rows += f'<div><dt>{e(P["rozmowa"])}</dt><dd>{e(P["rozmowa_wartosc"])}</dd></div>'
    poleca = ""
    if x.get("poleca", {}).get("cytat"):
        pc = x["poleca"]
        poleca = f"""<section class="section rec"><div class="wrap"><figure class="rec-card">
<blockquote>„{e(pc['cytat'])}”</blockquote><figcaption><b>{e(pc['imie_nazwisko'])}</b>, {e(pc['rola'])}</figcaption></figure></div></section>"""
    cena = x.get("cena_netto", K["cena_netto"])
    main = f"""<div class="wrap"><nav class="crumbs" aria-label="Okruszki"><a href="./">AI Clinic Hours</a><span aria-hidden="true">/</span><a href="./#eksperci">{e(L['nav_eksperci'])}</a><span aria-hidden="true">/</span><span aria-current="page">{e(name(x))}</span></nav></div>
<section class="xhero" aria-labelledby="x-h">
  <div class="wrap xhero-grid">
    <div class="xhero-photo">{picture(x, [300, 570], "(max-width: 860px) 80vw, 460px", "", eager=True, vt=True)}</div>
    <div class="xhero-copy">
      <p class="eyebrow">{e(OBSZARY[x['obszar']]['etykieta'])}</p>
      <h1 id="x-h" class="display-2">{e(name(x))}</h1>
      <p class="xhero-role">{e(x['rola'])}</p>
      <p class="lead lead-dark">{md(x['jednym_zdaniem'])}</p>
      <p class="mini-h">{e(L['doswiadczenie'])}</p>
      {proof_list(x, None, 'proof proof-lg')}
      <dl class="xmeta">{meta_rows}</dl>
      <div class="xprice">
        <p><b class="price-mid">{zl(cena)} netto</b><small>{zl(brutto(cena))} brutto, {e(S['cena']['za_co'])}</small></p>
        {book_btn(x, P['zarezerwuj'] + ' ' + x['narzednik_imie'], 'btn btn-flame btn-lg')}
        <p class="xterms">{md(P.get('warunki', ''))}</p>
      </div>
    </div>
  </div>
</section>
<section class="section x-sits" aria-labelledby="xs-h">
  <div class="wrap">
    {section_head(P['przyjdz'] + ' ' + x['dopelniacz_imie'] + ', jeśli', '', P.get('przyjdz_lead', ''), '', 'xs-h')}
    <ul class="sit-cards">{sit_cards}</ul>
    {also}
  </div>
</section>
{note_sec}
{f'''<section class="section stats stats-light" aria-label="{e(P['liczby'])}"><div class="wrap"><ul class="stat-grid">{stats}</ul></div></section>''' if stats else ''}
<section class="section x-not" aria-labelledby="xn-h">
  <div class="wrap x-not-grid">
    <div>{section_head(P['nie_przychodz'], '', '', '', 'xn-h')}<p class="lead lead-dark">{md(nd.get('tekst', ''))}</p></div>
    <div class="alt-list"><p class="mini-h">{e(P['zamiast'])}</p>{alts}</div>
  </div>
</section>
{poleca}
{how_block('how-compact')}
<section class="section others" aria-labelledby="xo-h">
  <div class="wrap">{section_head(P['pozostali'], '', '', '', 'xo-h')}<div class="alt-row">{others}</div></div>
</section>
{final_cta(P['final_tytul'].replace('{imie}', x['narzednik_imie']), P['final_tekst'], book_btn(x, P['zarezerwuj'] + ' ' + x['narzednik_imie'], 'btn btn-flame btn-lg'))}"""
    title = f"{name(x)} - {OBSZARY[x['obszar']]['seo']} | AI Clinic Hours"
    if len(title) > 62:
        title = f"{name(x)} | AI Clinic Hours"
    desc = x["meta_opis"]
    person = {
        "@type": "Person", "@id": BASE + x["slug"] + ".html#osoba", "name": name(x),
        "jobTitle": x["rola"], "description": x["jednym_zdaniem"].replace("**", ""),
        "image": BASE + f"img/{Path(x['zdjecie']).stem}-570.jpg",
        "worksFor": {"@id": BASE + "#org"}, "knowsAbout": x.get("wie_o", []),
    }
    if x.get("linkedin"):
        person["sameAs"] = [x["linkedin"]]
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "ProfilePage", "url": BASE + x["slug"] + ".html", "inLanguage": "pl",
         "dateModified": TODAY, "mainEntity": {"@id": BASE + x["slug"] + ".html#osoba"}},
        person,
        {"@type": "Organization", "@id": BASE + "#org", "name": K["organizacja"], "url": BASE},
        breadcrumbs([("AI Clinic Hours", BASE), (name(x), None)]),
    ]}
    sticky = sticky_bar(P["zarezerwuj_krotko"], booking_href(x), f' data-ekspert="{e(x["slug"])}"')
    return page(x["slug"] + ".html", title, desc, main, ld, f"og/{x['slug']}.jpg", "profile", sticky=sticky)


def breadcrumbs(items):
    return {"@type": "BreadcrumbList", "itemListElement": [
        dict({"@type": "ListItem", "position": i + 1, "name": n}, **({"item": u} if u else {}))
        for i, (n, u) in enumerate(items)]}


# ---------------------------------------------------------------- other pages

def simple(path, key, body_html, ld_extra=None):
    M = S["meta"][key]
    main = f"""<div class="wrap"><nav class="crumbs" aria-label="Okruszki"><a href="./">AI Clinic Hours</a><span aria-hidden="true">/</span><span aria-current="page">{e(M['okruszek'])}</span></nav></div>
{body_html}"""
    ld = {"@context": "https://schema.org", "@graph": [
        {"@type": "WebPage", "url": BASE + path, "name": M["title"], "inLanguage": "pl",
         "isPartOf": {"@id": BASE + "#site"}},
        breadcrumbs([("AI Clinic Hours", BASE), (M["okruszek"], None)]),
    ] + (ld_extra or [])}
    return page(path, M["title"], M["description"], main, ld, M.get("og", "og/strona.jpg"))


def sample_note_page():
    N = S["notatka"]
    P = S["strona_notatki"]
    ann = "".join(
        f'<li><span class="ann-h">{e(p["naglowek"])}</span><span>{md(p["objasnienie"])}</span></li>'
        for p in N["przyklad"]["punkty"])
    body = f"""<section class="section note-sec note-page" aria-labelledby="np-h">
  <div class="wrap note-grid">
    <div class="note-copy">
      <p class="eyebrow">{e(P['nad'])}</p>
      <h1 id="np-h" class="display-2">{md(P['h1'])}</h1>
      <p class="section-lead">{md(P['lead'])}</p>
      <ol class="annotations">{ann}</ol>
      <p class="small">{md(P['dopisek'])}</p>
      <a class="btn btn-flame" href="./#sytuacje">{e(L['cta_glowne'])} <span class="arr" aria-hidden="true">→</span></a>
    </div>
    <div class="note-doc">
      <p class="note-disclaimer">{e(N['zastrzezenie'])}</p>
      {note_card(N['przyklad'], 'note note-paper')}
    </div>
  </div>
</section>"""
    return simple("przykladowa-notatka.html", "notatka", body, [service_ld()])


def fragment_page(path, key):
    frag = (DANE / "strony" / path).read_text()
    return simple(path, key, frag)


def not_found():
    M = S["meta"]["404"]
    main = f"""<section class="section nf"><div class="wrap">
<p class="eyebrow">404</p><h1 class="display-2">{md(M['h1'])}</h1><p class="section-lead">{md(M['tekst'])}</p>
<a class="btn btn-flame" href="{BASE}#sytuacje">{e(L['cta_glowne'])} <span class="arr" aria-hidden="true">→</span></a></div></section>"""
    html_ = page("404.html", M["title"], M["description"], main, None, prefix=BASE)
    return html_.replace('<link rel="canonical"', '<link data-x rel="canonical"')


# ---------------------------------------------------------------- assets

IMG_SIZES = {}


def build_images():
    (OUT / "img").mkdir(parents=True, exist_ok=True)
    for src in sorted((ZAS / "img").glob("*.jpg")):
        im = Image.open(src).convert("RGB")
        IMG_SIZES[src.stem] = im.size
        for w in (300, 570):
            if w > im.size[0]:
                continue
            r = im.resize((w, round(im.size[1] * w / im.size[0])), Image.LANCZOS)
            base = OUT / "img" / f"{src.stem}-{w}"
            if not base.with_suffix(".jpg").exists() or base.with_suffix(".jpg").stat().st_mtime < src.stat().st_mtime:
                r.save(base.with_suffix(".jpg"), quality=82, optimize=True, progressive=True)
                r.save(base.with_suffix(".webp"), quality=80, method=6)
                r.save(base.with_suffix(".avif"), quality=60)


def build_static():
    global ASSET_V
    (OUT / "css").mkdir(parents=True, exist_ok=True)
    (OUT / "js").mkdir(parents=True, exist_ok=True)
    (OUT / "fonts").mkdir(parents=True, exist_ok=True)
    for f in (ZAS / "fonts").glob("*.woff2"):
        shutil.copy2(f, OUT / "fonts" / f.name)
    css = (ZAS / "fonts" / "fonts.css").read_text() + "\n" + (ZAS / "css" / "styles.css").read_text()
    (OUT / "css" / "styles.css").write_text(css)
    shutil.copy2(ZAS / "js" / "app.js", OUT / "js" / "app.js")
    cfg = {x["slug"]: {"zencal": x.get("rezerwacja", {}).get("zencal", ""),
                       "zencalOwn": x.get("rezerwacja", {}).get("zencal_wlasny", ""),
                       "ownCode": x.get("rezerwacja", {}).get("kod_linku", "")} for x in EXP}
    js = ("// Generated by build.py from dane/eksperci/*.toml. Do not edit here.\n"
          "window.AICH_BOOKING = " + json.dumps(cfg, ensure_ascii=False, indent=1) + ";\n"
          + (ZAS / "js" / "rezerwacja.js").read_text())
    (OUT / "js" / "rezerwacja.js").write_text(js)
    h = hashlib.sha1((css + js + (ZAS / "js" / "app.js").read_text()).encode()).hexdigest()[:8]
    ASSET_V = h
    shutil.copy2(ZAS / "icon.svg", OUT / "icon.svg")
    (OUT / ".nojekyll").write_text("")


def chrome_shot(html_path, png_path, w, h):
    subprocess.run([CHROME, "--headless=new", "--disable-gpu", "--hide-scrollbars",
                    f"--window-size={w},{h}", "--force-device-scale-factor=1",
                    f"--screenshot={png_path}", f"file://{html_path}"],
                   check=True, capture_output=True, timeout=60)


def build_og():
    """Social cards (1200x630) and icons, rendered by the browser from zasoby/og.html."""
    (OUT / "og").mkdir(exist_ok=True)
    tpl = (ZAS / "og.html").read_text()
    css_url = (OUT / "css" / "styles.css").as_uri()
    cards = [("strona", S["og"]["tytul"], S["og"]["podpis"], EXP[:3])]
    cards += [(x["slug"], name(x), OBSZARY[x["obszar"]]["etykieta"] + " · " + x["og_linia"], [x]) for x in EXP]
    with tempfile.TemporaryDirectory() as td:
        for slug, title, sub, people in cards:
            imgs = "".join(f'<img src="{(OUT / "img" / (Path(p["zdjecie"]).stem + "-570.jpg")).as_uri()}" alt="">' for p in people)
            doc = (tpl.replace("{{css}}", css_url).replace("{{tytul}}", md(title))
                   .replace("{{podpis}}", e(sub)).replace("{{zdjecia}}", imgs)
                   .replace("{{liczba}}", str(len(people))))
            hp = Path(td) / f"{slug}.html"
            hp.write_text(doc)
            png = Path(td) / f"{slug}.png"
            chrome_shot(hp, png, 1200, 630)
            Image.open(png).convert("RGB").save(OUT / "og" / f"{slug}.jpg", quality=86, optimize=True)
        # icons
        ip = Path(td) / "icon.html"
        ip.write_text(f'<html><body style="margin:0;background:transparent"><img src="{(ZAS / "icon.svg").as_uri()}" width="512" height="512"></body></html>')
        png = Path(td) / "icon.png"
        chrome_shot(ip, png, 512, 512)
        im = Image.open(png).convert("RGBA")
        im.resize((180, 180), Image.LANCZOS).save(OUT / "apple-touch-icon.png")
        im.save(OUT / "favicon.ico", sizes=[(48, 48), (32, 32), (16, 16)])


def build_meta_files(paths):
    if K["indeksowanie"]:
        robots = f"User-agent: *\nAllow: /\n\nSitemap: {BASE}sitemap.xml\n"
    else:
        robots = "# Zamknięta beta: strona poza wyszukiwarkami. Zmień konfig.indeksowanie w dane/strona.toml.\nUser-agent: *\nDisallow: /\n"
    (OUT / "robots.txt").write_text(robots)
    urls = "".join(
        f"<url><loc>{BASE + ('' if p == 'index.html' else p)}</loc><lastmod>{TODAY}</lastmod></url>"
        for p in paths)
    (OUT / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{urls}</urlset>\n')
    if K.get("domena"):
        (OUT / "CNAME").write_text(K["domena"] + "\n")


# ---------------------------------------------------------------- main

ASSET_V = "0"


def main():
    check_data()
    OUT.mkdir(exist_ok=True)
    build_images()
    build_static()
    pages = {"index.html": home()}
    for x in EXP:
        pages[x["slug"] + ".html"] = expert(x)
    pages["przykladowa-notatka.html"] = sample_note_page()
    pages["dla-ekspertow.html"] = fragment_page("dla-ekspertow.html", "dla_ekspertow")
    pages["regulamin.html"] = fragment_page("regulamin.html", "regulamin")
    pages["polityka-prywatnosci.html"] = fragment_page("polityka-prywatnosci.html", "polityka")
    for p, h in pages.items():
        (OUT / p).write_text(h)
    (OUT / "404.html").write_text(not_found())
    build_meta_files([p for p in pages if p not in ("regulamin.html", "polityka-prywatnosci.html")]
                     + ["regulamin.html", "polityka-prywatnosci.html"])
    if "--og" in sys.argv:
        build_og()
    print(f"Built {len(pages) + 1} pages into {OUT}/ "
          f"({len(EXP)} experts, {len(SYT)} situations, indexing {'on' if K['indeksowanie'] else 'off'}).")


if __name__ == "__main__":
    main()
