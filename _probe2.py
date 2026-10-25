import re, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr

site = pywikibot.Site()
contrib_text = Page(site, tr.CONTRIB_PAGE).text or ""
m = re.search(r"^===\s*2022春\s*===\s*$", contrib_text, re.M)
body = contrib_text[m.end(): contrib_text.find("===", m.end())]
for cell in tr.COLORLINK_CELL_RE.finditer(body):
    if cell.group("rank") in ("46", "53", "56", "57"):
        print("RAW:", cell.group(0))
print()
for t in ("maison", "Maison", "メゾン", "東京Nighthawk", "东京Nighthawk", "Equivalent", "傀儡(Sadoya)"):
    p = Page(site, t)
    print(f"{t:<20} exists={p.exists()} redirect={p.isRedirectPage() if p.exists() else '-'}")
