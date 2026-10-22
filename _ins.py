import difflib, pywikibot
from pywikibot import Page
import bots.vocaloid_collection_translations as tr
text = Page(pywikibot.Site(), tr.PAGE_TITLE).text or ""
cases = [("ボカコレ2022春", "TOP100", 30, "Colors(kouta)", "kouta", "某人", "5800"),
         ("ボカコレ2022春", "ROOKIE", 40, "心不在焉", "saikawa", "甲", "3414"),
         ("ボカコレ2021春", "ROOKIE", 15, "ハロー", "乙", "丙", "7608"),
         ("ボカコレ2020冬", "ROOKIE", 26, "テスト曲", "P太郎", "丁", "1234")]
new = text
for season, track, rank, title, producer, translator, pid in cases:
    sides = tr.section_sides(dict(tr.split_sections(new, tr.SEASON_HEADING_RE))[season])
    body = dict(tr.split_sections(new, tr.SEASON_HEADING_RE))[season]
    side = sides.index(track)
    note = tr.section_uses_note(body, side)
    rank_cell = str(rank)
    if track == "ROOKIE" and note:
        rank_cell = "{{注|%d|总榜为第%d}}" % (rank, rank + 5)
    values = [rank_cell, tr.render_song_title(title), tr.render_producer(producer),
              "{{color|#FF0000|未创建}}",
              tr.render_source(tr.ATWIKI_PAGE.format(pid=pid), "VOCALID中文歌词wiki", translator),
              ""]
    new = tr.insert_row(new, season, track, rank, tr.build_row(len(sides), side, values))
d = list(difflib.unified_diff(text.splitlines(), new.splitlines(), "before", "after", lineterm="", n=2))
open("_insdiff.txt", "w", encoding="utf-8").write("\n".join(d))
print("hunks", len(d))
