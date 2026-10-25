import re, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
page = Page(site, tr.PAGE_TITLE).text or ""
rows, _ = tr.parse_rows(page)
seasons = tr.season_of_lines(page)
want = {"视觉差错", "RITA", "Burial-Marker", "Lost Love", "Fixity", "Redial(鹤三)", "EDEN(酔シグレ)"}
rowinfo = {}
for row in rows:
    for side in range(row.sides):
        raw = row.text(side, tr.COLUMNS.index("title")).strip()
        if not raw:
            continue
        disp = tr.link_display(raw)
        if disp in {tr.link_display(w) for w in want} or tr.link_target(raw) in want:
            rowinfo[tr.link_target(raw)] = row.text(side, tr.COLUMNS.index("producer")).strip()
for title, producer in rowinfo.items():
    art_title = title.split("(")[0] if "(" in title else title
    p = Page(site, art_title)
    text = p.text or ""
    m = re.search(r"\|\s*(?:P主|職人)\s*=\s*([^\n]*)", text)
    art_producer = (m.group(1).strip() if m else "")
    ok = tr.person_key(art_producer) == tr.person_key(producer)
    print(f"{title:<22} row={producer:<22} article[{art_title}]={art_producer:<22} match={ok}")
