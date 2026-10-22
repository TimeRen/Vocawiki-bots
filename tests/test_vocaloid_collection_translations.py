# -*- coding: utf-8 -*-
"""bots/vocaloid_collection_translations.py 的测试（不联网）。"""
import time
import urllib.error
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

    def test_bot_format_is_recognized_without_a_cache(self):
        """缓存丢了（换了运行环境）也要认得出自己写的格子，否则错数据永远改不掉。"""
        value = ("[https://music.163.com/#/song?id=1 网易云音乐(by. 甲)]<br/>"
                 "[https://www.bilibili.com/video/BV1 B站视频简介]")
        self.assertEqual("ours", tr.cell_state(value, None))
        self.assertEqual("ours", tr.cell_state("[https://a.example 巴哈姆特]", {}))
        self.assertTrue(tr.is_bot_source(value))

    def test_other_formats_are_not_ours(self):
        self.assertFalse(tr.is_bot_source("[[月之花]]"))
        self.assertFalse(tr.is_bot_source("[https://music.163.com/#/song?id=1]"))
        self.assertFalse(tr.is_bot_source("[https://a.example 我自己写的]"))
        self.assertFalse(tr.is_bot_source(""))

    def test_our_sources_were_dropped(self):
        """机器人上轮查出过来源、这轮结论变成空 —— 那格仍是自己的，可以清空。"""
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
                                         "<div id=\"wikibody\">翻譯：甲<br/>歌詞…</div>"
                                         "<div class=\"atwiki-page-keyword\">x</div>"})
        self.assertEqual([], tr.lookup_atwiki(fetcher, song, {}))
        self.assertEqual(["[https://w.atwiki.jp/vocaloidchly/pages/9.html "
                          "VOCALOID中文歌词wiki(by. 甲)]"],
                         tr.lookup_atwiki(fetcher, song, {title_key("月之花"): "9"}))

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


class CollectSourcesTest(TestCase):
    def test_caps_at_three_and_dedups(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        with patch.object(tr, "lookup_atwiki", return_value=["[a 甲]"]), \
             patch.object(tr, "lookup_netease", return_value=["[b 乙]", "[a 甲]"]), \
             patch.object(tr, "lookup_bilibili", return_value=(["[c 丙]", "[d 丁]"], [], [])):
            sources = tr.collect_sources(object(), song, {})
        self.assertEqual(["[a 甲]", "[b 乙]", "[c 丙]"], sources)

    def test_a_failing_source_does_not_break_the_others(self):
        song = Song(0, 0, "11", "千本桜", "千本樱", "黒うさP")
        with patch.object(tr, "lookup_atwiki", side_effect=RuntimeError("boom")), \
             patch.object(tr, "lookup_netease", return_value=["[b 乙]"]), \
             patch.object(tr, "lookup_bilibili", return_value=([], [], [])):
            self.assertEqual(["[b 乙]"], tr.collect_sources(object(), song, {}))
