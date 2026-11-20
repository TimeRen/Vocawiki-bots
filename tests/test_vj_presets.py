"""`is_vj_song` 的判定（`test_is_vj_song` 读线上数据；其余用假页面，离线）。

具体分数线与计分行格式见 `tests/test_mobilization_tally.py`。
"""
from unittest import TestCase
from unittest import mock

from pywikibot import Page

from bots.mobilization_tally import presets as pr
from utils.sites import voca


class FakeCategory:
    def __init__(self, name):
        self._name = name

    def title(self, with_ns: bool = False):
        return self._name


class FakePage:
    def __init__(self, title, text="", categories=()):
        self._title = title
        self.text = text
        self._categories = list(categories)

    def title(self, as_link: bool = False, allow_interwiki: bool = True):
        return self._title

    def categories(self):
        return [FakeCategory(name) for name in self._categories]

    def site(self):
        return None


class Test(TestCase):
    def test_is_vj_song(self):
        site = voca()
        self.assertTrue(pr.is_vj_song(Page(site, "同一夜")))
        self.assertTrue(not pr.is_vj_song(Page(site, "中华缘木娘")))
        self.assertTrue(not pr.is_vj_song(Page(site, "NHOT_BOT(歌曲)")))

    def test_vj_furigana(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ}}", ["使用VOCALOID的歌曲"])
        contribution = {"page": page, "ns": 0, "new": False, "minor": False,
                        "comment": "歌词注音", "revid": 1}
        self.assertEqual("[[同一夜]]（+0.20）", pr.vj_furigana(contribution))

    def test_vj_translate(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ\n|translated=" + "啊" * 100 + "\n}}",
                        ["使用VOCALOID的歌曲"])
        contribution = {"page": page, "ns": 0, "new": False, "minor": False,
                        "comment": "翻译歌词", "revid": 1}
        self.assertEqual("[[同一夜]]（+2.00）", pr.vj_translate(contribution))

    def test_translate_ignores_other_summaries(self):
        page = FakePage("同一夜", "{{LyricsKai|original=あ\n|translated=啊\n}}",
                        ["使用VOCALOID的歌曲"])
        contribution = {"page": page, "ns": 0, "new": False, "minor": False,
                        "comment": "改错别字", "revid": 1}
        self.assertIsNone(pr.vj_translate(contribution))
