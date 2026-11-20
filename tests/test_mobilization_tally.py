"""动员令计分（bots/mobilization_tally）的单测：全部离线，不读写维基。

口径对照：`Vocawiki:动员令/2027年冬/计分规则`
（歌曲 1.5、翻译 字节/150、注音 0.2、周刊 20 或 25、模板 每 10 链接 1 分、
P主等条目 字节/200、内容扩充 ≥500 字节）。
"""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest import mock

from bots.mobilization_tally import mobilization_tally as mt
from bots.mobilization_tally import presets as pr
from bots.mobilization_tally import update_scoreboard as us
from bots.mobilization_tally.utils import CST, adjust, count_bytes, count_bytes_simple

SCOREBOARD = """{{../导航}}

说明文字。

== -{[[U:甲|甲]]}- ==
=== 创建歌曲 ===
#[[旧条目]]（+1.50）

== -{[[U:乙|乙]]}- ==
"""

RANKING = """{{../导航}}

排行榜由机器人自动维护。

== 排行榜 ==
"""


class FakeCategory:
    def __init__(self, name):
        self._name = name

    def title(self, with_ns: bool = False):
        return self._name


class FakePage:
    """够用的假 Page：分类、正文、标题。"""

    def __init__(self, title, text="", categories=()):
        self._title = title
        self.text = text
        self._categories = list(categories)

    def title(self, as_link: bool = False, allow_interwiki: bool = True):
        return f"[[{self._title}]]" if as_link else self._title

    def categories(self):
        return [FakeCategory(name) for name in self._categories]

    def site(self):
        return None


def _contribution(page, **kwargs):
    data = {"page": page, "ns": 0, "new": True, "minor": False, "comment": "", "revid": 1}
    data.update(kwargs)
    return data


# ---------------------------------------------------------------- 分数线

class ScoreMathTest(TestCase):
    def test_song_is_one_and_a_half(self):
        self.assertEqual(1.5, pr.SONG_POINTS)

    def test_translation_divides_by_150(self):
        self.assertEqual(2.0, pr.translation_points(300))
        self.assertEqual(0.67, pr.translation_points(100))
        self.assertEqual(0.0, pr.translation_points(0))

    def test_furigana_is_point_two(self):
        self.assertEqual(0.2, pr.FURIGANA_POINTS)

    def test_weekly_is_20_or_25_for_u_issues(self):
        self.assertEqual(20, pr.weekly_points("周刊VOCAL Character & UTAU排行榜341"))
        self.assertEqual(25, pr.weekly_points("周刊UTAU排行榜340"))

    def test_template_counts_ten_links_per_point(self):
        self.assertIsNone(pr.template_points(0))
        self.assertIsNone(pr.template_points(1), "规则要求至少 2 个蓝链")
        self.assertEqual(0.2, pr.template_points(2))
        self.assertEqual(1.0, pr.template_points(10))
        self.assertEqual(2.5, pr.template_points(25))

    def test_article_divides_by_200(self):
        self.assertEqual(2.0, pr.article_points(400))
        self.assertEqual(0.0, pr.article_points(-10))

    def test_expand_needs_500_raw_bytes(self):
        self.assertIsNone(pr.expand_points(499, 480))
        self.assertEqual(2.5, pr.expand_points(500, 500))
        self.assertIsNone(pr.expand_points(600, -5), "有效字节没增加就不记（机械填表的情况）")
        self.assertIsNone(pr.expand_points(600, 0))


class ByteTest(TestCase):
    def test_plain_bytes(self):
        self.assertEqual(12, count_bytes_simple("同一夜啊"))

    def test_mechanical_templates_count_a_quarter(self):
        text = "{{Producer_Song|a=" + "x" * 396 + "}}"
        raw = count_bytes_simple(text)
        self.assertEqual(round(raw * 0.25), count_bytes(text))

    def test_playlist_counts_half(self):
        text = "{{playlist|" + "y" * 100 + "}}"
        self.assertEqual(round(count_bytes_simple(text) / 2), count_bytes(text))


# ---------------------------------------------------------------- 各项判定

class SongRuleTest(TestCase):
    def test_new_vj_song_scores_1_5(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        self.assertEqual("[[同一夜]]（+1.50）", pr.vj_create_song(_contribution(page)))

    def test_page_without_lyrics_template_is_not_a_song(self):
        page = FakePage("某条目", "正文", ["使用VOCALOID的歌曲"])
        self.assertIsNone(pr.vj_create_song(_contribution(page)))

    def test_non_vj_page_is_not_a_song(self):
        page = FakePage("中华缘木娘", "{{LyricsKai|original=あ}}", ["中文歌曲"])
        self.assertIsNone(pr.vj_create_song(_contribution(page)))

    def test_only_new_or_moved_pages_count(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        self.assertIsNone(pr.vj_create_song(_contribution(page, new=False)))

    def test_moved_from_user_page_counts(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        contribution = _contribution(page, new=False,
                                     comment="移动页面 [[User:甲/同一夜]] 至 [[同一夜]]")
        self.assertEqual("[[同一夜]]（+1.50）", pr.vj_create_song(contribution))


class TranslationRuleTest(TestCase):
    def _translate(self, translated, comment="翻译歌词", extra=""):
        text = f"{{{{LyricsKai|original=あ\n|translated={translated}\n}}}}{extra}"
        page = FakePage("同一夜", text, ["使用VOCALOID的歌曲"])
        return pr.vj_translate(_contribution(page, new=False, comment=comment))

    def test_translated_bytes_divide_by_150(self):
        self.assertEqual("[[同一夜]]（+2.00）", self._translate("啊" * 100))     # 300 字节

    def test_both_summary_spellings(self):
        self.assertIsNotNone(self._translate("啊" * 100, comment="歌词翻译"))
        self.assertIsNotNone(self._translate("啊" * 100, comment="歌詞翻譯"))

    def test_without_keyword_is_ignored(self):
        self.assertIsNone(self._translate("啊" * 100, comment="修饰"))

    def test_empty_translated_is_ignored(self):
        self.assertIsNone(self._translate(""))

    def test_multiple_lyrics_blocks_are_summed(self):
        extra = "{{LyricsKai|original=い\n|translated=" + "啊" * 100 + "\n}}"
        self.assertEqual("[[同一夜]]（+4.00）", self._translate("啊" * 100, extra=extra))


class FuriganaRuleTest(TestCase):
    def test_furigana_scores_point_two(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        contribution = _contribution(page, new=False, comment="歌词注音")
        self.assertEqual("[[同一夜]]（+0.20）", pr.vj_furigana(contribution))

    def test_requires_keyword_and_song(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        self.assertIsNone(pr.vj_furigana(_contribution(page, new=False, comment="小修改")))
        other = FakePage("某条目", "{{LyricsKai|original=あ}}", ["杂项"])
        self.assertIsNone(pr.vj_furigana(_contribution(other, new=False, comment="歌词注音")))


class WeeklyRuleTest(TestCase):
    def test_weekly_pages_score_by_title(self):
        normal = FakePage("周刊VOCAL Character & UTAU排行榜341", "", [pr.WEEKLY_CATEGORY])
        u_issue = FakePage("周刊UTAU排行榜340", "", [pr.WEEKLY_CATEGORY])
        self.assertEqual("[[周刊VOCAL Character & UTAU排行榜341]]（+20.00）",
                         pr.vj_create_weekly(_contribution(normal)))
        self.assertEqual("[[周刊UTAU排行榜340]]（+25.00）",
                         pr.vj_create_weekly(_contribution(u_issue)))

    def test_other_pages_are_not_weekly(self):
        page = FakePage("普通条目", "", ["杂项"])
        self.assertIsNone(pr.vj_create_weekly(_contribution(page)))


class ProducerTemplateRuleTest(TestCase):
    def test_links_divide_by_ten(self):
        page = FakePage("Template:某P", "", ["P主模板"])
        contribution = _contribution(page, ns=10)
        self.assertEqual("[[Template:某P]]（+1.50）",
                         pr.vj_create_producer_template(contribution,
                                                        links=[f"页面{i}" for i in range(15)]))

    def test_vocalist_template_categories_are_navboxes(self):
        """歌姬模板挂在 `Category:<歌姬>模板`，父分类是 `虚拟歌手模板`。"""
        page = FakePage("Template:初音未来", "", ["初音未来模板"])
        category = mock.Mock()
        category.categories.return_value = [FakeCategory(pr.VOCALIST_TEMPLATE_CATEGORY)]
        with mock.patch.object(pr, "get_site", return_value="site"), \
             mock.patch.object(pr, "Page", return_value=category) as page_cls:
            self.assertTrue(pr.is_navbox_template(page))
        self.assertEqual("Category:初音未来模板", page_cls.call_args.args[1])

    def test_unknown_template_category_is_not_a_navbox(self):
        page = FakePage("Template:某", "", ["杂项模板"])
        category = mock.Mock()
        category.categories.return_value = [FakeCategory("提示模板")]
        with mock.patch.object(pr, "get_site", return_value="site"), \
             mock.patch.object(pr, "Page", return_value=category):
            self.assertFalse(pr.is_navbox_template(page))

    def test_single_link_is_ignored(self):
        page = FakePage("Template:某P", "", ["P主模板"])
        self.assertIsNone(pr.vj_create_producer_template(_contribution(page, ns=10),
                                                        links=["某一首歌"]))

    def test_other_templates_are_ignored(self):
        page = FakePage("Template:某", "", ["杂项模板"])
        self.assertIsNone(pr.vj_create_producer_template(_contribution(page, ns=10),
                                                        links=["a"] * 20))


class ProducerArticleRuleTest(TestCase):
    def test_p_producer_page_uses_effective_bytes(self):
        page = FakePage("某P", "x" * 400, ["P主"])
        self.assertEqual("[[某P]]（+2.00）", pr.vj_create_producer(_contribution(page)))

    def test_character_and_engine_pages_count(self):
        for categories in (["VOCALOID角色"], ["音声合成软件"], ["演唱会"]):
            page = FakePage("某条目", "x" * 400, categories)
            self.assertIsNotNone(pr.vj_create_producer(_contribution(page)), categories)

    def test_original_character_category_is_excluded(self):
        page = FakePage("某角色", "x" * 400, ["P主原创角色"])
        self.assertIsNone(pr.vj_create_producer(_contribution(page)))

    def test_song_pages_are_not_articles(self):
        page = FakePage("同一夜", "x" * 400, ["使用VOCALOID的歌曲"])
        self.assertIsNone(pr.vj_create_producer(_contribution(page)))


class ExpandRuleTest(TestCase):
    def test_expand_needs_keyword_threshold_and_category(self):
        page = FakePage("某P", "x" * 600, ["P主"])
        contribution = _contribution(page, new=False, comment="内容扩充")
        self.assertEqual("[[某P]]（+3.00）",
                         pr.vj_expand_article(contribution, texts=("x" * 600, "")))
        self.assertEqual("[[某P]]（+2.50）",
                         pr.vj_expand_article(contribution, texts=("x" * 600, "x" * 100)))
        self.assertIsNone(pr.vj_expand_article(contribution, texts=("x" * 400, "")),
                          "只增加 400 字节，未达 500 门槛")
        self.assertIsNone(pr.vj_expand_article(_contribution(page, new=False, comment="小改"),
                                               texts=("x" * 600, "")))

    def test_expand_ignores_non_article_pages(self):
        page = FakePage("同一夜", "x" * 900, ["使用VOCALOID的歌曲"])
        contribution = _contribution(page, new=False, comment="内容扩充")
        self.assertIsNone(pr.vj_expand_article(contribution, texts=("x" * 900, "")))


# ---------------------------------------------------------------- 计分板

class ScoreboardTest(TestCase):
    def test_parse_section_title_username(self):
        self.assertEqual("甲", us.parse_section_title_username("-{[[U:甲|甲]]}-"))
        self.assertEqual("甲", us.parse_section_title_username("-{[[U:甲]]}-"))
        self.assertIsNone(us.parse_section_title_username("创建歌曲"))

    def test_adds_lines_into_existing_section(self):
        text, added = us.add_score_lines(SCOREBOARD, {"甲": {"创建歌曲": ["[[新条目]]（+1.50）"]}})
        self.assertEqual(1, added)
        self.assertIn("=== 创建歌曲 ===\n#[[旧条目]]（+1.50）\n#[[新条目]]（+1.50）", text)

    def test_creates_user_and_category_sections(self):
        text, added = us.add_score_lines(SCOREBOARD, {"丙": {"歌词翻译": ["[[某歌]]（+2.00）"]}})
        self.assertEqual(1, added)
        self.assertIn("== -{[[U:丙|丙]]}- ==", text)
        self.assertIn("=== 歌词翻译 ===\n#[[某歌]]（+2.00）", text)

    def test_is_idempotent(self):
        once, _ = us.add_score_lines(SCOREBOARD, {"甲": {"创建歌曲": ["[[新条目]]（+1.50）"]}})
        twice, added = us.add_score_lines(once, {"甲": {"创建歌曲": ["[[新条目]]（+1.50）"]}})
        self.assertEqual(0, added)
        self.assertEqual(once, twice)
        self.assertEqual(1, twice.count("[[新条目]]"))

    def test_existing_human_lines_are_kept(self):
        text, _ = us.add_score_lines(SCOREBOARD, {"甲": {"创建歌曲": ["[[新条目]]（+1.50）"]}})
        self.assertIn("#[[旧条目]]（+1.50）", text)

    def test_collect_scores_sums_all_marks(self):
        text = ("== -{[[U:甲|甲]]}- ==\n=== 创建歌曲 ===\n#[[A]]（+1.50）\n#[[B]]（+1.5）（+0.5）\n"
                "=== 歌词翻译 ===\n#[[C]]（+2.00）\n")
        scores = us.collect_scores(text)
        self.assertEqual({"创建歌曲": 3.5, "歌词翻译": 2.0}, scores["甲"])

    def test_collect_scores_reads_manual_edits(self):
        """评委手写的分（用半角括号、少写小数）也要算进总分。"""
        text = "== -{[[U:甲|甲]]}- ==\n=== 创建歌曲 ===\n#[[A]] (+3)\n"
        self.assertEqual(3.0, us.collect_scores(text)["甲"]["创建歌曲"])


class RankingTest(TestCase):
    def test_table_sorted_by_total_then_name(self):
        scores = {"乙": {"创建歌曲": 3.0}, "甲": {"创建歌曲": 1.5, "歌词翻译": 0.5}}
        table = us.render_ranking(scores)
        self.assertIn("! 排名 !! 用户名 !! 创建歌曲 !! 歌词翻译", table)
        self.assertLess(table.index("-{[[U:乙|乙]]}-"), table.index("-{[[U:甲|甲]]}-"),
                        "乙 3 分在前")
        self.assertIn("| 1 || -{[[U:乙|乙]]}- || 3.00 || 0.00", table)
        self.assertIn("|| 0.00 || 3.00", table)
        self.assertIn("|- class=\"sortbottom\"", table)
        self.assertIn("! 总和 !! !! 4.50 !! 0.50", table)

    def test_ties_are_broken_by_username(self):
        scores = {"b": {"创建歌曲": 1.5}, "a": {"创建歌曲": 1.5}}
        table = us.render_ranking(scores)
        self.assertLess(table.index("-{[[U:a|a]]}-"), table.index("-{[[U:b|b]]}-"))

    def test_fixed_columns_even_when_empty(self):
        table = us.render_ranking({"甲": {"创建歌曲": 1.5}})
        for column in pr.CATEGORY_ORDER:
            self.assertIn(column, table)
        self.assertIn("内容扩充", us.render_ranking({}))

    def test_extra_columns_are_appended(self):
        table = us.render_ranking({"甲": {"评委加分": 1.0}})
        self.assertIn("内容扩充 !! 评委加分 !! 总分", table)
        self.assertIn("| 1 || -{[[U:甲|甲]]}- || 0.00 || 0.00 || 0.00 || 0.00 || 0.00 || 0.00 "
                      "|| 0.00 || 1.00 || 1.00", table)

    def test_rebuild_keeps_intro_and_replaces_section(self):
        updated = us.rebuild_ranking(RANKING, SCOREBOARD)
        self.assertIn("{{../导航}}", updated)
        self.assertIn("排行榜由机器人自动维护。", updated)
        self.assertEqual(1, updated.count("== 排行榜 =="))
        self.assertIn("-{[[U:甲|甲]]}-", updated)

    def test_rebuild_appends_section_when_missing(self):
        updated = us.rebuild_ranking("{{../导航}}\n", SCOREBOARD)
        self.assertIn("== 排行榜 ==", updated)


# ---------------------------------------------------------------- 流程

class WindowTest(TestCase):
    def test_parse_timestamp_accepts_both_shapes(self):
        """pywikibot 11 给的是 ISO 字符串，旧版是 Timestamp（datetime 子类）。"""
        self.assertEqual(datetime(2026, 11, 17, 14, 1, 38, tzinfo=CST),
                         mt.parse_timestamp("2026-11-17T06:01:38Z"))
        self.assertEqual(datetime(2026, 11, 17, 14, 1, 38, tzinfo=CST),
                         mt.parse_timestamp(datetime(2026, 11, 17, 6, 1, 38,
                                                     tzinfo=timezone.utc)))
        self.assertIsNone(mt.parse_timestamp(None))
        self.assertIsNone(mt.parse_timestamp(""))

    def test_parse_time(self):
        self.assertEqual(datetime(2026, 12, 1, tzinfo=CST), mt.parse_time("2026-12-01"))
        self.assertEqual(datetime(2026, 12, 1, tzinfo=CST),
                         mt.parse_time("2026-12-01T00:00:00+08:00"))
        self.assertEqual(datetime(2026, 12, 1, tzinfo=CST),
                         mt.parse_time("2026-11-30T16:00:00Z"), "UTC 时间要换算成东八区")
        self.assertIsNone(mt.parse_time(None))

    def test_in_window(self):
        start = datetime(2026, 12, 1, tzinfo=CST)
        end = datetime(2027, 2, 15, 23, 59, tzinfo=CST)
        self.assertFalse(mt.in_window(start, start, end), "开始那一刻之前的编辑不算")
        self.assertTrue(mt.in_window(start + timedelta(minutes=1), start, end))
        self.assertTrue(mt.in_window(end, start, end))
        self.assertFalse(mt.in_window(end + timedelta(minutes=1), start, end))

    def test_collect_additions_filters_by_time_and_ignores_errors(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        early = _contribution(page, timestamp=datetime(2026, 11, 30, tzinfo=CST))
        later = _contribution(page, timestamp=datetime(2026, 12, 2, tzinfo=CST))
        preset = {"创建歌曲": pr.vj_create_song,
                  "出错项": mock.Mock(side_effect=RuntimeError("boom"))}
        additions = mt.collect_additions([early, later], preset,
                                         datetime(2026, 12, 1, tzinfo=CST),
                                         datetime(2027, 1, 1, tzinfo=CST))
        self.assertEqual({"创建歌曲": ["[[同一夜]]（+1.50）"]}, additions)


class ParticipantTest(TestCase):
    def test_reads_signup_links(self):
        text = "*-{[[U:人间百态]]}-\n*-{[[U:月隐夜色|月隐夜色]]}-\n*无关链接"
        with mock.patch.object(mt, "Page") as page:
            page.return_value.text = text
            self.assertEqual(["人间百态", "月隐夜色"], mt.participants(object(), "T"))
        page.assert_called_once()
        self.assertTrue(page.call_args.args[1].endswith("/报名"))


class FakeSitePage:
    """按标题返回固定正文的假 Page（`run_once` / `save_page` 用）。"""

    store: dict = {}

    def __init__(self, site, title):
        self._title = title

    @property
    def text(self):
        return self.store.get(self._title, "")

    @text.setter
    def text(self, value):
        self.store[self._title] = value

    def title(self):
        return self._title

    def save(self, **kwargs):
        self.saved = kwargs


class SavePageTest(TestCase):
    def setUp(self):
        FakeSitePage.store = {"Vocawiki:X/排行榜": "同样的内容"}

    def test_unchanged_text_is_not_saved(self):
        with mock.patch.object(mt, "Page", FakeSitePage):
            self.assertFalse(mt.save_page(object(), "Vocawiki:X/排行榜", "同样的内容", "更新"))

    def test_changed_text_is_saved(self):
        with mock.patch.object(mt, "Page", FakeSitePage):
            self.assertTrue(mt.save_page(object(), "Vocawiki:X/排行榜", "新内容", "更新排行榜"))
        self.assertEqual("新内容", FakeSitePage.store["Vocawiki:X/排行榜"])


class RunOnceTest(TestCase):
    """整轮流程：报名 → 扫贡献 → 计分板 → 排行榜（不联网）。"""

    def setUp(self):
        self.now = datetime(2026, 12, 2, 12, 0, tzinfo=CST)
        FakeSitePage.store = {
            "Vocawiki:X/报名": "*-{[[U:甲]]}-",
            "Vocawiki:X/计分板": "{{../导航}}\n\n说明。\n",
            "Vocawiki:X/排行榜": "{{../导航}}\n\n导语。\n\n== 排行榜 ==\n",
        }
        self.song = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])

    def _run(self, write=False, contributions=None, out_dir=None):
        contribution = _contribution(self.song, timestamp=datetime(2026, 12, 2, tzinfo=CST))
        contributions = contributions if contributions is not None else [contribution]
        with mock.patch.object(mt, "Page", FakeSitePage), \
             mock.patch.object(mt, "user_contributions", return_value=contributions), \
             mock.patch.object(mt, "save_page") as save, \
             mock.patch.object(mt, "save_state") as state:
            added = mt.run_once(object(), target="Vocawiki:X", write=write, now=self.now,
                                state_path=Path("unused"), ignore_window=True,
                                out_dir=out_dir)
        return added, save, state

    def test_dry_run_scores_without_writing(self):
        with TemporaryDirectory() as folder:
            added, save, state = self._run(out_dir=folder)
            ranking = Path(folder, "排行榜.wikitext").read_text(encoding="utf-8")
            scoreboard = Path(folder, "计分板.wikitext").read_text(encoding="utf-8")
        self.assertEqual(1, added)
        self.assertIn("-{[[U:甲|甲]]}-", ranking)
        self.assertIn("#[[同一夜]]（+1.50）", scoreboard)
        self.assertIn("说明。", scoreboard, "导语要保留")
        save.assert_not_called()
        state.assert_not_called()
        self.assertEqual("{{../导航}}\n\n导语。\n\n== 排行榜 ==\n",
                         FakeSitePage.store["Vocawiki:X/排行榜"], "预演不写页面")

    def test_write_saves_pages_and_advances_state(self):
        added, save, state = self._run(write=True)
        self.assertEqual(1, added)
        saved_titles = [call.args[1] for call in save.call_args_list]
        self.assertEqual(["Vocawiki:X/计分板", "Vocawiki:X/排行榜"], saved_titles)
        state.assert_called_once()

    def test_edits_outside_the_event_are_ignored(self):
        old = _contribution(self.song, timestamp=datetime(2026, 11, 30, tzinfo=CST))
        added, _, _ = self._run(contributions=[old])
        self.assertEqual(0, added)

    def test_window_gate_skips_before_start(self):
        with mock.patch.object(mt, "Page", FakeSitePage), \
             mock.patch.object(mt, "user_contributions") as contributions:
            self.assertEqual(0, mt.run_once(object(), target="Vocawiki:X",
                                            now=datetime(2026, 11, 1, tzinfo=CST),
                                            state_path=Path("unused")))
        contributions.assert_not_called()
