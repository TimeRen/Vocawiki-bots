import json
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from unittest import TestCase
from unittest.mock import Mock, patch

import bots.vocaloid_collection_contributions as contributions

from bots.vocaloid_collection_contributions import (
    Entry,
    Legend,
    Section,
    count_by_listed,
)


class FakeSite:
    def __init__(self, redirects=None, converted=None):
        self.redirects = redirects or {}
        self.converted = converted or {}

    def simple_request(self, **kwargs):
        self.titles = kwargs["titles"].split("|")
        return self

    def submit(self):
        # 模仿 MediaWiki：先按变体转换，再解重定向，页面列表用最终标题
        keyed = {t: self.converted.get(t, t) for t in self.titles}
        resolved = {t: self.redirects.get(keyed[t], keyed[t]) for t in self.titles}
        pages = [{"title": t} for t in dict.fromkeys(resolved.values())]
        redirects = [
            {"from": keyed[t], "to": resolved[t]}
            for t in self.titles
            if keyed[t] != resolved[t]
        ]
        converted = [
            {"from": t, "to": keyed[t]} for t in self.titles if keyed[t] != t
        ]
        return {"query": {"pages": pages, "redirects": redirects,
                          "converted": converted}}


class PagedSite:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def simple_request(self, **kwargs):
        self.requests.append(kwargs)
        return self

    def submit(self):
        return next(self.responses)


class FakeSession:
    """假装的萌百官方站会话：按顺序吐出预先准备好的 JSON，并记下问过什么。"""

    def __init__(self, responses):
        self.responses = list(responses)
        self.requests = []

    def api(self, params, post=False):
        self.requests.append(params)
        return self.responses.pop(0) if self.responses else None


class FakeOpener:
    """假装的 urllib opener：记下请求，按顺序回放预先准备好的 JSON。"""

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.requests = []

    def open(self, request, timeout=None):
        self.requests.append(request)
        return FakeResponse(self.payloads.pop(0))


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def read(self):
        return json.dumps(self.payload).encode()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class TestCountByListed(TestCase):
    @patch.object(contributions, "Page")
    def test_batch_creators_uses_single_page_oldest_revision_queries(
            self, page_factory):
        site = object()
        page = page_factory.return_value
        page.revisions.return_value = iter([{"user": "User", "timestamp": "2024-01-01T00:00:00Z"}])
        cache = {"Cached": ("Existing", "", None)}

        contributions.batch_creators(
            site, ["Alias", "Target", "Cached"], cache, {"Alias": "Target"})

        self.assertEqual(cache["Target"],
                         ("User", "", "2024-01-01T00:00:00Z"))
        self.assertEqual(cache["Cached"], ("Existing", "", None))
        page_factory.assert_called_once_with(site, "Target")
        page.revisions.assert_called_once_with(
            total=1, reverse=True, content=False)

    @patch.object(contributions, "Page")
    def test_creator_of_keeps_the_cross_wiki_prefix(self, page_factory):
        # zhmoe>某人：voca 抄的是源站最后一版的作者，来源得留着，page_creator
        # 才知道不能拿这个人当创建者；时间戳也留着，反查源条目名要用
        page_factory.return_value.revisions.return_value = iter(
            [{"user": "zhmoe>源站编辑者", "timestamp": "2024-05-06T07:08:09Z"}])
        cache = {}

        self.assertEqual(contributions.creator_of(object(), "曲", cache),
                         "zhmoe>源站编辑者")
        self.assertEqual(cache["曲"],
                         ("zhmoe>源站编辑者", "zhmoe", "2024-05-06T07:08:09Z"))

    @patch.object(contributions, "Page")
    def test_creator_of_requeries_legacy_cache_entries(self, page_factory):
        # 旧缓存只存了剥掉前缀的用户名，分辨不出来源，只能重查一次
        page_factory.return_value.revisions.return_value = iter(
            [{"user": "本站用户", "timestamp": "2024-05-06T07:08:09Z"}])
        cache = {"曲": "本站用户"}

        contributions.creator_of(object(), "曲", cache)

        page_factory.assert_called_once()
        self.assertEqual(cache["曲"],
                         ("本站用户", "", "2024-05-06T07:08:09Z"))

    def test_season_template_ignores_links_that_are_not_articles(self):
        # Navbox 尾巴上的 [[Category:...]] 会落进最后一个 list 参数，被当成一首歌
        # 收下来，最后给创建那个分类页的人记一份贡献。
        text = (
            "| title = 其他歌曲\n"
            "| group1 = 未上榜歌曲\n"
            "| list1 = [[榜外歌曲]] • [[Category:The VOCALOID Collection导航模板]]\n"
        )

        parsed = contributions.parse_season_template(text)

        self.assertEqual(set(parsed["neta:未上榜歌曲"].values()), {"榜外歌曲"})

    @patch.object(contributions, "creator_of")
    @patch.object(contributions, "batch_creators")
    def test_outside_ranking_participants_are_included_in_season_stats(
            self, batch_creators, creator_of):
        ranked_colour = "#000000"
        outside_colour = "#123456"
        sections = [
            Section("2021秋", "TOP100", [Entry("榜内歌曲", [ranked_colour])]),
            Section("2021秋", "neta", [Entry("榜外有颜色歌曲", [outside_colour])]),
            Section("2021秋", "REMIX", [Entry("混音歌曲", [])]),
        ]
        legend = Legend(colour_to_name={
            ranked_colour: "榜内创建者",
            outside_colour: "榜外标注创建者",
        })
        creator_of.side_effect = lambda _site, title, _cache: {
            "混音歌曲": "榜外页面创建者",
            "榜外未列出歌曲": "榜外页面创建者",
        }.get(title)

        counts = count_by_listed(
            FakeSite(), sections, legend, {},
            lambda _season: {"榜内歌曲", "榜外有颜色歌曲", "混音歌曲", "榜外未列出歌曲"},
            lambda _season: {"榜内歌曲", "榜外有颜色歌曲", "混音歌曲", "榜外未列出歌曲"})

        self.assertEqual(counts["2021秋"]["#000000"], 1)
        self.assertEqual(counts["2021秋"]["#123456"], 1)
        self.assertEqual(counts["2021秋"]["榜外页面创建者"], 2)

    @patch.object(contributions, "creator_of")
    @patch.object(contributions, "batch_creators")
    def test_stats_ignore_pages_that_only_carry_the_season_navbox(
            self, batch_creators, creator_of):
        """挂模板 ≠ 参赛：统计只认赛季模板列出的曲目。

        总条目 The VOCALOID Collection 挂着全部 12 个赛季的模板，如果拿
        ``list=embeddedin`` 当名单，它的创建者会每季都拿到一份贡献。
        """
        colour = "#000000"
        sections = [Section("2021秋", "TOP100", [Entry("榜内歌曲", [colour])])]
        legend = Legend(colour_to_name={colour: "榜内创建者"})
        creator_of.side_effect = lambda _site, title, _cache: (
            "总条目创建者" if title == "只挂了模板的页面" else None)

        counts = count_by_listed(
            FakeSite(), sections, legend, {},
            lambda _season: {"榜内歌曲", "只挂了模板的页面"},
            lambda _season: {"榜内歌曲"})

        self.assertEqual(counts["2021秋"]["#000000"], 1)
        self.assertNotIn("总条目创建者", counts["2021秋"])

    def test_season_template_collects_sections_without_rank_ranges(self):
        # 「其他歌曲」下的分组（其他部门 / 未上榜歌曲）没有名次区间，但里面的链接
        # 仍然是本赛季的歌，必须收下来，否则榜外歌曲会被统计当成外人；
        # 键上带分组名，统计才能把原创与二创分开（见 is_counted_track）。
        text = (
            "| title = 其他歌曲\n"
            "| group1 = 其他部门\n"
            "| list1 = （待补充）\n"
            "| group2 = 未上榜歌曲\n"
            "| list2 = [[榜外歌曲甲]] • {{lj|[[榜外歌曲乙|ボカロ曲]]}}\n"
        )

        parsed = contributions.parse_season_template(text)

        self.assertEqual(set(parsed["neta:未上榜歌曲"].values()),
                         {"榜外歌曲甲", "榜外歌曲乙"})
        self.assertNotIn("neta", parsed)

    def test_batch_exists_records_canonical_titles(self):
        # 模板写 ダウナ、页面叫 Downa：报告要靠这份归一后的标题来比对，
        # 否则全是写法差异造成的噪声。
        site = FakeSite(redirects={"ダウナ": "Downa"})
        exists, canonical = {}, {}

        contributions.batch_exists(site, ["ダウナ", "Downa"], exists, None, canonical)

        self.assertEqual(exists, {"ダウナ": True, "Downa": True})
        self.assertEqual(canonical, {"ダウナ": "Downa", "Downa": "Downa"})

    def test_batch_exists_canonicalises_variant_spellings(self):
        # 模板写日文/繁体（後篇、黒白），页面上是简体：靠 converttitles 归一。
        site = FakeSite(converted={"後篇": "后篇", "黒白": "黑白"})
        exists, canonical = {}, {}

        contributions.batch_exists(site, ["後篇", "黒白"], exists, None, canonical)

        self.assertEqual(exists, {"後篇": True, "黒白": True})
        self.assertEqual(canonical, {"後篇": "后篇", "黒白": "黑白"})

    def test_batch_exists_resolves_via_the_converted_title(self):
        # 站点区分大小写：页面叫 parastraea，链接写 Parastraea。认转换后的标题才找得到。
        site = FakeSite(converted={"Parastraea": "parastraea"})
        exists, canonical = {}, {}

        contributions.batch_exists(site, ["Parastraea"], exists, None, canonical)

        self.assertEqual(exists, {"Parastraea": True})
        self.assertEqual(canonical, {"Parastraea": "parastraea"})

    def test_template_participants_follows_api_continuation(self):
        site = PagedSite([
            {"query": {"embeddedin": [{"title": "榜内歌曲"}]},
             "continue": {"continue": "-||", "eicontinue": "page|123"}},
            {"query": {"embeddedin": [{"title": "榜外歌曲"}]}},
        ])

        participants = contributions.template_participants(site, "2021秋")

        self.assertEqual(participants, ["榜内歌曲", "榜外歌曲"])
        self.assertEqual(site.requests[1]["eicontinue"], "page|123")

    def test_template_participants_skips_pages_that_are_not_songs(self):
        # 总条目挂着全部赛季的模板，会被 embeddedin 当成每一季的参赛曲目；
        # 不排掉它，创建总条目的用户就凭空多出 12 份贡献。
        site = PagedSite([
            {"query": {"embeddedin": [
                {"title": "榜内歌曲"},
                {"title": "The VOCALOID Collection"},
                {"title": "榜外歌曲"},
            ]}},
        ])

        participants = contributions.template_participants(site, "2021秋")

        self.assertEqual(participants, ["榜内歌曲", "榜外歌曲"])

    def test_redirect_titles_are_counted_as_one_song_per_season(self):
        colour = "#000000"
        sections = [
            Section("2021秋", "TOP100", [
                Entry("Entelecheia", [colour]),
                *[Entry(f"主榜曲目{i}", [colour]) for i in range(14)],
            ]),
            Section("2021秋", "ROOKIE", [
                Entry("新人曲目A", [colour]),
                Entry("新人曲目B", [colour]),
                Entry("隐德来希", [colour]),
            ]),
        ]
        legend = Legend(colour_to_name={colour: "贡献者"})
        site = FakeSite(redirects={"隐德来希": "Entelecheia"})

        counts = count_by_listed(site, sections, legend, {})

        self.assertEqual(counts["2021秋"]["#000000"], 17)


class TestCountedTracks(TestCase):
    def test_remix_and_derivative_tracks_do_not_count(self):
        # 「除了 Remix 和 neta 非原创曲都算」：REMIX 赛道整条不算，
        # neta 里「其他部门」与「原曲/作者」写法的二创也不算。
        self.assertFalse(contributions.is_counted_track("REMIX", "Rolling Girl/郁P"))
        self.assertFalse(contributions.is_counted_track("neta:其他部门", "某演奏"))
        self.assertFalse(contributions.is_counted_track("neta:未上榜歌曲", "某曲/某P"))
        self.assertTrue(contributions.is_counted_track("neta:未上榜歌曲", "榜外原创曲"))
        self.assertTrue(contributions.is_counted_track("TOP100", "榜内曲"))
        self.assertTrue(contributions.is_counted_track("neta", "没带分组名的榜外曲"))


class TestRenderChart(TestCase):
    def test_rows_are_sorted_by_creation_count(self):
        # ECharts 的 yAxis 自下而上画：数组升序排，图上看起来才是从多到少。
        colour = "#000000"
        chart = {
            "legend": {"data": ["ボカコレ2021秋"]},
            "yAxis": {"data": ["大戶", "小戶", "中戶"]},
            "series": [
                {"name": "ボカコレ2021秋", "type": "bar",
                 "itemStyle": {"color": "#111111"}, "data": [10, 1, 5]},
            ],
        }
        text = ("{{Echart|data=<nowiki>"
                + json.dumps(chart, ensure_ascii=False) + "</nowiki>}}")
        sections = [Section("2021秋", "TOP100", [Entry("甲", [colour])])]
        legend = Legend(colour_to_name={colour: "大戶"})

        updated, _ = contributions.render_chart(
            text, sections, legend, {"2021秋": {"#000000": 20}})

        parsed = json.loads(contributions.CHART_RE.search(updated).group(2))
        self.assertEqual(parsed["yAxis"]["data"], ["小戶", "中戶", "大戶"])
        self.assertEqual(parsed["series"][0]["data"], [1, 5, 20])

    def test_excluded_tracks_lower_numbers_and_keep_manual_ones(self):
        # REMIX/二创以前被算进图表，现在不算了：要把那部分减回去，
        # 而站外人工记账的数字（机器人本来就推不出来）仍然保留。
        colour = "#000000"
        chart = {
            "legend": {"data": ["ボカコレ2021秋"]},
            "yAxis": {"data": ["人工记帐", "二创作者"]},
            "series": [
                {"name": "ボカコレ2021秋", "type": "bar",
                 "itemStyle": {"color": "#111111"}, "data": [7, 4]},
            ],
        }
        text = ("{{Echart|data=<nowiki>"
                + json.dumps(chart, ensure_ascii=False) + "</nowiki>}}")
        sections = [Section("2021秋", "TOP100", [Entry("甲", [colour])])]
        legend = Legend(colour_to_name={colour: "二创作者"})

        updated, _ = contributions.render_chart(
            text, sections, legend, {"2021秋": {"#000000": 1}},
            {"2021秋": {"#000000": 3}})

        parsed = json.loads(contributions.CHART_RE.search(updated).group(2))
        data = dict(zip(parsed["yAxis"]["data"], parsed["series"][0]["data"]))
        self.assertEqual(data["二创作者"], 1)   # 4 - 3 = 1：多算的 REMIX/二创被抹掉
        self.assertEqual(data["人工记帐"], 7)   # 没有排除来源，人工数字不动

    def test_moved_credits_are_added_to_the_real_creator(self):
        # 真创建者那一格原本比机器人算出来的高（人工记账），只减不加的话条目
        # 会被「只升不降」挡住，永远搬不到他头上。
        colour = "#000000"
        chart = {
            "legend": {"data": ["ボカコレ2021秋"]},
            "yAxis": {"data": ["真创建者", "导入版作者"]},
            "series": [
                {"name": "ボカコレ2021秋", "type": "bar",
                 "itemStyle": {"color": "#111111"}, "data": [9, 3]},
            ],
        }
        text = ("{{Echart|data=<nowiki>"
                + json.dumps(chart, ensure_ascii=False) + "</nowiki>}}")
        sections = [Section("2021秋", "TOP100", [Entry("甲", [colour])])]
        legend = Legend(colour_to_name={colour: "真创建者"})

        updated, _ = contributions.render_chart(
            text, sections, legend, {"2021秋": {"#000000": 2}},
            {"2021秋": {"导入版作者": 1}},      # 从旧口径那里减掉
            {"2021秋": {"#000000": 1}})         # 记到真创建者头上

        parsed = json.loads(contributions.CHART_RE.search(updated).group(2))
        data = dict(zip(parsed["yAxis"]["data"], parsed["series"][0]["data"]))
        self.assertEqual(data["真创建者"], 10)      # 9 + 1：条目搬过来了
        self.assertEqual(data["导入版作者"], 2)      # 3 - 1：不再记在他头上

    def test_migration_takes_the_old_numbers_from_the_base_revision(self):
        # 一次性迁移以固定的基准版为准：当前页面就算已经被加过一次，也不会越滚越大。
        colour = "#000000"
        base = {
            "legend": {"data": ["ボカコレ2021秋"]},
            "yAxis": {"data": ["真创建者", "导入版作者"]},
            "series": [{"name": "ボカコレ2021秋", "type": "bar",
                        "itemStyle": {"color": "#111111"}, "data": [9, 3]}],
        }
        base_text = ("{{Echart|data=<nowiki>"
                     + json.dumps(base, ensure_ascii=False) + "</nowiki>}}")
        now = {
            "legend": {"data": ["ボカコレ2021秋"]},
            "yAxis": {"data": ["真创建者", "导入版作者"]},
            "series": [{"name": "ボカコレ2021秋", "type": "bar",
                        "itemStyle": {"color": "#111111"}, "data": [12, 0]}],
        }
        text = ("{{Echart|data=<nowiki>"
                + json.dumps(now, ensure_ascii=False) + "</nowiki>}}")
        sections = [Section("2021秋", "TOP100", [Entry("甲", [colour])])]
        legend = Legend(colour_to_name={colour: "真创建者"})

        updated, _ = contributions.render_chart(
            text, sections, legend, {"2021秋": {"#000000": 2}},
            {"2021秋": {"导入版作者": 1}}, {"2021秋": {"#000000": 1}},
            base_text=base_text)

        parsed = json.loads(contributions.CHART_RE.search(updated).group(2))
        data = dict(zip(parsed["yAxis"]["data"], parsed["series"][0]["data"]))
        self.assertEqual(data["真创建者"], 10)      # 9 + 1，而不是 12 + 1
        self.assertEqual(data["导入版作者"], 2)      # 3 - 1


class TestRecredit(TestCase):
    """一次性迁移：把导入错记的数字搬到真创建者头上。"""

    def test_requires_a_base_revision(self):
        with self.assertRaises(ValueError):
            contributions.recredit(None, "", [], Legend(), {}, {},
                                   None, None, None, None)

    @patch.object(contributions, "render_chart", return_value=("NEW", {}))
    @patch.object(contributions, "count_by_listed", return_value={})
    @patch.object(contributions, "revision_text", return_value="BASETEXT")
    def test_takes_the_old_numbers_from_the_given_revision(
            self, revision_text, _count, render_chart):
        text = contributions.recredit(Mock(), "TEXT", [], Legend(), {}, {},
                                      None, None, None, 123)

        revision_text.assert_called_once()
        self.assertEqual(revision_text.call_args.args[1], 123)
        self.assertEqual(text, "NEW")
        self.assertEqual(render_chart.call_args.kwargs["base_text"], "BASETEXT")

    def test_revision_text_rejects_another_page(self):
        site = Mock()
        site.simple_request.return_value.submit.return_value = {
            "query": {"pages": [{"title": "别的页面",
                                 "revisions": [{"slots": {"main": {"content": "X"}}}]}]}}

        with self.assertRaises(ValueError):
            contributions.revision_text(site, 123)


class TestScheduledMaintenance(TestCase):
    @patch("sys.argv", ["vocaloid_collection_contributions.py", "all", "--write"])
    @patch.object(contributions.pywikibot, "Site")
    @patch.object(contributions, "run_once")
    def test_full_pass_runs_all_actions_without_recent_changes_polling(
            self, run_once, site_factory):
        site = site_factory.return_value

        contributions.main()

        run_once.assert_called_once_with(
            site, set(contributions.ALL_ACTIONS), "listed", True, None, None)

    @patch.object(contributions, "load_cache", return_value={})
    @patch.object(contributions, "save_cache")
    @patch.object(contributions, "DATA_DIR")
    @patch.object(contributions, "render_chart", return_value=("", {}))
    @patch.object(contributions, "count_by_listed", return_value={})
    @patch.object(contributions, "plan_colours",
                  return_value={"Song": ("#123456", "Canonical song")})
    @patch.object(contributions, "Page")
    def test_stats_uses_entries_after_colouring_and_title_correction(
            self, page_factory, _plan_colours, count_by_listed,
            render_chart, _data_dir, _save_cache, _load_cache):
        page_factory.return_value.text = (
            "=== 2024春 ===\n"
            "{{multicol}}\n"
            "<poem>;TOP100 (0/1)\n"
            "{| class=\"wikitable\"\n"
            "|-\n"
            "| [[Song|1]]\n"
            "|}\n"
            "{{Echart|data=<nowiki>{"
            "\"legend\":{\"data\":[\"ボカコレ2024春\"]},"
            "\"yAxis\":{\"data\":[\"Creator\"]},"
            "\"series\":[{\"name\":\"ボカコレ2024春\",\"data\":[0]}]"
            "}</nowiki>}}\n"
        )
        render_chart.side_effect = lambda text, *_: (text, {})

        contributions.run_once(object(), {"colour", "stats"})

        updated_sections = count_by_listed.call_args.args[1]
        self.assertEqual(updated_sections[0].entries[0].title, "Canonical song")
        self.assertEqual(updated_sections[0].entries[0].colours, ["#123456"])
        render_chart.assert_called_once()


class TestPageCreator(TestCase):
    """跨站导入的首版挂的是源站最后一版的作者，不能拿来当创建者。"""

    @patch.object(contributions, "creator_of", return_value="本站用户")
    @patch.object(contributions, "moegirl_creator_of")
    def test_local_creator_is_used_as_is(self, moegirl, _creator_of):
        self.assertEqual(contributions.page_creator(None, "曲", {}, {}), "本站用户")
        moegirl.assert_not_called()

    @patch.object(contributions, "creator_of", return_value="zhmoe>源站最后编辑者")
    @patch.object(contributions, "moegirl_creator_of", return_value="真正的作者")
    def test_imported_revision_defers_to_the_source_article(
            self, _moegirl, _creator_of):
        self.assertEqual(contributions.page_creator(None, "曲", {}, {}), "真正的作者")

    @patch.object(contributions, "creator_of", return_value="zhmoe>源站最后编辑者")
    @patch.object(contributions, "moegirl_creator_of", return_value=None)
    @patch.object(contributions, "import_stamp", return_value=None)
    @patch.object(contributions, "moegirl_imported_creator", return_value=None)
    def test_imports_are_not_credited_when_the_source_is_unknown(
            self, _imported, _stamp, _moegirl, _creator_of):
        # 宁可不归属，也不拿源站的最后一位编辑者顶替
        self.assertIsNone(contributions.page_creator(None, "曲", {}, {}))
        _imported.assert_called_once()

    @patch.object(contributions, "creator_of", return_value="wikipedia>某人")
    @patch.object(contributions, "moegirl_creator_of")
    def test_other_wikis_are_not_credited(self, moegirl, _creator_of):
        self.assertIsNone(contributions.page_creator(None, "曲", {}, {}))
        moegirl.assert_not_called()

    def test_credit_pair_maps_names_to_colours_and_drops_bots(self):
        colour = "#FF0000"
        legend = Legend(colour_to_name={colour: "图例用户"},
                        name_to_colour={"图例用户": colour})

        self.assertEqual(contributions.credit_pair(legend, "某人", "旧作者"),
                         ("某人", "旧作者"))
        self.assertEqual(contributions.credit_pair(legend, "图例用户", "图例用户"),
                         (colour, colour))
        # 机器人账号两边都不记
        self.assertEqual(contributions.credit_pair(legend, "星海-interfacebot", "某人"),
                         (None, "某人"))
        self.assertEqual(contributions.credit_pair(legend, None, None), (None, None))

    @patch.object(contributions, "page_credits",
                  return_value=("真正的作者", "源站最后编辑者"))
    @patch.object(contributions, "batch_creators")
    def test_import_credits_move_and_the_old_ones_are_subtracted(
            self, _batch_creators, _page_credits):
        # 榜外曲原来是按导入时抄来的源站最后一版作者记的：现在记真正的作者，
        # 旧图表里多给源站最后编辑者的那一份要减回去、真作者那一格要加上。
        colour = "#000000"
        sections = [Section("2021秋", "TOP100", [Entry("榜内曲", [colour])])]
        legend = Legend(colour_to_name={colour: "榜内创建者"})
        corrections, gains = {}, {}

        counts = count_by_listed(
            FakeSite(), sections, legend, {},
            lambda _season: {"榜外曲"},
            lambda _season: {"榜内曲", "榜外曲"},
            corrections=corrections, gains=gains)

        self.assertEqual(counts["2021秋"]["#000000"], 1)
        self.assertEqual(counts["2021秋"]["真正的作者"], 1)
        self.assertEqual(corrections["2021秋"]["源站最后编辑者"], 1)
        self.assertEqual(gains["2021秋"]["真正的作者"], 1)


class TestMoegirlCrossCheck(TestCase):
    """voca 上说不出创建者时，拿萌娘百科的同名条目当参照。"""

    def test_titles_follow_redirects_and_variant_conversions(self):
        # 模板写日文原名、萌娘条目用中文：靠 converttitles 归一；
        # 「ダウナ」在萌娘是重定向，要认最终标题。
        data = {"query": {
            "converted": [{"from": "後篇", "to": "后篇"}],
            "redirects": [{"from": "ダウナ", "to": "Downa"}],
            "pages": [{"title": "パメラ"}, {"title": "后篇"},
                      {"title": "虚构曲", "missing": True}, {"title": "Downa"}],
        }}
        with patch.object(contributions, "moegirl_api", return_value=data), \
                patch.object(contributions.time, "sleep"):
            found = contributions.moegirl_titles(
                ["パメラ", "後篇", "虚构曲", "ダウナ"])

        self.assertEqual(found, {"パメラ": "パメラ", "後篇": "后篇",
                                 "虚构曲": None, "ダウナ": "Downa"})

    def test_titles_leave_unanswered_queries_out_of_the_result(self):
        # 问不到 ≠ 没有：萌娘 API 挂了就不能返回「无同名条目」。
        with patch.object(contributions, "moegirl_api", return_value=None), \
                patch.object(contributions.time, "sleep"):
            found = contributions.moegirl_titles(["甲"])

        self.assertEqual(found, {})

    def test_lookup_caches_creators_and_confirmed_absences(self):
        def fake(params):
            if params.get("prop") == "revisions":
                return {"query": {"pages": [{"title": "甲",
                                             "revisions": [{"user": "萌娘用户"}]}]}}
            return {"query": {"pages": [{"title": "甲"},
                                        {"title": "乙", "missing": True}]}}

        with patch.object(contributions, "moegirl_api", side_effect=fake), \
                patch.object(contributions.time, "sleep"):
            cache = {}
            pages = contributions.moegirl_lookup(["甲", "乙"], cache)

        self.assertEqual((pages["甲"].title, pages["甲"].creator, pages["甲"].known),
                         ("甲", "萌娘用户", True))
        self.assertEqual((pages["乙"].title, pages["乙"].creator, pages["乙"].known),
                         (None, None, True))
        self.assertEqual(cache["甲"][:2], ("甲", "萌娘用户"))
        self.assertEqual(cache["乙"][:2], (None, None))

        # 第二次跑吃缓存，不再请求萌娘 API
        with patch.object(contributions, "moegirl_api") as api:
            again = contributions.moegirl_lookup(["甲", "乙"], cache)
        api.assert_not_called()
        self.assertEqual(again["甲"].creator, "萌娘用户")
        self.assertTrue(again["乙"].known)

    def test_candidates_flag_red_mismatched_and_bot_created_entries(self):
        colour = "#FF0000"
        legend = Legend(colour_to_name={colour: "某人"},
                        name_to_colour={"某人": colour})
        sections = [Section("2021秋", "TOP100", [
            Entry("红链曲", []),
            Entry("标注不符曲", [colour]),
            Entry("标注相符曲", [colour]),
            Entry("机器人建的曲", []),
        ])]
        exists = {"红链曲": False, "标注不符曲": True,
                  "标注相符曲": True, "机器人建的曲": True}
        creators = {"标注不符曲": "别人", "标注相符曲": "某人",
                    "机器人建的曲": "星海-interfacebot"}

        rows = contributions.moegirl_candidates(
            sections, legend, None, exists, {}, creators)

        self.assertEqual({(row["reason"], row["title"]) for row in rows},
                         {("red", "红链曲"), ("mismatch", "标注不符曲"),
                          ("bot", "机器人建的曲")})

    def test_candidates_cover_outside_songs_from_the_season_template(self):
        # 榜外原创曲在页面上没有名次格子，归属全靠赛季模板，也要拿去比对。
        sections = [Section("2021秋", "TOP100", [Entry("榜内曲", [])])]

        rows = contributions.moegirl_candidates(
            sections, Legend(), lambda _season: {"榜外原创曲"}, {"榜内曲": False},
            {}, {})

        self.assertEqual([(row["reason"], row["title"]) for row in rows],
                         [("red", "榜内曲"), ("red", "榜外原创曲")])

    @patch.object(contributions, "batch_creators")
    @patch.object(contributions, "batch_exists")
    def test_report_lists_moegirl_creators_without_touching_the_page(
            self, batch_exists, batch_creators):
        sections = [Section("2021秋", "TOP100", [Entry("红链曲", [])])]
        pages = {"红链曲": contributions.MoePage("同曲", "萌娘用户", True)}

        with patch.object(contributions, "moegirl_lookup", return_value=pages):
            report = contributions.moegirl_report(
                object(), sections, Legend(), {}, {}, moe_cache={})

        self.assertIn("2021秋/TOP100 红链曲", report)
        self.assertIn("萌娘《同曲》（经重定向）创建者 萌娘用户", report)
        self.assertIn("萌娘用户：+1", report)
        self.assertIn("只出报告", report)

    @patch.object(contributions, "batch_creators")
    @patch.object(contributions, "batch_exists")
    def test_report_marks_imported_first_revisions(
            self, batch_exists, batch_creators):
        # 「voca 首版」其实来自源站最后一版时要写清楚，否则看报告的人会把
        # 那当成创建者。
        sections = [Section("2021秋", "TOP100", [Entry("曲", [])])]
        cache = {"曲": ("zhmoe>源站最后编辑者", "zhmoe")}
        pages = {"曲": contributions.MoePage("同曲", "真正的作者", True)}

        with patch.object(contributions, "moegirl_lookup", return_value=pages):
            report = contributions.moegirl_report(
                object(), sections, Legend(), cache, {}, moe_cache={})

        self.assertIn("voca 首版 源站最后编辑者（萌百导入）", report)
        self.assertIn("最后一版", report)

    @patch.object(contributions, "batch_creators")
    @patch.object(contributions, "batch_exists")
    def test_report_keeps_coloured_cells_out_of_the_gain_tally(
            self, batch_exists, batch_creators):
        # 上色但页面不存在的格子已经算给标注的创建者了，萌娘的答案只是参照，
        # 不能再加一遍。
        colour = "#FF0000"
        sections = [Section("2021秋", "TOP100", [Entry("红链曲", [colour])])]
        legend = Legend(colour_to_name={colour: "某人"})
        pages = {"红链曲": contributions.MoePage("同曲", "萌娘用户", True)}

        with patch.object(contributions, "moegirl_lookup", return_value=pages):
            report = contributions.moegirl_report(
                object(), sections, legend, {}, {}, moe_cache={})

        self.assertIn("标注 某人", report)
        self.assertNotIn("萌娘用户：+1", report)

    def test_api_treats_an_error_response_as_unknown(self):
        # 萌娘回 error（限流、参数被禁）时必须当成「没问到」；当成「没有这条」
        # 会把整批条目写成「无同名条目」，报告就成了误导。
        payload = json.dumps({"error": {"code": "action-notallowed",
                                        "info": "Unauthorized API call"}}).encode()

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def read(self):
                return payload

        with patch.object(contributions.urllib.request, "urlopen",
                          return_value=FakeResponse()), \
                patch.object(contributions.pywikibot, "error") as log:
            data = contributions.moegirl_api({"action": "query", "titles": "甲"})

        self.assertIsNone(data)
        log.assert_called_once()

    @patch.object(contributions, "batch_creators")
    @patch.object(contributions, "batch_exists")
    def test_report_summarises_red_links_moegirl_does_not_have(
            self, batch_exists, batch_creators):
        # 红链且萌娘也没有同名条目：对判断没帮助，只报数量，别灌满整份报告。
        sections = [Section("2021秋", "TOP100",
                            [Entry("红链甲", []), Entry("红链乙", [])])]
        pages = {"红链甲": contributions.MoePage(None, None, True),
                 "红链乙": contributions.MoePage("同曲乙", "萌娘用户", True)}

        with patch.object(contributions, "moegirl_lookup", return_value=pages):
            report = contributions.moegirl_report(
                object(), sections, Legend(), {}, {}, moe_cache={})

        self.assertNotIn("红链甲", report)
        self.assertIn("红链乙", report)
        self.assertIn("另有 1 条在萌娘也没有同名条目", report)

    @patch.object(contributions, "batch_creators")
    @patch.object(contributions, "batch_exists")
    def test_report_only_marks_matches_found_through_a_redirect(
            self, batch_exists, batch_creators):
        sections = [Section("2021秋", "TOP100", [Entry("同名曲", [])])]
        pages = {"同名曲": contributions.MoePage("同名曲", "萌娘用户", True)}

        with patch.object(contributions, "moegirl_lookup", return_value=pages):
            report = contributions.moegirl_report(
                object(), sections, Legend(), {}, {}, moe_cache={})

        self.assertIn("萌娘《同名曲》创建者 萌娘用户", report)
        self.assertNotIn("经重定向", report)

    @patch.object(contributions, "batch_creators")
    @patch.object(contributions, "batch_exists")
    def test_report_counts_a_legend_user_as_a_colour_gain(
            self, batch_exists, batch_creators):
        # 萌娘创建者在图例里有颜色：采用的话直接加到这个颜色上，不是新开一行。
        colour = "#FF0000"
        sections = [Section("2021秋", "TOP100", [Entry("红链曲", [])])]
        legend = Legend(colour_to_name={colour: "某人"},
                        name_to_colour={"某人": colour})
        pages = {"红链曲": contributions.MoePage("同曲", "某人", True)}

        with patch.object(contributions, "moegirl_lookup", return_value=pages):
            report = contributions.moegirl_report(
                object(), sections, legend, {}, {}, moe_cache={})

        self.assertIn(f"某人（{colour}）：+1", report)


class TestMoegirlOfficial(TestCase):
    """镜像站看不见萌百「待审核」的条目——那些要去官方站（得先登录）才查得到。"""

    def test_login_asks_for_json_and_confirms_it_through_userinfo(self):
        # 登录请求漏了 format=json 会拿到 XML，json 解析失败就被当成「登录没成功」，
        # 所以这里连请求参数一起盯着。
        opener = FakeOpener([
            {"query": {"tokens": {"logintoken": "tok"}}},
            {"login": {"result": "Success"}},
            {"query": {"userinfo": {"name": "人间百态"}}},
        ])
        session = contributions.MoegirlSession(("人间百态@vclc", "secret"))

        with patch.object(contributions.urllib.request, "build_opener",
                          return_value=opener), \
                patch.object(contributions.time, "sleep"):
            self.assertTrue(session.ready())

        token_url, login_url, userinfo_url = (request.full_url
                                             for request in opener.requests)
        self.assertIn("format=json", token_url)
        self.assertIn("meta=tokens", token_url)
        self.assertEqual(login_url, contributions.MOEGIRL_OFFICIAL)
        body = opener.requests[1].data
        self.assertIn(b"lgtoken=tok", body)
        self.assertIn(b"lgname=%E4%BA%BA%E9%97%B4%E7%99%BE%E6%80%81%40vclc", body)
        self.assertIn("meta=userinfo", userinfo_url)
        self.assertTrue(session.ready())  # 第二次问不再登录
        self.assertEqual(len(opener.requests), 3)

    def test_login_that_never_lands_leaves_the_session_unusable(self):
        opener = FakeOpener([
            {"query": {"tokens": {"logintoken": "tok"}}},
            {"login": {"result": "WrongPass"}},
            {"query": {"userinfo": {"name": "1.2.3.4", "anon": True}}},
        ])
        session = contributions.MoegirlSession(("人间百态@vclc", "secret"))

        with patch.object(contributions.urllib.request, "build_opener",
                          return_value=opener), \
                patch.object(contributions.time, "sleep"):
            self.assertFalse(session.ready())
            self.assertIsNone(session.api({"action": "query", "meta": "tokens"}))

    def test_missing_token_leaves_the_session_unusable(self):
        opener = FakeOpener([{"query": {}}])
        session = contributions.MoegirlSession(("人间百态@vclc", "secret"))

        with patch.object(contributions.urllib.request, "build_opener",
                          return_value=opener):
            self.assertFalse(session.ready())

    def test_credentials_read_the_zh_entry_and_the_bot_password_suffix(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "user-password.py"
            path.write_text(
                "# 注释\n"
                "('voca', 'voca', 'Renjian-bot', 'secret')\n"
                "('zh', 'zh', '人间百态', BotPassword('vclc', 'token'))\n",
                encoding="utf-8")
            with patch.object(contributions.pywikibot.config, "password_file",
                              str(path)):
                self.assertEqual(contributions.moegirl_credentials(),
                                 ("人间百态@vclc", "token"))

    def test_credentials_are_absent_without_a_zh_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "user-password.py"
            path.write_text("('voca', 'voca', 'Renjian-bot', 'secret')\n",
                            encoding="utf-8")
            with patch.object(contributions.pywikibot.config, "password_file",
                              str(path)):
                self.assertIsNone(contributions.moegirl_credentials())

    def test_variants_only_swap_punctuation(self):
        title = "奔向暗影，由阳光刺穿，闪耀着。"
        variants = contributions.moegirl_variants(title)

        self.assertEqual(variants[0], title)
        self.assertIn("奔向暗影、由阳光刺穿、闪耀着。", variants)
        self.assertIn("奔向暗影，由阳光刺穿，闪耀着", variants)
        for variant in variants:
            self.assertEqual(
                variant.translate({ord(char): None for char in "，、,。（）()"}),
                title.translate({ord(char): None for char in "，、,。（）()"}))

    def test_official_page_answers_through_a_title_variant(self):
        session = FakeSession([
            {"query": {"pages": [{"title": "奔向暗影、由阳光刺穿、闪耀着。"}]}},
            {"query": {"pages": [{"title": "奔向暗影、由阳光刺穿、闪耀着。",
                                  "revisions": [{"user": "源站创建者"}]}]}},
        ])
        with patch.object(contributions.time, "sleep"):
            page = contributions.moegirl_official_page(
                "奔向暗影，由阳光刺穿，闪耀着。", session)

        self.assertEqual((page.title, page.creator, page.known),
                         ("奔向暗影、由阳光刺穿、闪耀着。", "源站创建者", True))

    def test_official_page_reports_a_title_it_does_not_have(self):
        session = FakeSession([{"query": {"pages": [
            {"title": "没有这条", "missing": True}]}}])
        page = contributions.moegirl_official_page("没有这条", session)

        self.assertEqual((page.title, page.creator, page.known),
                         (None, None, True))

    def test_official_page_stays_unknown_when_it_cannot_ask(self):
        self.assertIsNone(contributions.moegirl_official_page("曲", FakeSession([])))

    def test_source_title_needs_an_exact_timestamp(self):
        # 导入版抄的是源站**最后一版**的作者与时间：那位编辑在同一时刻的编辑
        # 才是源条目本身，差一秒都不认。
        stamp = datetime(2024, 7, 13, 1, 2, 4, tzinfo=timezone.utc)
        session = FakeSession([{"query": {"usercontribs": [
            {"title": "差一分钟的编辑", "timestamp": "2024-07-13T01:03:04Z"},
            {"title": "源条目", "timestamp": "2024-07-13T01:02:04Z"},
        ]}}])

        self.assertEqual(
            contributions.moegirl_source_title("源站编辑者", stamp, session),
            (True, "源条目"))

    def test_source_title_admits_when_it_could_not_ask(self):
        stamp = datetime(2024, 7, 13, 1, 2, 4, tzinfo=timezone.utc)
        self.assertEqual(
            contributions.moegirl_source_title("源站编辑者", stamp, FakeSession([])),
            (False, None))

    @patch.object(contributions, "moegirl_source_title")
    @patch.object(contributions, "moegirl_official_page")
    def test_imported_creator_falls_back_to_the_source_title(self, official_page,
                                                             source_title):
        # voca 的条目名是自己的消歧写法（Flare(PedestrianP)），源条目叫别的名字
        source_title.return_value = (True, "Flare(初音未来)")
        official_page.side_effect = [
            contributions.MoePage(None, None, True),
            contributions.MoePage("Flare(初音未来)", "源站创建者", True),
        ]
        cache = {}

        creator = contributions.moegirl_imported_creator(
            "Flare(PedestrianP)", "源站编辑者", "2024-01-01T00:00:00Z", cache)

        self.assertEqual(creator, "源站创建者")
        self.assertEqual(cache["Flare(PedestrianP)"][:2],
                         ("Flare(初音未来)", "源站创建者"))
        self.assertEqual(cache["Flare(PedestrianP)"][3],
                         contributions.MOEGIRL_SOURCE_OFFICIAL)

    @patch.object(contributions, "moegirl_official_page", return_value=None)
    def test_imported_creator_does_not_cache_a_query_it_could_not_make(self, _page):
        cache = {}

        self.assertIsNone(contributions.moegirl_imported_creator(
            "曲", "源站编辑者", "2024-01-01T00:00:00Z", cache))

        self.assertEqual(cache, {})

    @patch.object(contributions, "moegirl_official_page")
    def test_imported_creator_trusts_the_official_cache(self, official_page):
        cache = {"曲": (None, None, time.time(),
                        contributions.MOEGIRL_SOURCE_OFFICIAL)}

        self.assertIsNone(contributions.moegirl_imported_creator(
            "曲", "源站编辑者", "2024-01-01T00:00:00Z", cache))

        official_page.assert_not_called()

    def test_cache_remembers_which_source_answered(self):
        cache = {"官方": ("《官方》", "甲", time.time(),
                          contributions.MOEGIRL_SOURCE_OFFICIAL),
                 "镜像": ("《镜像》", "乙", time.time()),
                 "过期": ("《过期》", "丙",
                          time.time() - contributions.MOEGIRL_CACHE_TTL - 1)}

        self.assertEqual(contributions.moegirl_cached(cache, "官方")[2],
                         contributions.MOEGIRL_SOURCE_OFFICIAL)
        self.assertEqual(contributions.moegirl_cached(cache, "镜像")[2],
                         contributions.MOEGIRL_SOURCE_MIRROR)
        self.assertIsNone(contributions.moegirl_cached(cache, "过期"))

    @patch.object(contributions, "creator_of", return_value="zhmoe>源站最后编辑者")
    @patch.object(contributions, "moegirl_creator_of", return_value=None)
    @patch.object(contributions, "import_stamp", return_value=None)
    @patch.object(contributions, "moegirl_imported_creator", return_value="真正的作者")
    def test_page_credits_use_the_official_site_as_a_second_chance(
            self, imported, _stamp, _moegirl, _creator_of):
        self.assertEqual(contributions.page_credits(None, "曲", {}, {})[0],
                         "真正的作者")
        imported.assert_called_once()


class TestMoegirlAction(TestCase):
    def test_moe_is_a_known_action_but_not_part_of_all(self):
        self.assertNotIn("moe", contributions.ALL_ACTIONS)
        self.assertIn("moe", contributions.EXTRA_ACTIONS)

    @patch("sys.argv", ["vocaloid_collection_contributions.py", "moe"])
    @patch.object(contributions.pywikibot, "Site")
    @patch.object(contributions, "run_once")
    def test_moe_action_runs_without_write(self, run_once, site_factory):
        contributions.main()

        run_once.assert_called_once_with(
            site_factory.return_value, {"moe"}, "listed", False, None, None)
