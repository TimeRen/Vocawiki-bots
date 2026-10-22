import difflib, pywikibot
site = pywikibot.Site()
title = "User:周某不是轴某/VOCALOID collection搜集库"
def rev_content(revid):
    data = site.simple_request(action="query", prop="revisions", titles=title,
                               rvstartid=revid, rvlimit=1, rvdir="newer",
                               rvprop="content|ids|timestamp|comment|user").submit()
    page = list(data["query"]["pages"].values())[0]
    rev = page["revisions"][0]
    return rev["*"], rev
old, _ = rev_content(274600)
new, info = rev_content(274610)
print("rev", info["revid"], info["timestamp"], info.get("user"), info.get("comment"))
d = list(difflib.unified_diff(old.splitlines(), new.splitlines(), "274600", "274610", lineterm="", n=1))
open("_d.txt", "w", encoding="utf-8").write("\n".join(d))
print("diff lines", len(d))
