import pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr

site = pywikibot.Site()
site.login()
contrib_text = Page(site, tr.CONTRIB_PAGE).text or ""
seasons = tr.parse_contrib_seasons(contrib_text)
spring = seasons["ボカコレ2022春"]
page = Page(site, tr.PAGE_TITLE)
text = page.text or ""
print("current page rows for 2022春:")
import re
m = re.search(r"^==\s*ボカコレ2022春\s*==\s*$", text, re.M)
start = m.end(); nxt = re.search(r"^==\s*[^=]", text[start:], re.M)
body = text[start:start + (nxt.start() if nxt else len(text))]
rows, _ = tr.parse_rows(body)
for r in rows:
    t0 = r.text(0, 1).strip(); t1 = r.text(1, 1).strip()
    print("  ", r.text(0,0).strip(), tr.link_target(t0) if t0 else "-", "|", r.text(1,0).strip(), tr.link_target(t1) if t1 else "-")
print()
print("contrib TOP100 created flags:", {k: v for k, v in sorted(spring["TOP100"].items()) if k in (24,46,52,53,56,57)})
print("contrib ROOKIE created flags:", {k: v for k, v in sorted(spring["ROOKIE"].items()) if k in (3,5,9,13,14,15)})
