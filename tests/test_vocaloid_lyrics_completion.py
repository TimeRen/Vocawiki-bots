# -*- coding: utf-8 -*-
"""bots/vocaloid_lyrics_completion.py 的测试（不联网：AtWiki / Vocawiki 全部用假页面）。"""
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import bots.vocaloid_lyrics_completion as completion

from bots.vocaloid_lyrics_completion import (
    build_name_index,
    classify,
    is_song_page,
    link_text,
    name_key,
    page_plaintext,
    parse_page_list,
    render_page,
    song_names,
)

# 真实的 AtWiki 消歧义页（pages/667「Alice in Dreamland」）：正文只有两个链接
DISAMBIG_HTML = (
    '<div id="wrapper"><div id="wikibody" class="box">\n'
    '                <!--@@@@@--><div>\n'
    '<a href="//w.atwiki.jp/vocaloidchly/pages/664.html"  title="Alice in Dreamland/匿名 (6567d)">'
    'Alice in Dreamland/匿名</a>\n<br />\n'
    '<a href="//w.atwiki.jp/vocaloidchly/pages/665.html"  title="Alice in Dreamland/なぞ (6567d)">'
    'Alice in Dreamland/なぞ</a>\n'
    '</div><div class="atwiki-page-keyword">\n'
    '    <a href="//w.atwiki.jp/vocaloidchly/search?andor=and&keyword=Alice+in+Dreamland" '
    'rel="nofollow">「Alice in Dreamland」をウィキ内検索</a>\n'
    '</div>\n<div class="atwiki-lastmodify">最終更新：2008年10月24日 12:56</div>\n'
    '</div></div>'
)
# 有的消歧义页直接写着这句话
MARKED_DISAMBIG_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>這是一個消歧義頁的曲子的曲子</div>'
    '<div class="atwiki-page-keyword">檢索</div></div>'
)
# 目录页（歌名五十音順）：也不是歌曲
INDEX_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>曲名五十音順あ行か行さ行'
    'た行な行は行ま行や行ら行わ行英數</div><div class="atwiki-page-keyword">檢索</div></div>'
)
SONG_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>作詞：すんｚりヴぇｒ<br />'
    '作曲：すんｚりヴぇｒ<br />歌：鏡音リン・鏡音レン<br />翻譯：夜明晴月<br /><br />'
    '想一眼就看穿那橙色之物吧?<br />這點我跟你真是一丘之貉呢</div>'
    '<div class="atwiki-page-keyword">檢索</div></div>'
)


class NameKeyTest(TestCase):
    def test_normalises_spacing_width_and_markup(self):
        self.assertEqual(name_key("千本桜"), name_key(" 千本桜\u3000"))
        self.assertEqual("千本桜", name_key("{{lj|千本桜}}"))
        self.assertEqual("千本樱", name_key("'''千本樱'''"))
        self.assertEqual("alice", name_key("ＡＬＩＣＥ"))

    def test_keeps_punctuation_that_tells_two_songs_apart(self):
        """「14」与「1/4」是两首不同的歌，去掉 `/` 会把它们并成一条。"""
        self.assertNotEqual(name_key("14"), name_key("1/4"))


class SongNamesTest(TestCase):
    def test_reads_the_japanese_and_chinese_names(self):
        lead = ('{{VOCALOID Songbox\n|演唱 = [[初音未来]]\n'
                "|歌曲名称 = {{lj|千本桜}}<br>'''千本樱'''\n|P主 = [[黑兔P]]\n}}")
        self.assertEqual(["{{lj|千本桜}}", "千本桜", "'''千本樱'''"], song_names(lead))

    def test_ignores_pages_without_a_songbox(self):
        self.assertEqual([], song_names("只是歌词，没有信息框"))
        self.assertEqual([], song_names("{{VOCALOID Songbox\n|演唱 = [[初音未来]]\n}}"))


class BuildNameIndexTest(TestCase):
    def test_titles_redirects_and_songbox_names_all_count(self):
        pages = {
            "千本樱": {"redirects": ["千本桜"],
                      "lead": "|歌曲名称 = {{lj|千本桜}}<br>千本樱"},
            "卑怯战队UROTANDA": {
                "redirects": ["卑怯戦隊うろたんだー！", "卑怯战队"],
                "lead": "|歌曲名称 = {{lj|卑怯戦隊うろたんだー！}}<br>卑怯战队UROTANDA"},
        }
        names = build_name_index(pages)
        self.assertEqual("千本樱", names[name_key("千本樱")])
        self.assertEqual("千本樱", names[name_key("千本桜")])
        self.assertEqual("卑怯战队UROTANDA", names[name_key("卑怯戦隊うろたんだー！")])
        self.assertEqual("卑怯战队UROTANDA", names[name_key("卑怯战队")])

    def test_first_title_wins_for_reused_names(self):
        pages = {"Alice(A)": {"redirects": [], "lead": ""},
                 "Alice(B)": {"redirects": [], "lead": ""}}
        names = build_name_index(pages)
        self.assertEqual("Alice(A)", names[name_key("Alice(A)")])
        self.assertNotIn(name_key("Alice"), names)


class ParsePageListTest(TestCase):
    MARKUP = (
        '<div class="menubar"><ul><li><a href="//w.atwiki.jp/vocaloidchly/pages/1.html">首頁</a>'
        '</li></ul></div>'
        '<div class="taglist_pagenation"><ul class="atwiki_pagination">'
        '<li class="next"><span><a href="?sort=pagename&pp=86">&raquo;</a></span></li></ul></div>'
        '<table class="pagelist"><tr><td>ページ名</td></tr>'
        '<tr><td><a href="//w.atwiki.jp/vocaloidchly/pages/1192.html" title="x">\n'
        '                            777はラッキーキッス♡\n</a></td></tr>'
        '<tr><td><a href="//w.atwiki.jp/vocaloidchly/pages/1307.html" title="x">\n'
        '                            [It&#039;s not] World&#039;s end\n</a></td></tr>'
        '</table>'
    )

    def test_reads_only_the_pagelist_table(self):
        pages, total = parse_page_list(self.MARKUP)
        self.assertEqual({"1192": "777はラッキーキッス♡",
                          "1307": "[It's not] World's end"}, pages)
        self.assertEqual(86, total)
        self.assertNotIn("1", pages, "側边栏的「首頁」不是清单条目")

    def test_empty_markup(self):
        self.assertEqual(({}, 0), parse_page_list(""))
        self.assertEqual(({}, 0), parse_page_list("<html>没有表格</html>"))


class PagePlaintextTest(TestCase):
    def test_disambiguation_page_keeps_no_text(self):
        self.assertEqual("", page_plaintext(DISAMBIG_HTML))

    def test_link_text_is_dropped_but_prose_is_kept(self):
        # 「ウィキ内検索」那一行在 keyword 容器里，不算正文
        self.assertEqual("這是一個消歧義頁的曲子的曲子",
                         page_plaintext(MARKED_DISAMBIG_HTML))
        self.assertTrue(page_plaintext(SONG_HTML).startswith("作詞：すんｚりヴぇｒ"))

    def test_unknown_markup(self):
        self.assertIsNone(page_plaintext("<html>Just a moment...</html>"))


class IsSongPageTest(TestCase):
    def test_a_disambiguation_page_is_not_a_song(self):
        self.assertFalse(is_song_page(page_plaintext(DISAMBIG_HTML)))

    def test_the_marker_wording_is_enough(self):
        self.assertFalse(is_song_page(page_plaintext(MARKED_DISAMBIG_HTML)))

    def test_an_index_page_is_not_a_song(self):
        self.assertFalse(is_song_page(page_plaintext(INDEX_HTML)))

    def test_a_lyrics_page_is_a_song(self):
        self.assertTrue(is_song_page(page_plaintext(SONG_HTML)))

    def test_unknown_is_kept(self):
        """抓不到正文时不许把页面删掉，宁可留在清单里。"""
        self.assertTrue(is_song_page(None))

    def test_the_wikis_own_pages_are_recognised_by_name(self):
        self.assertFalse(completion.is_song_title("首頁"))
        self.assertFalse(completion.is_song_title("歌名あ行"))
        self.assertEqual(True, completion.is_song_title("千本桜"))
        self.assertEqual(True, completion.is_song_title("首頁に恋して"))


class CleanTitleTest(TestCase):
    def test_nfc_normalisation(self):
        """AtWiki 的页面名可能带组合浊点；MediaWiki 存盘时会规范化成 NFC。"""
        decomposed = "カ\u3099ラス"          # カ + 组合浊点 + ラス
        self.assertEqual("ガラス", completion.clean_title(decomposed))

    def test_control_characters_are_dropped(self):
        self.assertEqual("曲名", completion.clean_title("曲\x00名\x1f"))


class LinkTextTest(TestCase):
    def test_escapes_the_closing_bracket(self):
        self.assertEqual("Molecular[underfloor-0&#93;", link_text("Molecular[underfloor-0]"))

    def test_unescapes_entities(self):
        self.assertEqual("[It's not&#93; World's end", link_text("[It's not] World's end"))


class RenderPageTest(TestCase):
    def test_header_and_bullets(self):
        text = render_page([("441", "卑怯戦隊うろたんだー！"), ("667", "Alice in Dreamland")],
                           source_total=8554, matched=3200, excluded=120, today="2026-10-17")
        lines = text.splitlines()
        self.assertEqual("<!-- 比對日期：2026-10-17；來源共 8554 個不同頁面；"
                         "已匹配 3200 個 Vocawiki 歌曲條目；"
                         "排除 120 個消歧義／站務／目錄／測試頁。 -->", lines[0])
        self.assertIn("共 '''2''' 頁", lines[1])
        self.assertEqual("* [https://w.atwiki.jp/vocaloidchly/pages/441.html "
                         "卑怯戦隊うろたんだー！]", lines[3])
        self.assertEqual("* [https://w.atwiki.jp/vocaloidchly/pages/667.html "
                         "Alice in Dreamland]", lines[4])
        self.assertTrue(text.endswith("\n"))


class AtwikiPagesTest(TestCase):
    @staticmethod
    def _page(entries, total=2):
        rows = "".join(
            '<tr><td><a href="//w.atwiki.jp/vocaloidchly/pages/%s.html">%s</a></td></tr>' % row
            for row in entries)
        return ('<table class="pagelist">%s</table>'
                '<a href="?sort=pagename&pp=%d">&raquo;</a>' % (rows, total))

    def test_walks_every_page(self):
        batches = [self._page([("1", "あ"), ("2", "い")]), self._page([("3", "う")], total=1)]
        seen = []

        def fetcher(url):
            seen.append(url)
            return batches[len(seen) - 1]

        result = completion.atwiki_pages(fetcher)
        self.assertEqual({"1": "あ", "2": "い", "3": "う"}, result)
        self.assertEqual(2, len(seen))
        self.assertIn("?sort=pagename", seen[0])
        self.assertIn("pp=2", seen[1])

    def test_stops_when_a_page_cannot_be_read(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return "" if len(calls) > 1 else self._page([("1", "あ")])

        self.assertEqual({"1": "あ"}, completion.atwiki_pages(fetcher))

    def test_stops_when_pagination_repeats(self):
        """翻页条坏掉（没有总页数）时，翻到一页里全是见过的条目就停。"""
        page = self._page([("1", "あ")], total=0)
        calls = []

        def fetcher(url):
            calls.append(url)
            return page

        self.assertEqual({"1": "あ"}, completion.atwiki_pages(fetcher))
        self.assertEqual(2, len(calls))


class LooseKeyTest(TestCase):
    """歌名结尾的标点各站写法不一（用户 2026-10-17 报的 pages/441）。"""

    def test_trailing_punctuation_is_ignored(self):
        pages = {"卑怯战队UROTANDA": {"redirects": ["卑怯戦隊うろたんだー"], "lead": ""}}
        names = build_name_index(pages)
        self.assertEqual("卑怯战队UROTANDA",
                         completion.lookup_song(names, "卑怯戦隊うろたんだー！"))

    def test_exact_titles_still_win(self):
        pages = {"Doubt": {"redirects": [], "lead": ""},
                 "Doubt!": {"redirects": [], "lead": ""}}
        names = build_name_index(pages)
        self.assertEqual("Doubt!", completion.lookup_song(names, "Doubt!"))

    def test_punctuation_in_the_middle_is_not_ignored(self):
        """「14」与「1/4」是两首歌：宽松键只去结尾的标点。"""
        names = build_name_index({"14": {"redirects": [], "lead": ""}})
        self.assertIsNone(completion.lookup_song(names, "1/4"))


class ClassifyTest(TestCase):
    PAGES = {
        "667": "Alice in Dreamland",     # 消歧义页
        "3772": "千本桜",                 # 已经有条目
        "441": "卑怯戦隊うろたんだー！",   # 已经有条目（条目标题是中文）
        "1999": "まだない曲",             # 真要补的
    }
    NAMES = {name_key("千本桜"): "千本樱",
             name_key("卑怯戦隊うろたんだー！"): "卑怯战队UROTANDA"}

    @staticmethod
    def _fetcher(pages):
        def fetcher(url):
            pid = url.rsplit("/", 1)[-1].split(".")[0]
            return pages.get(pid, "")
        return fetcher

    def test_disambiguation_and_matched_pages_are_dropped(self):
        fetcher = self._fetcher({"667": DISAMBIG_HTML, "1999": SONG_HTML})
        listed, matched, excluded, verdicts = classify(
            self.PAGES, self.NAMES, {}, fetcher=fetcher)
        self.assertEqual([("1999", "まだない曲")], listed)
        self.assertEqual(2, matched)
        self.assertEqual(1, excluded)
        self.assertFalse(verdicts["667"]["song"])
        self.assertTrue(verdicts["1999"]["song"])

    def test_a_title_differing_only_by_trailing_punctuation_is_matched(self):
        """pages/441「卑怯戦隊うろたんだー！」其实已经有条目（重定向不带 `！`）。"""
        names = build_name_index({"卑怯战队UROTANDA": {"redirects": ["卑怯戦隊うろたんだー"],
                                                       "lead": ""}})
        listed, matched, _excluded, _ = classify(self.PAGES, names, {}, fetcher=self._fetcher({}))
        self.assertEqual(1, matched)
        self.assertNotIn("441", [pid for pid, _ in listed])

    def test_cached_verdict_avoids_refetching(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return SONG_HTML

        verdicts = {pid: {"song": True, "at": time.time()} for pid in self.PAGES}
        verdicts["667"] = {"song": False, "at": time.time()}      # 消歧义页，上一轮已经判定过
        listed, _matched, excluded, _ = classify(self.PAGES, self.NAMES, verdicts,
                                                 fetcher=fetcher)
        self.assertEqual([("1999", "まだない曲")], listed)
        self.assertEqual(1, excluded)
        self.assertEqual([], calls)

    def test_unreadable_page_stays_listed_and_is_retried(self):
        fetcher = self._fetcher({})                       # 全部读不到
        listed, _matched, excluded, verdicts = classify(
            {"1999": "まだない曲"}, {}, {}, fetcher=fetcher)
        self.assertEqual([("1999", "まだない曲")], listed)
        self.assertEqual(0, excluded)
        self.assertFalse(completion.is_fresh(verdicts["1999"]["at"], 30 * 24 * 3600))

    def test_probe_budget_limits_this_rounds_probes(self):
        calls = []

        def fetcher(url):
            calls.append(url)
            return SONG_HTML

        classify(self.PAGES, self.NAMES, {}, probe_budget=1, fetcher=fetcher)
        self.assertEqual(1, len(calls))

    def test_listing_is_sorted_by_title(self):
        pages = {"3": "あ", "1": "B", "2": "a"}
        verdicts = {pid: {"song": True, "at": time.time()} for pid in pages}
        listed, _matched, _excluded, _ = classify(
            pages, {}, verdicts, fetcher=self._fetcher({}))
        # 大小写不敏感、其余按码位：「a」<「B」<「あ」
        self.assertEqual(["2", "1", "3"], [pid for pid, _ in listed])


class FakeSite:
    def __init__(self):
        self.logins = 0

    def logged_in(self):
        return True

    def login(self):
        self.logins += 1


class FakePage:
    def __init__(self, text=""):
        self.text = text
        self.saved = []

    def save(self, **kwargs):
        self.saved.append((self.text, kwargs))


PAGES = {
    "667": "Alice in Dreamland",
    "3772": "千本桜",
    "1999": "まだない曲",
}
SONGS = {
    "千本樱": {"redirects": ["千本桜"], "lead": "|歌曲名称 = {{lj|千本桜}}<br>千本樱"},
}


def fake_fetcher(url):
    if "/list" in url:
        rows = "".join(
            '<tr><td><a href="//w.atwiki.jp/vocaloidchly/pages/%s.html">%s</a></td></tr>' % item
            for item in PAGES.items())
        return '<table class="pagelist">%s</table>' % rows
    pid = url.rsplit("/", 1)[-1].split(".")[0]
    return {"667": DISAMBIG_HTML, "1999": SONG_HTML}.get(pid, "")


class RunOnceTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        patcher = patch.multiple(
            completion,
            PAGES_CACHE=root / "pages.pickle",
            INDEX_CACHE=root / "index.pickle",
            VERDICT_CACHE=root / "verdicts.pickle",
            PAGE_TITLE="User:测试/补完计划",
            atwiki_pages=lambda fetcher=None: dict(PAGES),
            song_pages=lambda site, batch_size=50: dict(SONGS),
        )
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, original, write):
        page = FakePage(original)
        with patch.object(completion, "Page", lambda site, title: page):
            changed = completion.run_once(FakeSite(), write=write, refresh=True,
                                          fetcher=fake_fetcher)
        return changed, page

    def test_dry_run_reports_the_change_without_saving(self):
        changed, page = self._run("旧内容", write=False)
        self.assertTrue(changed)
        self.assertEqual([], page.saved)

    def test_write_saves_only_the_pages_that_should_stay(self):
        changed, page = self._run("旧内容", write=True)
        self.assertTrue(changed)
        self.assertEqual(1, len(page.saved))
        text = page.saved[0][0]
        self.assertIn("1999.html まだない曲", text)
        self.assertNotIn("667.html", text, "消歧义页不该列进清单")
        self.assertNotIn("3772.html", text, "已经有条目的页面不该列进清单")

    def test_no_change_does_not_save(self):
        _changed, page = self._run("", write=True)
        text = page.saved[0][0]
        changed, page = self._run(text, write=True)
        self.assertFalse(changed)
        self.assertEqual([], page.saved, "页面没变时不该再保存一次")
