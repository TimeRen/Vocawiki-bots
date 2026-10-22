import pywikibot
site = pywikibot.Site()
title = "User:周某不是轴某/VOCALOID collection搜集库"
def rev_content(revid):
    data = site.simple_request(action="query", prop="revisions", titles=title,
                               rvstartid=revid, rvlimit=1, rvdir="newer",
                               rvprop="content|ids").submit()
    return list(data["query"]["pages"].values())[0]["revisions"][0]["*"]
for revid, tag in ((274600, "OLD"), (274610, "NEW")):
    text = rev_content(revid)
    start = text.index("== ボカコレ2022春 ==")
    end = text.index("== ", start + 5)
    section = text[start:end]
    open(f"_sec_{tag}.txt", "w", encoding="utf-8").write(section)
    print(tag, "lines", len(section.split("\n")))
