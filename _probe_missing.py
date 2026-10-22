import io, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
text = Page(site, tr.PAGE_TITLE).text or ""
contrib = tr.parse_contrib_seasons(io.open("_contrib.txt", encoding="utf-8").read())
print("seasons:", list(contrib)[:4], "...", len(contrib))
print("tracks 2022春:", {k: len(v) for k, v in contrib["ボカコレ2022春"].items()})
recorded = tr.page_season_songs(text)
print("page sides:", {k: {t: len(r) for t, r in v.items()} for k, v in list(recorded.items())[:3]})
missing = tr.missing_songs(text, contrib)
print("missing total", len(missing))
from collections import Counter
print(Counter(m.season for m in missing).most_common(6))
for m in missing[:5]:
    print("  ", m)
