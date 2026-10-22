import io, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
text = Page(site, tr.PAGE_TITLE).text or ""
contrib = tr.parse_contrib_seasons(io.open("_contrib.txt", encoding="utf-8").read())
f = tr.Fetcher()
index = tr.atwiki_page_index(f)
names = {}
for season in contrib:
    markup = Page(site, tr.NAVBOX_TEMPLATE.format(season=season.replace("ボカコレ", ""))).text or ""
    names.update(tr.navbox_names(markup))
print("names", len(names))
missing = tr.missing_songs(text, contrib, limit=80)
hits = []
for song in missing[:80]:
    found = tr.atwiki_song(f, index, names, song.title)
    if found:
        hits.append((song,) + found)
print("hits", len(hits), "/", 80)
for song, pid, translator, producer in hits[:15]:
    print(f"  {song.season} {song.track} {song.rank} {song.title} -> p/{pid} tr={translator!r} P={producer!r}")
