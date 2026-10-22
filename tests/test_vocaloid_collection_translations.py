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

        def save(self, **kwargs):
            self.saved.append(self.text)

    class FakeSite:
        def logged_in(self):
            return True

    def _run(self, page_text, cache=None, sources=()):
        page = self.FakePage(None, None)
        page.text = page_text
        with patch.object(tr, "Page", return_value=page), \
                patch.object(tr, "load_cache", return_value=cache or {}), \
                patch.object(tr, "save_cache"), \
                patch.object(tr, "atwiki_page_index", return_value={}), \
                patch.object(tr, "collect_sources", return_value=list(sources)):
            changed = tr.run_once(self.FakeSite(), write=True, refresh=True,
                                  fetcher=object())
        return changed, page

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

    def test_navbox_names(self):
        names = tr.navbox_names(NAVBOX)
        self.assertEqual("こころもとなく", names[tr.title_key("心不在焉")])
        self.assertEqual("メゾン", names[tr.title_key("maison")])
        self.assertNotIn(tr.title_key("ORDER"), names)


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
    """补录前必须核实 P主：同名不同曲在歌词wiki 上到处都是。"""

    class FakeFetcher:
        def __init__(self, bodies):
            self.bodies = bodies

        def text(self, url, attempts=3):
            return self.bodies.get(url, "")

    def _page(self, pid, body):
        return {tr.ATWIKI_PAGE.format(pid=pid):
                f'<div id="wikibody">{body}</div><div class="atwiki-page-keyword">x</div>'}

    def test_parenthetical_hint_must_match_the_composer(self):
        bodies = self._page("3414", "作詞：骨盤P<br/>作曲：骨盤P<br/>翻譯：某人<br/>歌詞")
        fetcher = self.FakeFetcher(bodies)
        self.assertIsNone(tr.atwiki_song(fetcher, {tr.title_key("Colors(kouta)"): "3414"},
                                        {}, "Colors(kouta)"))
        bodies = self._page("3414", "作曲：kouta<br/>翻譯：某人<br/>歌詞")
        fetcher = self.FakeFetcher(bodies)
        self.assertEqual(("3414", "某人", "kouta"),
                         tr.atwiki_song(fetcher, {tr.title_key("Colors(kouta)"): "3414"},
                                        {}, "Colors(kouta)"))

    def test_japanese_title_needs_no_hint(self):
        bodies = self._page("3460", "作曲：コーチP<br/>翻譯：MIU<br/>歌詞")
        fetcher = self.FakeFetcher(bodies)
        self.assertEqual(("3460", "MIU", "コーチP"),
                         tr.atwiki_song(fetcher, {tr.title_key("死亡フラグ"): "3460"},
                                        {}, "死亡フラグ"))

    def test_plain_chinese_title_without_alias_is_rejected(self):
        bodies = self._page("2231", "作曲：やしきん<br/>翻譯：cyataku<br/>歌詞")
        fetcher = self.FakeFetcher(bodies)
        index = {tr.title_key("PANDORA"): "2231", tr.title_key("パンドラ"): "2231"}
        self.assertIsNone(tr.atwiki_song(fetcher, index, {}, "PANDORA"))
        # 有大家族模板的日文原名时才认
        self.assertEqual(("2231", "cyataku", "やしきん"),
                         tr.atwiki_song(fetcher, index, {tr.title_key("PANDORA"): "パンドラ"},
                                        "PANDORA"))

    def test_title_hint(self):
        self.assertEqual("kouta", tr.title_hint("Colors(kouta)"))
        self.assertEqual("", tr.title_hint("ORDER"))
        self.assertEqual("", tr.title_hint("无题(2005)"))

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
