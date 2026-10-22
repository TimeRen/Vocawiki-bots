import difflib, pywikibot
from pywikibot import Page
site = pywikibot.Site()
title = "User:周某不是轴某/VOCALOID collection搜集库"
def text_of(revid):
    data = site.simple_request(action="query", titles=title, rvstartid=revid,
                               rvlimit=1, rvprop="content|ids|timestamp|comment|user",
                               rvdir="newer").submit()
    page = list(data["query"]["pages"].values())[0]
    return page["revisions"][0]["*"], page["revisions"][0]
old, _ = text_of(274600)
new, info = text_of(274610)
print("rev", info["revid"], info["timestamp"], info.get("user"), info.get("comment"))
d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "274600", "274610", lineterm="", n=1))
open("_d.txt", "w", encoding="utf-8").write("\n".join(d))
print("diff lines", len(d))
