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
  模板里还没有对应页面的标题只报告，不动页面。
* ``counts``  - recompute every section header ``(已创建/总数)``.
* ``colour``  - colour uncoloured cells whose page exists, using the creator's
  colour from the legend.  A link whose target does not exist is matched
  against the real page first (e.g. ``[[FrailLaVillanos]]`` for the existing
  ``FrailL'aVillanos``), and a link that points at a redirect is rewritten to
  its target (``[[毒deンぱ]]`` -> ``[[毒电波]]``); both are corrected while
  colouring.
* ``stats``   - recompute the Echart from creation records (``--basis``).
  A cell's colour is the hand-made creator annotation and wins outright; only
  entries without a colour fall back to the creator of the local page.  Some
  of the chart's numbers come from bookkeeping outside the wiki and cannot be
  derived at all, so a cell is only ever raised, never lowered.
* ``report``  - list anomalies (coloured but page missing / page exists but
  not coloured).
* ``watch``   - near-real-time: poll ``list=recentchanges`` and maintain the
  page whenever a listed entry, or the page itself, changes.  ``--max-runtime``
  lets a CI job bow out before the runner's 6-hour limit so the next trigger
  takes over, which is how the unreliable ``schedule`` event still yields
  near-continuous coverage.

Everything runs in dry-run mode unless ``--write`` is given.

Note on ``--basis window``: it counts pages *created on voca.wiki* inside the
season's calendar window.  voca.wiki imported most pre-2024 entries, so their
first revision timestamps are recent; window counting therefore only produces
meaningful output for seasons that are still running.  ``--basis listed``
(the default) instead resolves the creator of every entry listed in a season's
tables from its local first revision, which works for every season.
"""

from __future__ import annotations

import argparse
import json
import pickle
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import unquote

import pywikibot
from pywikibot import Page
from pywikibot.exceptions import NoPageError

PAGE_TITLE = "Vocawiki:贡献列表/The VOCALOID Collection"
DATA_DIR = Path("data")
CREATOR_CACHE = DATA_DIR / "vocaloid_collection_creators.pickle"
CHART_SERIES_PREFIX = "ボカコレ"

# Bots / import accounts must not appear in the statistics.
KNOWN_BOTS = {
    "AnnAngela-abot", "AnnAngela-bbot", "AnnAngela-bot", "AnnAngela-cbot", "AnnAngela-dbot",
    "Bhsd-bot", "C8H17OH-bot", "Delete page script", "Dm bot", "Eizenchan", "Funce", "LihaohongBot",
    "Senyu-bot", "SinonJZH-bot", "Swampland Robot", "UNC HA Bot", "XzonnBot", "星海-adminbot",
    "星海-interfacebot", "星海-oversightbot", "机娘史蒂文", "机娘史蒂夫", "机娘星海酱", "机娘鬼影233号",
    "滥用过滤器", "萌百娘", "重定向修复器",
}

# Sections whose entries are counted in 相关统计. REMIX and friends are excluded.
def is_counted_section(name: str) -> bool:
    upper = name.upper()
    return upper.startswith("TOP") or upper.startswith("ROOKIE") or name.lower().startswith("neta")


HEX = r"#[0-9A-Fa-f]{3,8}"
TITLE_RE = re.compile(r"\{\{colorlink\|[^|]*\|([^|}]+?)\|[^}]*\}\}|\{\{colorlink\|[^|]*\|([^|}]+?)\}\}|\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
BG_RE = re.compile(r"bgcolor\s*=\s*(%s)|background:\s*linear-gradient\(([^)]*)\)" % HEX)
HEADER_RE = re.compile(r";\s*([A-Za-z0-9]+)\s*\((.*?)/([^)]*)\)")
SEASON_RE = re.compile(r"^===\s*(\d{4}[冬春夏秋])\s*===\s*$", re.M)
CHART_RE = re.compile(r"(\{\{Echart\|data=<nowiki>)(.*?)(</nowiki>)", re.S)

# 每个赛季的榜单模板，如 Template:The VOCALOID Collection2023夏
SEASON_TEMPLATE = "Template:The VOCALOID Collection"
# 模板里 Navbox 子表的标题 -> 贡献列表里的小节名
TEMPLATE_SECTIONS = {"TOP100": "TOP100", "TOP30": "TOP30", "ROOKIE": "ROOKIE",
                     "REMIX": "REMIX", "其他歌曲": "neta"}
TEMPLATE_ITEM_RE = re.compile(r"\|\s*([A-Za-z0-9_]+)\s*=\s*")
GROUP_RANGE_RE = re.compile(r"(\d+)\s*[-–~〜ー]\s*(\d+)\s*位")
LIST_LINK_RE = re.compile(r"\[\[([^\]|]+)(?:\|[^\]]*)?\]\]")
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
    """
    marks = [(m.start(), m.end(), m.group(1)) for m in TEMPLATE_ITEM_RE.finditer(text)]
    result: Dict[str, Dict[int, str]] = defaultdict(dict)
    section: Optional[str] = None
    starts: Dict[str, int] = {}
    for i, (_, end, key) in enumerate(marks):
        stop = marks[i + 1][0] if i + 1 < len(marks) else len(text)
        value = text[end:stop]
        if key == "title":
            section = TEMPLATE_SECTIONS.get(value.strip())
            starts = {}
            continue
        if not section:
            continue
        group = re.fullmatch(r"group(\d+)", key)
        if group:
            rng = GROUP_RANGE_RE.search(value)
            if rng:
                starts[group.group(1)] = (int(rng.group(1)), int(rng.group(2)))
            continue
        listing = re.fullmatch(r"list(\d+)", key)
        if listing and listing.group(1) in starts:
            start, end = starts[listing.group(1)]
            links = [title.strip() for title in LIST_LINK_RE.findall(value) if title.strip()]
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


def template_participants(site, season: str) -> List[str]:
    """Pages that transclude the season's template (i.e. 参加该赛季的歌曲）。"""
    try:
        data = site.simple_request(action="query", list="embeddedin", formatversion="2",
                                   eititle=f"{SEASON_TEMPLATE}{season}", einamespace=0,
                                   eilimit=500).submit()
    except Exception as exc:  # noqa: BLE001
        pywikibot.error(f"{season}: 无法读取模板引用 ({exc})")
        return []
    return [entry["title"] for entry in data.get("query", {}).get("embeddedin", [])]


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
def strip_prefix(user: str) -> str:
    return user.split(">", 1)[1] if ">" in user else user


def load_cache(path: Path) -> Dict[str, Optional[str]]:
    if path.exists():
        try:
            with open(path, "rb") as f:
                return pickle.load(f)
        except Exception:  # noqa: BLE001
            return {}
    return {}


def save_cache(path: Path, cache: Dict[str, Optional[str]]) -> None:
    path.parent.mkdir(exist_ok=True)
    with open(path, "wb") as f:
        pickle.dump(cache, f, protocol=pickle.HIGHEST_PROTOCOL)


def batch_creators(site, titles: Iterable[str], cache: Dict[str, Optional[str]],
                   resolved: Optional[Dict[str, str]] = None) -> None:
    """Fill ``cache`` for many titles using batched oldest-revision queries.

    ``creator_of`` costs one request per song, which makes a cold ``stats`` run
    take minutes; 45 titles per request brings that down to tens of requests.
    Only real answers are cached, so a song that does not exist yet is retried
    on the next run.
    """
    resolved = resolved or {}
    pending: List[str] = []
    for title in titles:
        target = resolved.get(title, title)
        if target and target not in cache and target not in pending:
            pending.append(target)
    for i in range(0, len(pending), 45):
        batch = pending[i:i + 45]
        try:
            data = site.simple_request(action="query", prop="revisions", rvprop="user",
                                       rvlimit=1, rvdir="newer", formatversion=2,
                                       titles="|".join(batch)).submit()
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"批量创建者查询失败: {exc}")
            continue
        query = data.get("query", {})
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        found: Dict[str, Optional[str]] = {}
        for page in query.get("pages", []):
            revisions = page.get("revisions")
            found[page["title"]] = strip_prefix(revisions[0]["user"]) if revisions else None
        for title in batch:
            user = found.get(normalized.get(title, title))
            if user:
                cache[title] = user


def creator_of(site, title: str, cache: Dict[str, Optional[str]]):
    if title in cache:
        return cache[title]
    try:
        revisions = list(Page(site, title).revisions(total=1, reverse=True, content=False))
        user = strip_prefix(revisions[0]["user"]) if revisions else None
    except NoPageError:
        # 不缓存：条目可能马上就要被创建（否则会把"还没建"记成永久结论）
        return None
    except Exception as exc:  # noqa: BLE001
        pywikibot.error(f"{title}: {exc}")
        return None  # do not cache transient failures
    if user:
        cache[title] = user
    return user


def batch_exists(site, titles: Iterable[str], exists: Dict[str, bool],
                 resolved: Optional[Dict[str, str]] = None) -> None:
    """Fill ``exists`` for many titles using batched ``prop=info`` queries.

    When ``resolved`` is given it also records which titles are redirects and
    what they point at, so the caller can both credit the real page's creator
    and point the link straight at it (the page has dozens of romanised
    redirect titles).
    """
    pending = [t for t in dict.fromkeys(titles) if t not in exists]
    for i in range(0, len(pending), 50):
        batch = pending[i:i + 50]
        try:
            data = site.simple_request(action="query", prop="info", redirects=1,
                                       formatversion=2, titles="|".join(batch)).submit()
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"批量存在性查询失败: {exc}")
            continue
        query = data.get("query", {})
        normalized = {n["from"]: n["to"] for n in query.get("normalized", [])}
        redirected = {r["from"]: r["to"] for r in query.get("redirects", [])}
        pages = query.get("pages", [])
        if isinstance(pages, dict):
            pages = list(pages.values())
        present = {p["title"]: not p.get("missing") for p in pages}
        for title in batch:
            key = normalized.get(title, title)
            final = redirected.get(key, key)
            exists[title] = present.get(final, False)
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
    sweep is cached, so a long-running ``watch`` process does not repeat it.
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
                    cache: Dict[str, Optional[str]]) -> Dict[str, Counter]:
    result: Dict[str, Counter] = defaultdict(Counter)
    seen: Dict[str, set] = defaultdict(set)
    counted = [s for s in sections if is_counted_section(s.name)]
    exists: Dict[str, bool] = {}
    resolved: Dict[str, str] = {}
    batch_exists(site, (e.title for s in counted for e in s.entries), exists, resolved)
    # 先把要按"谁建的页面"归属的条目一次性查出来，避免每条一次请求
    batch_creators(site, (e.title for s in counted for e in s.entries
                          if not e.colours and exists.get(e.title)), cache, resolved)
    for section in counted:
        for entry in section.entries:
            if entry.title in seen[section.season]:  # a song counts once per season
                continue
            seen[section.season].add(entry.title)
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
            target = resolved.get(entry.title, entry.title)
            user = creator_of(site, target, cache)
            if user and user not in KNOWN_BOTS:
                result[section.season][legend.identity(user)] += 1
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


def render_chart(text: str, sections: List[Section], legend: Legend,
                 counts: Dict[str, Counter]) -> Tuple[str, dict]:
    match = CHART_RE.search(text)
    if not match:
        raise RuntimeError("未找到 {{Echart}} - 页面结构可能已改变")
    chart = json.loads(match.group(2))
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

    palette = [s.get("itemStyle", {}).get("color") for s in chart["series"]]
    series_by_label = {s["name"]: s for s in chart["series"]}
    # 有些数字来自站外的人工记账（既没上色、本地也没页面），任何算法都推不出来，
    # 所以只在机器人算得更多时提高，绝不把人工数字改小。
    kept: Dict[str, Dict[str, int]] = {}
    for label, series in series_by_label.items():
        for name, value in zip(yaxis, series.get("data", [])):
            if value:
                kept.setdefault(label, {})[name] = value

    users = [u for u in yaxis if totals[u] >= 5 or any(u in kept.get(l, {}) for l in labels)]
    users += sorted((u for u in totals if totals[u] >= 5 and u not in users),
                    key=lambda u: (-totals[u], u))

    manual = 0
    new_series = []
    for index, label in enumerate(labels):
        season = seasons[index]
        colour = series_by_label.get(label, {}).get("itemStyle", {}).get("color")
        if colour is None:
            colour = palette[index % len(palette)] if palette else "#888888"
        data = []
        for user in users:
            computed = per_season[season].get(user, 0)
            previous = kept.get(label, {}).get(user, 0)
            if previous > computed:
                manual += 1
            data.append(max(computed, previous))
        new_series.append({
            "name": label,
            "type": "bar",
            "stack": "total",
            "itemStyle": {"color": colour},
            "label": {"formatter": " {c} ", "distance": 0, "backgroundColor": "white",
                      "fontWeight": "bold", "borderColor": "auto", "borderWidth": 1.2,
                      "borderRadius": 10, "lineHeight": 16, "padding": [1, 0, 0, 0]},
            "emphasis": {"label": {"show": True}},
            "data": data,
        })
    new_series += [s for s in chart["series"] if s["name"] not in labels]
    if manual:
        pywikibot.output(f"统计: 保留 {manual} 个机器人推不出来的人工数字")

    chart["legend"]["data"] = labels
    chart["yAxis"]["data"] = users
    chart["series"] = new_series
    rendered = json.dumps(chart, ensure_ascii=False, separators=(",", ":"))
    return text[:match.start(2)] + rendered + text[match.end(2):], chart


# --------------------------------------------------------------------------- #
# colour
# --------------------------------------------------------------------------- #
def text_colour(background: str) -> str:
    """Pick black or white text for a background hex colour."""
    r, g, b = (int(background[i:i + 2], 16) for i in (1, 3, 5))
    luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
    return "#000" if luminance > 0.6 else "#FFF"


def plan_colours(site, sections: List[Section], legend: Legend,
                 cache: Dict[str, Optional[str]],
                 exists: Dict[str, bool]) -> Dict[str, Tuple[str, str]]:
    """entry title -> (background colour, page title to link to).

    Only entries whose page exists are coloured; a link whose target does not
    exist is matched against the real title first and corrected in the same
    edit (``[[FrailLaVillanos]]`` -> ``[[FrailL'aVillanos]]``).
    """
    uncoloured = [e for s in sections for e in s.entries if not e.colours]
    resolved: Dict[str, str] = {}
    batch_exists(site, (e.title for e in uncoloured), exists, resolved)
    index: Optional[Dict[str, str]] = None
    plan: Dict[str, Tuple[str, str]] = {}
    targets: Dict[str, str] = {}
    for entry in uncoloured:
        if not page_exists(site, entry.title, exists):
            continue
        # 链接指向重定向时按真页面取创建者，并把链接改写成真标题
        targets[entry.title] = resolved.get(entry.title, entry.title)
    batch_creators(site, targets.values(), cache)
    for entry in uncoloured:
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
        user = creator_of(site, target, cache)
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
ALL_ACTIONS = ("entries", "counts", "colour", "stats", "report")
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


def save_page(page: Page, text: str, summary: Optional[str]) -> None:
    """Save with the bot/tags flags, degrading gracefully if not permitted."""
    page.text = text
    summary = summary or DEFAULT_SUMMARY
    try:
        page.save(summary=summary, minor=True, bot=True, tags="Bot")
        return
    except TypeError:  # older pywikibot: ``bot`` is named ``botflag``
        page.save(summary=summary, minor=True, botflag=True, tags="Bot")
        return
    except pywikibot.exceptions.APIError as exc:
        # the account may lack the "bot" right or the "changetags" right
        pywikibot.error(f"带 bot/tags 保存失败，改用普通保存重试：{exc}")
    page.save(summary=summary, minor=True)


def run_once(site, actions, basis: str = "listed", write: bool = False,
             summary: Optional[str] = None) -> bool:
    """Run one maintenance pass.  Returns True when the page would change."""
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
    text = original
    created = None
    plan: Dict[str, Tuple[str, str]] = {}
    exists: Dict[str, bool] = {}
    if "entries" in actions:
        # 赛季模板是「哪些歌、第几名、条目该叫什么」的权威来源：只要模板里的标题
        # 有对应页面，就把名次格子统一改写成规范标题（重定向写法一并归一），
        # 模板里还没有页面的标题只报告、不动。
        wanted = season_templates(site, dict.fromkeys(s.season for s in sections))
        diffs = entry_diffs(text, wanted)
        fixes: Dict[Tuple[str, str, int], str] = {}
        repaired = 0
        normalised = 0
        if diffs:
            probe: Dict[str, bool] = {}
            redirects: Dict[str, str] = {}
            batch_exists(site, [d[3] for d in diffs] + [d[4] for d in diffs], probe, redirects)
            for season, name, rank, current, want in diffs:
                if not probe.get(want):
                    continue  # 模板里的标题还没有页面，不动页面
                # 模板标题本身可能是重定向（"ダウナ" 指回 "Downa"），要取最终页面，
                # 否则会把链接改成一个绕回原地的重定向。
                target = redirects.get(want, want)
                if target == current:
                    continue
                fixes[(season, name, rank)] = target
                if not probe.get(current):
                    repaired += 1
                else:
                    normalised += 1
        text, synced, notes = sync_entries(text, fixes)
        pywikibot.output(f"条目: 赛季模板对比出 {len(diffs)} 处差异，改写 {synced} 个名次"
                         f"（死链修复 {repaired}，统一成规范标题 {normalised}）")
        for note in notes[:20]:
            pywikibot.output(f"  {note}")
        if len(notes) > 20:
            pywikibot.output(f"  ……另有 {len(notes) - 20} 处未逐条列出")
        missing = [f"{season}/{title}" for season, secs in wanted.items()
                   for title in sorted(set(template_participants(site, season))
                                       - {t for ranks in secs.values() for t in ranks.values()}
                                       - {"The VOCALOID Collection"})]
        if missing:
            pywikibot.output(f"有赛季模板但不在该赛季榜单里: {len(missing)} 条，例如："
                             + "；".join(missing[:8]))
        if synced:
            sections = parse_sections(text)
    if "colour" in actions:
        plan = plan_colours(site, sections, legend, cache, exists)
        text, coloured = apply_colours(text, plan)
        pywikibot.output(f"上色: 处理 {coloured} 个单元格（可自动上色条目 {len(plan)}）")
    if actions & {"counts", "report"}:
        created = compute_created(site, sections, cache, exists, set(plan))
    if "counts" in actions:
        text, changed = recompute_counts(text, created)
        pywikibot.output(f"计数: 更新 {changed} 个小节")
    if "stats" in actions:
        counts = (count_by_listed(site, sections, legend, cache)
                  if basis == "listed" else count_by_window(site, sections))
        text, _ = render_chart(text, sections, legend, counts)
        pywikibot.output(f"统计: 依据 {basis} 重算图表")
    if "report" in actions:
        report = build_report(site, sections, legend, cache, exists, plan)
        pywikibot.output("异常报告:\n" + (report or "  （无）"))

    save_cache(CREATOR_CACHE, cache)

    if actions == {"report"}:
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
    save_page(page, text, summary)
    return True


def watch(site, *, interval: float, settle: float, stats_interval: float,
          basis: str, write: bool, summary: Optional[str],
          max_runtime: float = 0) -> None:
    """Near-real-time mode: poll recent changes and maintain the page on the fly.

    voca.wiki runs no EventStreams/EventBus, so there is no push stream; polling
    ``list=recentchanges`` every few seconds is the closest available.
    ``max_runtime`` (seconds, 0 = forever) makes the loop return on its own so a
    CI job can bow out before the runner's hard limit kills it.
    """
    page = Page(site, PAGE_TITLE)
    relevant: set = set()
    deadline = time.monotonic() + max_runtime if max_runtime else 0.0

    def refresh() -> None:
        nonlocal relevant
        relevant = {e.title for s in parse_sections(page.text) for e in s.entries}

    refresh()
    pywikibot.output(f"监听 {PAGE_TITLE}：{len(relevant)} 个条目，轮询间隔 {interval}s"
                     + (f"，本次最多运行 {max_runtime:.0f}s" if deadline else ""))

    seen: set = set()
    last_ts = pywikibot.Timestamp.now() - timedelta(seconds=60)
    dirty = False
    last_relevant = 0.0
    actions = {"entries", "counts", "colour", "report"}

    # 立刻跑一轮，并带上 stats：定时事件很稀疏，每次开工都该把图表刷到最新，
    # 之后才受 stats_interval 节流（批量取创建者后这一轮很便宜）
    run_once(site, actions | {"stats"}, basis, write, summary)
    last_stats = time.monotonic()

    while True:
        if deadline and time.monotonic() >= deadline:
            pywikibot.output("本轮监听结束，交给下一次触发。")
            return
        try:
            for rc in site.recentchanges(namespaces=[0], start=last_ts, reverse=True):
                key = rc.get("rcid") or (rc.get("title"), str(rc.get("timestamp")), rc.get("user"))
                if key in seen:
                    continue
                seen.add(key)
                timestamp = rc.get("timestamp")
                if timestamp and timestamp > last_ts:
                    last_ts = timestamp
                title = rc.get("title")
                if title == PAGE_TITLE or title in relevant:
                    dirty = True
                    last_relevant = time.monotonic()
                    pywikibot.output(f"检测到变更: {title}（{rc.get('user')}）")
        except KeyboardInterrupt:
            raise
        except Exception as exc:  # noqa: BLE001
            pywikibot.error(f"读取最近更改失败: {exc}")

        if len(seen) > 20000:
            seen.clear()

        if dirty and time.monotonic() - last_relevant >= settle:
            todo = set(actions)
            if time.monotonic() - last_stats >= stats_interval:
                todo.add("stats")
                last_stats = time.monotonic()
            try:
                run_once(site, todo, basis, write, summary)
                refresh()
            except Exception as exc:  # noqa: BLE001
                pywikibot.error(f"维护失败: {exc}")
            dirty = False

        time.sleep(interval)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", nargs="?", default="all",
                        help="all | watch | one or more of counts,colour,stats,report "
                             "(comma separated, e.g. counts,colour,report)")
    parser.add_argument("--basis", choices=["listed", "window"], default="listed",
                        help="how to resolve creators when recomputing the chart")
    parser.add_argument("--write", action="store_true", help="save the page (default: dry-run)")
    parser.add_argument("--summary", default=None)
    parser.add_argument("--interval", type=float, default=20,
                        help="watch: seconds between recent-changes polls (default 20)")
    parser.add_argument("--settle", type=float, default=15,
                        help="watch: wait this long after the last relevant change (default 15)")
    parser.add_argument("--stats-interval", type=float, default=1800,
                        help="watch: minimum seconds between chart recomputations (default 1800)")
    parser.add_argument("--max-runtime", type=float, default=0,
                        help="watch: give up after this many seconds (0 = run forever); "
                             "used by CI so a long job ends before the 6h runner limit")
    args = parser.parse_args()

    site = pywikibot.Site()
    if args.action == "watch":
        try:
            watch(site, interval=args.interval, settle=args.settle,
                  stats_interval=args.stats_interval, basis=args.basis,
                  write=args.write, summary=args.summary,
                  max_runtime=args.max_runtime)
        except KeyboardInterrupt:
            pywikibot.output("已停止监听。")
        return
    if args.action == "all":
        actions = set(ALL_ACTIONS)
    else:
        actions = {a.strip() for a in args.action.split(",") if a.strip()}
        unknown = actions - set(ALL_ACTIONS)
        if not actions or unknown:
            parser.error(f"未知的动作：{', '.join(sorted(unknown)) or args.action}")
    run_once(site, actions, args.basis, args.write, args.summary)


if __name__ == "__main__":
    main()
