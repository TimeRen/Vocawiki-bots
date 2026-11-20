"""动员令计分的公共小工具：站点、分数线、有效字节数。

被 `presets` / `update_scoreboard` / `mobilization_tally` 共用；不联网、不写页面。
"""
from __future__ import annotations

from datetime import timedelta, timezone
from typing import List, Optional, Sequence

import wikitextparser as wtp
from pywikibot import Site

from utils.utils import find_templates

# 活动时间一律按东八区墙钟（与站点上「2026-12-01 00:00 ~ 2027-02-15 23:59」一致）
CST = timezone(timedelta(hours=8))

# 有效字节数里要打折的模板（见 `count_bytes`）：
#   * Producer_Song / Album Infobox / Tracklist 是机械填表，只算 1/4；
#   * playlist 里的歌曲 / 专辑列表同理，只算一半。
QUARTER_TEMPLATES = ("Producer_Song", "Album Infobox", "Tracklist")
HALF_TEMPLATES = ("playlist",)

_site: Optional[Site] = None


def get_site() -> Site:
    return _site


def set_site(value: Site) -> None:
    global _site
    _site = value


def username_to_section_title(username: str) -> str:
    """计分板里用户的二级节标题：`-{[[U:人间百态|人间百态]]}-`。

    `-{ }-` 是给语言转换器看的：不加的话繁体界面会把用户名也转掉。
    """
    return "-{[[U:" + username + "|" + username + "]]}-"


def adjust(num: float) -> float:
    """分数一律保留两位小数（规则页写的是「保留两位小数」）。"""
    return round(float(num), 2)


def format_points(num: float) -> str:
    """计分板里写的分数：`1.50` / `0.20`（统一两位小数，评委核对时一眼看出精度）。"""
    return f"{adjust(num):.2f}"


def count_bytes_simple(text: str) -> int:
    """原始字节数（UTF-8）。"""
    return len((text or "").encode("utf-8"))


def count_bytes(text: str) -> int:
    """**有效字节数**：原始字节 − 3/4 的机械模板 − 1/2 的 playlist 列表。

    规则页（`/计分规则` 的「有效字节数（暂定）的解释」）要求的「日语原文等复制粘贴的内容不计」
    「没有可查证来源的内容不计」机器人判不了，留给评委；这里只做能自动判定的两项：
    `Producer_Song` / `Album Infobox` / `Tracklist` 是机械填表（沿用上游的 3/4 折扣），
    `{{playlist}}` 里的歌曲 / 专辑列表按一半算。
    """
    total = count_bytes_simple(text)
    parsed = wtp.parse(text or "")
    quarter = 0
    for name in QUARTER_TEMPLATES:
        for found in find_templates(parsed.templates, name):
            quarter += count_bytes_simple(str(found))
    half = 0
    for found in find_templates(parsed.templates, *HALF_TEMPLATES, loose=True):
        half += count_bytes_simple(str(found))
    return max(0, round(total - quarter * 3 / 4 - half / 2))


def link_titles(text: str) -> List[str]:
    """一段 wikitext 里的内部链接目标（去重、保序）。"""
    seen = set()
    result = []
    for link in wtp.parse(text or "").wikilinks:
        title = (link.title or "").strip()
        if title and title not in seen:
            seen.add(title)
            result.append(title)
    return result


def category_names(page) -> set:
    """页面所属分类（不带 `Category:` 前缀）。"""
    return {c.title(with_ns=False) for c in page.categories()}


def byte_difference(current: str, previous: str) -> int:
    """有效字节增量（可能为负，调用方自己截断到 0）。"""
    return count_bytes(current) - count_bytes(previous)


def join_lines(lines: Sequence[str]) -> str:
    return "\n".join(lines)
