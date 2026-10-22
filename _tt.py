import pywikibot
from pywikibot import Page
site = pywikibot.Site()
t = Page(site, "Template:The VOCALOID Collection2023春").text or ""
open("_tpl2023.txt", "w", encoding="utf-8").write(t)
print("len", len(t))
