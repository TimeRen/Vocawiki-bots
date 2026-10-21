# -*- coding: utf-8 -*-
"""bots/user_contributions_navbox.py 的测试（不联网）。"""
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

import bots.user_contributions_navbox as navbox

from bots.user_contributions_navbox import (
    balanced_end,
    merge_songs,
    merge_templates,
    parse_links,
    parse_templates,
    rebuild,
    render_song_group,
    render_template_group,
    template_creations,
)

PAGE = """{{Navbox
|group1 = VOCALOID
|list1 = {{Navbox subgroup
         |group1 = 歌曲
         |list1  = {{Navbox subgroup
                   |group1 = 萌百时期
                   |list1 = {{Navbox subgroup
                   |group1 = 1-2
                   |list1  = {{links|n=4|甲|乙}}}}
         |group2 = Vocawiki时期
         |list2  ={{Navbox subgroup
                   |group1 = 1-10
                   |list1  = {{links|n=4|丙|丁|戊|己|庚|辛|壬|癸|子|丑}}
                   |group2 = 11-12
                   |list2  = {{links|n=4|寅|卯}}
     }}
  }}
         |group2 = 列表
         |list2  = {{links|n=4|传说曲}}
         |group5 = 歌姬模板
         |list5  = {{tl|甲姬}}{{w}}{{tl|乙姬}}
}}
|below = 说明
}}
"""


class BalancedEndTest(TestCase):
    def test_finds_the_matching_braces(self):
        text = "x{{a|{{b|c}}}}y"
        self.assertEqual(text.index("y"), balanced_end(text, 1))

    def test_unbalanced_raises(self):
        with self.assertRaises(ValueError):
            balanced_end("{{a|b}", 0)


class ListSpanTest(TestCase):
    def test_multiline_value(self):
        start, end = navbox.list_span(PAGE, "Vocawiki时期")
        value = PAGE[start:end]
        self.assertTrue(value.startswith("{{Navbox subgroup"))
        self.assertTrue(value.endswith("}}"))
        self.assertIn("寅|卯", value)

    def test_single_line_value_keeps_every_template(self):
        """`歌姬模板` 一行里连着两个 `{{tl|…}}`，按括号配对只会取到第一个。"""
        start, end = navbox.list_span(PAGE, "歌姬模板", single_line=True)
        self.assertEqual("{{tl|甲姬}}{{w}}{{tl|乙姬}}", PAGE[start:end])

    def test_missing_group_raises(self):
        with self.assertRaises(ValueError):
            navbox.list_span(PAGE, "不存在的分组")


class ParseLinksTest(TestCase):
    def test_reads_entries_and_keeps_display_forms(self):
        value = ('{{links|n=4|甲|乙(作者){{!}}乙|'
                 'vcp:丙{{!}}{{color|#fec600|丙}}}}')
        self.assertEqual(["甲", "乙(作者){{!}}乙", "vcp:丙{{!}}{{color|#fec600|丙}}"],
                         parse_links(value))

    def test_reads_several_blocks(self):
        value = "{{links|n=4|甲}}{{links|n=4|乙|丙}}"
        self.assertEqual(["甲", "乙", "丙"], parse_links(value))

    def test_empty(self):
        self.assertEqual([], parse_links(""))


class ParseTemplatesTest(TestCase):
    def test_names(self):
        self.assertEqual(["甲姬", "乙姬"], parse_templates("{{tl|甲姬}}{{w}}{{tl|乙姬}}"))


class IsDisambiguationTest(TestCase):
    """消歧义页的判定只认真正的标记（2026-10-21 的误删就是判太宽）。"""

    def test_the_real_category(self):
        self.assertTrue(navbox.is_disambiguation(["Category:消歧义页"], []))

    def test_the_real_template(self):
        self.assertTrue(navbox.is_disambiguation([], ["Template:消歧义页"]))
        self.assertTrue(navbox.is_disambiguation([], ["Template:Disambig"]))

    def test_maintenance_categories_do_not_count(self):
        """`{{About}}` 指向消歧义页时留下的维护分类，不代表页面是消歧义页。

        2026-10-21：`涅槃(HotaRu)` 挂在 `Category:消歧义模板链入页面错误` 下，
        旧代码按「分类名含『消歧』」判定，把它当成消歧义页从清单里删掉了。
        """
        self.assertFalse(navbox.is_disambiguation(
            ["Category:消歧义模板链入页面错误"], []))
        self.assertFalse(navbox.is_disambiguation(
            ["Category:消歧义模板链入页面不存在"], []))
        self.assertFalse(navbox.is_disambiguation(
            ["Category:消歧义分类"], ["Template:About"]))

    def test_ordinary_page(self):
        self.assertFalse(navbox.is_disambiguation(
            ["Category:2022年投稿至YouTube的歌曲"], ["Template:VOCALOID Songbox"]))


class MergeSongsTest(TestCase):
    def test_redirect_is_replaced_by_its_target(self):
        status = {"Boo! Boo! Etranger": {"redirect": True},
                  "Boo！Boo！Etranger": {}}
        self.assertEqual(["Boo！Boo！Etranger"],
                         merge_songs(["Boo! Boo! Etranger"], [],
                                     status, {"Boo! Boo! Etranger": "Boo！Boo！Etranger"}))

    def test_disambiguation_pages_are_dropped(self):
        status = {"Redial": {"disambig": True}}
        self.assertEqual([], merge_songs(["Redial"], [], status, {}))

    def test_redirect_to_a_disambiguation_page_is_dropped(self):
        status = {"某重定向": {"redirect": True}, "Redial": {"disambig": True}}
        self.assertEqual([], merge_songs(["某重定向"], [], status, {"某重定向": "Redial"}))

    def test_new_creations_are_appended_in_order_without_duplicates(self):
        status = {"丙": {}, "丁": {}, "新歌": {}}
        self.assertEqual(["丙", "丁", "新歌"],
                         merge_songs(["丙", "丁"], ["新歌", "丙"], status, {}))

    def test_new_entries_with_a_disambiguation_suffix_show_the_bare_name(self):
        """用户 2026-10-17 的手改口径（差异 272789）：带括号的标题只显示括号前的歌名。"""
        status = {"希望(Dopamine)": {}, "我爱你(Mealerrand)": {}, "Redial(鹤三)": {},
                  "Front Glass ni chou à la crème": {}}
        self.assertEqual(
            ["希望(Dopamine){{!}}希望", "我爱你(Mealerrand){{!}}我爱你",
             "Redial(鹤三){{!}}Redial", "Front Glass ni chou à la crème"],
            merge_songs([], ["希望(Dopamine)", "我爱你(Mealerrand)", "Redial(鹤三)",
                             "Front Glass ni chou à la crème"], status, {}))

    def test_full_width_parentheses_are_handled_too(self):
        status = {"Redial（鹤三）": {}}
        self.assertEqual(["Redial（鹤三）{{!}}Redial"],
                         merge_songs([], ["Redial（鹤三）"], status, {}))

    def test_existing_entries_keep_the_display_they_already_have(self):
        status = {"希望(Dopamine)": {}, "甲(乙)": {}}
        self.assertEqual(["希望(Dopamine){{!}}希望", "甲(乙)"],
                         merge_songs(["希望(Dopamine){{!}}希望", "甲(乙)"], [], status, {}))

    def test_redirect_target_with_a_suffix_shows_the_bare_name(self):
        status = {"旧名": {"redirect": True}, "Redial(鹤三)": {}}
        self.assertEqual(["Redial(鹤三){{!}}Redial"],
                         merge_songs(["旧名"], [], status, {"旧名": "Redial(鹤三)"}))

    def test_display_forms_are_kept(self):
        status = {"乙(作者)": {}}
        self.assertEqual(["乙(作者){{!}}乙"],
                         merge_songs(["乙(作者){{!}}乙"], [], status, {}))

    def test_interwiki_entries_are_left_alone(self):
        self.assertEqual(["vcp:丙{{!}}丙"],
                         merge_songs(["vcp:丙{{!}}丙"], [], {}, {}))

    def test_an_unresolved_redirect_is_kept_instead_of_dropped(self):
        """重定向的目标查不到（这一批查询失败）时保留原条目，不能凭空删。"""
        status = {"旧名": {"redirect": True}}
        self.assertEqual(["旧名"], merge_songs(["旧名"], [], status, {}))

    def test_a_misdetected_disambiguation_page_stays_when_it_is_a_real_article(self):
        """回归：`涅槃(HotaRu)` 只是用了 `{{About}}`，不是消歧义页。

        条目本身带括号消歧后缀，所以按页面上的写法显示成 `涅槃(HotaRu){{!}}涅槃`。
        """
        status = {"涅槃(HotaRu)": {"disambig": False, "redirect": False}}
        self.assertEqual(["涅槃(HotaRu){{!}}涅槃"],
                         merge_songs([], ["涅槃(HotaRu)"], status, {},
                                     {"涅槃(HotaRu)": "2026-09-28T21:36:11Z"}))

    def test_a_readded_song_goes_back_to_its_creation_position(self):
        """补回来的旧条目按创建时间插回原位，而不是排到最末尾。"""
        existing = ["早1", "早2", "晚1", "晚2"]
        created_at = {"早1": "2026-09-01T00:00:00Z", "早2": "2026-09-10T00:00:00Z",
                      "旧条目": "2026-09-20T00:00:00Z",
                      "晚1": "2026-10-01T00:00:00Z", "晚2": "2026-10-02T00:00:00Z"}
        status = {title: {} for title in created_at}
        self.assertEqual(["早1", "早2", "旧条目", "晚1", "晚2"],
                         merge_songs(existing, ["旧条目"], status, {}, created_at))

    def test_a_brand_new_song_is_appended(self):
        created_at = {"甲": "2026-09-01T00:00:00Z", "乙": "2026-10-01T00:00:00Z"}
        status = {title: {} for title in created_at}
        self.assertEqual(["甲", "乙"],
                         merge_songs(["甲"], ["乙"], status, {}, created_at))

    def test_without_timestamps_new_entries_are_appended(self):
        status = {"丙": {}}
        self.assertEqual(["甲", "丙"], merge_songs(["甲"], ["丙"], status, {}))

    def test_redirect_duplicate_is_dropped(self):
        """重定向的目标已经在清单里时，不再重复列一次。"""
        status = {"旧名": {"redirect": True}, "正名": {}}
        self.assertEqual(["正名"], merge_songs(["正名", "旧名"], [], status,
                                               {"旧名": "正名"}))


class MergeTemplatesTest(TestCase):
    def test_subpages_are_never_listed(self):
        """用户 2026-10-17 要求：不要出现 Template:重音Teto/2026 这种子模板。"""
        status = {"Template:重音Teto": {}, "Template:IA": {}}
        self.assertEqual(["重音Teto", "IA"],
                         merge_templates(["重音Teto", "重音Teto/2026"],
                                         ["IA/2025", "IA/2026"], status))

    def test_missing_and_redirect_templates_are_dropped(self):
        status = {"Template:甲": {"missing": True}, "Template:乙": {"redirect": True},
                  "Template:丙": {}}
        self.assertEqual(["丙"], merge_templates(["甲", "乙", "丙"], [], status))

    def test_no_duplicates(self):
        status = {"Template:甲": {}}
        self.assertEqual(["甲"], merge_templates(["甲"], ["甲", "甲"], status))


class TemplateCreationsTest(TestCase):
    ROWS = [
        {"ns": 10, "title": "Template:IA/2026", "comment": "由 Vocawiki条目辅助工具 创建：歌姬模板"},
        {"ns": 10, "title": "Template:IA/2025", "comment": "由 Vocawiki条目辅助工具 创建：歌姬模板"},
        {"ns": 10, "title": "Template:IA", "comment": "由 Vocawiki条目辅助工具 创建：歌姬模板"},
        {"ns": 10, "title": "Template:Noy", "comment": "由 Vocawiki条目辅助工具 创建：P主模板"},
        {"ns": 0, "title": "某歌", "comment": "由 Vocawiki条目辅助工具 创建"},
    ]

    def test_takes_the_base_template_only(self):
        self.assertEqual(["IA"], template_creations(self.ROWS, "歌姬模板"))

    def test_ignores_other_kinds(self):
        self.assertEqual(["Noy"], template_creations(self.ROWS, "P主模板"))


class RenderTest(TestCase):
    def test_groups_of_ten(self):
        entries = [f"歌{i}" for i in range(1, 12)]
        lines = render_song_group(entries).splitlines()
        self.assertEqual("{{Navbox subgroup", lines[0])
        self.assertIn("|group1 = 1-10", lines[1])
        self.assertIn("{{links|n=4|" + "|".join(entries[:10]) + "}}", lines[2])
        self.assertIn("|group2 = 11-11", lines[3])
        self.assertIn("{{links|n=4|歌11}}", lines[4])
        self.assertEqual("     }}", lines[5])

    def test_template_group(self):
        self.assertEqual("{{tl|甲}}{{w}}{{tl|乙}}", render_template_group(["甲", "乙"]))


class RebuildTest(TestCase):
    def test_replaces_both_groups_and_keeps_the_rest(self):
        songs = [f"新{i}" for i in range(1, 13)]
        text = rebuild(PAGE, songs, ["甲姬", "乙姬", "丙姬"])
        self.assertIn("|group1 = 1-10", text)
        self.assertIn("|group2 = 11-12", text)
        self.assertIn("{{links|n=4|" + "|".join(songs[:10]) + "}}", text)
        self.assertEqual("{{tl|甲姬}}{{w}}{{tl|乙姬}}{{w}}{{tl|丙姬}}",
                         text[navbox.list_span(text, "歌姬模板", True)[0]:
                              navbox.list_span(text, "歌姬模板", True)[1]])
        self.assertIn("|group1 = 萌百时期", text, "萌百时期整组保持原样")
        self.assertIn("{{links|n=4|传说曲}}", text)
        self.assertIn("|below = 说明", text)
        self.assertTrue(text.endswith("}}\n"))

    def test_result_is_stable(self):
        """同样的输入再跑一次不会改动页面（不然机器人会自己跟自己打架）。"""
        songs = ["甲", "乙"]
        once = rebuild(PAGE, songs, ["甲姬"])
        twice = rebuild(once, songs, ["甲姬"])
        self.assertEqual(once, twice)


class FakeSite:
    def __init__(self, responses=None, logged=True):
        self.responses = responses or {}
        self.logged = logged
        self.logins = 0

    def logged_in(self):
        return self.logged

    def login(self):
        self.logins += 1

    def simple_request(self, **kwargs):
        return FakeRequest(self.responses, kwargs)


class FakeRequest:
    def __init__(self, responses, params):
        self.responses = responses
        self.params = params

    def submit(self):
        if self.params.get("list") == "usercontribs":
            return {"query": {"usercontribs": self.responses.get("contribs", [])}}
        if self.params.get("redirects") == "1":
            return {"query": {"redirects": self.responses.get("redirects", []),
                              "pages": []}}
        status = self.responses.get("status", {})
        titles = self.params.get("titles", "").split("|")
        pages = []
        for title in titles:
            info = dict(status.get(title, {}))
            page = {"title": title}
            if info.get("missing"):
                page["missing"] = True
            if info.get("redirect"):
                page["redirect"] = True
            if info.get("disambig"):
                page["categories"] = [{"title": "Category:消歧义页面"}]
            if info.get("templates"):
                page["templates"] = [{"title": name} for name in info["templates"]]
            pages.append(page)
        return {"query": {"pages": pages}}


class FakePage:
    def __init__(self, text):
        self.text = text
        self.saved = []

    def save(self, **kwargs):
        self.saved.append((self.text, kwargs))


class RunOnceTest(TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        patcher = patch.object(navbox, "PAGE_TITLE", "User:测试/贡献")
        patcher.start()
        self.addCleanup(patcher.stop)

    def _run(self, text, write, responses):
        page = FakePage(text)
        site = FakeSite(responses)
        with patch.object(navbox, "Page", lambda site, title: page):
            changed = navbox.run_once(site, write=write)
        return changed, page

    def test_dry_run_reports_without_saving(self):
        changed, page = self._run(PAGE, False, {"contribs": []})
        self.assertFalse(changed)
        self.assertEqual([], page.saved)

    def test_new_song_is_added_and_saved(self):
        responses = {"contribs": [
            {"ns": 0, "title": "新歌", "comment": "由 Vocawiki条目辅助工具 创建"},
            {"ns": 0, "title": "某消歧义", "comment": "由 Vocawiki条目辅助工具 创建：同名条目消歧义"},
            {"ns": 10, "title": "Template:丙姬/2026", "comment": "由 Vocawiki条目辅助工具 创建：歌姬模板"},
        ], "status": {"丙姬": {}}, "redirects": []}
        changed, page = self._run(PAGE, True, responses)
        self.assertTrue(changed)
        text = page.saved[0][0]
        self.assertIn("新歌", text)
        self.assertNotIn("某消歧义", text)
        self.assertIn("{{tl|甲姬}}{{w}}{{tl|乙姬}}{{w}}{{tl|丙姬}}", text)
