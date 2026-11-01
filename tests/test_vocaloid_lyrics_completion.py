# -*- coding: utf-8 -*-
"""bots/vocaloid_lyrics_completion.py 的测试（不联网：AtWiki / Vocawiki 全部用假页面）。"""
import tempfile
import time
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import bots.vocaloid_lyrics_completion as completion

from bots.vocaloid_lyrics_completion import (
    VERDICT_VERSION,
    build_alias_index,
    build_name_index,
    classify,
    collect_variants,
    hint_tokens,
    is_song_page,
    is_song_pid,
    is_song_title,
    label_variants,
    link_text,
    linked_exclusions,
    loose_producer,
    match_song,
    name_key,
    name_suffix_variants,
    page_plaintext,
    page_stats,
    parse_page_list,
    producer_matches,
    render_page,
    song_names,
    song_producer,
    spaced_separator_splits,
    strip_trailing_paren,
    title_splits,
    variant_lookup,
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
                         "排除 120 個消歧義／站務／目錄／非歌曲翻譯頁。 -->", lines[0])
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

        verdicts = {pid: {"song": True, "at": time.time(), "v": VERDICT_VERSION} for pid in self.PAGES}
        verdicts["667"] = {"song": False, "at": time.time(), "v": VERDICT_VERSION}      # 消歧义页，上一轮已经判定过
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
        pages = {"913": "あ", "911": "B", "912": "a"}
        verdicts = {pid: {"song": True, "at": time.time(), "v": VERDICT_VERSION} for pid in pages}
        listed, _matched, _excluded, _ = classify(
            pages, {}, verdicts, fetcher=self._fetcher({}))
        # 大小写不敏感、其余按码位：「a」<「B」<「あ」
        self.assertEqual(["912", "911", "913"], [pid for pid, _ in listed])


class FakeSite:
    def __init__(self):
        self.logins = 0
        self.requests = []

    def logged_in(self):
        return True

    def login(self):
        self.logins += 1

    def simple_request(self, **params):
        self.requests.append(params)
        return FakeRequest({"query": {"converted": []}})


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


# 站务页：正文只剩导航，26 个链接 / 68 字（实测 pages/2「メニュー」）
MENU_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>目錄中文歌詞庫歌名五十音順'
    + "".join('<a href="//w.atwiki.jp/vocaloidchly/pages/%d.html">%d</a>\n<br />\n' % (i, i)
              for i in range(100, 126))
    + '</div><div class="atwiki-page-keyword">檢索</div></div>'
)
# 歌页也可能带几个链接，但不是「只有链接」
SONG_WITH_LINKS_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>作詞：すんｚりヴぇｒ<br />'
    '作曲：すんｚりヴぇｒ<br />歌：鏡音リン・鏡音レン<br />翻譯：夜明晴月<br /><br />'
    + "想一眼就看穿那橙色之物吧<br />" * 12
    + '<a href="//w.atwiki.jp/vocaloidchly/pages/441.html">卑怯戦隊うろたんだー</a>'
    '</div><div class="atwiki-page-keyword">檢索</div></div>'
)
# 「歌曲以外的翻譯」（pages/448）的正文：列出的都是广播剧 / 小剧场 / 散文
NON_SONG_LIST_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>'
    '<a href="//w.atwiki.jp/vocaloidchly/pages/3970.html">あなたの不在は</a>\n<br />\n'
    '<a href="//w.atwiki.jp/vocaloidchly/pages/638.html">雪見姫</a>\n'
    '<a href="//w.atwiki.jp/vocaloidchly/pages/1.html">首頁</a>\n'
    '</div><div class="atwiki-page-keyword">檢索</div></div>'
)

# Songbox 都照线上抄：歌名用 {{lj|…}}，P主 有纯链接、也有 {{lj|[[a|b]]}}
ECHO_SONGS = {
    "ECHO(Crusher-P)": {
        "redirects": [],
        "lead": "{{VOCALOID Songbox\n|歌曲名称 = ECHO\n|P主 = [[Crusher-P]]\n}}",
    },
}
SEKAI_SONGS = {
    "世界(初音未来)": {
        "redirects": [],
        "lead": ("{{VOCALOID Songbox\n|歌曲名称 = {{lj|セカイ}}<br/>世界\n"
                 "|P主      = [[DECO*27]]、[[堀江晶太]](kemu)\n}}"),
    },
}
CINDERELLA_SONGS = {
    "灰姑娘(DECO*27)": {
        "redirects": [],
        "lead": ("{{VOCALOID Songbox\n|歌曲名称 = {{lj|シンデレラ}}<br>灰姑娘\n"
                 "|P主      = [[DECO*27]]\n}}"),
    },
    "灰姑娘(zig)": {
        "redirects": [],
        "lead": ("{{VOCALOID Songbox\n|歌曲名称 = {{lj|シンデレラ}}<br>Cinderella<br>灰姑娘\n"
                 "|P主      = {{lj|[[zig|ジグ]]}}\n}}"),
    },
}


class NonSongPidTest(TestCase):
    def test_whitelisted_pids_never_reach_the_list(self):
        pages = {"2": "メニュー", "1557": "LOG下半年", "1999": "まだない曲"}
        verdicts = {pid: {"song": True, "at": time.time(), "v": VERDICT_VERSION} for pid in pages}
        listed, matched, excluded, _ = classify(pages, {}, verdicts,
                                               fetcher=lambda url: "")
        self.assertEqual([("1999", "まだない曲")], listed)
        self.assertEqual(0, matched)
        self.assertEqual(2, excluded)

    def test_a_song_that_looks_like_paperwork_is_kept(self):
        """3518「合唱コンクール」、3609「未完成人間」是真歌，只按 pid 排不按关键词排。"""
        self.assertTrue(is_song_pid("3518"))
        self.assertTrue(is_song_pid("3609"))
        self.assertFalse(is_song_pid("1557"))
        self.assertFalse(is_song_pid("448"))


class LinkedExclusionTest(TestCase):
    def test_pages_listed_by_the_source_are_excluded(self):
        self.assertEqual(["3970", "638"], linked_exclusions(lambda url: NON_SONG_LIST_HTML))

    def test_navigation_links_are_not_taken_for_entries(self):
        self.assertNotIn("1", linked_exclusions(lambda url: NON_SONG_LIST_HTML))

    def test_a_missing_source_means_no_exclusions(self):
        self.assertEqual([], linked_exclusions(lambda url: ""))

    def test_they_are_dropped_from_the_list(self):
        listed, matched, excluded, _ = classify(
            {"3970": "あなたの不在は、私には耐え難い苦痛でした", "1999": "まだない曲"},
            {}, {"1999": {"song": True, "at": 0, "v": VERDICT_VERSION}}, fetcher=lambda url: "",
            excluded_pids=["3970"])
        self.assertEqual([("1999", "まだない曲")], listed)
        self.assertEqual(0, matched)
        self.assertEqual(1, excluded)


class IndexPageDensityTest(TestCase):
    def test_a_page_that_is_mostly_links_is_not_a_song(self):
        plain, links = page_stats(MENU_HTML)
        self.assertGreaterEqual(links, 12)
        self.assertLess(len(plain), 120)
        self.assertFalse(is_song_page(plain, links))

    def test_a_lyrics_page_with_a_couple_of_links_stays(self):
        plain, links = page_stats(SONG_WITH_LINKS_HTML)
        self.assertEqual(1, links)
        self.assertTrue(is_song_page(plain, links))

    def test_the_link_count_is_optional(self):
        self.assertTrue(is_song_page("作" * 200))


class TitleSplitsTest(TestCase):
    def test_a_trailing_paren_is_peeled_with_nested_brackets(self):
        self.assertEqual(("セカイ", "DECO*27×堀江晶太(kemu)"),
                         strip_trailing_paren("セカイ(DECO*27×堀江晶太(kemu))"))

    def test_producer_tokens_drop_their_own_brackets(self):
        self.assertEqual(["DECO*27", "堀江晶太", "kemu"],
                         hint_tokens("DECO*27×堀江晶太(kemu)"))

    def test_slash_titles_split_into_name_and_producer(self):
        self.assertEqual([("シンデレラ", ["DECO*27"])], title_splits("シンデレラ/DECO*27"))

    def test_a_plain_name_has_no_splits(self):
        self.assertEqual([], title_splits("千本桜"))

    def test_a_slash_in_a_song_name_only_matches_with_producer_proof(self):
        """「1/4」这种名字拆开是「1」，没有作者佐证绝不能当成条目「1」。"""
        self.assertEqual([("1", ["4"])], title_splits("1/4"))
        aliases = {name_key("1"): [("某曲", "somebody")]}
        self.assertIsNone(match_song({}, aliases, "1/4"))


class MatchSongTest(TestCase):
    def _match(self, songs, title):
        return match_song(build_name_index(songs), build_alias_index(songs), title)

    def test_a_slash_title_matches_the_parenthetical_article(self):
        self.assertEqual("ECHO(Crusher-P)", self._match(ECHO_SONGS, "ECHO/Crusher-P"))

    def test_nested_producer_brackets_are_handled(self):
        self.assertEqual("世界(初音未来)",
                         self._match(SEKAI_SONGS, "セカイ(DECO*27×堀江晶太(kemu))"))

    def test_the_producer_picks_between_two_articles_with_the_same_name(self):
        self.assertEqual("灰姑娘(DECO*27)", self._match(CINDERELLA_SONGS, "シンデレラ/DECO*27"))
        self.assertEqual("灰姑娘(zig)", self._match(CINDERELLA_SONGS, "シンデレラ/ジグ"))

    def test_an_ambiguous_name_without_producer_proof_stays_listed(self):
        self.assertIsNone(self._match(CINDERELLA_SONGS, "シンデレラ/誰か"))

    def test_an_exact_title_is_untouched(self):
        self.assertEqual("灰姑娘(zig)",
                         match_song(build_name_index(CINDERELLA_SONGS), {}, "灰姑娘(zig)"))

    def test_a_producer_that_contradicts_the_article_is_not_trusted(self):
        self.assertIsNone(self._match(ECHO_SONGS, "ECHO/別の人"))


class AliasIndexTest(TestCase):
    def test_the_producer_field_is_flattened(self):
        lead = CINDERELLA_SONGS["灰姑娘(zig)"]["lead"]
        self.assertEqual("ジグ", song_producer(lead))
        lead = SEKAI_SONGS["世界(初音未来)"]["lead"]
        self.assertEqual("DECO*27、堀江晶太(kemu)", song_producer(lead))

    def test_pages_without_a_songbox_are_not_aliases(self):
        pages = dict(CINDERELLA_SONGS)
        pages["セカイ"] = {"redirects": [], "lead": "#REDIRECT [[:世界]]"}
        aliases = build_alias_index(pages)
        self.assertNotIn(name_key("セカイ"), aliases)

    def test_every_candidate_is_kept_for_disambiguation(self):
        aliases = build_alias_index(CINDERELLA_SONGS)
        titles = [title for title, _producer in aliases[name_key("シンデレラ")]]
        self.assertEqual(["灰姑娘(DECO*27)", "灰姑娘(zig)"], titles)

    def test_producer_matching_ignores_case_and_width(self):
        self.assertTrue(producer_matches("ＣＲＵＳＨＥＲ－Ｐ", ["crusher-p"]))
        self.assertFalse(producer_matches("DECO*27", ["ジグ"]))


class FakeRequest:
    def __init__(self, data):
        self.data = data

    def submit(self):
        return self.data


class FakeApiSite:
    """只够 ``simple_request`` 用的假 site：recentchanges + 按标题取首段。"""

    def __init__(self, changes, leads=None, fail=False):
        self.changes = changes
        self.leads = leads or {}
        self.fail = fail
        self.calls = []

    def simple_request(self, **params):
        self.calls.append(params)
        if self.fail:
            raise RuntimeError("boom")
        if params.get("list") == "recentchanges":
            return FakeRequest({"query": {"recentchanges": [
                {"title": title} for title in self.changes]}})
        pages = []
        for title in str(params.get("titles", "")).split("|"):
            pages.append({"title": title, "revisions": [{"slots": {"main": {
                "content": self.leads.get(title, "")}}}]})
        return FakeRequest({"query": {"pages": pages}})

    def recentchanges_calls(self):
        return [call for call in self.calls if call.get("list") == "recentchanges"]


class IndexPatchTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.multiple(completion, INDEX_CACHE=self.root / "index.pickle")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _cache(self, age, **extra):
        cache = {"built": time.time() - age, "names": {name_key("千本桜"): "千本樱"},
                 "aliases": {}, "pages": 1, "version": completion.INDEX_VERSION}
        cache.update(extra)
        return cache

    def test_a_stale_index_is_patched_with_new_pages(self):
        site = FakeApiSite(["AGE"], leads={
            "AGE": "{{VOCALOID Songbox\n|歌曲名称 = AGE\n|P主 = [[Synzi]]\n}}"})
        names, _cache = completion.collect_names(
            site, refresh=False, cache=self._cache(3 * 3600))
        self.assertEqual("AGE", names.get(name_key("AGE")))
        self.assertEqual(1, len(site.recentchanges_calls()))

    def test_a_fresh_index_is_not_patched(self):
        site = FakeApiSite(["AGE"])
        completion.collect_names(site, refresh=False, cache=self._cache(600))
        self.assertEqual([], site.recentchanges_calls())

    def test_too_many_changes_fall_back_to_a_full_rebuild(self):
        site = FakeApiSite([str(i) for i in range(completion.INDEX_PATCH_LIMIT + 5)])
        called = []

        def song_pages(_site, batch_size=50):
            called.append(True)
            return {"千本樱": {"redirects": [], "lead": "{{VOCALOID Songbox\n"
                                                       "|歌曲名称 = {{lj|千本桜}}\n}}"}}

        with patch.object(completion, "song_pages", song_pages):
            names, _cache = completion.collect_names(site, refresh=False,
                                                    cache=self._cache(3 * 3600))
        self.assertEqual([True], called)
        self.assertEqual("千本樱", names.get(name_key("千本桜")))

    def test_a_broken_recentchanges_query_falls_back_to_a_full_rebuild(self):
        site = FakeApiSite([], fail=True)
        called = []

        def song_pages(_site, batch_size=50):
            called.append(True)
            return {"千本樱": {"redirects": [], "lead": "{{VOCALOID Songbox\n"
                                                       "|歌曲名称 = {{lj|千本桜}}\n}}"}}

        with patch.object(completion, "song_pages", song_pages):
            completion.collect_names(site, refresh=False, cache=self._cache(3 * 3600))
        self.assertEqual([True], called)


class ShrinkGuardTest(TestCase):
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

    PAGE_TEXT = ("<!-- 比對日期：2026-10-17；來源共 3 個不同頁面；已匹配 9 個 Vocawiki "
                 "歌曲條目；排除 1 個消歧義／站務／目錄／非歌曲翻譯頁。 -->\n"
                 "旧清单\n")

    def _run(self, **kwargs):
        page = FakePage(self.PAGE_TEXT)
        with patch.object(completion, "Page", lambda site, title: page):
            changed = completion.run_once(FakeSite(), write=True, refresh=True,
                                          fetcher=fake_fetcher, **kwargs)
        return changed, page

    def test_a_smaller_match_count_is_not_saved(self):
        changed, page = self._run()
        self.assertFalse(changed)
        self.assertEqual([], page.saved, "已匹配变少时不该写页面")

    def test_the_guard_can_be_bypassed(self):
        changed, page = self._run(allow_shrink=True)
        self.assertTrue(changed)
        self.assertEqual(1, len(page.saved))


# 目录页表头（pages/11「初音ミク原創曲」实测）
CATALOG_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>格式(暫定)這裡是曲名網址:原創曲'
    'sugarchocolatewaffleShibayan（原曲動畫）（翻譯在此）貴方に花を私に唄をRe:nGテラカゾク'
    '</div><div class="atwiki-page-keyword">檢索</div></div>'
)
# 没填的模板（pages/1427「激孃想歌」实测）
UNTRANSLATED_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>:nicovideoエラー'
    '(正しい動画URLを入力してください.)作詞：作曲：編曲：歌：翻譯：'
    '(想具名的話寫在這裡，不想的話把這行刪掉)(有翻譯標題的話寫這行)(歌詞)'
    '</div><div class="atwiki-page-keyword">檢索</div></div>'
)
# 真翻译页 + 文末残留模板提示（pages/2127「月雪花」实测）：不能删
TRANSLATED_LEFTOVER_HTML = (
    '<div id="wikibody" class="box">\n<!--@@@@@--><div>作詞：Ebot作曲：Ebot歌：翻譯：四海漂泊怪叔叔'
    '殘櫻落紅珠滴滴為風逐嘗綻天地間靜觀春華度花藟不諳愁欲訴相思語枉顧離別恨溫存只今宵'
    '願得卿垂憐甘為花與露明朝夢醒時消散歸塵土空懷脈脈情枉做癡心夢愁緒催腸斷'
    '(有註解的話寫在這條線下面，沒有的話連線一起刪掉)(下面tag欄)'
    '</div><div class="atwiki-page-keyword">檢索</div></div>'
)

# 各种「作者挂在曲名前 / 后用分隔符或标签」的条目
WRAPPED_SONGS = {
    "世界(初音未来)": {
        "redirects": [],
        "lead": ("{{VOCALOID Songbox\n|歌曲名称 = {{lj|セカイ}}<br/>世界\n"
                 "|P主      = [[DECO*27]]、[[堀江晶太]](kemu)\n}}"),
    },
    "EAT ME": {"redirects": [],
               "lead": "{{VOCALOID Songbox\n|歌曲名称 = EAT ME\n|P主 = [[OSTER project]]\n}}"},
    "Re:birthed": {"redirects": [],
                   "lead": "{{VOCALOID Songbox\n|歌曲名称 = Re:birthed\n|P主 = [[某P]]\n}}"},
    "说谎家": {
        "redirects": [],
        "lead": "{{VOCALOID Songbox\n|歌曲名称 = {{lj|うそつき}}\n|P主 = [[めざめP]]\n}}",
    },
    "约定的地方": {
        "redirects": [],
        "lead": "{{VOCALOID Songbox\n|歌曲名称 = {{lj|約束の場所}}\n|P主 = [[仕事してP]]\n}}",
    },
    "洁癖症": {
        "redirects": [],
        "lead": "{{VOCALOID Songbox\n|歌曲名称 = {{lj|ケッペキショウ}}\n|P主 = [[すこっぷ]]\n}}",
    },
    "恋爱勇者": {
        "redirects": [],
        "lead": "{{VOCALOID Songbox\n|歌曲名称 = {{lj|恋愛勇者}}\n|P主 = [[Last Note.]]\n}}",
    },
}


class CatalogMarkerTest(TestCase):
    def test_a_name_and_url_table_is_not_a_song(self):
        self.assertFalse(is_song_page(page_plaintext(CATALOG_HTML)))

    def test_the_catalog_title_prefix_is_recognised(self):
        self.assertFalse(is_song_title("中文歌詞列表作者別(五十音順)"))
        self.assertFalse(is_song_title("中文歌詞列表VOCALOID別"))

    def test_a_real_song_title_is_kept(self):
        self.assertTrue(is_song_title("合唱コンクール"))
        self.assertTrue(is_song_title("未完成人間"))


class UntranslatedMarkerTest(TestCase):
    def test_an_unfilled_template_is_not_listed(self):
        self.assertFalse(is_song_page(page_plaintext(UNTRANSLATED_HTML)))

    def test_a_translation_with_leftover_template_text_is_kept(self):
        """pages/2127「月雪花」有翻译，只是文末残留模板提示 —— 不能删。"""
        self.assertTrue(is_song_page(page_plaintext(TRANSLATED_LEFTOVER_HTML)))


class LabelStripTest(TestCase):
    def test_leading_and_trailing_labels_are_stripped(self):
        self.assertEqual(["【GUMI】ケッペキショウ（洁癖症）", "ケッペキショウ（洁癖症）"],
                         label_variants("【GUMI】ケッペキショウ（洁癖症）"))
        self.assertEqual(["Fireworks【流星プロジェクト】", "Fireworks"],
                         label_variants("Fireworks【流星プロジェクト】"))
        # 两层标签：逐层剥，中间结果也留着（多一个候选而已）
        self.assertEqual(["【ののた】おこちゃま戦争【歌ってみた】",
                          "おこちゃま戦争【歌ってみた】",
                          "おこちゃま戦争"],
                         label_variants("【ののた】おこちゃま戦争【歌ってみた】"))

    def test_a_name_that_is_only_a_label_is_left_alone(self):
        self.assertEqual(["【オリジナル】"], label_variants("【オリジナル】"))

    def test_a_trailing_bracket_is_only_an_extra_candidate(self):
        """`女王←→魔女【中世騎士物語】` 的方括号是标题的一部分：剥掉只是多一个候选，
        真要对上还得靠条目名，剥掉后的名字在 voca 上没有条目 → 不会误删。"""
        variants = label_variants("女王←→魔女【中世騎士物語】")
        self.assertEqual("女王←→魔女【中世騎士物語】", variants[0])
        self.assertIn("女王←→魔女", variants)


class NameSuffixTest(TestCase):
    def test_the_trailing_suffix_is_dropped(self):
        self.assertEqual(["Re:birthed中文歌詞", "Re:birthed"],
                         name_suffix_variants("Re:birthed中文歌詞"))

    def test_a_plain_name_is_untouched(self):
        self.assertEqual(["Re:birthed"], name_suffix_variants("Re:birthed"))

    def test_the_suffix_in_the_middle_is_kept(self):
        self.assertEqual(["中文歌詞列表VOCALOID別"],
                         name_suffix_variants("中文歌詞列表VOCALOID別"))


class SpacedSeparatorSplitTest(TestCase):
    def test_both_directions_are_offered(self):
        self.assertEqual(
            [("DECO-27×堀江晶太(kemu)", ["セカイ"]),
             ("セカイ", ["DECO-27", "堀江晶太", "kemu"])],
            spaced_separator_splits("DECO-27×堀江晶太(kemu) - セカイ"))
        self.assertEqual([("EAT ME", ["OSTER", "project"]),
                          ("OSTER project", ["EAT", "ME"])],
                         spaced_separator_splits("EAT ME > OSTER project"))

    def test_full_width_and_long_dashes_are_handled(self):
        self.assertTrue(spaced_separator_splits("曲名　－　作者"))
        self.assertTrue(spaced_separator_splits("曲名 — 作者"))
        self.assertTrue(spaced_separator_splits("曲名 ＞ 作者"))

    def test_an_unspaced_separator_is_not_split(self):
        self.assertEqual([], spaced_separator_splits("DECO*27-セカイ"))
        self.assertEqual([], spaced_separator_splits("かがみのむこう＞"))
        self.assertEqual([], spaced_separator_splits("女王←→魔女【中世騎士物語】"))
        self.assertEqual([], spaced_separator_splits("千本桜"))


class WrappedMatchTest(TestCase):
    def _match(self, title):
        return match_song(build_name_index(WRAPPED_SONGS),
                          build_alias_index(WRAPPED_SONGS), title)

    def test_author_before_the_title(self):
        self.assertEqual("世界(初音未来)", self._match("DECO-27×堀江晶太(kemu) - セカイ"))

    def test_angle_separator(self):
        self.assertEqual("EAT ME", self._match("EAT ME > OSTER project"))
        self.assertEqual("说谎家", self._match("うそつき > めざめP"))
        self.assertEqual("约定的地方", self._match("約束の場所 > 仕事してP"))

    def test_the_translation_suffix(self):
        self.assertEqual("Re:birthed", self._match("Re:birthed中文歌詞"))

    def test_labels_and_the_chinese_name_in_brackets(self):
        self.assertEqual("洁癖症", self._match("【GUMI】ケッペキショウ（洁癖症）"))

    def test_subtitles_are_not_taken_for_producers(self):
        self.assertIsNone(self._match("リナリア - 第二章 -"))
        self.assertIsNone(self._match("光芒 - Twilight Ray -"))
        self.assertIsNone(self._match("自覚 - Awareness"))
        self.assertIsNone(self._match("かがみのむこう＞"))


class ProducerLooseTest(TestCase):
    def test_punctuation_differences_are_ignored(self):
        self.assertEqual("deco27", loose_producer("DECO-27"))
        self.assertEqual("deco27", loose_producer("DECO*27"))
        self.assertTrue(producer_matches("DECO*27、堀江晶太(kemu)", ["DECO-27"]))

    def test_short_hints_are_not_compared_loosely(self):
        self.assertFalse(producer_matches("DECO*27", ["D*"]))

    def test_an_unrelated_producer_does_not_match(self):
        self.assertFalse(producer_matches("DECO*27", ["ジグ"]))


class VariantSite:
    def __init__(self, mapping):
        self.mapping = mapping
        self.requests = []

    def simple_request(self, **params):
        self.requests.append(params)
        titles = str(params.get("titles", "")).split("|")
        converted = [{"from": title, "to": self.mapping[title]}
                     for title in titles
                     if self.mapping.get(title) and self.mapping[title] != title]
        return FakeRequest({"query": {"converted": converted}})


class VariantMatchTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        patcher = patch.multiple(completion, VARIANT_CACHE=self.root / "variants.pickle")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_a_traditional_name_is_matched_through_the_simplified_one(self):
        site = VariantSite({"魔法少女幸福論": "魔法少女幸福论"})
        variants = collect_variants(site, ["魔法少女幸福論"])
        self.assertEqual({"魔法少女幸福論": "魔法少女幸福论"}, variants)
        names = {name_key("魔法少女幸福论"): "魔法少女幸福论"}
        self.assertEqual("魔法少女幸福论",
                         variant_lookup(names, {}, "魔法少女幸福論", variants))

    def test_the_conversion_is_cached(self):
        site = VariantSite({"魔法少女幸福論": "魔法少女幸福论"})
        collect_variants(site, ["魔法少女幸福論"])
        collect_variants(site, ["魔法少女幸福論"])
        self.assertEqual(1, len(site.requests), "同一个名字不该再问一次")

    def test_names_that_are_already_simplified_cost_nothing(self):
        site = VariantSite({})
        collect_variants(site, ["千本桜"])
        collect_variants(site, ["千本桜"])
        self.assertEqual(1, len(site.requests))
        self.assertIsNone(variant_lookup({}, {}, "千本桜", {"千本桜": "千本桜"}))


class LenientVerificationTest(TestCase):
    """宽松匹配到的页面要验一次正文：空模板要算「排除」，不能算「已匹配」。"""

    PAGES = {"8217": "DECO-27×堀江晶太(kemu) - セカイ",
             "4130": "【GUMI】恋愛勇者【オリジナル】"}

    def test_an_unfilled_template_is_excluded_even_though_it_matches(self):
        def fetcher(url):
            pid = url.rsplit("/", 1)[-1].split(".")[0]
            return {"8217": SONG_HTML, "4130": UNTRANSLATED_HTML}.get(pid, "")

        listed, matched, excluded, _ = classify(
            self.PAGES, build_name_index(WRAPPED_SONGS), {},
            aliases=build_alias_index(WRAPPED_SONGS), fetcher=fetcher)
        self.assertEqual([], listed)
        self.assertEqual(1, matched)
        self.assertEqual(1, excluded)
