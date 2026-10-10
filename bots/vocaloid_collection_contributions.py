# -*- coding: utf-8 -*-
"""Automatically maintains [[Vocawiki:贡献列表/The VOCALOID Collection]].

The page consists of two independently maintained parts:

* ``创建列表``  - per-season ranking tables.  A song entry counts as
  "created" when its cell carries a ``bgcolor``/gradient (the creator's
  colour) or its page already exists.  The header of every section shows
  ``(已创建/总数)``.

* ``相关统计`` - an ``{{Echart}}`` matrix of "how many entries each user
  created in each season".

The bot can:

* ``entries`` - 按赛季榜单模板（``Template:The VOCALOID Collection2023夏`` 这类
  Navbox）补正贡献列表：模板按名次列出参赛作品，机器人据此把每个名次格子的
  链接统一改写成规范标题（死链修复、重定向写法归一），新公布的排名不需要人工誊抄；
  模板里还没有对应页面的标题只报告，不动页面。模板标题对应的页面若不属于
  **本赛季**（同名不同曲：2022秋 第 81 名的模板标题 ``スワンプマン`` 其实是
  2026夏 的 ``SWAMPMAN`` 的重定向）也不动，免得把另一首歌的名字安到这一季的
  格子上、甚至抹掉人工改过的链接。
* ``counts``  - recompute every section header ``(已创建/总数)``.
* ``colour``  - colour uncoloured cells whose page exists, using the creator's
  colour from the legend.  A link whose target does not exist is matched
  against the real page first (e.g. ``[[FrailLaVillanos]]`` for the existing
  ``FrailL'aVillanos``), and a link that points at a redirect is rewritten to
  its target (``[[毒deンぱ]]`` -> ``[[毒电波]]``); both are corrected while
  colouring.  A page that is not a participant of that season is left alone:
  the same name is a different song, and colouring it would credit its
  creator (and its season) here.
* ``stats``   - recompute the Echart from creation records (``--basis``).
  The season's authoritative song list is the ranking template, but only
  *original* songs count: the REMIX track and neta's non-original entries
  (「其他部门」 and 二创 written as ``原曲/创作者``) are left out, see
  ``is_counted_track``.  A page that merely carries the season's navbox (the
  overview article) does not count either.  Rows are ordered by their total, so
  the chart reads 多→少 from top to bottom.  A cell's colour is the hand-made
  creator annotation and wins outright; other entries use the creator of the
  local page. Some chart numbers come from bookkeeping outside the wiki and
  cannot be derived at all, so a cell is normally only raised, never lowered.
  Two exceptions subtract from a cell: the REMIX/二创 songs, and the credits
  earlier runs gave to the author of an *imported* revision (that author is the
  source article's last editor, see ``page_creator``).  Moving those credits to
  the real creator's cell is a one-off migration - ``recredit`` - because
  re-applying the delta every hour would keep growing the number.
* ``report``  - list anomalies (coloured but page missing / page exists but
  not coloured).
* ``moe``     - 与萌娘百科交叉比对创建者，**只出报告、不改页面**。贡献列表记的是
  「萌娘百科及 Vocawiki 上」的创建：页面上标着的创建者（格子颜色/图例）与本机
  页面的首版作者可能不是同一个人。三类条目会去萌娘百科查同名条目的最旧一版作者
  辅助判断：本机还没有页面（红链）的参赛曲、标注与本机首版作者不符的条目、
  以及本机首版作者是机器人/导入账号的条目。走的是镜像站 ``moegirl.icu``（官方
  ``zh.moegirl.org.cn`` 对匿名调用回 ``action-notallowed``，拿不到版本），
  镜像的最旧一版同样可能是导入/搬运留下的作者，所以这份报告只供人工判断，
  机器人不据此上色或计数。
* ``recredit`` - 一次性迁移（必须给 ``--from-rev <版本号>``）：把早期按「导入版
  作者」记进图表的那些数字减掉，并加到源站真正的创建者那一格。图表本身只把数字
  往上抬，所以这件事不能每轮都做——必须以某个基准版为参照跑一次，否则每跑一轮
  都会再加一遍。之后每小时的任务会照旧把结果保持住。
* ``all``      - run all maintenance actions once. Toolforge and GitHub Actions
  schedule this full pass hourly; it does not poll ``list=recentchanges``, whose
  results can omit entries that have not yet appeared in the maintained list.

The page is maintained hourly by Toolforge and GitHub Actions, at staggered
minutes. Each run is a full pass, so new or previously unlisted entries are not
dependent on recent-changes polling.

Everything runs in dry-run mode unless ``--write`` is given.

Note on ``--basis window``: it counts pages *created on voca.wiki* inside the
season's calendar window.  voca.wiki imported most pre-2024 entries, so their
first revision timestamps are recent; window counting therefore only produces
meaningful output for seasons that are still running.  ``--basis listed``
(the default) instead resolves the creator of every entry listed in a season's
tables from its local first revision, which works for every season.

How a creator is resolved (``colour``, ``counts`` and ``stats`` all share it,
see ``page_creator``): the author of the page's *oldest* revision.  An imported
revision is the exception - voca.wiki copied most pre-2024 entries from
Moegirlpedia, and such a revision carries the **source article's last editor**
(``zhmoe>某用户``), not its creator.  For those entries the creator comes from
the source article's own oldest revision instead, and when that cannot be
resolved the entry is credited to nobody rather than to whoever imported it.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import time
import urllib.request
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Optional, Set, Tuple
from urllib.parse import unquote, urlencode

import pywikibot
from pywikibot import Page
from pywikibot.exceptions import EditConflictError, NoPageError

PAGE_TITLE = "Vocawiki:贡献列表/The VOCALOID Collection"
DATA_DIR = Path("data")
CREATOR_CACHE = DATA_DIR / "vocaloid_collection_creators.pickle"
MOEGIRL_CACHE = DATA_DIR / "vocaloid_collection_moegirl.pickle"
CHART_SERIES_PREFIX = "ボカコレ"

# 萌娘百科（voca.wiki 的条目大多从那边来，创建者对不上时拿它当参照）。它不在
# pywikibot 的 family 里，直接走 HTTP API（stdlib，不引新依赖）。
#
# 用镜像站而不是 zh.moegirl.org.cn：官方站对匿名调用回
# ``action-notallowed / Unauthorized API call``，prop=revisions、action=parse、
# list=search 全都不给，拿不到最旧一版的作者。moegirl.icu 是整站镜像（pageid 与
# 官方一致，历史也全），user-config.py 里本来就有它的 family。
#
# 这里查的是「条目的创建者」：跨站导入的页面（``zhmoe>某人``）首版挂的是源站
# 最后一版的作者，只有源站自己的最旧一版才是创建者（见 ``page_creator``）。
MOEGIRL_API = "https://moegirl.icu/api.php"
# 请求头必须是 ASCII：中文会让 urllib 直接抛 UnicodeEncodeError
MOEGIRL_UA = ("Vocawiki-bots/1.0 (maintains voca.wiki contribution list; "
              "https://github.com/TimeRen/Vocawiki-bots)")
MOEGIRL_TIMEOUT = 30
MOEGIRL_DELAY = 0.2  # 两次请求之间的间隔：别把对方 API 打疼
MOEGIRL_CACHE_TTL = 7 * 24 * 3600  # 「萌娘没有这条」过一阵要重新确认

# Bots / import accounts must not appear in the statistics.
KNOWN_BOTS = {
    "AnnAngela-abot", "AnnAngela-bbot", "AnnAngela-bot", "AnnAngela-cbot", "AnnAngela-dbot",
    "Bhsd-bot", "C8H17OH-bot", "Delete page script", "Dm bot", "Eizenchan", "Funce", "LihaohongBot",
    "Senyu-bot", "SinonJZH-bot", "Swampland Robot", "UNC HA Bot", "XzonnBot", "星海-adminbot",
    "星海-interfacebot", "星海-oversightbot", "机娘史蒂文", "机娘史蒂夫", "机娘星海酱", "机娘鬼影233号",
    "滥用过滤器", "萌百娘", "重定向修复器",
}

# 挂着赛季导航模板、本身却不是参赛曲目的页面。总条目 The VOCALOID Collection
# 把 12 个赛季的模板全挂上了，``list=embeddedin`` 于是认为它是每一季的参赛曲目，
# 创建这个总条目的用户会凭空拿到 12 份贡献（2026-10-10 那次编辑就是被它搞坏的）。
# 它是一篇条目，不是歌，所以要从「参赛曲目」里排掉。
NON_SONG_PAGES = {"The VOCALOID Collection"}

# Explicit ranking sections; the chart also adds every season-template participant.
def is_counted_section(name: str) -> bool:
    upper = name.upper()
    return upper.startswith("TOP") or upper.startswith("ROOKIE")


# 「其他歌曲」下的分组名：只有「未上榜歌曲」是本季的原创曲，其他分组（其他部门
# 之类，歌ってみた/演奏等）属于二创，不算创建条目的贡献。
ORIGINAL_GROUPS = {"未上榜歌曲"}


def is_counted_track(section_key: str, title: str) -> bool:
    """这条曲目算不算创建贡献：REMIX 赛道与二创（neta 非原创曲）都不算。

    ``section_key`` 是 ``parse_season_template`` 的键，形如 ``REMIX`` /
    ``neta`` / ``neta:未上榜歌曲``（无区间分组会带上分组名）。
    """
    name, _, label = section_key.partition(":")
    if name == "REMIX":
        return False
    if name == "neta":
        if label and label not in ORIGINAL_GROUPS:
            return False
        if "/" in title:
            return False  # 二创写法「原曲/创作者」
    return True


HEX = r"#[0-9A-Fa-f]{3,8}"
TITLE_RE = re.compile(r"\{\{colorlink\|[^|]*\|([^|}]+?)\|[^}]*\}\}|\{\{colorlink\|[^|]*\|([^|}]+?)\}\}|\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
BG_RE = re.compile(r"bgcolor\s*=\s*(%s)|background:\s*linear-gradient\(([^)]*)\)" % HEX)
HEADER_RE = re.compile(r";\s*([A-Za-z0-9]+)\s*\((.*?)/([^)]*)\)")
SEASON_RE = re.compile(r"^===\s*(\d{4}[冬春夏秋])\s*===\s*$", re.M)
CHART_RE = re.compile(r"(\{\{Echart\|data=<nowiki>)(.*?)(</nowiki>)", re.S)

# 页面上没有旧块可参照时（第一次加赛季）用的模板，照抄页面现有的手写风格
FALLBACK_SERIES = (
    '{"name": "%(name)s","type": "bar","stack":"total","itemStyle":{"color":"%(colour)s"},'
    '"label": {"formatter": " {c} ","distance":0,"backgroundColor": "white","fontWeight": "bold",'
    '"borderColor": "auto","borderWidth": 1.2,"borderRadius": 10,"lineHeight": 16,'
    '"padding": [1,0,0,0]},"emphasis":{"label": {"show": true}},"data": [%(data)s]}'
)

# 每个赛季的榜单模板，如 Template:The VOCALOID Collection2023夏
SEASON_TEMPLATE = "Template:The VOCALOID Collection"
# 模板里 Navbox 子表的标题 -> 贡献列表里的小节名
TEMPLATE_SECTIONS = {"TOP100": "TOP100", "TOP30": "TOP30", "ROOKIE": "ROOKIE",
                     "REMIX": "REMIX", "其他歌曲": "neta"}
TEMPLATE_ITEM_RE = re.compile(r"\|\s*([A-Za-z0-9_]+)\s*=\s*")
GROUP_RANGE_RE = re.compile(r"(\d+)\s*[-–~〜ー]\s*(\d+)\s*位")
LIST_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
# Navbox 尾巴上的 [[Category:...]]（常在 <noinclude> 里）会落在最后一个 list 参数
# 的值里，被当成一首歌收下来，最后给创建那个分类页的人记一份贡献。
NON_ARTICLE_RE = re.compile(
    r"^(?:Category|File|Image|Template|User|User talk|Help|Module|Widget|"
    r"MediaWiki|Talk|Special|Portal|Draft)\s*:", re.I)


def is_article_title(title: str) -> bool:
    """链接目标是不是条目：模板里夹着的 [[Category:...]] 这类不算。"""
    return not NON_ARTICLE_RE.match(title.strip())
# 贡献列表里的名次单元格：{{colorlink|#色|标题|名次}} 或 [[标题|名次]]
CELL_RANK_RE = re.compile(r"\{\{colorlink\|([^|]*)\|([^|}]+)\|(\d+)\}\}|\[\[([^\]|]+)\|(\d+)\]\]")


def normalise_colour(colour: str) -> str:
    """Uppercase and expand shorthand hex so #000 matches the legend's #000000."""
    colour = colour.upper()
    if len(colour) == 4:
        return "#" + "".join(c * 2 for c in colour[1:])
    return colour


APOSTROPHE_RE = re.compile(r"['’‘`´ʼ]")
TITLE_INDEX = DATA_DIR / "vocaloid_collection_titles.pickle"
TITLE_INDEX_TTL = 12 * 3600  # seconds between full title sweeps
TITLE_INDEX_MAX = 30000  # safety cap on the sweep


def title_key(title: str) -> str:
    """Match key for song titles: ignore apostrophe style and %-escapes.

    Case is kept (MediaWiki only ignores the case of the first letter), so a
    link is never rewritten to a page that differs by more than punctuation.
    """
    decoded = APOSTROPHE_RE.sub("", unquote(title)).replace("_", " ").strip()
    return decoded[:1].upper() + decoded[1:]


@dataclass
class Entry:
    title: str
    colours: List[str]  # empty -> not created


@dataclass
class Section:
    season: str
    name: str
    entries: List[Entry] = field(default_factory=list)


@dataclass
class Legend:
    colour_to_name: Dict[str, str] = field(default_factory=dict)
    name_to_colour: Dict[str, str] = field(default_factory=dict)
    alias_to_name: Dict[str, str] = field(default_factory=dict)

    def identity(self, user: str) -> str:
        """Collapse a revision username to a stable key (its colour when known)."""
        name = self.alias_to_name.get(user.lower(), user)
        return self.name_to_colour.get(name, name)

    def display(self, identity: str) -> str:
        return self.colour_to_name.get(identity, identity)

    def _add_aliases(self, name: str, segment: str) -> None:
        m = re.search(r"<!--(.*?)-->", segment, re.S)
        if not m:
            return
        for alias in re.split(r"[、,，/]", m.group(1)):
            alias = alias.strip()
            if alias:
                self.alias_to_name.setdefault(alias.lower(), name)

    @classmethod
    def parse(cls, text: str) -> "Legend":
        legend = cls()
        pattern = re.compile(
            r"color block/wl\|(#\w+)\}\}\s*"
            r"(?:\{\{User\|([^}|]+)\}\}|'''\[\[(?:zhmoe):User:([^|\]]+)\|([^\]]+)\]\]''')")
        for m in pattern.finditer(text):
            colour = normalise_colour(m.group(1))
            name = (m.group(2) or m.group(4)).strip()
            legend.colour_to_name.setdefault(colour, name)
            legend.name_to_colour.setdefault(name, colour)
            legend.alias_to_name[name.lower()] = name
            line_end = text.find("\n", m.end())
            legend._add_aliases(name, text[m.end():line_end if line_end != -1 else len(text)])
        # 榜外 creators carry no colour but still have aliases worth canonicalising
        for line in text.splitlines():
            if "榜外歌曲条目创建者" not in line:
                continue
            for um in re.finditer(r"\{\{User\|([^}|]+)\}\}|\[\[(?:zhmoe):(?:User:)?([^|\]]+)\|([^\]]+)\]\]", line):
                name = (um.group(1) or um.group(3)).strip()
                legend.alias_to_name.setdefault(name.lower(), name)
                legend._add_aliases(name, line[um.end():])
        return legend


def parse_sections(text: str) -> List[Section]:
    seasons = [(m.start(), m.group(1)) for m in SEASON_RE.finditer(text)]
    sections: List[Section] = []
    for i, (pos, season) in enumerate(seasons):
        end = seasons[i + 1][0] if i + 1 < len(seasons) else len(text)
        region = text[pos:end]
        marks = [(m.start(), m.group(1)) for m in HEADER_RE.finditer(region)]
        for j, (bpos, name) in enumerate(marks):
            bend = marks[j + 1][0] if j + 1 < len(marks) else len(region)
            section = Section(season, name)
            for table in re.findall(r"\{\|.*?\|\}", region[bpos:bend], re.S):
                for row in re.split(r"\n\|-+", table):
                    for cell in row.split("||"):
                        tm = TITLE_RE.search(cell)
                        if not tm:
                            continue
                        title = unquote((tm.group(1) or tm.group(2) or tm.group(3)).strip())
                        colours: List[str] = []
                        for bm in BG_RE.finditer(cell):
                            if bm.group(1):
                                colours.append(normalise_colour(bm.group(1)))
                            else:
                                colours.extend(normalise_colour(c) for c in re.findall(HEX, bm.group(2)))
                        section.entries.append(Entry(title, colours))
            sections.append(section)
    return sections


# --------------------------------------------------------------------------- #
# 赛季榜单模板（新条目与名次的来源）
# --------------------------------------------------------------------------- #
def parse_season_template(text: str) -> Dict[str, Dict[int, str]]:
    """赛季 Navbox -> ``{小节: {名次: 页面标题}}``。

    模板按名次顺序列出每个小节（TOP100 / ROOKIE / REMIX / 其他歌曲），
    并用 ``1-10位`` 之类的分组标出区间，所以链接在分组里的位置就是名次。
    「其他歌曲」下的分组（``其他部门``、``未上榜歌曲``）没有名次区间，
    只为「哪些歌属于这一季」而收下来，名次用负数占位，不会和真名次撞车；
    这类分会带上分组名（``neta:未上榜歌曲``），统计时才能把原创和二创分开
    （见 ``is_counted_track``）。
    """
    marks = [(m.start(), m.end(), m.group(1)) for m in TEMPLATE_ITEM_RE.finditer(text)]
    result: Dict[str, Dict[int, str]] = defaultdict(dict)
    section: Optional[str] = None
    starts: Dict[str, Optional[Tuple[int, int]]] = {}
    labels: Dict[str, str] = {}
    for i, (_, end, key) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        value = text[end:stop]
        if key == "title":
            section = TEMPLATE_SECTIONS.get(value.strip())
            starts = {}
            labels = {}
            continue
        if not section:
            continue
        group = re.fullmatch(r"group(\d+)", key)
        if group:
            rng = GROUP_RANGE_RE.search(value)
            starts[group.group(1)] = ((int(rng.group(1)), int(rng.group(2)))
                                      if rng else None)
            labels[group.group(1)] = value.strip()
            continue
        listing = re.fullmatch(r"list(\d+)", key)
        if listing and listing.group(1) in starts:
            links = [title.strip() for title in LIST_LINK_RE.findall(value)
                     if title.strip() and is_article_title(title)]
            if starts[listing.group(1)] is None:
                label = labels.get(listing.group(1), "")
                key_name = f"{section}:{label}" if label else section
                for title in links:
                    result[key_name][-(len(result[key_name]) + 1)] = title
                continue
            start, end = starts[listing.group(1)]
            span = end - start + 1
            if len(links) > span:
                # 分组标着 81-90位 却塞了 11 项（2024冬 ROOKIE 就多挂了一个 column），
                # 多的会顶掉下一组的名次，只能丢掉并提醒。
                pywikibot.warning(f"{section} {start}-{end}位 有 {len(links)} 项，"
                                  f"多出的 {'、'.join(links[span:])} 已忽略")
            for offset, title in enumerate(links[:span]):
                result[section].setdefault(start + offset, title)
    return {name: dict(ranks) for name, ranks in result.items()}


def season_templates(site, seasons: Iterable[str]) -> Dict[str, Dict[str, Dict[int, str]]]:
    """Fetch every season's ranking template: ``{赛季: {小节: {名次: 标题}}}``."""
    wanted: Dict[str, Dict[str, Dict[int, str]]] = {}
    for season in seasons:
        title = f"{SEASON_TEMPLATE}{season}"
        try:
            text = Page(site, title).text
        except NoPageError:
            continue
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"{title}: {exc}")
            continue
        parsed = parse_season_template(text)
        if parsed:
            wanted[season] = parsed
        else:
            pywikibot.error(f"{title}: 没解析出任何小节，模板结构可能变了")
    return wanted


def template_participants(site, season: str) -> Optional[List[str]]:
    """Pages that transclude the season's template (i.e. 参加该赛季的歌曲）。

    挂着模板但不是歌曲的页面（见 ``NON_SONG_PAGES``）不算参赛曲目：总条目挂着
    全部赛季的模板，不排掉它就会给每一季都多算一份贡献。

    查询失败返回 ``None``：调用方不能把「没查到」当成「没有」。
    """
    titles: List[str] = []
    params = {}
    try:
        while True:
            data = site.simple_request(
                action="query", list="embeddedin", formatversion="2",
                eititle=f"{SEASON_TEMPLATE}{season}", einamespace=0,
                eilimit="max", **params).submit()
            titles.extend(entry["title"]
                          for entry in data.get("query", {}).get("embeddedin", [])
                          if entry["title"] not in NON_SONG_PAGES)
            continuation = data.get("continue")
            if not continuation:
                return titles
            params = continuation
    except Exception as exc:  # noqa: BLE001
        pywikibot.error(f"{season}: 无法读取模板引用 ({exc})")
        return None


def belongs_to_season(season: str, target: str,
                      participants_of: Callable[[str], Optional[set]]) -> bool:
    """``target`` 能不能算作 ``season`` 的参赛曲目（页面挂了该赛季的 Navbox）。

    同名不同曲会骗过机器人：2022秋 榜单第 81 名的模板标题写作 ``スワンプマン``，
    而它只是 2026夏 的 ``SWAMPMAN`` 的重定向，重定向页面本身又是 Kim8394 建的。
    照它改写链接或上色，就会把 2026夏 那首歌连同 Kim8394 一起算进 2022秋。
    所以只认挂着**本赛季**模板的页面。
    名单查不到（``None``）时不据此下结论，放行。
    """
    members = participants_of(season)
    return True if members is None else target in members


def entry_diffs(text: str, wanted: Dict[str, Dict[str, Dict[int, str]]]
                ) -> List[Tuple[str, str, int, str, str]]:
    """列出名次格子与赛季模板不一致的地方：(赛季, 小节, 名次, 页面标题, 模板标题)。"""
    diffs: List[Tuple[str, str, int, str, str]] = []
    seasons = list(SEASON_RE.finditer(text))
    for i, season_match in enumerate(seasons):
        end = seasons[i + 1].start() if i + 1 < len(seasons) else len(text)
        season = season_match.group(1)
        wanted_sections = wanted.get(season, {})
        region = text[season_match.end():end]
        headers = list(HEADER_RE.finditer(region))
        for j, header in enumerate(headers):
            stop = headers[j + 1].start() if j + 1 < len(headers) else len(region)
            ranks = wanted_sections.get(header.group(1))
            if not ranks:
                continue
            for cell in CELL_RANK_RE.finditer(region[header.start():stop]):
                if cell.group(3) is not None:
                    rank, current = int(cell.group(3)), cell.group(2)
                else:
                    rank, current = int(cell.group(5)), cell.group(4)
                want = ranks.get(rank)
                if want and want != current:
                    diffs.append((season, header.group(1), rank, current, want))
    return diffs


def sync_entries(text: str, replacements: Dict[Tuple[str, str, int], str]
                 ) -> Tuple[str, int, List[str]]:
    """按 ``{(赛季, 小节, 名次): 标题}`` 改写名次格子（保留原有颜色包装）。"""
    if not replacements:
        return text, 0, []
    changed = 0
    notes: List[str] = []
    seasons = list(SEASON_RE.finditer(text))
    pieces = [text[:seasons[0].start()]] if seasons else [text]
    for i, season_match in enumerate(seasons):
        end = seasons[i + 1].start() if i + 1 < len(seasons) else len(text)
        season = season_match.group(1)
        region = text[season_match.end():end]
        headers = list(HEADER_RE.finditer(region))
        parts = [season_match.group(0)]
        if headers:
            parts.append(region[:headers[0].start()])
        else:
            parts.append(region)
        for j, header in enumerate(headers):
            stop = headers[j + 1].start() if j + 1 < len(headers) else len(region)
            name, table = header.group(1), region[header.start():stop]

            def repl(cell: re.Match, name: str = name, season: str = season) -> str:
                nonlocal changed
                if cell.group(3) is not None:  # {{colorlink|#色|标题|名次}}
                    rank, current = int(cell.group(3)), cell.group(2)
                else:
                    rank, current = int(cell.group(5)), cell.group(4)
                want = replacements.get((season, name, rank))
                if not want or want == current:
                    return cell.group(0)
                changed += 1
                notes.append(f"{season}/{name} {rank}: {current} -> {want}")
                if cell.group(3) is not None:
                    return f"{{{{colorlink|{cell.group(1)}|{want}|{rank}}}}}"
                return f"[[{want}|{rank}]]"

            parts.append(CELL_RANK_RE.sub(repl, table))
        pieces.append("".join(parts))
    return "".join(pieces), changed, notes


# --------------------------------------------------------------------------- #
# counts
# --------------------------------------------------------------------------- #
def new_header(match: re.Match, created: int) -> str:
    numerator = match.group(2)
    if "{{color|" in numerator:
        head, _, _ = numerator.rpartition("|")
        numerator = f"{head}|{created}}}}}"
    else:
        numerator = re.sub(r"\d+", str(created), numerator, count=1)
    return f";{match.group(1)} ({numerator}/{match.group(3)})"


def compute_created(site, sections: Iterable[Section], cache: Dict[str, Optional[str]],
                    exists: Dict[str, bool],
                    planned: Optional[set] = None) -> Dict[Tuple[str, str], int]:
    """A song entry counts as created when it is coloured *or* its page exists.

    Both cases occur on the page: a freshly created entry is often still
    uncoloured (the creator's colour is assigned by hand).  ``planned`` holds
    the entries this pass is about to colour, so a song whose link had to be
    corrected is already counted in the same edit.
    """
    planned = planned or set()
    sections = list(sections)
    batch_exists(site, (e.title for s in sections for e in s.entries
                        if not e.colours and e.title not in planned), exists)
    result: Dict[Tuple[str, str], int] = {}
    for section in sections:
        if not section.entries:
            continue
        created = sum(1 for e in section.entries
                      if e.colours or e.title in planned
                      or page_exists(site, e.title, exists))
        result[(section.season, section.name)] = created
    return result


def recompute_counts(text: str, created: Dict[Tuple[str, str], int]) -> Tuple[str, int]:
    changed = 0
    matches = list(SEASON_RE.finditer(text))
    if not matches:
        return text, 0
    pieces = [text[:matches[0].start()]]
    for i, m in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        season = m.group(1)

        def repl(header: re.Match, season: str = season) -> str:
            nonlocal changed
            value = created.get((season, header.group(1)))
            if value is None:
                return header.group(0)
            result = new_header(header, value)
            if result != header.group(0):
                changed += 1
            return result

        pieces.append(HEADER_RE.sub(repl, text[m.start():end]))
    return "".join(pieces), changed


# --------------------------------------------------------------------------- #
# stats
# --------------------------------------------------------------------------- #
# voca 把跨站导入的版本挂在「源站前缀>用户名」名下（``zhmoe>某人``）。那一版连作者和
# 时间都是从源站抄来的，而且抄的通常是源站条目的**最后一版**——拿它当创建者就错了
# （2026-10-10 反馈）。真正的作者要去源站查，见 ``page_creator``。
IMPORT_USER_RE = re.compile(r"^([A-Za-z0-9_-]+)>(.+)$")
IMPORT_SOURCES = {"zhmoe": "萌娘百科"}


def strip_prefix(user: str) -> str:
    """去掉跨站导入前缀，取用户名本身。"""
    match = IMPORT_USER_RE.match(user)
    return match.group(2) if match else user


def import_source(user: str) -> str:
    """``zhmoe>某人`` 的来源是 ``zhmoe``；本站账号返回空串。"""
    match = IMPORT_USER_RE.match(user)
    return match.group(1) if match else ""


def cached_creator(cache: Dict, title: str) -> Optional[Tuple[str, str]]:
    """``(最旧一版的原始用户名, 跨站来源)``；没有缓存返回 ``None``。

    旧缓存里存的是剥掉前缀的用户名，分辨不出来源，只能当作没缓存、重查一次。
    """
    entry = cache.get(title)
    if isinstance(entry, tuple) and len(entry) == 2:
        return entry
    return None


def load_cache(path: Path) -> Dict:
    if path.exists():
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_cache(path: Path, cache: Dict) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)


def batch_creators(site, titles: Iterable[str], cache: Dict,
                   resolved: Optional[Dict[str, str]] = None) -> None:
    """Fill ``cache`` for many titles using oldest-revision queries.

    MediaWiki only permits ``rvdir=newer`` on single-page requests, so the first
    revision creator must be fetched once per title.
    Only real answers are cached, so a song that does not exist yet is retried
    on the next run.
    """
    resolved = resolved or {}
    pending: List[str] = []
    for title in titles:
        target = resolved.get(title, title)
        if target and cached_creator(cache, target) is None and target not in pending:
            pending.append(target)
    for title in pending:
        creator_of(site, title, cache)


def creator_of(site, title: str, cache: Dict) -> Optional[str]:
    """页面最旧一版的用户名，**原始写法**（跨站导入会带上 ``zhmoe>`` 前缀）。

    带前缀的那一版是导入时连源站作者一起抄过来的，不能直接当创建者用，
    调用方请走 ``page_creator``。
    """
    cached = cached_creator(cache, title)
    if cached is not None:
        return cached[0]
    try:
        revisions = list(Page(site, title).revisions(total=1, reverse=True, content=False))
        user = revisions[0]["user"] if revisions else None
    except NoPageError:
        # 不缓存：条目可能马上就要被创建（否则会把"还没建"记成永久结论）
        return None
    except Exception as exc:  # noqa: BLE001
        pywikibot.error(f"{title}: {exc}")
        return None  # do not cache transient failures
    if user:
        cache[title] = (user, import_source(user))
    return user


def batch_exists(site, titles: Iterable[str], exists: Dict[str, bool],
                 resolved: Optional[Dict[str, str]] = None,
                 canonical: Optional[Dict[str, str]] = None) -> None:
    """Fill ``exists`` for many titles using batched ``prop=info`` queries.

    When ``resolved`` is given it also records which titles are redirects and
    what they point at, so the caller can both credit the real page's creator
    and point the link straight at it (the page has dozens of romanised
    redirect titles).

    When ``canonical`` is given it records **every** title's on-site form, so a
    caller can compare two hand-written title lists that spell the same page
    differently (``ダウナ`` / ``Downa``, ``後篇`` / ``后篇``).
    """
    pending = [t for t in dict.fromkeys(titles) if t not in exists]
    for i in range(0, len(pending), 50):
        batch = pending[i:i + 50]
        try:
            data = site.simple_request(action="query", prop="info", redirects=1,
                                       converttitles=1, formatversion=2,
                                       titles="|".join(batch)).submit()
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"批量存在性查询失败: {exc}")
            continue
        query = data.get("query", {})
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        # 繁简/日文汉字归一：模板写「後篇」「黒白」「失態生態実験体」，页面上
        # 叫「后篇」「黑白」「失态生态实验体」，只有这一步能把它们对上。
        converted = {cv["from"]: cv["to"] for cv in query.get("converted", [])}
        redirected = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = query.get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())
        present = {p["title"]: not p.get("missing") for p in pages}
        for title in batch:
            # MediaWiki 也是按 normalize → 变体转换 → redirect 的顺序解析的，
            # 所以认的是转换后的标题（站点区分大小写时 parastraea 才算数）。
            key = normalized.get(title, title)
            variant = converted.get(key, key)
            final = redirected.get(variant, variant)
            exists[title] = present.get(final, False)
            if canonical is not None:
                canonical[title] = final
            if resolved is not None and final != key:
                resolved[title] = final


def page_exists(site, title: str, exists: Dict[str, bool]) -> bool:
    if title not in exists:
        batch_exists(site, [title], exists)
    return exists.get(title, False)


def build_title_index(site) -> Dict[str, str]:
    """``title_key`` -> real page title, for every mainspace page."""
    index: Dict[str, str] = {}
    try:
        for count, page in enumerate(site.allpages(namespace=0)):
            if count >= TITLE_INDEX_MAX:
                pywikibot.error(f"标题索引超过 {TITLE_INDEX_MAX} 条，已截断。")
                break
            index.setdefault(title_key(page.title()), page.title())
    except Exception as exc:  # noqa: BLE001
        pywikibot.error(f"标题索引建立失败: {exc}")
    return index


def title_index(site) -> Dict[str, str]:
    """The title index, rebuilt at most once per ``TITLE_INDEX_TTL``.

    The page links songs by hand, so a typo such as ``[[FrailLaVillanos]]``
    (the page is ``FrailL'aVillanos``) cannot be derived from the page alone.
    One sweep of the wiki's titles makes every such link resolvable - and the
    sweep is cached so each scheduled maintenance run does not repeat the full
    mainspace scan.
    """
    try:
        with open(TITLE_INDEX, "rb") as f:
            blob = pickle.load(f)
        if time.time() - blob.get("built", 0) < TITLE_INDEX_TTL:
            return blob.get("index", {})
    except Exception:  # noqa: BLE001  (no cache yet / unreadable cache)
        pass
    index = build_title_index(site)
    if index:
        try:
            TITLE_INDEX.parent.mkdir(exist_ok=True)
            with open(TITLE_INDEX, "wb") as f:
                pickle.dump({"built": time.time(), "index": index}, f,
                            protocol=pickle.HIGHEST_PROTOCOL)
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"标题索引写入失败: {exc}")
    return index


def season_window(season: str, end_shift_days: int = 0) -> Tuple[datetime, datetime]:
    year, kind = int(season[:4]), season[4]
    if kind == "冬":
        start, end = datetime(year, 12, 1), datetime(year + 1, 2, 28)
    elif kind == "春":
        start, end = datetime(year, 3, 1), datetime(year, 5, 31)
    elif kind == "夏":
        start, end = datetime(year, 6, 1), datetime(year, 8, 31)
    else:
        start, end = datetime(year, 9, 1), datetime(year, 11, 30)
    end += timedelta(days=end_shift_days)
    tz = timezone(timedelta(hours=8))
    return start.replace(tzinfo=tz), end.replace(tzinfo=tz)


def count_by_listed(site, sections: List[Section], legend: Legend,
                    cache: Dict,
                    participants_of: Optional[Callable[[str], Optional[set]]] = None,
                    songs_of: Optional[Callable[[str], Optional[set]]] = None,
                    excluded_of: Optional[Callable[[str], Optional[set]]] = None,
                    excluded: Optional[Dict[str, Counter]] = None,
                    moe_cache: Optional[Dict] = None,
                    corrections: Optional[Dict[str, Counter]] = None,
                    gains: Optional[Dict[str, Counter]] = None
                    ) -> Dict[str, Counter]:
    """Count the ranked cells plus the rest of the season's songs.

    ``songs_of(season)`` is the season's authoritative song list - the ranking
    template's original songs, 榜外「其他歌曲」 included.  Songs it lists that no
    ranked cell covers are credited to whoever created their page.
    ``participants_of`` only guards the ranked cells: a same-name song from
    another season must not be credited here either.

    ``excluded_of(season)`` lists the season's songs that do *not* count
    (REMIX 赛道、neta 的二创): they are tallied separately into ``excluded`` so
    that ``render_chart`` can undo the numbers earlier runs had added for them.

    ``corrections`` and ``gains`` are only for the one-off ``recredit`` migration:
    they collect, per season, the credits earlier runs gave to the author of an
    imported revision (``corrections``) and the same credits under the name that
    should have got them (``gains``).  The hourly pass must not apply them - the
    chart only ever raises a number, so re-applying the delta every run would
    grow it forever.

    A ranked cell's colour is its creator annotation. Redirects and pages listed
    more than once count only once.
    """
    result: Dict[str, Counter] = defaultdict(Counter)
    seen: Dict[str, set] = defaultdict(set)
    counted = [s for s in sections if is_counted_section(s.name)]
    seasons = dict.fromkeys(s.season for s in counted)
    listed: Dict[str, set] = {}
    if songs_of is not None:
        for season in seasons:
            songs = songs_of(season)
            if songs:
                listed[season] = songs
    dropped: Dict[str, set] = {}
    if excluded_of is not None:
        for season in seasons:
            songs = excluded_of(season)
            if songs:
                dropped[season] = songs

    exists: Dict[str, bool] = {}
    resolved: Dict[str, str] = {}
    all_entries = [s for s in sections if s.season in seasons]
    batch_exists(site, (e.title for s in all_entries for e in s.entries), exists, resolved)
    batch_exists(site, (title for songs in listed.values() for title in songs),
                 exists, resolved)
    batch_exists(site, (title for songs in dropped.values() for title in songs),
                 exists, resolved)
    # 先把要按"谁建的页面"归属的条目一次性查出来，避免每条一次请求
    batch_creators(site, (e.title for s in all_entries for e in s.entries
                          if not e.colours and exists.get(e.title)), cache, resolved)
    batch_creators(site, (title for songs in listed.values() for title in songs
                          if exists.get(title)), cache, resolved)
    batch_creators(site, (title for songs in dropped.values() for title in songs
                          if exists.get(title)), cache, resolved)
    colours_by_target: Dict[str, List[str]] = {}
    for section in all_entries:
        for entry in section.entries:
            target = resolved.get(entry.title, entry.title)
            if entry.colours:
                colours_by_target.setdefault(target, entry.colours)

    for section in counted:
        for entry in section.entries:
            target = resolved.get(entry.title, entry.title)
            if target in seen[section.season]:  # redirects are the same song
                continue
            seen[section.season].add(target)
            # 单元格上的颜色是人工标注的创建者，最可信（页面缺失也照样算）；
            # 没有颜色的条目才回退到「谁在 voca 建的页面」，两者合起来才是
            # 页面上图表的口径。
            if entry.colours:
                for colour in dict.fromkeys(entry.colours):
                    if colour in legend.colour_to_name:
                        result[section.season][colour] += 1
                continue
            if not exists.get(entry.title):
                continue  # 页面还没建，等 build 出来再算
            if participants_of is not None and not belongs_to_season(
                    section.season, target, participants_of):
                # 同名不同曲，页面是别的赛季的歌：算进来就会给这一季添一个假数字
                continue
            current, previous = page_credits(site, target, cache, moe_cache)
            new, old = credit_pair(legend, current, previous)
            if new != old:
                if old and corrections is not None:
                    corrections.setdefault(section.season, Counter())[old] += 1
                if new and gains is not None:
                    gains.setdefault(section.season, Counter())[new] += 1
            if new:
                result[section.season][new] += 1

    for season, songs in listed.items():
        for title in songs:
            target = resolved.get(title, title)
            if target in seen[season] or not exists.get(title):
                continue
            seen[season].add(target)
            colours = colours_by_target.get(target, [])
            if colours:
                for colour in dict.fromkeys(colours):
                    if colour in legend.colour_to_name:
                        result[season][colour] += 1
                continue
            current, previous = page_credits(site, target, cache, moe_cache)
            new, old = credit_pair(legend, current, previous)
            if new != old:
                if old and corrections is not None:
                    corrections.setdefault(season, Counter())[old] += 1
                if new and gains is not None:
                    gains.setdefault(season, Counter())[new] += 1
            if new:
                result[season][new] += 1

    # 排除曲目以前也算进过图表：减掉的是**旧口径**算出来的那份（旧图表就是照它
    # 加的），跨站导入的条目减的是源站最后一版的作者，不然减不到点上。
    if excluded is not None:
        for season, songs in dropped.items():
            counter = excluded.setdefault(season, Counter())
            for title in songs:
                target = resolved.get(title, title)
                if target in seen[season] or not exists.get(title):
                    continue
                seen[season].add(target)
                colours = colours_by_target.get(target, [])
                if colours:
                    for colour in dict.fromkeys(colours):
                        if colour in legend.colour_to_name:
                            counter[colour] += 1
                    continue
                _, old = credit_pair(legend, *page_credits(site, target, cache, moe_cache))
                if old:
                    counter[old] += 1
    return result


def count_by_window(site, sections: List[Section]) -> Dict[str, Counter]:
    result: Dict[str, Counter] = defaultdict(Counter)
    for season in {s.season for s in sections}:
        start, end = season_window(season)
        try:
            for log in site.logevents(logtype="create", start=end, end=start, total=None):
                if log.ns != 0 or not log.user or log.user in KNOWN_BOTS:
                    continue
                result[season][strip_prefix(log.user)] += 1
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"{season}: cannot read creation log ({exc})")
    return result


# --------------------------------------------------------------------------- #
# chart
# --------------------------------------------------------------------------- #
def canonical_names(legend: Legend, yaxis: List[str]) -> Dict[str, str]:
    """identity -> the name already used in the chart's yAxis."""
    mapping: Dict[str, str] = {}
    for name in yaxis:
        identities = {legend.identity(tok.strip()) for tok in re.split(r"[/／]", name)}
        identities.add(legend.identity(name))
        for identity in identities:
            mapping.setdefault(identity, name)
    return mapping


def _matching_bracket(text: str, open_index: int) -> int:
    """Index just past the ``]``/``}`` that closes ``text[open_index]``."""
    depth = 0
    in_string = False
    escaped = False
    for index in range(open_index, len(text)):
        char = text[index]
        if in_string:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == '"':
                in_string = False
            continue
        if char == '"':
            in_string = True
        elif char in "[{":
            depth += 1
        elif char in "]}":
            depth -= 1
            if depth == 0:
                return index + 1
    raise RuntimeError("图表 JSON 的括号不匹配")


def _container(text: str, pattern: str) -> Tuple[int, int]:
    """``[start, end)`` of the JSON container the ``pattern`` ends on."""
    match = re.search(pattern, text)
    if not match:
        raise RuntimeError(f"图表里找不到 {pattern}")
    start = match.end() - 1
    if text[start] not in "[{":
        raise RuntimeError(f"图表里 {pattern} 之后不是 JSON 容器")
    return start, _matching_bracket(text, start)


def _nested(text: str, outer: str, key: str) -> Tuple[int, int]:
    """Span of ``key``'s value inside the ``outer`` container, in ``text`` coordinates."""
    start, end = _container(text, outer)
    inner_start, inner_end = _container(text[start:end], key)
    return start + inner_start, start + inner_end


def _elements(text: str, start: int, end: int) -> List[Tuple[int, int]]:
    """Spans of the top-level elements inside the container ``text[start:end]``."""
    spans: List[Tuple[int, int]] = []
    index = start + 1
    while index < end - 1:
        char = text[index]
        if char.isspace() or char == ",":
            index += 1
        elif char in "[{":
            stop = _matching_bracket(text, index)
            spans.append((index, stop))
            index = stop
        elif char == '"':
            stop = index + 1
            while stop < end - 1:
                if text[stop] == "\\":
                    stop += 2
                elif text[stop] == '"':
                    break
                else:
                    stop += 1
            spans.append((index, stop + 1))
            index = stop + 1
        else:
            stop = index
            while stop < end - 1 and text[stop] not in ",]}":
                stop += 1
            spans.append((index, stop))
            index = stop
    return spans


def _edges(inner: str) -> Tuple[str, str]:
    """Leading/trailing whitespace an editor left inside an array."""
    if not inner.strip():
        return "", ""
    return inner[:len(inner) - len(inner.lstrip())], inner[len(inner.rstrip()):]


def _refill(text: str, span: Tuple[int, int], values: List[str]) -> str:
    """Replace an array's elements while keeping its own spacing and line breaks."""
    start, end = span
    lead, trail = _edges(text[start + 1:end - 1])
    body = lead + ",".join(values) + trail if values else ""
    return text[:start + 1] + body + text[end - 1:]


def _relabel_series(model: Optional[str], name: str, colour: str,
                    values: List[str]) -> str:
    """Copy a series block under a new name/colour so a new season matches its neighbours."""
    if model is None:
        return FALLBACK_SERIES % {"name": name, "colour": colour, "data": ",".join(values)}
    block = re.sub(r'("name"\s*:\s*")[^"]*(")',
                   lambda m: m.group(1) + name + m.group(2), model, count=1)
    block = re.sub(r'("color"\s*:\s*")[^"]*(")',
                   lambda m: m.group(1) + colour + m.group(2), block, count=1)
    return _refill(block, _container(block, r'"data"\s*:\s*\['), values)


def render_chart(text: str, sections: List[Section], legend: Legend,
                 counts: Dict[str, Counter],
                 excluded: Optional[Dict[str, Counter]] = None,
                 gained: Optional[Dict[str, Counter]] = None,
                 base_text: Optional[str] = None) -> Tuple[str, dict]:
    match = CHART_RE.search(text)
    if not match:
        raise RuntimeError("未找到 {{Echart}} - 页面结构可能已改变")
    # 这份 JSON 是人在页面上手排的版（换行、冒号后的空格都不统一），所以只替换
    # 数值本身，不重新序列化——否则排版会被洗成机器人自己的样子（257698 那次的教训）。
    raw = match.group(2)
    chart = json.loads(raw)
    yaxis: List[str] = chart["yAxis"]["data"]
    colours = canonical_names(legend, yaxis)

    seasons: List[str] = []
    for section in sections:
        if section.season not in seasons:
            seasons.append(section.season)
    labels = [CHART_SERIES_PREFIX + s for s in seasons]

    # aggregate per user, preserving existing yAxis order
    per_season: Dict[str, Dict[str, int]] = {s: defaultdict(int) for s in seasons}
    totals: Counter = Counter()
    for season in seasons:
        for key, count in counts.get(season, {}).items():
            user = colours.get(key, legend.display(key))
            per_season[season][user] += count
            totals[user] += count

    # 排除曲目（REMIX/二创）以前也算进过图表，现在不算了：先按同一套归属规则
    # 算出一个减数，才能把以前多给的数字改回来，而不是被「只升不降」护住。
    removed: Dict[str, Dict[str, int]] = {s: {} for s in seasons}
    for season in seasons:
        for key, count in (excluded or {}).get(season, {}).items():
            user = colours.get(key, legend.display(key))
            removed[season][user] = removed[season].get(user, 0) + count

    # 归属改到真创建者头上的那份要**加到**他头上：那些条目在他这一格原本没记过
    # （旧图表记的是导入版作者），只减不加的话会被「只升不降」吃掉。
    added: Dict[str, Dict[str, int]] = {s: {} for s in seasons}
    for season in seasons:
        for key, count in (gained or {}).get(season, {}).items():
            user = colours.get(key, legend.display(key))
            added[season][user] = added[season].get(user, 0) + count

    series_span = _container(raw, r'"series"\s*:\s*\[')
    spans = _elements(raw, *series_span)
    blocks: List[Tuple[str, dict]] = []
    for start, end in spans:
        block = raw[start:end]
        try:
            blocks.append((block, json.loads(block)))
        except ValueError:  # 混了注释之类的东西，别碰它
            continue

    palette = [obj.get("itemStyle", {}).get("color") for _, obj in blocks]
    # 每格的老数字取自 ``base_text`` 那一版（默认就是当前页面）。一次性的迁移
    # 必须相对一个固定的基准版算，否则「减旧加新」每轮都会重来一遍。
    base = base_text if base_text is not None else text
    base_match = CHART_RE.search(base)
    if base_match is None:
        raise RuntimeError("基准版本里没有 {{Echart}}，取不到老的数字")
    try:
        base_chart = json.loads(base_match.group(2))
    except ValueError as exc:
        raise RuntimeError(f"基准版本的 {{Echart}} 解析失败：{exc}") from exc
    base_axis: List[str] = base_chart["yAxis"]["data"]
    # 有些数字来自站外的人工记账（既没上色、本地也没页面），任何算法都推不出来，
    # 所以只在机器人算得更多时提高，绝不把人工数字改小。
    kept: Dict[str, Dict[str, int]] = {}
    for series in base_chart.get("series", []):
        label = series.get("name", "")
        kept[label] = {name: value for name, value in
                       zip(base_axis, series.get("data", [])) if value}

    users = [u for u in yaxis if totals[u] >= 5 or any(u in kept.get(l, {}) for l in labels)]
    users += [u for u in totals if totals[u] >= 5 and u not in users]

    def previous_of(label: str, season: str, user: str) -> int:
        """上一版图表里的数字，扣掉机器人不再计入的、加上改归到这一格的。"""
        previous = kept.get(label, {}).get(user, 0)
        return max(0, previous - removed.get(season, {}).get(user, 0)
                   + added.get(season, {}).get(user, 0))

    def chart_total(user: str) -> int:
        """这一行在整张图上的合计（推不出来、只能沿用的人工数字也算）。"""
        total = 0
        for index, label in enumerate(labels):
            computed = per_season[seasons[index]].get(user, 0)
            total += max(computed, previous_of(label, seasons[index], user))
        return total

    # ECharts 的 yAxis 自下而上画：数组里靠前的画在图的下方。所以按创建数
    # **升序**排，图上看起来才是从多到少。
    users.sort(key=lambda u: (chart_total(u), u))

    separators = [raw[spans[i][1]:spans[i + 1][0]] for i in range(len(spans) - 1)]
    separator = separators[-1] if separators else ",\n\n"
    model = blocks[0][0] if blocks else None

    manual = 0
    ordered: List[str] = []
    for index, label in enumerate(labels):
        season = seasons[index]
        data: List[str] = []
        for user in users:
            computed = per_season[season].get(user, 0)
            previous = previous_of(label, season, user)
            if previous > computed:
                manual += 1
            data.append(str(max(computed, previous)))
        existing = next((block for block, obj in blocks if obj.get("name") == label), None)
        if existing is not None:
            ordered.append(_refill(existing, _container(existing, r'"data"\s*:\s*\['), data))
        else:
            colour = palette[index % len(palette)] if palette else "#888888"
            ordered.append(_relabel_series(model, label, colour, data))
    ordered += [block for block, obj in blocks if obj.get("name") not in labels]
    if manual:
        pywikibot.output(f"统计: 保留 {manual} 个机器人推不出来的人工数字")

    inner = raw[series_span[0] + 1:series_span[1] - 1]
    lead, trail = _edges(inner)
    updated = (raw[:series_span[0] + 1] + lead + separator.join(ordered) + trail
               + raw[series_span[1] - 1:])
    updated = _refill(updated, _nested(updated, r'"legend"\s*:\s*\{', r'"data"\s*:\s*\['),
                      [json.dumps(value, ensure_ascii=False) for value in labels])
    updated = _refill(updated, _nested(updated, r'"yAxis"\s*:\s*\{', r'"data"\s*:\s*\['),
                      [json.dumps(value, ensure_ascii=False) for value in users])

    chart["legend"]["data"] = labels
    chart["yAxis"]["data"] = users
    return text[:match.start(2)] + updated + text[match.end(2):], chart


# --------------------------------------------------------------------------- #
# colour
# --------------------------------------------------------------------------- #
def text_colour(background: str) -> str:
    """Pick black or white text for a background hex colour."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000" if luminance > 0.6 else "#FFF"


def plan_colours(site, sections: List[Section], legend: Legend,
                 cache: Dict,
                 exists: Dict[str, bool],
                 participants_of: Optional[Callable[[str], Optional[set]]] = None,
                 moe_cache: Optional[Dict] = None
                 ) -> Dict[str, Tuple[str, str]]:
    """entry title -> (background colour, page title to link to).

    Only entries whose page exists are coloured; a link whose target does not
    exist is matched against the real title first and corrected in the same
    edit (``[[FrailLaVillanos]]`` -> ``[[FrailL'aVillanos]]``).  A page that is
    not a participant of that season is skipped: same name, different song.
    """
    uncoloured = [(s.season, e) for s in sections for e in s.entries if not e.colours]
    resolved: Dict[str, str] = {}
    batch_exists(site, (e.title for _, e in uncoloured), exists, resolved)
    index: Optional[Dict[str, str]] = None
    plan: Dict[str, Tuple[str, str]] = {}
    targets: Dict[str, str] = {}
    for _, entry in uncoloured:
        if not page_exists(site, entry.title, exists):
            continue
        # 链接指向重定向时按真页面取创建者，并把链接改写成真标题
        targets[entry.title] = resolved.get(entry.title, entry.title)
    batch_creators(site, targets.values(), cache)
    for season, entry in uncoloured:
        if entry.title in plan:
            continue
        if entry.title in targets:
            target = targets[entry.title]
        else:
            if index is None:
                index = title_index(site)
            target = index.get(title_key(entry.title))
            if not target:
                continue
            exists[target] = True
        if participants_of is not None and not belongs_to_season(
                season, target, participants_of):
            pywikibot.warning(f"{season}/{entry.title}: {target} 不是本赛季的参赛曲目，"
                              f"同名不同曲，跳过上色")
            continue
        user = page_creator(site, target, cache, moe_cache)
        if not user or user in KNOWN_BOTS:
            continue
        identity = legend.identity(user)
        if re.fullmatch(HEX, identity):
            plan[entry.title] = (identity, target)
    return plan


def apply_colours(text: str, plan: Dict[str, Tuple[str, str]]) -> Tuple[str, int]:
    """Wrap uncoloured table cells in ``bgcolor`` + ``{{colorlink}}``."""
    if not plan:
        return text, 0
    changed = 0
    link_re = re.compile(r"\[\[([^\]|]+)\|([^\]]+)\]\]")

    def repl(m: re.Match) -> str:
        nonlocal changed
        title = unquote(m.group(1).strip())
        entry = plan.get(title)
        if entry is None:
            return m.group(0)  # an unrelated wikilink
        colour, target = entry
        changed += 1
        return (f"bgcolor={colour} | "
                f"{{{{colorlink|{text_colour(colour)}|{target}|{m.group(2)}}}}}")

    pieces: List[str] = []
    pos = 0
    for table in re.finditer(r"\{\|.*?\|\}", text, re.S):
        pieces.append(text[pos:table.start()])
        pieces.append(link_re.sub(repl, table.group(0)))
        pos = table.end()
    pieces.append(text[pos:])
    return "".join(pieces), changed


# --------------------------------------------------------------------------- #
# report
# --------------------------------------------------------------------------- #
def build_report(site, sections: List[Section], legend: Legend,
                 cache: Dict[str, Optional[str]], exists: Dict[str, bool],
                 plan: Optional[Dict[str, Tuple[str, str]]] = None) -> str:
    plan = plan or {}
    batch_exists(site, (e.title for s in sections for e in s.entries), exists)
    lines: List[str] = []
    for title, (_, target) in plan.items():
        if target != title:
            lines.append(f"链接已修正: {title} -> {target}")
    for section in sections:
        if not section.entries:
            continue
        for entry in section.entries:
            found = page_exists(site, entry.title, exists)
            if entry.colours and not found:
                lines.append(f"已上色但页面不存在: {section.season}/{section.name} - {entry.title}")
            elif found and not entry.colours and entry.title not in plan:
                lines.append(f"页面已存在但未上色（未能自动上色）: {section.season}/{section.name} - {entry.title}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# 萌娘百科交叉比对（只出报告，不改页面）
# --------------------------------------------------------------------------- #
@dataclass
class MoePage:
    """萌娘百科上的同名条目。

    ``title`` 为 ``None`` 表示萌娘百科没有同名条目；``known`` 为 ``False`` 表示
    这次没问到（网络/API 失败），不能当成「没有」。
    """

    title: Optional[str] = None
    creator: Optional[str] = None
    known: bool = False


def moegirl_api(params: Dict[str, str]) -> Optional[dict]:
    """一次萌娘百科 API 查询；网络出错或被对面拒绝都返回 ``None``。

    对面回 ``error``（限流、参数被禁）也算「没问到」，绝不能当成「没有这条」——
    否则整批条目会被写成「无同名条目」，报告就成了误导。
    """
    query = dict(params)
    query["format"] = "json"
    query["formatversion"] = "2"
    request = urllib.request.Request(
        MOEGIRL_API + "?" + urlencode(query),
        headers={"User-Agent": MOEGIRL_UA})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(request, timeout=MOEGIRL_TIMEOUT) as response:
                data = json.load(response)
        except Exception as exc:  # noqa: BLE001
            if attempt < 2:
                time.sleep(1 + attempt)
                continue
            pywikibot.error(f"萌娘百科查询失败: {exc}")
            return None
        if "error" in data:
            error = data["error"]
            pywikibot.error(f"萌娘百科拒绝请求: {error.get('code')} "
                            f"{error.get('info')}")
            return None
        return data
    return None


def _follow_links(title: str, links: Dict[str, str]) -> str:
    """顺着 normalize / 变体转换 / 重定向的表走到最终标题。"""
    seen: Set[str] = set()
    while title in links and title not in seen:
        seen.add(title)
        title = links[title]
    return title


def moegirl_titles(titles: Iterable[str]) -> Dict[str, Optional[str]]:
    """查询标题 -> 萌娘百科上的实际页面标题（没有同名条目则 ``None``）。

    问不到的标题不会出现在结果里，调用方不能把「没问到」当成「没有」。批量查询带上
    ``converttitles=1``：模板写日文原名、萌娘条目用中文时靠这一步才归一。
    """
    wanted = list(dict.fromkeys(titles))
    found: Dict[str, Optional[str]] = {}
    for i in range(0, len(wanted), 50):
        batch = wanted[i:i + 50]
        data = moegirl_api({"action": "query", "titles": "|".join(batch),
                            "redirects": "1", "converttitles": "1"})
        if data is None:
            continue
        query = data.get("query", {})
        pages = query.get("pages") or []
        if isinstance(pages, dict):
            pages = list(pages.values())
        by_title = {page["title"]: None if page.get("missing") else page["title"]
                    for page in pages}
        links: Dict[str, str] = {}
        for mapping in ((query.get("normalized") or []) + (query.get("converted") or [])
                        + (query.get("redirects") or [])):
            links[mapping["from"]] = mapping["to"]
        for title in batch:
            final = _follow_links(title, links)
            if final in by_title:
                found[title] = by_title[final]
        time.sleep(MOEGIRL_DELAY)
    return found


def moegirl_creator(title: str) -> Optional[str]:
    """萌娘百科页面的最旧一版作者；页面不存在或这一次没问到都返回 ``None``。

    MediaWiki 只允许对单页用 ``rvdir=newer``，所以一页一次请求。导入的页面这里
    拿到的是导入者，未必是真作者——报告里照实列出。
    """
    data = moegirl_api({"action": "query", "prop": "revisions", "titles": title,
                        "rvprop": "user", "rvlimit": "1", "rvdir": "newer",
                        "redirects": "1"})
    if data is None:
        return None
    pages = data.get("query", {}).get("pages") or []
    if isinstance(pages, dict):
        pages = list(pages.values())
    if not pages or pages[0].get("missing"):
        return None
    revisions = pages[0].get("revisions") or []
    return revisions[0].get("user") if revisions else None


def moegirl_cached(cache: Dict, title: str,
                   ) -> Optional[Tuple[Optional[str], Optional[str]]]:
    """``(萌娘标题, 创建者)``；没有缓存或缓存过期返回 ``None``。"""
    entry = cache.get(title)
    if not isinstance(entry, tuple) or len(entry) != 3:
        return None
    moe_title, user, stamped = entry
    if time.time() - stamped > MOEGIRL_CACHE_TTL:
        return None
    return moe_title, user


def moegirl_lookup(titles: Iterable[str], cache: Dict) -> Dict[str, MoePage]:
    """批量查萌娘百科有没有同名条目、以及它们的创建者，顺带填 ``cache``。"""
    wanted = list(dict.fromkeys(t for t in titles if t))
    result = {title: MoePage() for title in wanted}
    pending: List[str] = []
    for title in wanted:
        cached = moegirl_cached(cache, title)
        if cached is None:
            pending.append(title)
        else:
            result[title] = MoePage(cached[0], cached[1], True)
    if not pending:
        return result
    resolved = moegirl_titles(pending)
    for title in pending:
        if title not in resolved:
            continue  # 这一次没问到，留着下次再问，别当成「没有」
        moe_title = resolved[title]
        if moe_title is None:
            result[title] = MoePage(None, None, True)
            cache[title] = (None, None, time.time())
            continue
        user = moegirl_creator(moe_title)
        time.sleep(MOEGIRL_DELAY)
        if user is None:
            continue  # 页面在却拿不到作者：多半是这次请求失败，不写缓存
        result[title] = MoePage(moe_title, user, True)
        cache[title] = (moe_title, user, time.time())
    return result


def moegirl_creator_of(title: str, moe_cache: Optional[Dict] = None) -> Optional[str]:
    """萌娘百科同名条目的创建者（最旧一版作者）；没有同名条目或查不到返回 ``None``。"""
    if moe_cache is None:
        moe_cache = {}
    page = moegirl_lookup([title], moe_cache).get(title)
    if page is None or not page.title:
        return None
    return page.creator


def page_credits(site, title: str, cache: Dict, moe_cache: Optional[Dict] = None
                 ) -> Tuple[Optional[str], Optional[str]]:
    """``(这个条目该记谁, 修好之前算的是谁)``——第二个用来把旧图表里多给的减回去。

    voca 的首版若是跨站导入的，那一版挂的是**源站条目的最后一版**作者（见
    ``IMPORT_USER_RE``），不是创建者，照它算就把源站最后一位编辑者当成了创建者。
    这种条目改去源站找真正的作者，目前只认萌娘百科（``zhmoe``）；源站也查不到时
    宁可不归属，也不拿导入者顶替。两个用户名都已剥掉跨站前缀。
    """
    raw = creator_of(site, title, cache)
    if raw is None:
        return None, None
    previous = strip_prefix(raw)
    source = import_source(raw)
    if not source:
        return previous, previous
    if source not in IMPORT_SOURCES:
        pywikibot.warning(f"{title}: 首版来自 {source}>，认不出源站，不归属")
        return None, previous
    creator = moegirl_creator_of(title, moe_cache)
    if creator is None:
        pywikibot.warning(
            f"{title}: 首版是{IMPORT_SOURCES[source]}导入的"
            f"（{previous} 只是源站最后一版的作者），源站也查不到作者，不归属")
        return None, previous
    return strip_prefix(creator), previous


def page_creator(site, title: str, cache: Dict,
                 moe_cache: Optional[Dict] = None) -> Optional[str]:
    """这个条目该记谁的创建（细则见 ``page_credits``）。"""
    return page_credits(site, title, cache, moe_cache)[0]


def credit_pair(legend: Legend, current: Optional[str],
                previous: Optional[str]) -> Tuple[Optional[str], Optional[str]]:
    """``(现在该记的归属, 旧口径算出来的归属)``；机器人账号两边都不记。

    两边不同时，旧图表要减掉旧口径那份（``previous``）、再加上新口径那份——
    条目本来记在导入版作者头上，不减旧的就降不下来、不加新的就落不到真作者头上。
    """
    new = legend.identity(current) if current and current not in KNOWN_BOTS else None
    old = legend.identity(previous) if previous and previous not in KNOWN_BOTS else None
    return new, old


def moegirl_candidates(sections: List[Section], legend: Legend,
                       songs_of: Optional[Callable[[str], Optional[set]]],
                       exists: Dict[str, bool], resolved: Dict[str, str],
                       creators: Dict[str, Optional[str]],
                       imports: Optional[Dict[str, str]] = None) -> List[Dict]:
    """这一轮值得拿去和萌娘百科比对的条目。

    ``creators`` 是 ``{voca 页面标题: 首版作者}``；``imports`` 记下哪些条目的首版
    是跨站导入的（那份「作者」其实是源站最后一版的编辑者）。三类值得比对：本机还
    没有页面（``red``）、页面上标的创建者与首版作者不是同一个人（``mismatch``）、
    首版作者是机器人/导入账号所以统计里被整个丢掉（``bot``）。格子的颜色是全页面
    共用的标注（榜外歌曲也一样），所以榜外歌曲也要拿它来比。
    """
    imports = imports or {}
    counted = [s for s in sections if is_counted_section(s.name)]
    seasons = list(dict.fromkeys(s.season for s in counted))
    colours_by_target: Dict[str, List[str]] = {}
    for section in sections:
        for entry in section.entries:
            if entry.colours:
                colours_by_target.setdefault(
                    resolved.get(entry.title, entry.title), list(entry.colours))
    rows: List[Dict] = []
    seen = set()

    def add(season: str, name: str, title: str) -> None:
        target = resolved.get(title, title)
        if (season, target) in seen:
            return
        seen.add((season, target))
        colours = colours_by_target.get(target) or []
        local = creators.get(target)
        if not exists.get(title):
            reason = "red"
        elif colours and (not local or legend.identity(local) not in colours):
            reason = "mismatch"
        elif local and local in KNOWN_BOTS:
            reason = "bot"
        else:
            return
        rows.append({"season": season, "section": name, "title": title,
                     "target": target, "colours": colours, "local": local,
                     "source": imports.get(target, ""), "reason": reason})

    for section in counted:
        for entry in section.entries:
            add(section.season, section.name, entry.title)
    if songs_of is not None:
        for season in seasons:
            songs = songs_of(season)
            for title in sorted(songs or ()):
                add(season, "榜外", title)
    return rows


def moegirl_report(site, sections: List[Section], legend: Legend,
                   cache: Dict[str, Optional[str]], exists: Dict[str, bool],
                   songs_of: Optional[Callable[[str], Optional[set]]] = None,
                   moe_cache: Optional[Dict] = None) -> str:
    """与萌娘百科交叉比对创建者，返回给人看的报告（不改页面、不写图例）。"""
    if moe_cache is None:
        moe_cache = {}
    counted = [s for s in sections if is_counted_section(s.name)]
    if not counted:
        return ""
    titles = [e.title for s in sections for e in s.entries]
    for season in dict.fromkeys(s.season for s in counted):
        songs = songs_of(season) if songs_of else None
        if songs:
            titles.extend(sorted(songs))
    titles = list(dict.fromkeys(titles))
    resolved: Dict[str, str] = {}
    batch_exists(site, titles, exists, resolved)
    batch_creators(site, (t for t in titles if exists.get(t)), cache, resolved)
    creators: Dict[str, Optional[str]] = {}
    imports: Dict[str, str] = {}
    for target in (resolved.get(t, t) for t in titles):
        cached = cached_creator(cache, target)
        if cached is None:
            continue
        creators[target] = strip_prefix(cached[0])
        if cached[1]:
            imports[target] = cached[1]
    rows = moegirl_candidates(sections, legend, songs_of, exists, resolved,
                              creators, imports)
    if not rows:
        return "  （没有需要比对的条目）"
    pages = moegirl_lookup((row["title"] for row in rows), moe_cache)

    reasons = (("mismatch", "标注与 voca 首版作者不符"),
               ("bot", "voca 首版作者是机器人/导入账号"),
               ("red", "voca 还没有页面（红链）"))
    found = sum(1 for row in rows if pages[row["title"]].title)
    asked = sum(1 for row in rows if pages[row["title"]].known)
    lines = [f"萌娘百科镜像: {MOEGIRL_API}（官方站对匿名调用封锁 prop=revisions）",
             f"待比对 {len(rows)} 条（"
             + "、".join(f"{label} {sum(1 for r in rows if r['reason'] == key)}"
                         for key, label in reasons)
             + f"）；萌娘有同名条目 {found}/{asked} 条（问到的）"]
    if any(row["source"] for row in rows):
        lines.append("（「voca 首版」标了「萌百导入」的，那一版是导入时从源站抄来的"
                     "**最后一版**，作者不是创建者；机器人现在改记源站最旧一版的作者）")

    gains: Counter = Counter()
    outside = Counter()
    for key, label in reasons:
        group = [row for row in rows if row["reason"] == key]
        if not group:
            continue
        block: List[str] = []
        blank = unknown = 0
        for row in group:
            page = pages[row["title"]]
            # 红链在萌娘也没有同名条目：对判断没有帮助，只报数量
            if key == "red" and not page.title:
                if page.known:
                    blank += 1
                else:
                    unknown += 1
                continue
            parts = [f"{row['season']}/{row['section']} {row['title']}"]
            if row["colours"]:
                parts.append("标注 " + "、".join(
                    legend.colour_to_name.get(c, c) for c in row["colours"]))
            if row["local"]:
                mark = "（萌百导入）" if row["source"] else ""
                parts.append(f"voca 首版 {row['local']}{mark}")
            if not page.known:
                parts.append("萌娘查询失败")
            elif page.title is None:
                parts.append("萌娘无同名条目")
            else:
                # 标题对不上说明是走重定向/变体归一找到的，这种匹配更要人工过一眼
                via = "（经重定向）" if page.title != row["title"] else ""
                parts.append(f"萌娘《{page.title}》{via}"
                             f"创建者 {page.creator or '（未知）'}")
            block.append("  " + " | ".join(parts))
            # 带颜色的格子已经算给标注的创建者了，别重复算；只有现在谁都没算到的
            # （红链且未上色、首版作者是机器人）才谈「照萌娘结果归属」。
            if (key != "mismatch" and not row["colours"] and page.creator
                    and page.creator not in KNOWN_BOTS):
                identity = legend.identity(page.creator)
                if re.fullmatch(HEX, identity):
                    gains[identity] += 1
                else:
                    outside[page.creator] += 1
        lines.append("")
        lines.append(f"=== {label}（{len(group)} 条）===")
        lines.extend(block)
        if blank or unknown:
            lines.append(f"  （另有 {blank} 条在萌娘也没有同名条目、"
                         f"{unknown} 条这次没问到，未逐条列出）")
    if gains or outside:
        lines.append("")
        lines.append("若照萌娘结果给「红链/机器人」条目归属，创建者会变成：")
        for identity, count in gains.most_common():
            lines.append(f"  {legend.display(identity)}（{identity}）：+{count}")
        for user, count in outside.most_common():
            lines.append(f"  {user}：+{count}（萌娘账号，本站图例里没有颜色）")
    lines.append("")
    lines.append("[只出报告] 同名条目未必是同一首曲（尤其是短标题），机器人不会据此"
                 "上色或改数字，要不要采用由人工判断。")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
ALL_ACTIONS = ("entries", "counts", "colour", "stats", "report")
# 不进 ``all``：萌娘百科是别人的 wiki，别让每小时一次的维护去敲它；
# recredit 是一次性迁移，必须显式带着基准版本跑，见 ``recredit``。
EXTRA_ACTIONS = ("moe", "recredit")
DEFAULT_SUMMARY = "机器人：自动维护贡献列表"


def ensure_login(site) -> None:
    """Log in explicitly - pywikibot will not edit anonymously.

    Credentials come from ``user-config.py`` (``usernames``) plus
    ``user-password.py`` (``('Renjian-bot', 'password')`` or
    ``('Renjian-bot', BotPassword('suffix', 'token'))``).
    """
    hint = (
        "请检查 user-config.py 的 usernames 与 user-password.py"
        "（CI 中为 secret USER_PASSWORD_PY）；机器人密码必须写成 "
        "BotPassword('后缀', '机器人密码')，后缀即 Special:BotPasswords 里"
        "\"账号@后缀\" 中 @ 后面的部分。"
    )
    if not site.logged_in():
        try:
            # Site.login() 成功和失败都返回 None，不能依赖它的返回值，
            # 只能调用后用 site.logged_in() 判断结果。
            site.login()
        except Exception as exc:  # NoUsernameError / APIError / EOFError...
            raise RuntimeError(f"登录失败：{exc}\n{hint}") from exc
    if not site.logged_in():
        raise RuntimeError(f"登录失败：{hint}")
    if not site.has_right("edit"):
        raise RuntimeError(
            f"账号 {site.user()} 已登录但没有 edit 权限，无法编辑。"
            "请确认该账号已被授予编辑权限（voca.wiki 上匿名用户不能编辑）。")
    pywikibot.output(
        f"已登录：{site.user()}（权限组：{', '.join(site.userinfo['groups'])}）")


def _abandon_round(page: Page, exc: Exception) -> bool:
    """Drop a save that lost the race, and re-read the page from the wiki."""
    pywikibot.error(f"页面刚被其他进程编辑，放弃本轮：{exc}")
    try:
        # 不清掉本地缓存的话，之后每一轮都会拿着旧版本号去撞同一个冲突
        page.get(force=True)
    except Exception as reload_exc:  # noqa: BLE001
        pywikibot.error(f"重新读取页面失败：{reload_exc}")
    return False


def save_page(page: Page, text: str, summary: Optional[str]) -> bool:
    """Save, degrading gracefully when the account lacks ``bot``/``changetags``.

    Returns False when someone else edited the page first. Toolforge and
    GitHub Actions both maintain this page on staggered hourly schedules, so a
    race is abandoned rather than overwriting the other writer.
    """
    page.text = text
    summary = summary or DEFAULT_SUMMARY
    try:
        page.save(summary=summary, minor=True, bot=True, tags="Bot")
        return True
    except EditConflictError as exc:
        return _abandon_round(page, exc)
    except TypeError:  # older pywikibot: ``bot`` is named ``botflag``
        try:
            page.save(summary=summary, minor=True, botflag=True, tags="Bot")
            return True
        except EditConflictError as exc:
            return _abandon_round(page, exc)
        except pywikibot.exceptions.APIError as exc:
            pywikibot.error(f"带 botflag/tags 保存失败，改用普通保存重试：{exc}")
    except pywikibot.exceptions.APIError as exc:
        # the account may lack the "bot" right or the "changetags" right
        pywikibot.error(f"带 bot/tags 保存失败，改用普通保存重试：{exc}")
    try:
        page.save(summary=summary, minor=True)
        return True
    except EditConflictError as exc:
        return _abandon_round(page, exc)


def revision_text(site, revid: int) -> str:
    """取某一版的正文，并确认它就是本页面（迁移基准别拿错页面）。"""
    data = site.simple_request(action="query", prop="revisions", revids=str(revid),
                              rvprop="content", rvslots="main", formatversion=2).submit()
    pages = data.get("query", {}).get("pages") or []
    revisions = (pages[0].get("revisions") if pages else None) or []
    if not revisions:
        raise ValueError(f"拿不到版本 {revid} 的内容")
    if pages[0].get("title") != PAGE_TITLE:
        raise ValueError(f"版本 {revid} 不是 {PAGE_TITLE}（是 {pages[0].get('title')}）")
    return revisions[0]["slots"]["main"]["content"]


def recredit(site, text: str, sections: List[Section], legend: Legend,
             cache: Dict, moe_cache: Dict,
             participants_of, songs_of, excluded_of,
             from_rev: Optional[int]) -> str:
    """一次性把记在「导入版作者」名下的数字搬到真创建者头上。

    为什么不能每轮都做：图表只会把数字往上抬（站外的人工记账推不出来，不能丢），
    所以「减掉旧口径那份、给真创建者加上」必须相对**某个基准版**做一次；否则每跑
    一轮都会再加一遍，数字越滚越大。基准版由 ``from_rev`` 指定，同一版重跑得到的
    结果一致，所以重复执行、或者 CI 与 Toolforge 各跑一次，结果都一样。
    """
    if not from_rev:
        raise ValueError("recredit 需要 --from-rev <版本号>：拿哪一版的图表当基准")
    base_text = revision_text(site, from_rev)
    excluded: Dict[str, Counter] = {}
    corrections: Dict[str, Counter] = {}
    gains: Dict[str, Counter] = {}
    counts = count_by_listed(site, sections, legend, cache, participants_of,
                             songs_of, excluded_of, excluded, moe_cache,
                             corrections, gains)
    for season, counter in corrections.items():
        excluded.setdefault(season, Counter()).update(counter)
    moved = sum(sum(counter.values()) for counter in gains.values())
    dropped = sum(sum(counter.values()) for counter in corrections.values())
    updated, _ = render_chart(text, sections, legend, counts, excluded, gains,
                              base_text=base_text)
    pywikibot.output(f"迁移: 以版本 {from_rev} 为基准，导入误记改归真创建者 "
                     f"{moved} 处（从旧口径减掉 {dropped} 处）")
    return updated


def run_once(site, actions, basis: str = "listed", write: bool = False,
             summary: Optional[str] = None, from_rev: Optional[int] = None) -> bool:
    """Run one maintenance pass.  Returns True when the page changed.

    Returns False when there was nothing to do, and also when the save was
    skipped because another scheduled process edited the page
    first - that round is retried by the next trigger instead.
    """
    actions = set(actions)
    if write:
        ensure_login(site)
    page = Page(site, PAGE_TITLE)
    original = page.text
    sections = parse_sections(original)
    legend = Legend.parse(original)
    if not sections:
        pywikibot.error("未解析到任何赛季小节，跳过。")
        return False

    DATA_DIR.mkdir(exist_ok=True)
    cache = load_cache(CREATOR_CACHE)
    moe_cache = load_cache(MOEGIRL_CACHE)
    text = original
    created = None
    plan: Dict[str, Tuple[str, str]] = {}
    exists: Dict[str, bool] = {}
    seasons = list(dict.fromkeys(s.season for s in sections))
    participant_lists: Dict[str, Optional[set]] = {}

    def participants_of(season: str) -> Optional[set]:
        """挂着本赛季导航模板的页面标题集合；``None`` 表示没查到，不据此下结论。"""
        if season not in participant_lists:
            found = template_participants(site, season)
            participant_lists[season] = set(found) if found is not None else None
        return participant_lists[season]

    # 赛季模板是「哪些歌、第几名、条目该叫什么」的权威来源。
    wanted = (season_templates(site, seasons)
              if actions & {"entries", "stats", "moe", "recredit"} else {})

    def songs_of(season: str) -> Optional[set]:
        """赛季模板里**计入统计**的曲目（榜单曲 + 榜外原创曲）；``None`` 表示模板没取到。"""
        template_sections = wanted.get(season)
        if not template_sections:
            return None
        return {title for key, ranks in template_sections.items()
                for title in ranks.values() if is_counted_track(key, title)}

    def excluded_of(season: str) -> Optional[set]:
        """不计入统计的曲目（REMIX 赛道、neta 二创），用来把图表里多算的抹掉。"""
        template_sections = wanted.get(season)
        if not template_sections:
            return None
        return {title for key, ranks in template_sections.items()
                for title in ranks.values() if not is_counted_track(key, title)}

    if "entries" in actions:
        # 只要模板里的标题有对应页面，就把名次格子统一改写成规范标题（重定向写法
        # 一并归一），模板里还没有页面的标题只报告、不动。
        diffs = entry_diffs(text, wanted)
        fixes: Dict[Tuple[str, str, int], str] = {}
        repaired = 0
        normalised = 0
        foreign: List[str] = []
        actionable = 0
        if diffs:
            probe: Dict[str, bool] = {}
            redirects: Dict[str, str] = {}
            batch_exists(site, [d[3] for d in diffs] + [d[4] for d in diffs], probe, redirects)
            for season, name, rank, current, want in diffs:
                if not probe.get(want):
                    # 模板里的标题还没有页面（模板多写日文原名，那些链接是红的）：
                    # 不动页面，也不计入报告——否则七百多条差异里全是这种写法差异。
                    continue
                actionable += 1
                # 模板标题本身可能是重定向（"ダウナ" 指回 "Downa"），要取最终页面，
                # 否则会把链接改成一个绕回原地的重定向。
                target = redirects.get(want, want)
                if target == current:
                    continue
                if not belongs_to_season(season, target, participants_of):
                    # 同名不同曲：2022秋 的 "スワンプマン" 指向 2026夏 的 SWAMPMAN。
                    # 改写会把另一首歌的名字安到这一季，也等于抹掉人工改过的链接。
                    foreign.append(f"{season}/{name} {rank}: {current}"
                                   f"（模板标题 {want} 不是本赛季的参赛曲目）")
                    continue
                fixes[(season, name, rank)] = target
                if not probe.get(current):
                    repaired += 1
                else:
                    normalised += 1
        text, synced, notes = sync_entries(text, fixes)
        if actionable:
            pywikibot.output(f"条目: 赛季模板对比出 {actionable} 处差异，改写 {synced} 个名次"
                             f"（死链修复 {repaired}，统一成规范标题 {normalised}）")
        for note in notes[:20]:
            pywikibot.output(f"  {note}")
        if len(notes) > 20:
            pywikibot.output(f"  ……另有 {len(notes) - 20} 处未逐条列出")
        for note in foreign[:20]:
            pywikibot.output(f"  同名不同曲，不改写: {note}")
        if len(foreign) > 20:
            pywikibot.output(f"  ……另有 {len(foreign) - 20} 处同名不同曲未逐条列出")
        # 模板里的标题和页面上的标题写法常常不同（模板写日文/繁体，页面是中文真
        # 标题，或者只差首字母大小写），两边都按站上真标题归一后再比，否则这条
        # 报告会全是「ダウナ vs Downa」这种噪声。
        template_titles = [title for secs in wanted.values()
                           for ranks in secs.values() for title in ranks.values()]
        members_by_season = {season: participants_of(season) or set() for season in wanted}
        canonical: Dict[str, str] = {}
        batch_exists(site, dict.fromkeys(
            template_titles
            + [title for members in members_by_season.values() for title in members]),
            {}, None, canonical)

        def listed_key(title: str) -> str:
            return title_key(canonical.get(title, title))

        in_template = {listed_key(title) for title in template_titles}
        missing = [f"{season}/{title}" for season, members in members_by_season.items()
                   for title in sorted(members)
                   if listed_key(title) not in in_template]
        if missing:
            pywikibot.output(f"有赛季模板但不在该赛季榜单里: {len(missing)} 条，例如："
                             + "；".join(missing[:8]))
        if synced:
            sections = parse_sections(text)
    if "colour" in actions:
        plan = plan_colours(site, sections, legend, cache, exists, participants_of,
                            moe_cache)
        text, coloured = apply_colours(text, plan)
        if coloured:
            sections = parse_sections(text)
        pywikibot.output(f"上色: 处理 {coloured} 个单元格（可自动上色条目 {len(plan)}）")
    if actions & {"counts", "report"}:
        created = compute_created(site, sections, cache, exists, set(plan))
    if "counts" in actions:
        text, changed = recompute_counts(text, created)
        pywikibot.output(f"计数: 更新 {changed} 个小节")
    if "stats" in actions:
        excluded: Dict[str, Counter] = {}
        counts = (count_by_listed(site, sections, legend, cache, participants_of,
                                  songs_of, excluded_of, excluded, moe_cache)
                  if basis == "listed" else count_by_window(site, sections))
        text, _ = render_chart(text, sections, legend, counts, excluded)
        dropped = sum(sum(entry.values()) for entry in excluded.values())
        pywikibot.output(f"统计: 依据 {basis} 重算图表（排除 REMIX/二创 {dropped} 处）")
    if "recredit" in actions:
        text = recredit(site, text, sections, legend, cache, moe_cache,
                        participants_of, songs_of, excluded_of, from_rev)
    if "report" in actions:
        report = build_report(site, sections, legend, cache, exists, plan)
        pywikibot.output("异常报告:\n" + (report or "  （无）"))
    if "moe" in actions:
        report = moegirl_report(site, sections, legend, cache, exists,
                                songs_of, moe_cache)
        pywikibot.output("萌娘百科交叉比对:\n" + (report or "  （无）"))

    save_cache(MOEGIRL_CACHE, moe_cache)
    save_cache(CREATOR_CACHE, cache)

    if actions <= {"report", "moe"}:
        return False
    if text == original:
        pywikibot.output("页面无需更新。")
        return False
    if not write:
        import difflib
        diff = difflib.unified_diff(original.splitlines(), text.splitlines(),
                                    "old", "new", lineterm="")
        pywikibot.output("\n".join(list(diff)[:200]))
        pywikibot.output("\n[dry-run] 加 --write 以保存。")
        return True
    return save_page(page, text, summary)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="all",
                        help="all | one or more of counts,colour,stats,report,moe,recredit "
                             "(comma separated, e.g. counts,colour,report)")
    parser.add_argument("--basis", choices=["listed", "window"], default="listed",
                        help="how to resolve creators when recomputing the chart")
    parser.add_argument("--write", action="store_true", help="save the page (default: dry-run)")
    parser.add_argument("--summary", default=None)
    parser.add_argument("--from-rev", type=int, default=None, dest="from_rev",
                        help="recredit: 用哪一版的图表当迁移基准（版本号）")
    args = parser.parse_args()

    site = pywikibot.Site()
    if args.action == "all":
        actions = set(ALL_ACTIONS)
    else:
        actions = {a.strip() for a in args.action.split(",") if a.strip()}
        unknown = actions - set(ALL_ACTIONS) - set(EXTRA_ACTIONS)
        if not actions or unknown:
            parser.error(f"未知的动作：{', '.join(sorted(unknown)) or args.action}")
    run_once(site, actions, args.basis, args.write, args.summary, args.from_rev)


if __name__ == "__main__":
    main()
