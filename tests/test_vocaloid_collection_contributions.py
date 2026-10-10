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


class TestCountByListed(TestCase):
    @patch.object(contributions, "Page")
    def test_batch_creators_uses_single_page_oldest_revision_queries(
            self, page_factory):
        site = object()
        page = page_factory.return_value
        page.revisions.return_value = iter([{"user": "User"}])
        cache = {"Cached": ("Existing", "")}

        contributions.batch_creators(
            site, ["Alias", "Target", "Cached"], cache, {"Alias": "Target"})

        self.assertEqual(cache["Target"], ("User", ""))
        self.assertEqual(cache["Cached"], ("Existing", ""))
        page_factory.assert_called_once_with(site, "Target")
        page.revisions.assert_called_once_with(
            total=1, reverse=True, content=False)

    @patch.object(contributions, "Page")
    def test_creator_of_keeps_the_cross_wiki_prefix(self, page_factory):
        # zhmoe>某人：voca 抄的是源站最后一版的作者，来源得留着，page_creator
        # 才知道不能拿这个人当创建者
        page_factory.return_value.revisions.return_value = iter(
            [{"user": "zhmoe>源站编辑者"}])
        cache = {}

        self.assertEqual(contributions.creator_of(object(), "曲", cache),
                         "zhmoe>源站编辑者")
        self.assertEqual(cache["曲"], ("zhmoe>源站编辑者", "zhmoe"))

    @patch.object(contributions, "Page")
    def test_creator_of_requeries_legacy_cache_entries(self, page_factory):
        # 旧缓存只存了剥掉前缀的用户名，分辨不出来源，只能重查一次
        page_factory.return_value.revisions.return_value = iter(
            [{"user": "本站用户"}])
        cache = {"曲": "本站用户"}

        contributions.creator_of(object(), "曲", cache)

        page_factory.assert_called_once()
        self.assertEqual(cache["曲"], ("本站用户", ""))

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
    def test_imports_are_not_credited_when_the_source_is_unknown(
            self, _moegirl, _creator_of):
        # 宁可不归属，也不拿源站的最后一位编辑者顶替
        self.assertIsNone(contributions.page_creator(None, "曲", {}, {}))

    @patch.object(contributions, "creator_of", return_value="wikipedia>某人")
    @patch.object(contributions, "moegirl_creator_of")
    def test_other_wikis_are_not_credited(self, moegirl, _creator_of):
        self.assertIsNone(contributions.page_creator(None, "曲", {}, {}))
        moegirl.assert_not_called()


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
            site_factory.return_value, {"moe"}, "listed", False, None)
