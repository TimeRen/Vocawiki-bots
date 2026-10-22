import pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
p = Page(site, tr.PAGE_TITLE)
for r in p.revisions(total=4):
    print(r.revid, r.timestamp, "|", r.user, "|", (r.comment or "")[:70])
text = p.text or ""
needles = ["Colors(kouta)", "BLACKOUT", "Libra(mira)", "PANDORA", "死亡フラグ", "GRAVITY", "Life(kurara)", "Yellow(shu)", "Flashback", "月光(春风哈娜)"]
for n in needles:
    hits = [l for l in text.split("\n") if n in l]
    print(f"{n}: {len(hits)}")
    for l in hits[:1]:
        print("   ", l[:170])
