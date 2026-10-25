import re, pywikibot
from pywikibot import Page
site = pywikibot.Site()
for title in ("视觉差错", "RITA", "Burial-Marker", "Lost Love", "Fixity", "Redial(鹤三)", "言灵", "EDEN"):
    p = Page(site, title)
    if not p.exists():
        print(f"{title:<16} 不存在")
        continue
    text = p.text or ""
    fields = re.findall(r"\|\s*(職人|P主|作曲|作詞|歌名|歌曲名称)\s*=\s*([^\n|]{0,40})", text)
    print(f"{title:<16} len={len(text):<5} redirect={p.isRedirectPage()} fields={fields[:4]}")
