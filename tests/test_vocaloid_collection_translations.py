# -*- coding: utf-8 -*-
"""bots/vocaloid_collection_translations.py 的测试（不联网）。"""
import time
import urllib.error
import urllib.parse
from unittest import TestCase
from unittest.mock import patch

import bots.vocaloid_collection_translations as tr

from bots.vocaloid_collection_translations import (
    Song,
    apply_fills,
    chinese_lines,
    credit_name,
    join_sources,
    link_display,
    link_target,
    outbound_links,
    parse_rows,
    render_source,
    song_mentioned,
    songs_from,
    split_row,
    title_key,
)

PAGE = """== 关于 ==
说明文字。

== ボカコレ2021春 ==
{| class="wikitable " style="text-align:center;"
|-
! colspan="6"|ROOKIE
|-
! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注 
|-
| 11 || [[Secret Universe]] || {{lj|かぁ君}} || {{color|#FF0000|未创建}} ||
|-
| 13 || [[Empty Dumpty]] || A:me || {{color|#FF0000|未创建}} || [https://example.org/x 已有来源(by. 某人)]
|}

== ボカコレ2021秋 ==
{| class="wikitable " style="text-align:center;"
|-
! colspan="6"|TOP100 !! colspan="6"|ROOKIE
|-
! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注 !! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注
|-
| 63 || [[说起VocaColle]] || {{lj|真島ゆろ}} || {{color|#FF0000|未创建}} || || || {{注|33|总榜为67}} || [[视觉差错]] || QutaQuta || {{color|#FF0000|未创建}} || 
|-
| || || || || || || 66 || [[症例A]] || Riei || {{color|#FF0000|未创建}} ||  || 偏渣翻
|}
"""


class TitleKeyTest(TestCase):
    def test_strips_wiki_markup(self):
        self.assertEqual("meromu", title_key("{{lj|[[ Meromu]]}}"))
        self.assertEqual("月之花", title_key("[[月之花]]"))
        self.assertEqual("潘多拉", title_key("[[潘多拉(buzzG)|潘多拉]]"))

    def test_ignores_disambiguation_suffix(self):
        self.assertEqual("涅槃", title_key("涅槃(HotaRu)"))

    def test_ignores_comments(self):
        self.assertEqual("潘多拉", title_key("[[潘多拉(buzzG)|潘多拉]]<!-- 弄消歧义 -->"))


class LinkTest(TestCase):
    def test_target_and_display(self):
        self.assertEqual("潘多拉(buzzG)", link_target("[[潘多拉(buzzG)|潘多拉]]"))
        self.assertEqual("潘多拉", link_display("[[潘多拉(buzzG)|潘多拉]]"))
        self.assertEqual("Meromu", link_target("{{lj|[[ Meromu]]}}"))
        self.assertEqual("Meromu", link_display("{{lj|[[ Meromu]]}}"))

    def test_plain_cell(self):
        self.assertEqual("Higher Self", link_target("Higher Self"))
        self.assertEqual("Higher Self", link_display("Higher Self"))


class SplitRowTest(TestCase):
    def test_keeps_nested_pipes(self):
        cells = split_row("| 1 || {{注|33|总榜为67}} || {{lj|a|b}}")
        self.assertEqual(["1", "{{注|33|总榜为67}}", "{{lj|a|b}}"],
                         [cell.value for cell in cells])

    def test_keeps_whitespace_around_cells(self):
        cells = split_row("| 1 || 曲名 ||")
        self.assertEqual([" ", " ", ""], [cell.lead for cell in cells])
        self.assertEqual(["1", "曲名", ""], [cell.value for cell in cells])


class ParseRowsTest(TestCase):
    def test_sides_and_source_index(self):
        rows, per_side = parse_rows(PAGE)
        self.assertTrue(rows)
        # 2021春：单侧；2021秋：双侧
        two_sided = [row for row in rows if row.sides == 2]
        self.assertEqual(2, len(two_sided))
        row = two_sided[0]
        self.assertEqual("63", row.text(0, 0))
        self.assertEqual("[[说起VocaColle]]", row.text(0, 1))
        self.assertEqual("[[视觉差错]]", row.text(1, 1))
        self.assertEqual(1 * tr.PER_SIDE + tr.SOURCE_INDEX, row.source_index(1))

    def test_skips_headers_and_separators(self):
        rows, _ = parse_rows(PAGE)
        values = [row.text(0, 1) for row in rows]
        self.assertNotIn("名次", values)
        self.assertNotIn("|-", values)


class SongsFromTest(TestCase):
    def test_collects_both_sides_and_skips_empty(self):
        songs = songs_from(PAGE)
        titles = [(song.side, song.title_display) for song in songs]
        self.assertIn((0, "Secret Universe"), titles)
        self.assertIn((0, "Empty Dumpty"), titles)
        self.assertIn((0, "说起VocaColle"), titles)
        self.assertIn((1, "视觉差错"), titles)
        self.assertIn((1, "症例A"), titles)
        self.assertEqual(5, len(songs), "空的名次/曲名行不该算进去")

    def test_producer_is_kept(self):
        songs = {song.title_display: song for song in songs_from(PAGE)}
        self.assertEqual("{{lj|かぁ君}}", songs["Secret Universe"].producer)
        self.assertEqual("Riei", songs["症例A"].producer)


class ApplyFillsTest(TestCase):
    def test_only_touches_the_source_cell(self):
        songs = {song.title_display: song for song in songs_from(PAGE)}
        secret = songs["Secret Universe"]
        text = apply_fills(PAGE, {(secret.line, secret.side): "[u 来源(by. 甲)]"})
        self.assertIn("| 11 || [[Secret Universe]] || {{lj|かぁ君}} || "
                      "{{color|#FF0000|未创建}} || [u 来源(by. 甲)]", text)        # 其他行一字不动
        self.assertIn("| 13 || [[Empty Dumpty]] || A:me || {{color|#FF0000|未创建}} || "
                      "[https://example.org/x 已有来源(by. 某人)]", text)

    def test_pads_a_short_row(self):
        """两侧表里右侧行的行尾单元格常被省略；补内容时要补够列数。"""
        songs = {song.title_display: song for song in songs_from(PAGE)}
        case = songs["症例A"]
        text = apply_fills(PAGE, {(case.line, case.side): "[u 乙]"})
        row = [line for line in text.split("\n") if "症例A" in line][0]
        cells = [cell.value for cell in split_row(row)]
        self.assertEqual(12, len(cells))
        self.assertEqual("[u 乙]", cells[1 * tr.PER_SIDE + tr.SOURCE_INDEX])
        self.assertEqual("偏渣翻", cells[1 * tr.PER_SIDE + tr.COLUMNS.index("note")])

    def test_clearing_puts_the_cell_back_to_blank(self):
        """自己上轮写错的内容要能清回空格，别留下空方括号之类。"""
        page = ("{|\n"
                "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注\n"
                "|-\n"
                "| 13 || [[Empty Dumpty]] || A:me || 未创建 || [https://a.example 网易云音乐] || \n"
                "|}")
        song = songs_from(page)[0]
        text = apply_fills(page, {(song.line, song.side): ""})
        row = [line for line in text.split("\n") if "Empty Dumpty" in line][0]
        self.assertEqual("| 13 || [[Empty Dumpty]] || A:me || 未创建 ||  || ", row)
        self.assertEqual("", split_row(row)[tr.COLUMNS.index("source")].value)

    def test_no_fills_returns_the_same_text(self):
        self.assertEqual(PAGE, apply_fills(PAGE, {}))

    def test_fill_leaves_other_cells_byte_identical(self):
        """空着的格子（``|| ||``）不能因为写回时丢了首尾空白而多出空格。"""
        line = ("| 18 || [[月之花]] || R Sound Design || {{color|#FF0000|未创建}} || || || "
                "15 || [[Minority Syndrome]] || Ray || {{color|#FF0000|未创建}} || ")
        text = apply_fills("a\n" + line + "\nb", {(1, 0): "[u 甲]", (1, 1): "[u 乙]"})
        self.assertEqual(
            "| 18 || [[月之花]] || R Sound Design || {{color|#FF0000|未创建}} || [u 甲] || || "
            "15 || [[Minority Syndrome]] || Ray || {{color|#FF0000|未创建}} || [u 乙] ",
            text.split("\n")[1])


class CreditNameTest(TestCase):
    def test_common_spellings(self):
        self.assertEqual("yanao", credit_name("翻譯：yanao"))
        self.assertEqual("夜明晴月", credit_name("翻译: 夜明晴月"))
        self.assertEqual("某人", credit_name("作詞：甲\n譯者：某人"))
        self.assertEqual("kankan", credit_name("中文歌詞：kankan"))

    def test_rejects_placeholders(self):
        self.assertEqual("", credit_name("翻譯：无"))
        self.assertEqual("", credit_name("翻译：待补"))
        self.assertEqual("", credit_name("这只是普通歌词，没有署名"))

    def test_ignores_chinese_lyrics_without_credit(self):
        self.assertEqual("", credit_name("怨恨啊怨恨啊"))

    def test_ignores_prose_mentioning_translation(self):
        """「用谷歌翻译成英文后根据英文翻译而来」不是署名（真实案例：Ensemble）。"""
        text = "没学过法语，词句是用谷歌翻译成英文后根据英文翻译而来，如有理解偏差是我个人的问题。"
        self.assertEqual("", credit_name(text))


class MissTtlTest(TestCase):
    """查不到来源的歌用更短的有效期，否则页面会几周没动静。"""

    def test_miss_expires_sooner_than_a_hit(self):
        now = time.time()
        miss = {"at": now - 4 * 24 * 3600, "v": tr.CACHE_VERSION, "sources": []}
        hit = {"at": now - 4 * 24 * 3600, "v": tr.CACHE_VERSION, "sources": ["[u 甲]"]}
        self.assertFalse(tr.is_current(miss, tr.CACHE_TTL, tr.MISS_TTL))
        self.assertTrue(tr.is_current(hit, tr.CACHE_TTL, tr.MISS_TTL))
        self.assertTrue(tr.is_current(miss, tr.CACHE_TTL))       # 不传 miss_ttl 就按老规矩

    def test_defaults(self):
        self.assertLess(tr.MISS_TTL, tr.CACHE_TTL)


class NeteaseQueryTest(TestCase):
    """搜歌名不够时，再用「P主 歌名」搜一遍（hubble / walker / 次世代 就是这样找到的）。"""

    def test_queries_include_the_producer(self):
        song = Song(0, 0, "11", "hubble", "hubble", "{{lj|歩く人}}")
        queries = tr.netease_queries(song)
        self.assertEqual("hubble", queries[0])
        self.assertIn("歩く人 hubble", queries)
        self.assertEqual(1, sum(1 for q in queries if q == "hubble"), "重复的别加两次")

    def test_no_producer_no_extra_query(self):
        song = Song(0, 0, "11", "hubble", "hubble", "")
        self.assertEqual(["hubble"], tr.netease_queries(song))

    def test_variant_result_is_rejected(self):
        """``Silver Lining`` 对上了 ``Silver Lining (Yandere VIP Remix)``：不记。"""
        song = Song(0, 0, "11", "Silver Lining", "Silver Lining", "picco")
        fetcher = LookupTest.FakeFetcher(payloads={
            tr.NETEASE_SEARCH.format(kw=urllib.parse.quote("Silver Lining")):
                {"result": {"songs": [{"id": 2, "name": "Silver Lining (Yandere VIP Remix)",
                                       "alias": [], "transNames": [],
                                       "artists": [{"name": "picco"}]}]}},
            tr.NETEASE_LYRIC.format(id="2"): {"tlyric": {"lyric": "[00:01]银线"}},
        })
        self.assertEqual([], tr.lookup_netease(fetcher, song))


class CellStateTest(TestCase):
    """机器人只维护自己写过的格子：内容与缓存里的结论一致才算「自己的」。"""

    def test_empty_cell(self):
        self.assertEqual("empty", tr.cell_state("", {"sources": ["[u 甲]"]}))
        self.assertEqual("empty", tr.cell_state(" ", None))

    def test_our_own_value(self):
        self.assertEqual("ours", tr.cell_state("[u 甲]<br/>[u 乙]",
                                               {"sources": ["[u 甲]", "[u 乙]"]}))

    def test_edited_by_someone_else(self):
        self.assertEqual("skip", tr.cell_state("网易云", {"sources": ["[u 甲]"]}))
        self.assertEqual("skip", tr.cell_state("网易云", None))

    def test_human_cells_in_the_same_format_are_not_ours(self):
        """页面主人也按 ``[链接 说明(by. 译者)]`` 写；格式像不等于就是机器人写的。

        2026-10-22 早先按格式认领，把 ``巴哈姆特(by. 月勳)``、``B站笔记(by. YUSI雨似)``
        这些他写的来源覆盖甚至清空了。
        """
        value = "[https://home.gamer.com.tw/artwork.php?sn=6097695 巴哈姆特(by. 月勳)]"
        self.assertEqual("skip", tr.cell_state(value, None))
        self.assertEqual("skip", tr.cell_state(value, {"sources": ["[u 甲]"]}))
        self.assertEqual("skip", tr.cell_state(
            "[https://www.bilibili.com/opus/1054280382312087569 B站笔记(by. YUSI雨似)]", {}))
        self.assertEqual("skip", tr.cell_state("[https://a.example 巴哈姆特]", {}))

    def test_previous_written_value_still_counts_as_ours(self):
        """结论变了以后，页面上那份旧内容仍然是机器人写的，要能跟着更新。"""
        entry = {"sources": ["[u 新]"], "written": "[u 旧]"}
        self.assertEqual("ours", tr.cell_state("[u 旧]", entry))
        self.assertEqual("ours", tr.cell_state("[u 新]", entry))
        self.assertEqual("skip", tr.cell_state("[u 别人]", entry))
        self.assertEqual("skip", tr.cell_state("[u 旧]", {"sources": [], "written": ""}))

    def test_our_sources_were_dropped(self):
        """结论变成空时那格不再是「自己的」，下次也不会去清别人写的同类内容。"""
        self.assertEqual("skip", tr.cell_state("[u 甲]", {"sources": []}))
        self.assertEqual("ours", tr.cell_state("[u 甲]", {"sources": ["[u 甲]"]}))

    def test_source_count(self):
        self.assertEqual(0, tr.source_count(""))
        self.assertEqual(1, tr.source_count("[u 甲]"))
        self.assertEqual(2, tr.source_count("[u 甲]<br/>[u 乙]"))

    def test_cache_version_gate(self):
        self.assertTrue(tr.is_current({"at": time.time(), "v": tr.CACHE_VERSION}, 60))
        self.assertFalse(tr.is_current({"at": time.time(), "v": 0}, 60))
        self.assertFalse(tr.is_current({"at": time.time()}, 60))
        self.assertFalse(tr.is_current({"at": time.time(), "v": tr.CACHE_VERSION}, 0))
        self.assertFalse(tr.is_current(None, 60))


class RenderSourceTest(TestCase):
    def test_with_and_without_translator(self):
        self.assertEqual("[https://a.example 网易云音乐(by. 白夜)]",
                         render_source("https://a.example", "网易云音乐", "白夜"))
        self.assertEqual("[https://a.example 网易云音乐]",
                         render_source("https://a.example", "网易云音乐", ""))

    def test_joined_with_br(self):
        self.assertEqual("[a 甲]<br/>[b 乙]",
                         join_sources([render_source("a", "甲"), render_source("b", "乙")]))


class MatchingTest(TestCase):
    def test_song_mentioned(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        self.assertTrue(song_mentioned("【MMD】千本桜 4K", song))
        self.assertTrue(song_mentioned("千本樱 中文填词", song))
        self.assertFalse(song_mentioned("完全无关的视频", song))

    def test_short_titles_do_not_match_everything(self):
        song = Song(0, 0, "1", "14", "14", "P")
        self.assertFalse(song_mentioned("2014年的老歌", song) and len("14") < 2)

    def test_chinese_lines(self):
        self.assertEqual(3, chinese_lines("怨恨啊怨恨啊\n那么好吧\n永别了我的脸"))
        long_note = "这是一段很长的说明文字，讲的是投稿时间与转载须知之类的东西，" * 2
        self.assertEqual(1, chinese_lines("怨灵案件\n" + long_note))
        self.assertEqual(0, chinese_lines("うらめしや\nいないいないばあ"))
        # 单行也算 1：调用方要求「≥ 2 行」才当成译文，单行闲聊因此被挡掉
        self.assertEqual(1, chinese_lines("谢谢分享"))

    def test_outbound_links(self):
        text = ("看 https://home.gamer.com.tw/artwork.php?sn=6402210 和 "
                "https://www.bilibili.com/opus/1251644081024532483 ")
        gamer, opus = outbound_links(text)
        self.assertEqual(["https://home.gamer.com.tw/artwork.php?sn=6402210"], gamer)
        self.assertEqual(["https://www.bilibili.com/opus/1251644081024532483"], opus)


class LookupTest(TestCase):
    class FakeFetcher:
        def __init__(self, texts=None, payloads=None):
            self.texts = texts or {}
            self.payloads = payloads or {}
            self.calls = []

        def text(self, url, attempts=3):
            self.calls.append(url)
            return self.texts.get(url, "")

        def json(self, url, attempts=3):
            self.calls.append(url)
            return self.payloads.get(url)

    def test_atwiki_needs_an_exact_page_name(self):
        song = Song(0, 0, "11", "月之花", "月之花", "R Sound Design")
        fetcher = self.FakeFetcher(texts={"https://w.atwiki.jp/vocaloidchly/pages/9.html":
                                         "<div id=\"wikibody\">作曲：R Sound Design<br/>"
                                         "翻譯：甲<br/>歌詞…</div>"
                                         "<div class=\"atwiki-page-keyword\">x</div>"})
        self.assertEqual([], tr.lookup_atwiki(fetcher, song, {}))
        self.assertEqual(["[https://w.atwiki.jp/vocaloidchly/pages/9.html "
                          "VOCALOID中文歌词wiki(by. 甲)]"],
                         tr.lookup_atwiki(fetcher, song, {title_key("月之花"): "9"}))

    def test_atwiki_rejects_a_page_for_another_song_with_the_same_name(self):
        """真实案例：``Linaria`` 那一页（p/7861）是 Mysteka 的，不是子牛的。"""
        song = Song(0, 0, "11", "Linaria", "Linaria", "子牛")
        page = ("<div id=\"wikibody\">作詞：Mysteka<br/>作曲：Mysteka<br/>"
                "翻譯：kyroslee<br/>Linaria<br/>歌詞</div>"
                "<div class=\"atwiki-page-keyword\">x</div>")
        fetcher = self.FakeFetcher(texts={"https://w.atwiki.jp/vocaloidchly/pages/7861.html": page})
        self.assertEqual([], tr.lookup_atwiki(fetcher, song, {title_key("Linaria"): "7861"}))

    def test_netease_requires_a_translation_and_a_title_match(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        search_url = tr.NETEASE_SEARCH.format(kw="%E5%8D%83%E6%9C%AC%E6%A1%9C")
        lyric_url = tr.NETEASE_LYRIC.format(id="2386546")
        fetcher = self.FakeFetcher(
            payloads={search_url: {"result": {"songs": [
                {"id": 2386546, "name": "千本桜", "alias": [], "transNames": [],
                 "artists": [{"name": "黒うさP"}]}]}},
                lyric_url: {"tlyric": {"lyric": "[00:01]千本樱"},
                            "transUser": {"nickname": "白夜"}}})
        self.assertEqual(["[https://music.163.com/#/song?id=2386546 网易云音乐(by. 白夜)]"],
                         tr.lookup_netease(fetcher, song))

    def test_netease_without_tlyric_is_not_a_source(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        search_url = tr.NETEASE_SEARCH.format(kw="%E5%8D%83%E6%9C%AC%E6%A1%9C")
        lyric_url = tr.NETEASE_LYRIC.format(id="2386546")
        fetcher = self.FakeFetcher(
            payloads={search_url: {"result": {"songs": [
                {"id": 2386546, "name": "千本桜", "alias": [], "transNames": [],
                 "artists": [{"name": "黒うさP"}]}]}},
                lyric_url: {"tlyric": {"lyric": ""}}})
        self.assertEqual([], tr.lookup_netease(fetcher, song))

    def test_netease_ignores_other_songs(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        search_url = tr.NETEASE_SEARCH.format(kw="%E5%8D%83%E6%9C%AC%E6%A1%9C")
        fetcher = self.FakeFetcher(payloads={search_url: {"result": {"songs": [
            {"id": 1, "name": "别的歌", "alias": [], "transNames": [],
             "artists": [{"name": "黒うさP"}]}]}}})
        self.assertEqual([], tr.lookup_netease(fetcher, song))

    def test_netease_needs_the_producer_in_the_credits(self):
        """同名不同曲：``月之花`` 能搜到 Daoko 的 ``月の花``，歌手/专辑里都没有 P主 就不算。"""
        song = Song(0, 0, "18", "月之花", "月之花", "R Sound Design")
        search_url = tr.NETEASE_SEARCH.format(kw="%E6%9C%88%E4%B9%8B%E8%8A%B1")
        lyric_url = tr.NETEASE_LYRIC.format(id="2046697266")
        fetcher = self.FakeFetcher(
            payloads={search_url: {"result": {"songs": [
                {"id": 2046697266, "name": "月の花", "alias": [], "transNames": ["月之花"],
                 "artists": [{"name": "Daoko"}], "album": {"name": "月の花"}}]}},
                lyric_url: {"tlyric": {"lyric": "[00:01]月之花"}}})
        self.assertEqual([], tr.lookup_netease(fetcher, song))

    def test_netease_song_without_producer_cell_is_skipped(self):
        song = Song(0, 0, "18", "月之花", "月之花", "")
        search_url = tr.NETEASE_SEARCH.format(kw="%E6%9C%88%E4%B9%8B%E8%8A%B1")
        fetcher = self.FakeFetcher(payloads={search_url: {"result": {"songs": [
            {"id": 1, "name": "月之花", "alias": [], "transNames": [],
             "artists": [{"name": "某人"}]}]}}})
        self.assertEqual([], tr.lookup_netease(fetcher, song))


class BilibiliTest(TestCase):
    class FakeFetcher:
        def __init__(self, payloads=None, texts=None):
            self.payloads = payloads or {}
            self.texts = texts or {}

        def json(self, url, attempts=3):
            return self.payloads.get(url)

        def text(self, url, attempts=3):
            return self.texts.get(url, "")

    def _view(self, bvid, title, desc, owner="UP主", aid=1, cid=2):
        return {tr.BILIBILI_VIEW.format(bvid=bvid): {"code": 0, "data": {
            "bvid": bvid, "title": title, "desc": desc, "aid": aid, "cid": cid,
            "owner": {"name": owner}}}}

    def test_desc_credit_is_recorded(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        fetcher = self.FakeFetcher(payloads=self._view(
            "BV1", "千本桜 中文", "本家：黒うさP\n翻译：某人\n千本樱歌词"))
        sources, _, _ = tr.video_sources(fetcher, "BV1", song, require_mention=True)
        self.assertEqual(["[https://www.bilibili.com/video/BV1 B站视频简介(by. 某人)]"],
                         sources)

    def test_unrelated_video_is_skipped(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        fetcher = self.FakeFetcher(payloads=self._view("BV9", "别的东西", "翻译：某人"))
        self.assertEqual(([], "翻译：某人", "别的东西"),
                         tr.video_sources(fetcher, "BV9", song, require_mention=True))

    def test_search_video_without_the_producer_is_skipped(self):
        """真实案例：``RITA`` 搜到 TED 演讲的翻译视频、``亡灵`` 搜到有声书。"""
        song = Song(0, 0, "11", "RITA", "RITA", "黑泽まどか")
        fetcher = self.FakeFetcher(payloads=self._view(
            "BV1", "私塾翻译 | RITA Pierson TED 中英双语字幕", "翻译：私塾先生lilz"))
        self.assertEqual([], tr.video_sources(fetcher, "BV1", song, require_mention=True)[0])

    def test_producer_mention(self):
        song = Song(0, 0, "11", "RITA", "RITA", "Hal")
        self.assertTrue(tr.producer_mentioned("本家：Hal", song))
        self.assertTrue(tr.producer_mentioned("作詞作曲：hal", song))
        self.assertFalse(tr.producer_mentioned("halcyon days", song))
        cjk = Song(0, 0, "11", "狂信者", "狂信者", "{{lj|umigame}}")
        self.assertTrue(tr.producer_mentioned("music: umigame", cjk))
        self.assertFalse(tr.producer_mentioned("黑执事 OP", cjk))

    def test_own_upload_needs_no_title_match(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        fetcher = self.FakeFetcher(payloads=self._view("BV1", "本家", "翻译：甲"))
        sources, _, _ = tr.video_sources(fetcher, "BV1", song, require_mention=False)
        self.assertEqual(["[https://www.bilibili.com/video/BV1 B站视频简介(by. 甲)]"],
                         sources)

    def test_comment_with_translated_lyrics(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        payloads = self._view("BV2", "千本桜 / 黒うさP", "")
        payloads[tr.BILIBILI_REPLY.format(oid="1", pn=1)] = {"code": 0, "data": {
            "replies": [{"rpid": 55, "member": {"uname": "译者"},
                         "content": {"message": "翻译：译者\n千本樱\n怨恨啊怨恨啊"}}]}}
        payloads[tr.BILIBILI_REPLY.format(oid="1", pn=2)] = {"code": 0, "data": {"replies": []}}
        fetcher = self.FakeFetcher(payloads=payloads)
        sources, _, _ = tr.video_sources(fetcher, "BV2", song, require_mention=True)
        self.assertEqual(["[https://www.bilibili.com/video/BV2#reply55 B站评论区(by. 译者)]"],
                         sources)

    def test_danmaku_credit(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        payloads = self._view("BV3", "千本桜 / 黒うさP", "")
        payloads[tr.BILIBILI_REPLY.format(oid="1", pn=1)] = {"code": 0, "data": {"replies": []}}
        fetcher = self.FakeFetcher(payloads=payloads,
                                   texts={tr.BILIBILI_DANMAKU.format(cid="2"):
                                          '<i><d p="1,2">翻译：弹幕君</d></i>'})
        sources, _, _ = tr.video_sources(fetcher, "BV3", song, require_mention=True)
        self.assertEqual(["[https://www.bilibili.com/video/BV3 B站弹幕(by. 弹幕君)]"],
                         sources)

    def test_bahamut_requires_title_and_credit(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        page = ('<html><head><title>千本桜 中文 - 某人 的創作</title></head>'
                '<div class="article-content main">翻譯：某人<br/>千本樱</div>'
                '<a class="caption-text primary">某人</a></html>')
        fetcher = self.FakeFetcher(texts={"https://home.gamer.com.tw/artwork.php?sn=1": page})
        self.assertEqual(["[https://home.gamer.com.tw/artwork.php?sn=1 巴哈姆特(by. 某人)]"],
                         tr.lookup_bahamut(fetcher, "https://home.gamer.com.tw/artwork.php?sn=1",
                                           song))
        self.assertEqual([], tr.lookup_bahamut(
            fetcher, "https://home.gamer.com.tw/artwork.php?sn=2", song))


class FetcherBlockTest(TestCase):
    """被站点 412 盾掉之后，整轮都不再打这个站（GitHub runner 的机房 IP 就是这样）。"""

    def test_412_blocks_the_whole_site(self):
        fetcher = tr.Fetcher()
        calls = []

        def fake_open(url, timeout=None):
            calls.append(url)
            raise urllib.error.HTTPError(url, 412, "Precondition Failed", None, None)

        fetcher.opener.open = fake_open
        self.assertEqual("", fetcher.text("https://api.bilibili.com/x/web-interface/view?bvid=BV1"))
        self.assertEqual("", fetcher.text("https://www.bilibili.com/video/BV1"))
        self.assertEqual(1, len(calls), "同一个站第二次就该直接返回空")
        self.assertTrue(fetcher.is_blocked("https://api.bilibili.com/x/v2/reply?oid=1"))
        self.assertFalse(fetcher.is_blocked("https://music.163.com/api/search/get?s=x"))

    def test_repeated_failures_stop_the_site(self):
        """连不上的站要整轮放弃：补录扫描上千行，否则会一直卡在重试里。"""
        fetcher = tr.Fetcher()
        calls = []

        def fake_open(url, timeout=None):
            calls.append(url)
            raise urllib.error.URLError("ssl eof")

        fetcher.opener.open = fake_open
        with patch("time.sleep"):
            for _ in range(tr.FAILURE_LIMIT):
                fetcher.text("https://w.atwiki.jp/x", attempts=1)
            before = len(calls)
            fetcher.text("https://w.atwiki.jp/y", attempts=1)
        self.assertEqual(before, len(calls), "达到上限后不该再发请求")
        self.assertTrue(fetcher.is_blocked("https://w.atwiki.jp/z"))
        self.assertFalse(fetcher.is_blocked("https://music.163.com/api/x"))

    def test_other_errors_still_retry(self):
        fetcher = tr.Fetcher()
        calls = []

        def fake_open(url, timeout=None):
            calls.append(url)
            raise urllib.error.URLError("boom")

        fetcher.opener.open = fake_open
        with patch("time.sleep"):
            self.assertEqual("", fetcher.text("https://w.atwiki.jp/x", attempts=3))
        self.assertEqual(3, len(calls))
        self.assertFalse(fetcher.blocked)


class RunOnceTest(TestCase):
    """整轮跑下来也不能碰别人写的格子（哪怕格式和机器人一样）。"""

    class FakePage:
        def __init__(self, site, title):
            self.text = ""
            self.saved = []
            self.summaries = []

        def save(self, **kwargs):
            self.saved.append(self.text)
            self.summaries.append(kwargs.get("summary", ""))

    class FakeSite:
        def logged_in(self):
            return True

    def _run(self, page_text, cache=None, sources=(), fetcher=None, pruned=()):
        """``pruned``：模拟 prune_entries 的结论（默认不动页面）。"""
        page = self.FakePage(None, None)
        page.text = page_text

        def fake_prune(site, fetcher_, text, refresh=False, lookup=None):
            return tr.prune_created_rows(text, set(pruned)) if pruned else (text, [])

        with patch.object(tr, "Page", return_value=page), \
                patch.object(tr, "load_cache", return_value=cache or {}), \
                patch.object(tr, "save_cache"), \
                patch.object(tr, "atwiki_page_index", return_value={}), \
                patch.object(tr, "prune_entries", side_effect=fake_prune), \
                patch.object(tr, "collect_sources", return_value=list(sources)):
            changed = tr.run_once(self.FakeSite(), write=True, refresh=True,
                                  fetcher=fetcher or object(), add_missing=True)
        return changed, page

    def test_rows_of_created_songs_are_removed_before_filling(self):
        """有条目的行整行删掉，摘要里写清楚删了几个。"""
        page_text = ("== ボカコレ2022春 ==\n"
                     "{| class=\"wikitable\"\n"
                     "|-\n"
                     "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注\n"
                     "|-\n"
                     "| 46 || [[Maison]] || {{lj|歩く人}} || 未创建 || || \n"
                     "|-\n"
                     "| 24 || [[诅咒之吻]] || IZ || 未创建 || || \n"
                     "|}")
        changed, page = self._run(page_text, pruned={tr.title_key("Maison")})
        self.assertTrue(changed)
        self.assertNotIn("Maison", page.saved[0])
        self.assertIn("[[诅咒之吻]]", page.saved[0])
        self.assertIn("删掉 1 个已有条目的行", page.summaries[0])

    def test_no_prune_flag_keeps_created_rows(self):
        page_text = ("{|\n"
                     "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注\n"
                     "|-\n"
                     "| 46 || [[Maison]] || P || 未创建 || || \n"
                     "|}")
        page = self.FakePage(None, None)
        page.text = page_text
        with patch.object(tr, "Page", return_value=page), \
                patch.object(tr, "load_cache", return_value={}), \
                patch.object(tr, "save_cache"), \
                patch.object(tr, "atwiki_page_index", return_value={}), \
                patch.object(tr, "prune_entries") as prune, \
                patch.object(tr, "collect_sources", return_value=[]):
            tr.run_once(self.FakeSite(), write=True, refresh=True,
                        fetcher=object(), prune=False)
        prune.assert_not_called()
        self.assertEqual([], page.saved)

    def test_wrong_rows_are_dropped_even_when_atwiki_is_paused(self):
        """AtWiki 停用只停「收录」，配错的旧行还是要删（``USE_ATWIKI`` 不能挡住清理）。"""
        page_text = "\n".join([
            "== ボカコレ2022秋 ==",
            "{|",
            "|-",
            "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注",
            "|-",
            "| 60 || [[死亡フラグ]] || {{lj|コーチP}} || {{color|#FF0000|未创建}} || "
            "[https://w.atwiki.jp/vocaloidchly/pages/3460.html VOCALOID中文歌词wiki(by. MIU)] || ",
            "|}",
            "",
        ])
        fetcher = AtwikiSongTest.FakeFetcher({
            tr.ATWIKI_PAGE.format(pid="3460"):
                '<div id="wikibody">作曲：コーチP<br/>翻譯：MIU<br/>歌詞</div>'
                '<div class="atwiki-page-keyword">x</div>'
                '<a href="https://www.nicovideo.jp/watch/sm14446365">原曲</a>',
            tr.NICO_INFO.format(vid="sm14446365"):
                "<first_retrieve>2011-05-14T05:06:05+09:00</first_retrieve>",
        })
        changed, page = self._run(page_text, fetcher=fetcher)
        self.assertTrue(changed)
        self.assertNotIn("死亡フラグ", page.saved[0])
        self.assertIn("删掉 1 行配错的补录", page.summaries[0])

    def test_human_cells_are_never_overwritten(self):
        human = ("{|\n"
                 "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注\n"
                 "|-\n"
                 "| 41 || [[鸟笼(椿)|鸟笼]] || 椿 || {{color|#FF0000|未创建}} || "
                 "[https://home.gamer.com.tw/artwork.php?sn=6097695 巴哈姆特(by. 月勳)] || \n"
                 "|-\n"
                 "| 75 || [[十月，夏末残花之追忆]] || 奈良瀬 || {{color|#FF0000|未创建}} || "
                 "[https://www.bilibili.com/opus/1054280382312087569 B站笔记(by. YUSI雨似)] || \n"
                 "|}")
        changed, page = self._run(human, sources=["[https://a.example 网易云音乐(by. 甲)]"])
        self.assertFalse(changed)
        self.assertEqual(human, page.text, "别人写过的格子一个字节都不该动")
        self.assertEqual([], page.saved)

    def test_empty_cells_get_filled(self):
        page_text = ("{|\n"
                     "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注\n"
                     "|-\n"
                     "| 18 || [[月之花]] || R Sound Design || 未创建 || || \n"
                     "|}")
        changed, page = self._run(page_text, sources=["[https://a.example 网易云音乐]"])
        self.assertTrue(changed)
        self.assertIn("未创建 || [https://a.example 网易云音乐] || ",
                      page.saved[0])

    def test_own_cell_from_the_cache_is_updated(self):
        page_text = ("{|\n"
                     "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注\n"
                     "|-\n"
                     "| 18 || [[月之花]] || R Sound Design || 未创建 || [https://old.example 网易云音乐] || \n"
                     "|}")
        cache = {tr.title_key("月之花"): {"at": time.time(), "v": tr.CACHE_VERSION,
                                          "sources": ["[https://old.example 网易云音乐]"],
                                          "written": "[https://old.example 网易云音乐]"}}
        changed, page = self._run(page_text, cache=cache,
                                  sources=["[https://new.example 网易云音乐]"])
        self.assertTrue(changed)
        self.assertIn("[https://new.example 网易云音乐]", page.saved[0])
        self.assertNotIn("old.example", page.saved[0])


CONTRIB = """== 相关统计 ==
=== 2022春 ===
{{multicol}}
<poem>;TOP100 (75/100)
{|class="wikitable"
|-
| bgcolor=#8DA5B0 | {{colorlink|#000|随之任之|1}} || [[無題 ep.01|5]] || [[ORDER|27]]
|-
| {{colorlink|#FFF|maison|46}} || {{colorlink|#FFF|Equivalent|56}} || {{colorlink|#FFF|东京Nighthawk|53}}
|}
;ROOKIE (43/100)
{|class="wikitable"
|-
| {{colorlink|#FFF|感情欺诈|1}} || [[無題 ep.01|3]] || [[ORDER|14]]
|-
| [[心不在焉|5]] || [[没有心|7]]
|}
"""

NAVBOX = """{{Navbox
| list1 = {{lj|[[無題 ep.01]]}}<!--
     --> • {{lj|[[心不在焉|こころもとなく]]}}<!--
     --> • [[ORDER]]<!--
     --> • [[maison|メゾン]]
}}
"""

SEASON_PAGE = """== ボカコレ2022春 ==
{| class="wikitable " style="text-align:center;"
|-
! colspan="6"|TOP100 !! colspan="6"|ROOKIE
|-
! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注 !! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注
|-
| 24 || [[诅咒之吻]] || IZ || {{color|#FF0000|未创建}} || || || {{注|3|总榜为第5}} || [[无题 ep.01]] || {{lj|袖野あらわ}} || {{color|#FF0000|未创建}} || 
|-
| 52 || [[日本之夏]] || 平田義久 || {{color|#FF0000|未创建}} || || || 7 || [[没有心]] || saikawa || {{color|#FF0000|未创建}} || 
|}
"""


class ContribParseTest(TestCase):
    def test_tracks_and_created_flags(self):
        seasons = tr.parse_contrib_seasons(CONTRIB)
        self.assertIn("ボカコレ2022春", seasons)
        top = seasons["ボカコレ2022春"]["TOP100"]
        self.assertEqual(("随之任之", True), top[1])
        self.assertEqual(("無題 ep.01", False), top[5])
        self.assertEqual(("maison", True), top[46])
        self.assertEqual(5, len(seasons["ボカコレ2022春"]["ROOKIE"]))

    def test_navbox_titles(self):
        titles = tr.navbox_titles(NAVBOX)
        self.assertIn(tr.title_key("心不在焉"), titles)
        self.assertIn(tr.title_key("こころもとなく"), titles)   # 日文原名也算
        self.assertIn(tr.title_key("ORDER"), titles)
        self.assertIn(tr.title_key("maison"), titles)


class PageSeasonsTest(TestCase):
    def test_records_per_track(self):
        recorded = tr.page_season_songs(SEASON_PAGE)
        self.assertEqual({24, 52}, recorded["ボカコレ2022春"]["TOP100"])
        self.assertEqual({3, 7}, recorded["ボカコレ2022春"]["ROOKIE"])

    def test_missing_skips_created_and_recorded(self):
        seasons = tr.parse_contrib_seasons(CONTRIB)
        missing = tr.missing_songs(SEASON_PAGE, seasons)
        pairs = {(item.track, item.rank) for item in missing}
        self.assertNotIn(("TOP100", 46), pairs)     # maison 已经有条目
        self.assertNotIn(("TOP100", 56), pairs)     # Equivalent 已经有条目
        self.assertNotIn(("ROOKIE", 3), pairs)      # 已录入（无题 ep.01）
        self.assertNotIn(("ROOKIE", 7), pairs)      # 已录入（没有心）
        self.assertIn(("TOP100", 27), pairs)        # ORDER 未创建、未录入 → 缺
        self.assertIn(("ROOKIE", 5), pairs)
        # TOP100 第 5 号（無題 ep.01）已经以 ROOKIE 行 + 总榜注记录入过，不能再补一行
        self.assertNotIn(("TOP100", 5), pairs)
        # ROOKIE 第 1 号已有条目
        self.assertNotIn(("ROOKIE", 1), pairs)


class RowBuildTest(TestCase):
    def test_builds_only_the_target_side(self):
        row = tr.build_row(2, 1, ["5", "[[曲]]", "P主", "未创建", "[u 源]", ""])
        self.assertEqual("| || || || || || || 5 || [[曲]] || P主 || 未创建 || [u 源] || ", row)
        self.assertEqual(12, len(tr.split_row(row)))
        self.assertEqual("", tr.split_row(row)[0].value)

    def test_inserts_at_the_right_rank(self):
        text = tr.insert_row(SEASON_PAGE, "ボカコレ2022春", "TOP100", 30,
                             "| 30 || [[新歌]] || 某人 || {{color|#FF0000|未创建}} || || ")
        self.assertIn("| 24 || [[诅咒之吻]]", text)
        lines = text.split("\n")
        first = [i for i, l in enumerate(lines) if "新歌" in l][0]
        later = [i for i, l in enumerate(lines) if "日本之夏" in l][0]
        self.assertLess(first, later, "30 应该插在 52 前面")
        self.assertTrue(lines[first - 1].startswith("|-"), "新行前面要有分隔符")
        self.assertEqual("|-", lines[first + 1], "原来的行要留着自己的分隔符")
        self.assertNotIn("|-\n|-", text)

    def test_appends_at_the_end_when_rank_is_largest(self):
        text = tr.insert_row(SEASON_PAGE, "ボカコレ2022春", "ROOKIE", 90,
                             "| 90 || [[最后一首]] || P || {{color|#FF0000|未创建}} || || ")
        lines = text.split("\n")
        last_row = [i for i, l in enumerate(lines) if "没有心" in l][0]
        added = [i for i, l in enumerate(lines) if "最后一首" in l][0]
        self.assertGreater(added, last_row)
        self.assertIn("|}", lines[added + 1])

    def test_atwiki_credits_prefer_composer(self):
        body = "作詞：甲\n作曲：{{lj|乙}}\n編曲：丙\n翻譯：丁"
        self.assertEqual("{{lj|乙}}", tr.atwiki_credits(body))
        body2 = "作詞：甲\n翻譯：丁"
        self.assertEqual("甲", tr.atwiki_credits(body2))
        self.assertEqual("", tr.atwiki_credits("翻譯：丁"))

    def test_render_song_title(self):
        self.assertEqual("{{lj|[[ハロー]]}}", tr.render_song_title("ハロー"))
        self.assertEqual("[[心不在焉]]", tr.render_song_title("心不在焉"))
        self.assertEqual("[[ハロー(初音ミク)]]", tr.render_song_title("ハロー(初音ミク)"))


class AtwikiSongTest(TestCase):
    """补录前必须核实：曲名是日文原名 + P主 对得上同名不同曲 + 投稿年对得上赛季。"""

    class FakeFetcher:
        def __init__(self, bodies):
            self.bodies = bodies

        def text(self, url, attempts=3):
            return self.bodies.get(url, "")

    def _page(self, pid, body, video="sm14446365", upload="2011-05-14"):
        pages = {tr.ATWIKI_PAGE.format(pid=pid):
                 f'<div id="wikibody">{body}</div><div class="atwiki-page-keyword">x</div>'}
        if video:
            pages[tr.ATWIKI_PAGE.format(pid=pid)] += (
                f'<a href="https://www.nicovideo.jp/watch/{video}">原曲</a>')
            pages[tr.NICO_INFO.format(vid=video)] = (
                f"<thumb><first_retrieve>{upload}T05:06:05+09:00</first_retrieve></thumb>")
        return pages

    def test_parenthetical_hint_must_match_the_composer(self):
        fetcher = self.FakeFetcher(self._page("3414", "作曲：骨盤P<br/>翻譯：某人<br/>歌詞"))
        index = {tr.title_key("Colors(kouta)"): "3414"}
        self.assertIsNone(tr.atwiki_song(fetcher, index, "Colors(kouta)"))

    def test_japanese_title_with_matching_hint(self):
        fetcher = self.FakeFetcher(self._page("3414", "作曲：kouta<br/>翻譯：某人<br/>歌詞"))
        index = {tr.title_key("Colors(kouta)"): "3414"}
        self.assertEqual(("3414", "某人", "kouta"),
                         tr.atwiki_song(fetcher, index, "Colors(kouta)"))

    def test_japanese_title_is_accepted_when_the_year_matches(self):
        fetcher = self.FakeFetcher(self._page("3460", "作曲：コーチP<br/>翻譯：MIU<br/>歌詞",
                                              upload="2022-10-14"))
        index = {tr.title_key("死亡フラグ"): "3460"}
        self.assertEqual(("3460", "MIU", "コーチP"),
                         tr.atwiki_song(fetcher, index, "死亡フラグ", "ボカコレ2022秋"))

    def test_japanese_title_from_another_year_is_rejected(self):
        """真实案例：``死亡フラグ`` 的 p/3460 是 2011 年的老曲，却补进了 2022秋。"""
        fetcher = self.FakeFetcher(self._page("3460", "作曲：コーチP<br/>翻譯：MIU<br/>歌詞"))
        index = {tr.title_key("死亡フラグ"): "3460"}
        self.assertIsNone(tr.atwiki_song(fetcher, index, "死亡フラグ", "ボカコレ2022秋"))

    def test_page_without_an_upload_date_is_rejected(self):
        fetcher = self.FakeFetcher(self._page("3460", "作曲：コーチP<br/>翻譯：MIU<br/>歌詞",
                                              video=""))
        index = {tr.title_key("死亡フラグ"): "3460"}
        self.assertIsNone(tr.atwiki_song(fetcher, index, "死亡フラグ", "ボカコレ2022秋"))

    def test_remix_titles_skip_the_year_check(self):
        """改曲的译文本就挂在原曲页面上：投稿年是原曲那一年，不能当错配。"""
        fetcher = self.FakeFetcher(self._page("7835", "作曲：yuigot<br/>翻譯：某人<br/>歌詞",
                                              upload="2018-02-16"))
        self.assertTrue(tr.atwiki_year_ok(
            fetcher, "7835", 2020, "メルティランドナイトメア (yuigot Remix)"))
        self.assertFalse(tr.atwiki_year_ok(fetcher, "7835", 2020, "メルティランドナイトメア"))

    def test_plain_chinese_or_ascii_titles_are_rejected(self):
        """``PANDORA`` / ``Femme Fatale`` 这种对上同名的别国歌曲：一律不认。"""
        fetcher = self.FakeFetcher(self._page("2231", "作曲：やしきん<br/>翻譯：cyataku<br/>歌詞"))
        for title in ("PANDORA", "Femme Fatale", "心不在焉"):
            index = {tr.title_key(title): "2231"}
            self.assertIsNone(tr.atwiki_song(fetcher, index, title))

    def test_needs_a_composer_or_translator(self):
        fetcher = self.FakeFetcher(self._page("9", "歌詞だけ<br/>ラララ"))
        self.assertIsNone(tr.atwiki_song(fetcher, {tr.title_key("ハロー"): "9"}, "ハロー"))

    def test_season_year(self):
        self.assertEqual(2022, tr.season_year("ボカコレ2022秋"))
        self.assertEqual(2020, tr.season_year("ボカコレ2020冬"))
        self.assertIsNone(tr.season_year(""))

    def test_title_hint(self):
        self.assertEqual("kouta", tr.title_hint("Colors(kouta)"))
        self.assertEqual("", tr.title_hint("ORDER"))
        self.assertEqual("", tr.title_hint("无题(2005)"))


class DropWrongRowsTest(TestCase):
    """页面里引错 AtWiki 页面的行：整行是错配产物就删，只有来源是错的就清那一格。"""

    class FakeFetcher:
        def __init__(self, pages):
            self.pages = pages

        def text(self, url, attempts=3):
            return self.pages.get(url, "")

    PAGE = "\n".join([
        "== ボカコレ2022秋 ==",
        '{| class="wikitable " style="text-align:center;"',
        "|-",
        '! colspan="6"|TOP100 !! colspan="6"|ROOKIE',
        "|-",
        "! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注 "
        "!! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注",
        "|-",
        "| || || || || || || 32 || [[PANDORA]] || {{lj|やしきん}} || "
        "{{color|#FF0000|未创建}} || "
        "[https://w.atwiki.jp/vocaloidchly/pages/2231.html VOCALOID中文歌词wiki(by. cyataku)] ||",
        "|-",
        "| || || || || || || 60 || [[死亡フラグ]] || {{lj|コーチP}} || "
        "{{color|#FF0000|未创建}} || "
        "[https://w.atwiki.jp/vocaloidchly/pages/3460.html VOCALOID中文歌词wiki(by. MIU)] ||",
        "|}",
        "",
    ])

    def _fetcher(self, years):
        pages = {}
        for pid, (producer, translator, upload) in years.items():
            pages[tr.ATWIKI_PAGE.format(pid=pid)] = (
                f'<div id="wikibody">作曲：{producer}<br/>翻譯：{translator}<br/>歌詞</div>'
                f'<div class="atwiki-page-keyword">x</div>'
                f'<a href="https://www.nicovideo.jp/watch/sm{pid}">原曲</a>')
            pages[tr.NICO_INFO.format(vid="sm" + pid)] = (
                f"<first_retrieve>{upload}T00:00:00+09:00</first_retrieve>")
        return self.FakeFetcher(pages)

    def test_rows_whose_producer_came_from_the_wrong_page_are_removed(self):
        fetcher = self._fetcher({
            "2231": ("やしきん", "cyataku", "2010-04-10"),
            "3460": ("コーチP", "MIU", "2011-05-14"),
        })
        text, notes = tr.drop_wrong_rows(self.PAGE, fetcher)
        self.assertNotIn("PANDORA", text)
        self.assertNotIn("死亡フラグ", text)
        self.assertEqual(2, len(notes))
        self.assertIn("== ボカコレ2022秋 ==", text)
        self.assertEqual(text.count("|-"), 2)   # 只剩表头那两条分隔符

    def test_only_the_source_cell_is_cleared_when_the_producer_is_someone_elses(self):
        page = self.PAGE.replace("{{lj|コーチP}}", "别人写的P主")
        fetcher = self._fetcher({"3460": ("コーチP", "MIU", "2011-05-14")})
        text, notes = tr.drop_wrong_rows(page, fetcher)
        self.assertIn("[[死亡フラグ]]", text)
        self.assertIn("别人写的P主", text)
        self.assertNotIn("pages/3460.html", text)
        self.assertEqual(1, len(notes))

    def test_rows_from_the_right_year_are_untouched(self):
        fetcher = self._fetcher({
            "2231": ("やしきん", "cyataku", "2022-09-24"),
            "3460": ("コーチP", "MIU", "2022-10-08"),
        })
        text, notes = tr.drop_wrong_rows(self.PAGE, fetcher)
        self.assertEqual(self.PAGE, text)
        self.assertEqual([], notes)

    def test_rows_without_a_known_upload_date_are_untouched(self):
        fetcher = self.FakeFetcher({
            tr.ATWIKI_PAGE.format(pid="3460"):
                '<div id="wikibody">作曲：コーチP<br/>翻譯：MIU<br/>歌詞</div>'
                '<div class="atwiki-page-keyword">x</div>',
        })
        text, notes = tr.drop_wrong_rows(self.PAGE, fetcher)
        self.assertEqual(self.PAGE, text)
        self.assertEqual([], notes)


PRUNE_PAGE = """== ボカコレ2022春 ==
{| class="wikitable " style="text-align:center;"
|-
! colspan="6"|TOP100 !! colspan="6"|ROOKIE
|-
! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注 !! 名次 !! 曲名(无翻译则原名字) !! P主 !! 条目状态 !! 翻译来源 !! 备注
|-
| 46 || [[Maison]] || {{lj|歩く人}} || {{color|#FF0000|未创建}} || || || {{注|5|总榜为第10}} || [[没有心]] || saikawa || {{color|#FF0000|未创建}} || 
|-
| 24 || [[诅咒之吻]] || IZ || {{color|#FF0000|未创建}} || || || {{注|3|总榜为第5}} || [[无题 ep.01]] || {{lj|袖野あらわ}} || {{color|#FF0000|未创建}} || 
|-
| 56 || [[Equivalent]] || {{lj|きっと、ずっと、ぼっち。}} || {{color|#FF0000|未创建}} || || || {{注|14|总榜为第27}} || [[ORDER]] || Hal || {{color|#FF0000|未创建}} || 
|}
"""


class StrictKeyTest(TestCase):
    """删行必须按完整标题认：括注是消歧义后缀，不是装饰。"""

    def test_keeps_the_parenthetical_suffix(self):
        self.assertEqual("eden(酔シグレ)", tr.strict_key("[[EDEN(酔シグレ)|EDEN]]"))
        self.assertEqual("言灵(pirop)", tr.strict_key("[[言灵(PiroP)|言灵]]"))
        self.assertNotEqual(tr.strict_key("[[EDEN(酔シグレ)|EDEN]]"), tr.strict_key("EDEN"))

    def test_still_normalises_everything_else(self):
        self.assertEqual("maison", tr.strict_key("[[Maison]]"))
        self.assertEqual("meromu", tr.strict_key("{{lj|[[ Meromu]]}}<!-- x -->"))
        self.assertEqual("burial-marker", tr.strict_key("Burial-Marker"))


class ArticleProducerTest(TestCase):
    class FakeSite:
        pass

    def test_reads_p_main_field(self):
        with patch.object(tr, "Page") as page_cls:
            page_cls.return_value.text = "{{VOCALOID Songbox\n|P主 = {{lj|[[いち野]]}}\n}}"
            self.assertEqual("{{lj|[[いち野]]}}", tr.article_producer(self.FakeSite(), "RITA"))

    def test_missing_field_is_empty(self):
        with patch.object(tr, "Page") as page_cls:
            page_cls.return_value.text = "只是一个列表页"
            self.assertEqual("", tr.article_producer(self.FakeSite(), "Redial"))

    def test_same_producer(self):
        with patch.object(tr, "article_producer", return_value="{{lj|[[いち野]]}}"):
            self.assertTrue(tr.article_is_ours(self.FakeSite(), "RITA", "{{lj|いち野}}"))
        with patch.object(tr, "article_producer", return_value="{{lj|[[みつばちぼっち]]}}"):
            self.assertFalse(tr.article_is_ours(self.FakeSite(), "EDEN", "{{lj|酔シグレ}}"))
        with patch.object(tr, "article_producer", return_value=""):
            self.assertFalse(tr.article_is_ours(self.FakeSite(), "Redial", "鶴三"))


class CreatedAfterRedirectsTest(TestCase):
    """API 结果 → 已经有条目的标题（跟重定向、排除消歧义页）。"""

    def test_plain_existing_page(self):
        query = {"pages": {"1": {"title": "maison", "pageid": 1}}}
        self.assertEqual({"maison"}, tr.created_after_redirects(query))

    def test_missing_and_disambiguation_are_not_articles(self):
        query = {"pages": {
            "1": {"title": "ORDER", "missing": ""},
            "-1": {"title": "幽灵"},
            "2": {"title": "心不在焉", "pageid": 2,
                  "pageprops": {"disambiguation": ""}},
            "3": {"title": "涅槃", "pageid": 3,
                  "categories": [{"title": "Category:消歧义页"}]},
            "4": {"title": "涅槃(HotaRu)", "pageid": 4,
                  "categories": [{"title": "Category:消歧义模板链入页面错误"}]},
        }}
        self.assertEqual({"涅槃(HotaRu)"}, tr.created_after_redirects(query))

    def test_redirect_chain_maps_back_to_the_query_title(self):
        query = {
            "normalized": [{"from": "maison ", "to": "Maison"}],
            "redirects": [{"from": "Maison", "to": "メゾン"}],
            "pages": {"7": {"title": "メゾン", "pageid": 7}},
        }
        found = tr.created_after_redirects(query)
        self.assertIn("maison ", found)     # 原标题也算
        self.assertIn("メゾン", found)

    def test_redirect_to_a_missing_page_is_not_an_article(self):
        query = {
            "redirects": [{"from": "東京Nighthawk", "to": "东京Nighthawk"}],
            "pages": {"-1": {"title": "东京Nighthawk", "missing": ""}},
        }
        self.assertEqual(set(), tr.created_after_redirects(query))


class CreatedKeysTest(TestCase):
    def test_contrib_created_flags(self):
        seasons = tr.parse_contrib_seasons(CONTRIB)
        keys = tr.created_keys_from_contrib(seasons)
        self.assertIn(tr.title_key("随之任之"), keys)          # {{colorlink|…}} = 已创建
        self.assertNotIn(tr.title_key("無題 ep.01"), keys)     # [[曲名|名次]] = 未创建


class PruneCreatedRowsTest(TestCase):
    def test_deletes_the_whole_row_when_both_sides_have_articles(self):
        keys = {tr.title_key("Maison"), tr.title_key("没有心")}
        text, notes = tr.prune_created_rows(PRUNE_PAGE, keys)
        self.assertNotIn("Maison", text)
        self.assertNotIn("没有心", text)
        self.assertEqual(2, len(notes))

    def test_clears_only_the_created_side(self):
        """Only one side has an article: keep the other song in the table."""
        text, notes = tr.prune_created_rows(PRUNE_PAGE, {tr.title_key("Maison")})
        self.assertNotIn("Maison", text)
        self.assertIn("[[没有心]]", text)                      # 另一侧留着
        self.assertIn("{{注|5|总榜为第10}}", text)
        self.assertIn("[[诅咒之吻]]", text)
        self.assertEqual(1, len(notes))

    def test_matches_the_lowercase_article_of_a_capitalised_link(self):
        """页面写 [[Maison]]，条目是 maison（本 wiki 区分首字母大小写）。"""
        keys = {tr.title_key("maison")}
        self.assertEqual(keys, {tr.title_key("Maison")})
        text, _ = tr.prune_created_rows(PRUNE_PAGE, keys)
        self.assertNotIn("Maison", text)

    def test_no_keys_changes_nothing(self):
        self.assertEqual((PRUNE_PAGE, []), tr.prune_created_rows(PRUNE_PAGE, set()))


class CompactSidesTest(TestCase):
    """只清一侧之后，同侧后面的曲目上移补位——表格中间不能留一条空白带。

    2026-10-25 反馈：删行不能只清内容。整行删掉会把同一行另一侧的曲目也删没
    （274610 就是这么丢的 `没有心` / `ORDER`），所以这里把空位移到表尾。
    """

    PAGE = """== ボカコレ2022春 ==
{| class="wikitable " style="text-align:center;"
|-
! colspan="6"|TOP100 !! colspan="6"|ROOKIE
|-
! 名次 !! 曲名 !! P主 !! 条目状态 !! 翻译来源 !! 备注 !! 名次 !! 曲名 !! P主 !! 条目状态 !! 翻译来源 !! 备注
|-
| 46 || [[Maison]] || {{lj|歩く人}} || 未创建 || || || {{注|5|总榜为第10}} || [[没有心]] || saikawa || 未创建 || 
|-
| 24 || [[诅咒之吻]] || IZ || 未创建 || || || {{注|3|总榜为第5}} || [[无题 ep.01]] || {{lj|袖野あらわ}} || 未创建 || 
|-
| 56 || [[Equivalent]] || {{lj|きっと、ずっと、ぼっち。}} || 未创建 || || || {{注|14|总榜为第27}} || [[ORDER]] || Hal || 未创建 || 
|}
"""

    def test_a_cleared_side_pulls_the_next_song_up(self):
        text, _ = tr.prune_created_rows(self.PAGE, {tr.title_key("Maison")})
        text, moved = tr.compact_sides(text)

        rows, _ = tr.parse_rows(text)
        self.assertEqual(3, len(rows))
        self.assertEqual("24", rows[0].text(0, tr.COLUMNS.index("rank")).strip())
        self.assertEqual("[[没有心]]", rows[0].text(1, tr.COLUMNS.index("title")).strip())
        for title in ("[[诅咒之吻]]", "[[Equivalent]]", "[[没有心]]",
                      "[[无题 ep.01]]", "[[ORDER]]"):
            self.assertIn(title, text, f"{title} 不该丢")   # 曲目一个不丢、顺序不变
        self.assertGreater(moved, 0)

    def test_the_hole_moves_to_the_end_of_the_table(self):
        text, _ = tr.prune_created_rows(self.PAGE, {tr.title_key("Maison")})
        text, _ = tr.compact_sides(text)

        rows, _ = tr.parse_rows(text)
        last = rows[-1]
        self.assertEqual("", last.text(0, tr.COLUMNS.index("title")).strip())
        self.assertEqual("[[ORDER]]", last.text(1, tr.COLUMNS.index("title")).strip())

    def test_compacting_twice_changes_nothing(self):
        text, _ = tr.prune_created_rows(self.PAGE, {tr.title_key("Maison")})
        once, _ = tr.compact_sides(text)
        twice, moved = tr.compact_sides(once)
        self.assertEqual(once, twice)
        self.assertEqual(0, moved)

    def test_a_table_without_holes_is_left_alone(self):
        self.assertEqual((self.PAGE, 0), tr.compact_sides(self.PAGE))


class RemoveBlankRowsTest(TestCase):
    PAGE = """{| class="wikitable"
|-
! 名次 !! 曲名
|-
| 1 || [[甲]]
|-
|  || 
|-
| 2 || [[乙]]
|}"""

    def test_removes_the_row_and_the_separator_above_it(self):
        text, removed = tr.remove_blank_rows(self.PAGE)

        self.assertEqual(1, removed)
        self.assertNotIn("|  || ", text)
        self.assertNotIn("\n|-\n|-\n", text)
        rows, _ = tr.parse_rows(text)
        self.assertEqual(2, len(rows))

    def test_a_page_without_blank_rows_is_unchanged(self):
        text, removed = tr.remove_blank_rows(PRUNE_PAGE)
        self.assertEqual((PRUNE_PAGE, 0), (text, removed))


class PruneEntriesTest(TestCase):
    """整条链路：条目存在 + 贡献列表已创建，两种证据都要用上。"""

    class FakeSite:
        pass

    def test_uses_article_lookup_and_contrib_flags(self):
        seasons = tr.parse_contrib_seasons(CONTRIB)
        lookup_calls = []

        def fake_lookup(site, titles):
            lookup_calls.append(list(titles))
            return {tr.strict_key("Maison")}

        with patch.object(tr, "season_data", return_value={"contrib": seasons, "titles": {}}):
            text, notes = tr.prune_entries(self.FakeSite(), object(), PRUNE_PAGE,
                                           lookup=fake_lookup,
                                           ours=lambda site, title, producer: True)
        self.assertTrue(lookup_calls)
        self.assertNotIn("Equivalent", text)                    # 贡献列表标了已创建
        self.assertNotIn("Maison", text)                        # 条目存在 + P主 一致
        self.assertIn("[[诅咒之吻]]", text)                     # 未创建、无条目 → 留着

    def test_article_with_a_different_producer_is_kept(self):
        """``EDEN`` 是别人的歌：只同名不算，P主 对不上就不删。"""
        page = PRUNE_PAGE.replace("[[Equivalent]]", "[[EDEN(酔シグレ)|EDEN]]")
        with patch.object(tr, "season_data", return_value={"contrib": {}, "titles": {}}):
            text, notes = tr.prune_entries(
                self.FakeSite(), object(), page,
                lookup=lambda site, titles: {tr.strict_key("EDEN")},
                ours=lambda site, title, producer: False)
        self.assertIn("EDEN(酔シグレ)", text)
        self.assertEqual([], notes)

    def test_parenthetical_title_is_not_clipped_to_the_base_name(self):
        """``[[言灵(PiroP)|言灵]]`` 不能因为清单里有 ``言灵`` 就被删。"""
        page = PRUNE_PAGE.replace("[[Equivalent]]", "[[言灵(PiroP)|言灵]]")
        contrib = {"ボカコレ2022春": {"TOP100": {78: ("言灵", True)}}}
        with patch.object(tr, "season_data", return_value={"contrib": contrib, "titles": {}}):
            text, notes = tr.prune_entries(self.FakeSite(), object(), page,
                                           lookup=lambda site, titles: set())
        self.assertIn("言灵(PiroP)", text)
        self.assertEqual([], notes)

    def test_lookup_failure_does_not_break_the_run(self):
        def boom(site, titles):
            raise RuntimeError("api down")

        with patch.object(tr, "season_data", return_value={"contrib": {}, "titles": {}}):
            text, notes = tr.prune_entries(self.FakeSite(), object(), PRUNE_PAGE,
                                           lookup=boom)
        self.assertEqual(PRUNE_PAGE, text)
        self.assertEqual([], notes)


class CollectSourcesTest(TestCase):
    def test_caps_at_three_and_dedups(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        with patch.object(tr, "USE_ATWIKI", True), \
             patch.object(tr, "lookup_atwiki", return_value=["[a 甲]"]), \
             patch.object(tr, "lookup_netease", return_value=["[b 乙]", "[a 甲]"]), \
             patch.object(tr, "lookup_bilibili", return_value=(["[c 丙]", "[d 丁]"], [], [])):
            sources = tr.collect_sources(object(), song, {})
        self.assertEqual(["[a 甲]", "[b 乙]", "[c 丙]"], sources)

    def test_atwiki_is_off_by_default(self):
        """页面主人 2026-10-22：「暂时不收录中文歌词wiki」。"""
        self.assertFalse(tr.USE_ATWIKI)
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        with patch.object(tr, "lookup_atwiki", return_value=["[a 甲]"]) as wiki, \
             patch.object(tr, "lookup_netease", return_value=["[b 乙]"]), \
             patch.object(tr, "lookup_bilibili", return_value=([], [], [])):
            self.assertEqual(["[b 乙]"], tr.collect_sources(object(), song, {}))
        wiki.assert_not_called()

    def test_a_failing_source_does_not_break_the_others(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        with patch.object(tr, "USE_ATWIKI", True), \
             patch.object(tr, "lookup_atwiki", side_effect=RuntimeError("boom")), \
             patch.object(tr, "lookup_netease", return_value=["[b 乙]"]), \
             patch.object(tr, "lookup_bilibili", return_value=([], [], [])):
            self.assertEqual(["[b 乙]"], tr.collect_sources(object(), song, {}))
