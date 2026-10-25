import pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr

site = pywikibot.Site()
text = Page(site, tr.PAGE_TITLE).text or ""
targets = {"Fixity", "Redial", "言灵", "Lost Love", "Burial-Marker", "EDEN", "RITA", "视觉差错"}
rows, _ = tr.parse_rows(text)
seasons = tr.season_of_lines(text)
for row in rows:
    for side in range(row.sides):
        raw = row.text(side, tr.COLUMNS.index("title")).strip()
        if not raw:
            continue
        disp = tr.link_display(raw)
        if disp not in targets:
            continue
        tgt = tr.link_target(raw)
        key = tr.title_key(tgt)
        # 精确标题查询
        data = site.simple_request(action="query", titles=tgt, redirects=1,
                                   prop="info|pageprops|categories",
                                   ppprop="disambiguation", clshow="!hidden", cllimit=50).submit()
        q = data["query"]
        found = tr.created_after_redirects(q)
        page = list(q["pages"].values())[0]
        print(f"{seasons.get(row.line,'')} | {raw} -> target={tgt} key={key}")
        print(f"    exact exists={'pageid' in page} props={page.get('pageprops')} found={found}")
        # 按 key 再搜一遍
        d2 = site.simple_request(action="query", list="search", srsearch=disp, srlimit=3).submit()
        print("    search:", [h["title"] for h in d2["query"]["search"]])
