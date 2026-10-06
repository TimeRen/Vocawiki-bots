from unittest import TestCase

from bots.vocaloid_collection_contributions import (
    Entry,
    Legend,
    Section,
    count_by_listed,
)


class FakeSite:
    def simple_request(self, **kwargs):
        return self

    def submit(self):
        return {"query": {"pages": []}}


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
