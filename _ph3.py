import io, time, pywikibot
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
missing = tr.missing_songs(text, contrib, limit=40)
pid_found = body_found = 0
for song in missing[:40]:
    alias = names.get(tr.title_key(song.title))
    pid = index.get(tr.title_key(song.title)) or (index.get(tr.title_key(alias)) if alias else None)
    if not pid:
        continue
    pid_found += 1
    body = tr.atwiki_body(f, pid)
    if body:
        body_found += 1
        print(f"  {song.season} {song.title} p/{pid} tr={tr.credit_name(body)!r} P={tr.atwiki_credits(body)!r}")
    else:
        print(f"  {song.season} {song.title} p/{pid} ← body 读不到")
    time.sleep(1)
print("pid found", pid_found, "body ok", body_found, "of", 40)
