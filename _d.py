import difflib, pywikibot
from pywikibot import Page
site = pywikibot.Site()
title = "User:周某不是轴某/VOCALOID collection搜集库"
def text_of(revid):
    p = Page(site, title)
    p.latest_revision_id = revid
    return p.text
old = text_of(274600)
new = text_of(274610)
d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "274600", "274610", lineterm="", n=1))
open("_d.txt", "w", encoding="utf-8").write("\n".join(d))
print("diff lines", len(d))
