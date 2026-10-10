import json
from unittest import TestCase
from unittest.mock import patch

import bots.vocaloid_collection_contributions as contributions

from bots.vocaloid_collection_contributions import (
    Entry,
    Legend,
    Section,
    count_by_listed,
)


class FakeSite:
    def __init__(self, redirects=None):
        self.redirects = redirects or {}

    def simple_request(self, **kwargs):
        self.titles = kwargs["titles"].split("|")
        return self

    def submit(self):
        resolved = {title: self.redirects.get(title, title) for title in self.titles}
        pages = [{"title": title} for title in dict.fromkeys(resolved.values())]
        redirects = [
            {"from": title, "to": target}
            for title, target in resolved.items()
            if title != target
        ]
        return {"query": {"pages": pages, "redirects": redirects}}


class PagedSite:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []

    def simple_request(self, **kwargs):
        self.requests.append(kwargs)
        return self

    def submit(self):
        return next(self.responses)


class TestCountByListed(TestCase):
    @patch.object(contributions, "Page")
    def test_batch_creators_uses_single_page_oldest_revision_queries(
            self, page_factory):
        site = object()
        page = page_factory.return_value
        page.revisions.return_value = iter([{"user": "User"}])
        cache = {"Cached": "Existing"}

        contributions.batch_creators(
            site, ["Alias", "Target", "Cached"], cache, {"Alias": "Target"})

        self.assertEqual(cache, {"Cached": "Existing", "Target": "User"})
        page_factory.assert_called_once_with(site, "Target")
        page.revisions.assert_called_once_with(
            total=1, reverse=True, content=False)

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
        # 仍然是本赛季的歌，必须收下来，否则榜外歌曲会被统计当成外人。
        text = (
            "| title = 其他歌曲\n"
            "| group1 = 其他部门\n"
            "| list1 = （待补充）\n"
            "| group2 = 未上榜歌曲\n"
            "| list2 = [[榜外歌曲甲]] • {{lj|[[榜外歌曲乙|ボカロ曲]]}}\n"
        )

        parsed = contributions.parse_season_template(text)

        self.assertEqual(set(parsed["neta"].values()), {"榜外歌曲甲", "榜外歌曲乙"})

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


class TestScheduledMaintenance(TestCase):
    @patch("sys.argv", ["vocaloid_collection_contributions.py", "all", "--write"])
    @patch.object(contributions.pywikibot, "Site")
    @patch.object(contributions, "run_once")
    def test_full_pass_runs_all_actions_without_recent_changes_polling(
            self, run_once, site_factory):
        site = site_factory.return_value

        contributions.main()

        run_once.assert_called_once_with(
            site, set(contributions.ALL_ACTIONS), "listed", True, None)

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
