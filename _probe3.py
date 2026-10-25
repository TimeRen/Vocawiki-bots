import pywikibot
from pywikibot import Page
site = pywikibot.Site()
for q in ("没有心", "我写出了最棒的歌词", "ORDER", "巴别塔的迷宫", "Guitar Rock与星之歌", "诅咒之吻", "日本之夏"):
    data = site.simple_request(action="query", list="search", srsearch=q, srlimit=4,
                               srprop="snippet").submit()
    hits = [(h["title"], h["snippet"][:60].replace('<span class="searchmatch">','').replace("</span>","")) for h in data["query"]["search"]]
    print(f"== {q}")
    for t, s in hits:
        print("   ", t, "|", s)
