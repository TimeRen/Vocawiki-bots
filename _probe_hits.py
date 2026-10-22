import io, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
text = Page(site, tr.PAGE_TITLE).text or ""
contrib = tr.parse_contrib_seasons(io.open("_contrib.txt", encoding="utf-8").read())
f = tr.Fetcher()
index = tr.atwiki_page_index(f)
names = {}
for season in list(contrib)[:12]:
    markup = Page(site, tr.NAVBOX_TEMPLATE.format(season=season)).text or ""
    names.update(tr.navbox_names(markup))
print("names", len(names))
missing = tr.missing_songs(text, contrib, limit=60)
hits = 0
rows = []
for song in missing[:60]:
    found = tr.atwiki_song(f, index, names, song.title)
    if not found:
        continue
    pid, translator, producer = found
    hits += 1
    rows.append((song, pid, translator, producer))
    print(f"  HIT {song.season} {song.track} {song.rank} {song.title} -> p/{pid} tr={translator!r} P={producer!r}")
print("hits", hits, "/", 60)
