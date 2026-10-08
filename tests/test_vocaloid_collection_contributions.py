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


class TestCountByListed(TestCase):
    def test_neta_entries_are_not_included_in_season_stats(self):
        colour = "#000000"
        sections = [
            Section("2021秋", "TOP100", [Entry(f"主榜曲目{i}", [colour]) for i in range(15)]),
            Section("2021秋", "ROOKIE", [Entry(f"新人曲目{i}", [colour]) for i in range(2)]),
            Section("2021秋", "neta", [Entry("neta曲目", [colour])]),
            Section("2021秋", "REMIX", [Entry("remix曲目", [colour])]),
        ]
        legend = Legend(colour_to_name={colour: "贡献者"})

        counts = count_by_listed(FakeSite(), sections, legend, {})

        self.assertEqual(counts["2021秋"]["#000000"], 17)

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
