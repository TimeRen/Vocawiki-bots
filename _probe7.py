import re, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
contrib_text = Page(site, tr.CONTRIB_PAGE).text or ""
seasons = tr.parse_contrib_seasons(contrib_text)
created = {}
for season, tracks in seasons.items():
    for track, cells in tracks.items():
        for rank, (title, is_created) in cells.items():
            if is_created:
                created[(season, track, rank)] = title
print("created count:", len(created))
for key, title in sorted(created.items()):
    if title.lower() in {"fixity", "redial(鹤三)", "redial", "言灵(pirop)", "言灵", "lost love",
                          "burial-marker", "eden(酔シグレ)", "eden", "rita", "视觉差错"}:
        print("  ", key, title)
p = Page(site, "Redial(鹤三)")
t = p.text or ""
m = re.search(r"\|\s*(?:P主|職人)\s*=\s*([^\n]*)", t)
print("Redial(鹤三) P主:", m.group(1).strip() if m else "（无）")
