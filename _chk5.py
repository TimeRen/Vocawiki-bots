import pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
site = pywikibot.Site()
site.login()
print("logged in:", site.logged_in(), site.userinfo.get("name"))
page = Page(site, tr.PAGE_TITLE)
for r in page.revisions(total=3):
    print(r.revid, r.timestamp, "|", r.user, "|", (r.comment or "")[:60])
cur = page.text or ""
print("still has Colors(kouta):", "Colors(kouta)" in cur)
