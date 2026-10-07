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


class TestWatch(TestCase):
    @patch.object(contributions, "run_once")
    @patch.object(contributions, "Page")
    def test_watch_runs_one_full_pass_without_polling_recent_changes(
            self, page_class, run_once):
        page_class.return_value.text = ""
        site = FakeSite()
        contributions.watch(
            site, interval=0, settle=0, sweep_interval=0, basis="listed",
            write=False, summary=None, max_runtime=1)

        run_once.assert_called_once_with(
            site, {"entries", "counts", "colour", "report", "stats"},
            "listed", False, None)
