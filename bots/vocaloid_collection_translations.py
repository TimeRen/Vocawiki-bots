# -*- coding: utf-8 -*-
"""维护 [[User:周某不是轴某/VOCALOID collection搜集库]] 的「翻译来源」一栏。

页面是《The VOCALOID Collection》各季榜单的表：每行一首「还没有条目」的歌，
列是 名次 / 曲名 / P主 / 条目状态 / 翻译来源 / 备注。机器人只填**空着的**
「翻译来源」，从不覆盖别人写的内容。

一首歌去哪里找译文（按可靠程度排序，最多记三条）：

* **VOCALOID中文歌词wiki（AtWiki）**：拿页面名去比「全ページ一覧」的 8553 个页面名
  （名字完全一致才算），**并且页面正文的作詞 / 作曲里要有这首歌的 P主**——同名的
  不同曲太多（`Linaria` 那一页是 Mysteka 的、`EDEN` 是 真尋P 的）。再读页面里的
  ``翻譯：某人`` 作署名。这是最可靠的来源。
* **网易云音乐**：`/api/search/get` 搜日文名 / 中文名，标题对上**且** P主 出现在
  歌手或专辑名里才用（只有标题对上不够：同名不同曲太多）；`/api/song/lyric` 里有
  ``tlyric``（确实有译文）才记，译者取 ``transUser``（其次 ``lyricUser``）。
* **B站**：先看 voca 条目 Songbox 里的 ``bb_id``（本家投稿），再用站内搜索找
  「歌名 翻译」的视频；**搜来的视频要标题 / 简介里同时出现歌名和 P主**，否则
  ``RITA`` 会搜到 TED 演讲的翻译视频、``亡灵`` 会搜到有声书。对上以后读简介、
  前几页评论、弹幕：出现 `翻译：X` / `翻譯：X` / `译：X` 才记，并记下是谁说的。
* **巴哈姆特**：它的站内搜索是纯前端渲染，抓不到结果，所以改成**顺着链接找**：
  上面那些页面的正文 / 简介里出现的 ``home.gamer.com.tw/artwork.php?sn=…``
  链接，逐个抓下来核对标题与译者署名。
* **B站笔记 / 专栏**：同上，顺着 ``bilibili.com/opus/…``、``/read/cv…`` 链接找。

「标题对上」用 ``title_key()``（全半角、大小写、空白、``{{lj|…}}``、括号消歧后缀
都归一化）。查不到就留空——宁可少填，也不要把别人的翻译安到另一首歌上。

**补录未录入的曲目**（``--add-missing``）：搜集库只收「外站已经有译文」的歌，所以
拿活动清单反查——[[Vocawiki:贡献列表/The VOCALOID Collection]] 的赛季表列出每个赛季
每条赛道 100 格的曲名与名次（``[[曲名|名次]]`` 是还没条目、``{{colorlink|…}}`` 是
已经有条目），大家族模板 ``Template:The VOCALOID Collection2023春`` 给出条目名对应的
日文原名。某首歌如果还没条目、搜集库也没录入、而 AtWiki 查得到（页面名对上，从
作詞 / 作曲 里取 P主、从 ``翻譯：`` 里取译者），就按名次插进对应赛季的表格。

2026-10-22 页面上「已创建 ⇒ 手工删行」的差异也据此处理：**已经有条目的歌不会补回来**
（``created`` 标记 + 曲名在页面上 + 同赛道名次已存在 + ``{{注|N|总榜为第M}}`` 记过的
总榜名次，四种情况都算「已录入」）。同一首歌只录一次：以 ROOKIE 行录入时用
``{{注}}`` 标总榜，就不会再补一行 TOP100 的重复条目。

**维护自己的写法**：机器人只改两种格子——空的，和自己写过的（内容与缓存里记过的
``sources`` / ``written`` 逐字相同）。这些格子会随新结论更新 / 清空；别人写过的
格子一个字都不碰，**哪怕格式和机器人一模一样**（页面主人也按
``[链接 说明(by. 译者)]`` 写）。判定规则变化时把 ``CACHE_VERSION`` 加一。

缓存丢了（换了运行环境）就认不出自己写过的格子，那些格子会被当成「别人的」不动
——这是有意的：宁可少更新，也不能覆盖别人的来源。``--refresh`` 只跳过「缓存还有效
就不再查」，不会丢缓存。

结果（含「查过、没有」）缓存在 ``data/vocaloid_collection_translations.pickle``，
默认 14 天后重新核对；AtWiki 页面清单缓存 7 天。

Everything is a dry run unless ``--write`` is given.
"""

from __future__ import annotations

import argparse
import http.cookiejar
import json
import pickle
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
import zlib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Set, Tuple

import pywikibot
from pywikibot import Page
from pywikibot.exceptions import EditConflictError

PAGE_TITLE = "User:周某不是轴某/VOCALOID collection搜集库"
DEFAULT_SUMMARY = "补充「翻译来源」（机器人按 B站 / 中文歌词wiki / 网易云 / 巴哈姆特 自动核对）"

DATA_DIR = Path("data")
CACHE = DATA_DIR / "vocaloid_collection_translations.pickle"
ATWIKI_CACHE = DATA_DIR / "vocaloid_collection_translations_atwiki.pickle"

CACHE_TTL = 14 * 24 * 3600          # 一首歌多久重新核对一次
ATWIKI_TTL = 7 * 24 * 3600          # AtWiki 页面清单多久重建一次
CACHE_VERSION = 4                   # 判定规则变了就 +1，旧缓存自动作废
REQUEST_TIMEOUT = 25
FAILURE_LIMIT = 5                   # 同一个站连错几次就整轮不再查
MAX_SOURCES = 3

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

# 表格结构：每侧 6 列，翻译来源是第 5 列（下标 4）
COLUMNS = ("rank", "title", "producer", "status", "source", "note")
SOURCE_INDEX = COLUMNS.index("source")
PER_SIDE = len(COLUMNS)

ATWIKI_BASE = "https://w.atwiki.jp/vocaloidchly"
ATWIKI_LIST = ATWIKI_BASE + "/list?sort=pagename"
ATWIKI_PAGE = ATWIKI_BASE + "/pages/{pid}.html"
ATWIKI_MAX_PAGES = 500

NETEASE_SEARCH = "https://music.163.com/api/search/get?s={kw}&type=1&limit=10"
NETEASE_LYRIC = "https://music.163.com/api/song/lyric?os=pc&id={id}&lv=-1&kv=-1&tv=-1"
NETEASE_SONG = "https://music.163.com/#/song?id={id}"

BILIBILI_SEARCH = ("https://api.bilibili.com/x/web-interface/search/type"
                   "?search_type=video&keyword={kw}&page=1")
BILIBILI_VIEW = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
BILIBILI_REPLY = "https://api.bilibili.com/x/v2/reply?type=1&oid={oid}&ps=20&pn={pn}&sort=2"
BILIBILI_DANMAKU = "https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"
BILIBILI_VIDEO = "https://www.bilibili.com/video/{bvid}"

# 译者署名的写法：`翻譯：yanao`、`翻译: 某人`、`译 person`、`譯者：某人`
# 必须有冒号：「谷歌翻译成英文后……」这类句子里的「翻译」不是署名
CREDIT_RE = re.compile(
    r"(?:翻\s*[譯译]|譯\s*者|译\s*者|中\s*文\s*歌\s*[詞词]|嵌\s*字|CC\s*字幕|授\s*[權权])"
    r"\s*[:：]\s*(?P<name>[^\s,，、;；|/\\()（）\[\]【】<>:：]{1,20})", re.IGNORECASE)
# 常见的「这不是译文」的署名，别把它们当译者
NOT_TRANSLATOR = ("无", "暫無", "暂无", "待补", "待補", "未知", "不详", "不詳", "见简介",
                  "見簡介", "同上", "略", "本人", "作者", "原曲", "n/a", "none")

ATWIKI_BODY_RE = re.compile(
    r'<div id="wikibody"[^>]*>\s*(?:<!--@@@@@-->)?(.*?)'
    r'(?:<div class="atwiki-page-keyword">|<div id="ads">|<div id="body_footer">)', re.S)
ATWIKI_ROW_RE = re.compile(
    r'<a href="(?:https?:)?//w\.atwiki\.jp/vocaloidchly/pages/(\d+)\.html"[^>]*>\s*(.*?)\s*</a>',
    re.S)
ATWIKI_LIST_RE = re.compile(r'<table class="pagelist">(.*?)</table>', re.S)
ATWIKI_LAST_RE = re.compile(r"\?sort=pagename&(?:amp;)?pp=(\d+)")

LJ_RE = re.compile(r"\{\{lj\|([^{}]*)\}\}")
LINK_RE = re.compile(r"\[\[([^\]|]*)(?:\|([^\]]*))?\]\]")
COMMENT_RE = re.compile(r"<!--.*?-->", re.S)
TAG_RE = re.compile(r"<[^>]+>")
PAREN_SUFFIX_RE = re.compile(r"^(?P<base>.+?)\s*[(（][^()（）]+[)）]$")
EXTERNAL_LINK_RE = re.compile(r"\[(https?://[^\s\]]+)\s*([^\]]*)\]")
BARE_URL_RE = re.compile(r"https?://[^\s\)\]（）<>\"']+")
GAMER_URL_RE = re.compile(r"https?://home\.gamer\.com\.tw/artwork\.php\?sn=\d+")
OPUS_URL_RE = re.compile(r"https?://(?:www\.)?bilibili\.com/(?:opus/\d+|read/cv\d+)")
DANMAKU_RE = re.compile(r"<d p=\"[^\"]*\">([^<]*)</d>")


# ---------------------------------------------------------------- 名字归一化

def title_key(text: str) -> str:
    """比对用的歌名：全半角统一、去掉标记 / 空白 / 括号消歧后缀、转小写。

    ``{{lj|[[Meromu]]}}``、``[[ Meromu]]``、``[[潘多拉(buzzG)|潘多拉]]`` 都要能比得上。
    """
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = COMMENT_RE.sub("", text)
    text = LJ_RE.sub(lambda m: m.group(1), text)
    text = LINK_RE.sub(lambda m: (m.group(2) or m.group(1) or ""), text)
    text = TAG_RE.sub("", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\s+", "", text)
    text = text.strip("*")
    match = PAREN_SUFFIX_RE.match(text)
    if match:
        text = match.group("base")
    return text.lower()


def person_key(name: str) -> str:
    """比对用的 P主 / 歌手名：和 ``title_key()`` 同一套归一化，另去掉 ``{{…|名字}}`` 外壳。

    ``{{lj|かぁ君}}``、``EO({{lj|エオ}})``、``buzzG`` 都要能和对得上。
    """
    text = str(name or "")
    for _ in range(3):                  # {{lj|甲}} → 甲
        replaced = re.sub(r"\{\{[^{}]*\|([^{}]*)\}\}",
                          lambda m: m.group(1), text)
        if replaced == text:
            break
        text = replaced
    return title_key(text)


def link_target(cell: str) -> str:
    """``{{lj|[[Meromu]]}}`` → ``Meromu``（链接目标；没有链接时就是单元格文字）。"""
    text = COMMENT_RE.sub("", str(cell or ""))
    link = LINK_RE.search(text)
    if link:
        return link.group(1).strip()
    text = LJ_RE.sub(lambda m: m.group(1), text)
    return TAG_RE.sub("", text).strip()


def link_display(cell: str) -> str:
    """``[[潘多拉(buzzG)|潘多拉]]`` → ``潘多拉``（没有显示文字时就是目标）。"""
    text = COMMENT_RE.sub("", str(cell or ""))
    link = LINK_RE.search(text)
    if link:
        return (link.group(2) or link.group(1)).strip()
    return link_target(cell)


# ---------------------------------------------------------------- 表格读写

@dataclass
class Cell:
    lead: str
    value: str
    trail: str


@dataclass
class Row:
    line: int                       # 在整页 wikitext 的行下标
    cells: List[Cell]
    sides: int

    def cell(self, side: int, column: int) -> Optional[Cell]:
        index = side * PER_SIDE + column
        return self.cells[index] if index < len(self.cells) else None

    def text(self, side: int, column: int) -> str:
        cell = self.cell(side, column)
        return cell.value if cell else ""

    def source_index(self, side: int) -> int:
        return side * PER_SIDE + SOURCE_INDEX


@dataclass
class Song:
    line: int
    side: int
    rank: str
    title_target: str
    title_display: str
    producer: str

    @property
    def key(self) -> str:
        return title_key(self.title_display) or title_key(self.title_target)


def split_row(line: str) -> List[Cell]:
    """把一行表格拆成单元格（按**顶层**的 ``||``，不改动原有空白）。"""
    pieces: List[str] = []
    current: List[str] = []
    depth = 0
    index = 0
    body = line[1:] if line.startswith("|") else line
    while index < len(body):
        if body.startswith("{{", index) or body.startswith("[[", index):
            depth += 1
            current.append(body[index:index + 2])
            index += 2
        elif body.startswith("}}", index) or body.startswith("]]", index):
            depth = max(0, depth - 1)
            current.append(body[index:index + 2])
            index += 2
        elif body.startswith("||", index) and depth == 0:
            pieces.append("".join(current))
            current = []
            index += 2
        else:
            current.append(body[index])
            index += 1
    pieces.append("".join(current))
    return [_cell(piece) for piece in pieces]


def _cell(piece: str) -> Cell:
    lead = len(piece) - len(piece.lstrip())
    trail = len(piece) - len(piece.rstrip())
    if lead + trail > len(piece):       # 整格都是空白：别让首尾各吃掉一次
        lead, trail = len(piece), 0
    return Cell(piece[:lead], piece.strip(),
                piece[len(piece) - trail:] if trail else "")


def join_row(cells: Sequence[Cell]) -> str:
    return "|" + "||".join(cell.lead + cell.value + cell.trail for cell in cells)


def parse_rows(text: str) -> Tuple[List[Row], Dict[int, int]]:
    """整页 → ``(行列表, {行下标: 每侧列数})``。

    「每侧列数」由表头决定（``colspan`` 决定有几侧，表头单元格数 / 侧数 = 每侧列数）；
    现在的页面一律是 6 列、1~2 侧，但按表头算可以让以后改表时不必改代码。
    """
    lines = text.split("\n")
    rows: List[Row] = []
    sides_of: Dict[int, int] = {}
    sides = 1
    per_side = PER_SIDE
    for index, line in enumerate(lines):
        stripped = line.strip()
        if stripped.startswith("! colspan"):
            sides = max(1, len(re.findall(r'colspan="\d+"', stripped)))
        elif stripped.startswith("! 名次"):
            header_cells = [c for c in stripped.lstrip("!").split("!!") if c.strip()]
            if header_cells:
                sides = max(1, min(sides, len(header_cells)))
                per_side = max(1, len(header_cells) // sides)
        elif stripped.startswith("|-"):
            continue
        elif stripped.startswith("|}"):
            sides, per_side = 1, PER_SIDE
        elif stripped.startswith("|") and not stripped.startswith("|+"):
            cells = split_row(line)
            if per_side != PER_SIDE:            # 表结构变了：至少把多出来的列补上
                while len(cells) < sides * per_side:
                    cells.append(Cell(" ", "", ""))
            rows.append(Row(index, cells, sides))
            sides_of[index] = per_side
    return rows, sides_of


def songs_from(text: str) -> List[Song]:
    """页面里所有「有曲名」的行（名次空、曲名空的续行跳过）。"""
    rows, _ = parse_rows(text)
    songs: List[Song] = []
    for row in rows:
        for side in range(row.sides):
            title = row.text(side, COLUMNS.index("title")).strip()
            target = link_target(title)
            if not target or target in ("曲名(无翻译则原名字)", "曲名"):
                continue
            display = link_display(title)
            if not display or display.startswith("{{"):
                continue
            songs.append(Song(row.line, side,
                              row.text(side, COLUMNS.index("rank")).strip(),
                              target, display,
                              row.text(side, COLUMNS.index("producer")).strip()))
    return songs


def apply_fills(text: str, fills: Dict[Tuple[int, int], str]) -> str:
    """把 ``{(行下标, 侧): 单元格内容}`` 写回 wikitext，其余字节原样保留。"""
    if not fills:
        return text
    lines = text.split("\n")
    by_line: Dict[int, Dict[int, str]] = {}
    for (line, side), value in fills.items():
        by_line.setdefault(line, {})[side] = value
    for line, per_side in by_line.items():
        cells = split_row(lines[line])
        needed = max(side for side in per_side) * PER_SIDE + SOURCE_INDEX + 1
        while len(cells) < needed:
            cells.append(Cell(" ", "", ""))
        for side, value in per_side.items():
            index = side * PER_SIDE + SOURCE_INDEX
            cell = cells[index]
            if not cell.lead:
                cell.lead = " "
            if not cell.trail:
                cell.trail = " "
            cell.value = value
        lines[line] = join_row(cells)
    return "\n".join(lines)


# ---------------------------------------------------------------- 赛季清单
#
# 搜集库只收「外站已经有译文」的曲目，所以要拿活动清单反查：哪些歌还没条目、
# 而且外站查得到翻译，却没被录进搜集库。
#
# 清单有两处：
#   * [[Vocawiki:贡献列表/The VOCALOID Collection]]——按赛季分节，每节按赛道
#     （TOP100 / ROOKIE / TOP30）列出 100 格：``[[曲名|名次]]`` 表示还没条目，
#     ``{{colorlink|#色|曲名|名次}}`` 表示已被某位用户创建（颜色是创建者）。
#   * 大家族模板 ``Template:The VOCALOID Collection2023春`` 等——条目名 ↔ 日文原名，
#     拿日文原名才能和 AtWiki 的页面名对上。

CONTRIB_PAGE = "Vocawiki:贡献列表/The VOCALOID Collection"
NAVBOX_TEMPLATE = "Template:The VOCALOID Collection{season}"
SEASONS_CACHE = DATA_DIR / "vocaloid_collection_seasons.pickle"
SEASONS_TTL = 7 * 24 * 3600         # 活动清单多久重新抓一次

SEASON_HEADING_RE = re.compile(r"^==\s*(ボカコレ[^=\n]+?)\s*==\s*$", re.M)
CONTRIB_HEADING_RE = re.compile(r"^===\s*([^=\n]+?)\s*===\s*$", re.M)
TRACK_SPLIT_RE = re.compile(r";(TOP\d+|ROOKIE|REMIX)[^\n]*")
NOTE_OVERALL_RE = re.compile(r"\{\{注\|\s*\d+\s*\|\s*总榜为第?\s*(\d+)")
COLORLINK_CELL_RE = re.compile(r"\{\{colorlink\|[^|]*\|(?P<title>.+?)\|(?P<rank>\d+)\}\}")
RANK_LINK_CELL_RE = re.compile(r"\[\[(?P<title>[^\]|]+)\|(?P<rank>\d+)\]\]")
LJ_LINK_PAIR_RE = re.compile(r"\{\{lj\|\[\[(?P<target>[^\]|]+)(?:\|(?P<alias>[^\]]*))?\]\]\}\}")
LINK_PAIR_RE = re.compile(r"\[\[(?P<target>[^\]|]+)(?:\|(?P<alias>[^\]]*))?\]\]")
CREDIT_LINE_RE = re.compile(r"^\s*(?:作\s*[詞词]|作\s*曲)\s*[:：]\s*(?P<name>[^\n]{1,60})$", re.M)
COMPOSE_LINE_RE = re.compile(r"^\s*作\s*曲\s*[:：]\s*(?P<name>[^\n]{1,60})$", re.M)


@dataclass
class SeasonSong:
    """活动清单里的一格：某个赛季、某条赛道、某个名次上的歌。"""

    season: str                 # ``ボカコレ2022春``
    track: str                  # ``TOP100`` / ``ROOKIE`` / ``TOP30``
    rank: int
    title: str                  # 条目名（还没条目时就是日文名或暂定名）
    created: bool = False


def split_sections(text: str, pattern: re.Pattern) -> List[Tuple[str, str]]:
    """按 ``== 标题 ==`` 切分 → ``[(标题, 正文)]``（正文不含标题行）。"""
    marks = [(m.group(1), m.start(), m.end()) for m in pattern.finditer(text)]
    sections: List[Tuple[str, str]] = []
    for index, (name, _start, end) in enumerate(marks):
        stop = marks[index + 1][1] if index + 1 < len(marks) else len(text)
        sections.append((name, text[end:stop]))
    return sections


def section_sides(body: str) -> List[str]:
    """表头 ``! colspan="6"|TOP100 !! colspan="6"|ROOKIE`` → ``["TOP100", "ROOKIE"]``。"""
    labels = re.findall(r'! colspan="\d+"\s*\|\s*([^!\n|]+)', body)
    return [label.strip() for label in labels]


def parse_track_cells(body: str) -> Dict[int, Tuple[str, bool]]:
    """一条赛道的表格正文 → ``{名次: (曲名, 是否已有条目)}``。"""
    cells: Dict[int, Tuple[str, bool]] = {}
    for match in COLORLINK_CELL_RE.finditer(body):
        title = link_target(match.group("title")) or match.group("title").strip()
        cells[int(match.group("rank"))] = (title, True)
    for match in RANK_LINK_CELL_RE.finditer(body):
        rank = int(match.group("rank"))
        if rank in cells:               # colorlink 里的内层链接已经算过
            continue
        cells[rank] = (match.group("title").strip(), False)
    return cells


def parse_contrib_seasons(text: str) -> Dict[str, Dict[str, Dict[int, Tuple[str, bool]]]]:
    """贡献列表 → ``{赛季: {赛道: {名次: (曲名, 是否已有条目)}}}``。"""
    seasons: Dict[str, Dict[str, Dict[int, Tuple[str, bool]]]] = {}
    for name, body in split_sections(text, CONTRIB_HEADING_RE):
        parts = TRACK_SPLIT_RE.split(body)
        tracks: Dict[str, Dict[int, Tuple[str, bool]]] = {}
        for track, chunk in zip(parts[1::2], parts[2::2]):
            cells = parse_track_cells(chunk)
            if cells:
                tracks[track] = cells
        if tracks:
            seasons["ボカコレ" + name] = tracks
    return seasons


def navbox_names(text: str) -> Dict[str, str]:
    """大家族模板 → ``{归一化条目名: 日文原名}``（``{{lj|[[中文名|日文名]]}}``）。"""
    names: Dict[str, str] = {}
    for match in LJ_LINK_PAIR_RE.finditer(text):
        target, alias = match.group("target"), match.group("alias") or ""
        if alias and title_key(target) and title_key(target) != title_key(alias):
            names[title_key(target)] = alias.strip()
        elif alias and not names.get(title_key(alias)):
            names.setdefault(title_key(alias), target.strip())
    for match in LINK_PAIR_RE.finditer(text):
        target, alias = match.group("target"), (match.group("alias") or "").strip()
        if alias and not alias.isdigit() and title_key(target) and alias != target:
            names.setdefault(title_key(target), alias)
    return names


def page_season_songs(text: str) -> Dict[str, Dict[str, Set[int]]]:
    """搜集库页面 → ``{赛季: {赛道: {已录入的名次}}}``。"""
    result: Dict[str, Dict[str, Set[int]]] = {}
    for name, body in split_sections(text, SEASON_HEADING_RE):
        sides = section_sides(body)
        if not sides:
            continue
        rows, _ = parse_rows(body)
        tracks = {track: set() for track in sides}
        for row in rows:
            for side, track in enumerate(sides):
                if side >= row.sides:
                    continue
                found = re.search(r"\d+", row.text(side, COLUMNS.index("rank")))
                if found and row.text(side, COLUMNS.index("title")).strip():
                    tracks[track].add(int(found.group(0)))
        result[name] = tracks
    return result


def page_song_keys(text: str) -> Set[str]:
    """页面里出现过的所有曲名（比名次更保险，防止同一首歌算两种名次）。"""
    return {song.key for song in songs_from(text) if song.key}


def page_overall_ranks(text: str) -> Dict[str, Set[int]]:
    """搜集库里 ``{{注|13|总榜为第25}}`` 记下的「总榜名次」→ ``{赛季: {总榜名次}}``。

    同一首歌只录入一次：ROOKIE 的行用「总榜」标出它在 TOP100 里的名次，所以
    TOP100 的名次已经在页面上时，不该再补一行 TOP100 的重复条目。
    """
    result: Dict[str, Set[int]] = {}
    for name, body in split_sections(text, SEASON_HEADING_RE):
        found = {int(value) for value in NOTE_OVERALL_RE.findall(body)}
        if found:
            result[name] = found
    return result


def missing_songs(page_text: str, contrib: Dict[str, Dict[str, Dict[int, Tuple[str, bool]]]],
                  limit: int = 0, extra_keys: Optional[Set[str]] = None) -> List[SeasonSong]:
    """活动清单里「还没条目、搜集库也没录入」的歌。

    只认搜集库里**已经存在的那条赛道**（页面没有 TOP30 侧就不会凭空加一列）。
    判定「已录入」：同赛道名次在、总榜名次在（``{{注}}``）、或曲名原本就在页面上。
    ``created=True`` 的歌有条目了，不属于搜集库。
    """
    recorded = page_season_songs(page_text)
    overall = page_overall_ranks(page_text)
    keys = page_song_keys(page_text)
    keys |= set(extra_keys or ())
    missing: List[SeasonSong] = []
    for season, tracks in contrib.items():
        sections = recorded.get(season) or {}
        totals = overall.get(season) or set()
        for track, cells in tracks.items():
            if track not in sections:
                continue
            for rank, (title, created) in sorted(cells.items()):
                if created or rank in sections[track]:
                    continue
                if track != "ROOKIE" and rank in totals:
                    continue            # 这首歌以 ROOKIE 行录入过（注里写着总榜名次）
                if title_key(title) in keys:
                    continue
                missing.append(SeasonSong(season, track, rank, title))
    missing.sort(key=lambda item: (item.season, item.track, item.rank))
    return missing[:limit] if limit else missing


def atwiki_credits(body: str) -> str:
    """AtWiki 页面正文里的作曲（没有就作詞）——也就是 P主。"""
    for pattern in (COMPOSE_LINE_RE, CREDIT_LINE_RE):
        for match in pattern.finditer(body):
            name = re.split(r"[、,/／]", match.group("name"))[0].strip()
            name = re.sub(r"\s*(?:feat\.?|ft\.).*$", "", name, flags=re.I).strip()
            if clean_name(name):
                return name
    return ""


def render_song_title(title: str) -> str:
    """纯日文名的曲名包一层 ``{{lj|…}}``（和页面里其他行的写法一致）。"""
    title = title.strip()
    if re.search(r"[\u3040-\u30ff]", title) and not re.search(r"[\u4e00-\u9fff]", title):
        return "{{lj|[[" + title + "]]}}"
    return "[[" + title + "]]"


def render_producer(name: str) -> str:
    name = name.strip()
    if not name:
        return ""
    if re.search(r"[\u3040-\u30ff]", name) and not re.search(r"[\u4e00-\u9fff]", name):
        return "{{lj|" + name + "}}"
    return name


def section_uses_note(body: str, side: int) -> bool:
    """这一侧的名次格是不是统一写成 ``{{注|N|总榜为第M}}``（2022春 的 ROOKIE 就是这样）。"""
    rows, _ = parse_rows(body)
    seen = [row.text(side, COLUMNS.index("rank")).strip() for row in rows
            if side < row.sides and row.text(side, COLUMNS.index("rank")).strip()]
    return bool(seen) and all("{{注" in value for value in seen)


def overall_ranks(contrib: Dict[str, Dict[str, Dict[int, Tuple[str, bool]]]]
                  ) -> Dict[Tuple[str, str], int]:
    """``(赛季, 归一化曲名) → 总榜名次``（用 TOP100 / TOP30 那一份算）。"""
    result: Dict[Tuple[str, str], int] = {}
    for season, tracks in contrib.items():
        for track, cells in tracks.items():
            if track == "ROOKIE":
                continue
            for rank, (title, _created) in cells.items():
                result.setdefault((season, title_key(title)), rank)
    return result


def build_row(sides: int, side: int, values: Sequence[str]) -> str:
    """造一行表格：只填第 ``side`` 侧，另一侧留空（和页面里空半边的行一致）。"""
    cells = [Cell(" ", "", "") for _ in range(sides * PER_SIDE)]
    for offset, value in enumerate(values[:PER_SIDE]):
        cell = cells[side * PER_SIDE + offset]
        cell.value = value
        if value:
            cell.trail = " "
    return join_row(cells)


def insert_row(text: str, season: str, track: str, rank: int, row: str) -> str:
    """把一行插进某赛季某赛道，按名次排序；找不到位置就插在表格末尾。"""
    marks = [(m.start(), m.end()) for m in SEASON_HEADING_RE.finditer(text)]
    names = [m.group(1) for m in SEASON_HEADING_RE.finditer(text)]
    if season not in names:
        return text
    index = names.index(season)
    start = marks[index][1]
    stop = marks[index + 1][0] if index + 1 < len(marks) else len(text)
    body = text[start:stop]
    sides = section_sides(body)
    if track not in sides:
        return text
    side = sides.index(track)
    lines = body.split("\n")
    rows, _ = parse_rows(body)
    target = None
    for item in rows:
        if side >= item.sides:
            continue
        found = re.search(r"\d+", item.text(side, COLUMNS.index("rank")))
        if found and int(found.group(0)) > rank:
            target = item.line
            break
    if target is None:                  # 没有更大的名次：插在表格最后一行之后
        for position in range(len(lines) - 1, -1, -1):
            if lines[position].strip().startswith("|}"):
                target = position
                break
    if target is None:
        return text
    # 每行前面都有一行 ``|-``：插在它前面，别把原来那行的分隔符留成两条
    if target > 0 and lines[target - 1].strip().startswith("|-"):
        target -= 1
    new_lines = lines[:target] + ["|-", row] + lines[target:]
    return text[:start] + "\n".join(new_lines) + text[stop:]


# ---------------------------------------------------------------- 署名

def clean_name(name: str) -> str:
    name = str(name or "").strip().strip(".,;:，。；：、")
    return "" if name in NOT_TRANSLATOR or not name else name


def credit_name(text: str) -> str:
    """一段文字里第一个像「翻译：某人」的署名。"""
    for match in CREDIT_RE.finditer(str(text or "")):
        name = clean_name(match.group("name"))
        if name:
            return name
    return ""


def has_credit(text: str) -> bool:
    return bool(credit_name(text))


def render_source(url: str, label: str, translator: str = "") -> str:
    """``[url 说明(by. 译者)]``；没有译者时只写说明。"""
    text = f"[{url} {label}"
    if translator:
        text += f"(by. {translator})"
    return text + "]"


def source_count(value: str) -> int:
    """格子里有几条来源（``<br/>`` 分隔）。"""
    return len([item for item in str(value or "").split("<br/>") if item.strip()])


def join_sources(sources: Sequence[str]) -> str:
    return "<br/>".join(sources)


def cell_state(existing: str, cached: Optional[Dict]) -> str:
    """这一格归谁：``empty``（还没填）/ ``ours``（机器人自己填的）/ ``skip``（别人写的）。

    **只有内容与缓存里记过的内容逐字相同**才算自己的：``sources`` 是这一轮的结论，
    ``written`` 是上一轮真正写进页面的内容（结论变了以后仍然认得出自己的格子）。

    不要用「格式像机器人写的」来判断：页面主人自己也是按 ``[链接 说明(by. 译者)]``
    写的（``巴哈姆特(by. 月勳)``、``B站笔记(by. YUSI雨似)`` 这些都是他写的），
    早先按格式认领会把他的来源覆盖成新结论、甚至清空（2026-10-22）。
    缓存丢失时宁可当「别人的」不动。
    """
    text = str(existing or "").strip()
    if not text:
        return "empty"
    cached = cached or {}
    known = {join_sources(cached.get("sources") or []),
             str(cached.get("written") or "").strip()}
    return "ours" if text in known - {""} else "skip"


# ---------------------------------------------------------------- 网络

class Fetcher:
    """带浏览器 UA、bilibili cookie 与重试的抓取器（标准库，不引新依赖）。

    被站点盾掉（HTTP 412）之后整个站就不再访问：GitHub Actions 的机房 IP 会被
    B站 直接 412，硬重试只是把一轮拖到超时。
    """

    def __init__(self) -> None:
        jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(jar))
        self.opener.addheaders = [
            ("User-Agent", UA),
            ("Accept-Language", "zh-CN,zh;q=0.9,ja;q=0.8"),
            ("Referer", "https://www.bilibili.com/"),
        ]
        self._cookies_ready = False
        self.blocked: set = set()
        self.failures: Dict[str, int] = {}

    @staticmethod
    def site_of(url: str) -> str:
        host = urllib.parse.urlsplit(url).netloc.lower()
        if host.endswith("bilibili.com"):
            return "bilibili.com"
        if host.endswith("music.163.com"):
            return "music.163.com"
        return host

    def is_blocked(self, url: str) -> bool:
        return self.site_of(url) in self.blocked

    def _warm_up(self) -> None:
        """bilibili 的搜索接口要 ``buvid3`` cookie，先访问一次首页拿下来。"""
        if self._cookies_ready:
            return
        self._cookies_ready = True
        try:
            self.opener.open("https://www.bilibili.com/", timeout=REQUEST_TIMEOUT).read()
        except Exception:               # noqa: BLE001 - 拿不到 cookie 就退回无 cookie 请求
            pass

    def text(self, url: str, attempts: int = 3) -> str:
        if self.is_blocked(url):
            return ""
        site = self.site_of(url)
        for attempt in range(attempts):
            try:
                with self.opener.open(url, timeout=REQUEST_TIMEOUT) as response:
                    self.failures.pop(site, None)
                    return response.read().decode("utf-8", "replace")
            except urllib.error.HTTPError as exc:
                if exc.code == 412:     # 反爬：重试没用
                    self.blocked.add(site)
                    pywikibot.warning(f"{site} 拒绝访问（HTTP 412），"
                                      f"本轮不再查这个站：{url}")
                    return ""
                if attempt == attempts - 1:
                    pywikibot.warning(f"读取失败：{url}（{exc}）")
                    return ""
                time.sleep(1.5 * (attempt + 1))
            except Exception as exc:    # noqa: BLE001 - 单个来源失败不该中断整轮
                if attempt == attempts - 1:
                    pywikibot.warning(f"读取失败：{url}（{exc}）")
                    # 连着几次都连不上就别再试：扫描上千行的补录会一直卡在这里
                    self.failures[site] = self.failures.get(site, 0) + 1
                    if self.failures[site] >= FAILURE_LIMIT:
                        self.blocked.add(site)
                        pywikibot.warning(f"{site} 连续 {FAILURE_LIMIT} 次读取失败，"
                                          f"本轮不再查这个站")
                    return ""
                time.sleep(1.5 * (attempt + 1))
        return ""

    def json(self, url: str, attempts: int = 3) -> Optional[dict]:
        if "api.bilibili.com" in url:
            self._warm_up()
        raw = self.text(url, attempts)
        if not raw:
            return None
        try:
            return json.loads(raw)
        except ValueError:
            return None


def load_cache(path: Path = CACHE) -> Dict:
    try:
        with path.open("rb") as handle:
            data = pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(cache: Dict, path: Path = CACHE) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(cache, handle)


def is_fresh(stamp: object, ttl: float) -> bool:
    try:
        age = time.time() - float(stamp)
    except (TypeError, ValueError):
        return False
    return 0 <= age < ttl


def is_current(entry: Optional[Dict], ttl: float) -> bool:
    """这条缓存还能直接用（同版本、没过期）。规则一改就靠版本号整体作废。"""
    return (isinstance(entry, dict) and entry.get("v") == CACHE_VERSION
            and is_fresh(entry.get("at"), ttl))


# ---------------------------------------------------------------- AtWiki

def atwiki_page_index(fetcher: Fetcher, cache: Optional[Dict] = None,
                      refresh: bool = False) -> Dict[str, str]:
    """「全ページ一覧」→ ``{归一化页面名: 页面 id}``（缓存 7 天）。"""
    cache = load_cache(ATWIKI_CACHE) if cache is None else cache
    if not refresh and cache.get("index") and is_fresh(cache.get("built"), ATWIKI_TTL):
        return dict(cache["index"])
    pages: Dict[str, str] = {}
    total, number = 0, 1
    while number <= min(ATWIKI_MAX_PAGES, total or ATWIKI_MAX_PAGES):
        url = ATWIKI_LIST + ("" if number == 1 else f"&pp={number}")
        markup = fetcher.text(url)
        if not markup:
            break
        table = ATWIKI_LIST_RE.search(markup)
        batch = ATWIKI_ROW_RE.findall(table.group(1) if table else "")
        if not batch:
            break
        for pid, name in batch:
            name = re.sub(r"\s+", " ", TAG_RE.sub("", name)).strip()
            key = title_key(name)
            if key and key not in pages:
                pages[key] = pid
        total = total or max((int(value) for value in ATWIKI_LAST_RE.findall(markup)),
                             default=0)
        number += 1
    if pages:
        save_cache({"built": time.time(), "index": pages}, ATWIKI_CACHE)
    return pages


def atwiki_body(fetcher: Fetcher, pid: str) -> str:
    """AtWiki 页面正文（纯文本）。"""
    markup = fetcher.text(ATWIKI_PAGE.format(pid=pid))
    if not markup:
        return ""
    body = ATWIKI_BODY_RE.search(markup)
    if not body:
        return ""
    return urllib.parse.unquote(TAG_RE.sub("\n", body.group(1)))


def atwiki_translator(fetcher: Fetcher, pid: str) -> str:
    """AtWiki 页面正文里的 ``翻譯：某人``；没有就返回空串。"""
    return credit_name(atwiki_body(fetcher, pid))


def lookup_atwiki(fetcher: Fetcher, song: Song, index: Dict[str, str]) -> List[str]:
    """页面名精确匹配**且**正文里出现这首歌的 P主，才认。

    同名不同曲在歌词wiki 上很常见：``Linaria`` 那一页是 Mysteka 的（翻译 kyroslee），
    不是子牛的；``EDEN`` 那一页是真尋P 的，不是酔シグレ 的；``Redis``/``Redial``、
    ``Reboot`` 同理（2026-10-22 实测四条全错）。页面开头的「作詞：/作曲：」就是
    判据，对不上就不记。
    """
    tried = set()
    for name in (song.title_target, song.title_display):
        key = title_key(name)
        if not key or key in tried:
            continue
        tried.add(key)
        pid = index.get(key)
        if not pid:
            continue
        body = atwiki_body(fetcher, pid)
        if not body or not producer_mentioned(body, song):
            continue
        return [render_source(ATWIKI_PAGE.format(pid=pid), "VOCALOID中文歌词wiki",
                              credit_name(body))]
    return []


# ---------------------------------------------------------------- 网易云

def netease_search(fetcher: Fetcher, keyword: str) -> List[dict]:
    data = fetcher.json(NETEASE_SEARCH.format(kw=urllib.parse.quote(keyword)))
    if not data:
        return []
    return ((data.get("result") or {}).get("songs") or [])


def netease_lyrics(fetcher: Fetcher, song_id: str) -> Optional[dict]:
    return fetcher.json(NETEASE_LYRIC.format(id=song_id))


def netease_titles(candidate: dict) -> set:
    """搜索结果里的所有歌名写法（本名 / alias / transNames）。"""
    names = {title_key(candidate.get("name"))}
    for alias in candidate.get("alias") or []:
        names.add(title_key(alias))
    for trans in (candidate.get("transNames") or []):
        names.add(title_key(trans))
    names.discard("")
    return names


def netease_credits(candidate: dict) -> set:
    """搜索结果里的歌手名与专辑名（用来核对是不是同一首歌）。"""
    credits = {person_key(artist.get("name"))
               for artist in candidate.get("artists") or []}
    credits.add(person_key((candidate.get("album") or {}).get("name")))
    credits.discard("")
    return credits


def lookup_netease(fetcher: Fetcher, song: Song) -> List[str]:
    """歌名对上**且** P主 出现在歌手 / 专辑里才记。

    只有歌名对上是不够的：``月之花`` 能搜到 Daoko 的 ``月の花``，``言灵`` 能搜到
    V.W.P 的 ``言霊``，都是同名不同曲。网易云上 Vocaloid 曲一般由 P主 自己上传，
    所以「歌手或专辑里有 P主」是个便宜又准的判据；查不到 P主 就干脆不记。
    """
    wanted = {title_key(song.title_target), title_key(song.title_display)}
    wanted.discard("")
    producer = person_key(song.producer)
    if not producer:
        return []
    for keyword in (song.title_target, song.title_display):
        for candidate in netease_search(fetcher, keyword):
            if not (netease_titles(candidate) & wanted):
                continue
            if producer not in netease_credits(candidate):
                continue
            payload = netease_lyrics(fetcher, str(candidate.get("id")))
            if not payload or not (payload.get("tlyric") or {}).get("lyric"):
                continue                    # 没有译文：不记（原歌词不是翻译来源）
            user = payload.get("transUser") or payload.get("lyricUser") or {}
            translator = clean_name(user.get("nickname") or "")
            return [render_source(NETEASE_SONG.format(id=candidate.get("id")),
                                  "网易云音乐", translator)]
    return []


# ---------------------------------------------------------------- B站

def bilibili_search(fetcher: Fetcher, keyword: str) -> List[dict]:
    data = fetcher.json(BILIBILI_SEARCH.format(kw=urllib.parse.quote(keyword)))
    if not data or data.get("code") not in (0, None):
        return []
    return ((data.get("data") or {}).get("result") or [])


def bilibili_view(fetcher: Fetcher, bvid: str) -> Optional[dict]:
    data = fetcher.json(BILIBILI_VIEW.format(bvid=bvid))
    if not data or data.get("code") not in (0, None):
        return None
    return data.get("data") or {}


def bilibili_replies(fetcher: Fetcher, aid: str, pages: int = 2) -> List[dict]:
    result: List[dict] = []
    for page in range(1, pages + 1):
        data = fetcher.json(BILIBILI_REPLY.format(oid=aid, pn=page))
        if not data or data.get("code") not in (0, None):
            break
        payload = data.get("data") or {}
        result.extend(payload.get("replies") or [])
        if not payload.get("replies"):
            break
    return result


def bilibili_danmaku(fetcher: Fetcher, cid: str) -> List[str]:
    if not cid:
        return []
    blob = fetcher.text(BILIBILI_DANMAKU.format(cid=cid), attempts=2)
    if not blob:
        return []
    try:                                # 接口返回的是 deflate 流
        blob = zlib.decompressobj(-zlib.MAX_WBITS).decompress(blob.encode("latin-1"))
        blob = blob.decode("utf-8", "replace")
    except Exception:                   # noqa: BLE001 - 已经是明文时直接读
        pass
    return [line.strip() for line in DANMAKU_RE.findall(blob) if line.strip()]


def chinese_lines(text: str) -> int:
    """这段文字里有几行像中文歌词（有汉字、没有假名）。"""
    count = 0
    for line in str(text or "").split("\n"):
        line = line.strip()
        if len(line) < 2 or len(line) > 40:     # 太短 / 太长都不是歌词行
            continue
        if not re.search(r"[\u4e00-\u9fff]", line):
            continue
        if re.search(r"[\u3040-\u30ff]", line):  # 带假名的是日文原文
            continue
        count += 1
    return count


def song_mentioned(text: str, song: Song) -> bool:
    """标题 / 简介里有没有这首歌（日文名或中文名都算）。"""
    haystack = title_key(text)
    if not haystack:
        return False
    for name in (song.title_target, song.title_display):
        key = title_key(name)
        if key and len(key) >= 2 and key in haystack:
            return True
    return False


def producer_mentioned(text: str, song: Song) -> bool:
    """这段文字里有没有 P主 的名字。

    搜来的视频只对上歌名远远不够：``RITA`` 会搜到 TED 演讲的翻译视频，``亡灵`` 会搜到
    有声书。译文视频一般会在简介里写「本家：某某」，要求同时出现 P主 才敢用。
    歌名 / P主 是 ASCII 时按词边界比（``Hal`` 不能匹配 ``halcyon``）。
    """
    key = person_key(song.producer)
    haystack = title_key(text)
    if not key or not haystack:
        return False
    if key.isascii():
        return re.search(rf"(?<![a-z0-9]){re.escape(key)}(?![a-z0-9])", haystack) is not None
    return key in haystack


def outbound_links(text: str) -> Tuple[List[str], List[str]]:
    """正文里的 ``(巴哈姆特链接, B站笔记/专栏链接)``。"""
    gamer: List[str] = []
    opus: List[str] = []
    for url in BARE_URL_RE.findall(str(text or "")):
        url = url.rstrip(".,;，。；、")
        if GAMER_URL_RE.match(url):
            gamer.append(url)
        elif OPUS_URL_RE.match(url):
            opus.append(url)
    return list(dict.fromkeys(gamer)), list(dict.fromkeys(opus))


def video_sources_from_view(fetcher: Fetcher, view: dict, song: Song,
                            require_mention: bool, deep: bool = True
                            ) -> Tuple[List[str], str, str]:
    """已经取到 view 的 B站投稿能提供的译文来源 → ``(来源列表, 简介, 标题)``。

    ``require_mention=True``（搜索来的视频）时要求标题或简介**同时**提到这首歌和
    P主——只对上歌名会把 TED 演讲、有声书之类的翻译视频当成译文来源。
    本家投稿（voca 条目 Songbox 里的 ``bb_id``）不需要。
    ``deep=False`` 只看简介与评论（弹幕要额外一次请求，留给「还没找到」时用）。
    """
    bvid = str(view.get("bvid") or "")
    title = str(view.get("title") or "")
    desc = str(view.get("desc") or "")
    owner = clean_name(str((view.get("owner") or {}).get("name") or ""))
    if require_mention:
        mentioned = song_mentioned(title, song) or song_mentioned(desc, song)
        credited = producer_mentioned(title, song) or producer_mentioned(desc, song)
        if not (mentioned and credited):
            return [], desc, title

    url = BILIBILI_VIDEO.format(bvid=bvid) if bvid else ""
    sources: List[str] = []
    translator = credit_name(desc)
    if translator:
        sources.append(render_source(url, "B站视频简介", translator))

    aid = str(view.get("aid") or "")
    for reply in bilibili_replies(fetcher, aid, pages=1):
        message = str((reply.get("content") or {}).get("message") or "")
        if chinese_lines(message) < 2 or not has_credit(message):
            continue
        name = credit_name(message) or clean_name(
            str((reply.get("member") or {}).get("uname") or ""))
        rpid = reply.get("rpid")
        target = f"{url}#reply{rpid}" if rpid else url
        sources.append(render_source(target, "B站评论区", name))
        break

    if deep:
        for line in bilibili_danmaku(fetcher, str(view.get("cid") or "")):
            name = credit_name(line)
            if name:
                sources.append(render_source(url, "B站弹幕", name))
                break

    if not sources and owner and chinese_lines(desc) >= 3:
        # 简介本身就是「日文 + 中文」的歌词（译文直接贴在简介里）
        sources.append(render_source(url, "B站视频简介", owner))
    return sources, desc, title


def video_sources(fetcher: Fetcher, bvid: str, song: Song,
                  require_mention: bool) -> Tuple[List[str], str, str]:
    """按 bvid 取 view 再找来源（测试与单条调试用）。"""
    view = bilibili_view(fetcher, bvid)
    if not view:
        return [], "", ""
    view.setdefault("bvid", bvid)
    return video_sources_from_view(fetcher, view, song, require_mention)


def lookup_bilibili(fetcher: Fetcher, song: Song, bb_id: str = ""
                    ) -> Tuple[List[str], List[str], List[str]]:
    """B站来源 → ``(来源列表, 顺带发现的巴哈姆特链接, B站笔记链接)``。

    请求数要克制：每个候选视频一次 view，评论只看第一页，弹幕只在还没找到来源时
    才取（每首歌的请求数因此稳定在 4~6 次）。
    """
    sources: List[str] = []
    gamer: List[str] = []
    opus: List[str] = []
    candidates: List[str] = []
    if bb_id:
        candidates.append(bb_id)                # 本家投稿：不用核对标题
    for keyword in (f"{song.title_display} 翻译", f"{song.title_target} 翻译"):
        if not keyword.strip():
            continue
        for hit in bilibili_search(fetcher, keyword)[:4]:
            bvid = str(hit.get("bvid") or "")
            if bvid and bvid not in candidates:
                candidates.append(bvid)
        if len(candidates) >= 4 or sources:
            break
    for bvid in candidates[:3]:
        view = bilibili_view(fetcher, bvid)
        if not view:
            continue
        view.setdefault("bvid", bvid)
        require_mention = bvid != bb_id
        found, desc, title = video_sources_from_view(
            fetcher, view, song, require_mention, deep=not sources)
        sources.extend(found)
        found_gamer, found_opus = outbound_links(desc + " " + title)
        gamer.extend(found_gamer)
        opus.extend(found_opus)
        if len(sources) >= 2:
            break
    return sources[:2], list(dict.fromkeys(gamer)), list(dict.fromkeys(opus))


def bilibili_opus(fetcher: Fetcher, url: str, song: Song) -> List[str]:
    """B站笔记 / 专栏：作者卡片 + 正文里有没有译文署名。"""
    markup = fetcher.text(url)
    if not markup:
        return []
    plain = re.sub(r"<[^>]+>", "\n", markup)
    plain = urllib.parse.unquote(plain)
    if not song_mentioned(plain, song) or not has_credit(plain):
        return []
    author = ""
    card = re.search(r'opus-module-author__name[^>]*>([^<]{1,60})<', markup)
    if card:
        author = clean_name(card.group(1))
    if not author:
        pair = re.search(r'"name"\s*:\s*"([^"]{1,40})"[^{}]{0,200}?"mid"\s*:\s*"?\d+', markup)
        author = clean_name(pair.group(1)) if pair else ""
    return [render_source(url, "B站笔记", author)]


# ---------------------------------------------------------------- 巴哈姆特

def lookup_bahamut(fetcher: Fetcher, url: str, song: Song) -> List[str]:
    """核对一个巴哈姆特作品页：标题要对得上、正文要有译文署名。"""
    markup = fetcher.text(url)
    if not markup:
        return []
    title_match = re.search(r"<title>([^<]*)</title>", markup)
    title = urllib.parse.unquote(title_match.group(1)) if title_match else ""
    article = re.search(r'<div[^>]*class="[^"]*article-content main[^"]*"[^>]*>(.*?)</div>',
                        markup, re.S)
    body = TAG_RE.sub("\n", article.group(1) if article else markup)
    if not song_mentioned(title + " " + body, song):
        return []
    name = credit_name(body)
    if not name:
        return []
    return [render_source(url, "巴哈姆特", name)]


# ---------------------------------------------------------------- voca 条目

def article_video(site, song: Song) -> str:
    """voca.wiki 条目的 Songbox ``bb_id``（本家 B站投稿）；没有条目 / 没有 bb_id 返回空串。"""
    try:
        page = Page(site, song.title_target)
        if not page.exists() or page.isRedirectPage():
            return ""
        text = page.get()
    except Exception:                   # noqa: BLE001 - 查不到就当没有条目
        return ""
    box = re.search(r"\{\{\s*VOCALOID Songbox\b(.*?)\n\s*\}\}", text, re.S)
    if not box:
        return ""
    match = re.search(r"\|\s*bb_id\s*=\s*([A-Za-z0-9]+)", box.group(1))
    return match.group(1) if match else ""


# ---------------------------------------------------------------- 汇总

def collect_sources(fetcher: Fetcher, song: Song, index: Dict[str, str],
                    site=None) -> List[str]:
    """一首歌全部能查到的来源（最多 ``MAX_SOURCES`` 条，按可靠程度排序）。"""
    sources: List[str] = []
    try:
        sources.extend(lookup_atwiki(fetcher, song, index))
    except Exception as exc:            # noqa: BLE001 - 单个来源出错不影响其他来源
        pywikibot.warning(f"AtWiki 查询失败（{song.title_display}）：{exc}")
    try:
        sources.extend(lookup_netease(fetcher, song))
    except Exception as exc:            # noqa: BLE001
        pywikibot.warning(f"网易云查询失败（{song.title_display}）：{exc}")

    bb_id = ""
    if site is not None:
        bb_id = article_video(site, song)
    gamer_links: List[str] = []
    opus_links: List[str] = []
    try:
        found, gamer_links, opus_links = lookup_bilibili(fetcher, song, bb_id)
        sources.extend(found)
    except Exception as exc:            # noqa: BLE001
        pywikibot.warning(f"B站查询失败（{song.title_display}）：{exc}")
    for url in opus_links[:2]:
        try:
            sources.extend(bilibili_opus(fetcher, url, song))
        except Exception as exc:        # noqa: BLE001
            pywikibot.warning(f"B站笔记查询失败（{url}）：{exc}")
    for url in gamer_links[:3]:
        try:
            sources.extend(lookup_bahamut(fetcher, url, song))
        except Exception as exc:        # noqa: BLE001
            pywikibot.warning(f"巴哈姆特查询失败（{url}）：{exc}")

    unique: List[str] = []
    for item in sources:
        if item not in unique:
            unique.append(item)
    return unique[:MAX_SOURCES]


def season_data(site, fetcher: Fetcher, refresh: bool = False) -> Dict:
    """活动清单（贡献列表 + 12 个大家族模板）缓存 7 天。"""
    cache = load_cache(SEASONS_CACHE)
    if not refresh and cache.get("data") and is_fresh(cache.get("built"), SEASONS_TTL):
        return cache["data"]
    data: Dict = {"contrib": {}, "names": {}}
    try:
        contrib = Page(site, CONTRIB_PAGE).text or ""
        data["contrib"] = parse_contrib_seasons(contrib)
    except Exception as exc:            # noqa: BLE001
        pywikibot.warning(f"读取贡献列表失败：{exc}")
    names: Dict[str, str] = {}
    for season in data["contrib"]:
        template = NAVBOX_TEMPLATE.format(season=season.replace("ボカコレ", ""))
        try:
            markup = Page(site, template).text or ""
        except Exception as exc:        # noqa: BLE001
            pywikibot.warning(f"读取大家族模板失败（{template}）：{exc}")
            continue
        names.update(navbox_names(markup))
    data["names"] = names
    if data["contrib"]:
        save_cache({"built": time.time(), "data": data}, SEASONS_CACHE)
    return data


def atwiki_song(fetcher: Fetcher, index: Dict[str, str], names: Dict[str, str],
                title: str) -> Optional[Tuple[str, str, str]]:
    """按条目名 / 日文原名找 AtWiki → ``(页面 id, 译者, P主)``；对不上就不认。"""
    candidates = [title]
    alias = names.get(title_key(title))
    if alias:
        candidates.append(alias)
    for name in candidates:
        pid = index.get(title_key(name))
        if not pid:
            continue
        body = atwiki_body(fetcher, pid)
        if not body:
            continue
        producer = atwiki_credits(body)
        translator = credit_name(body)
        if producer or translator:
            return pid, translator, producer
    return None


def add_missing_entries(site, fetcher: Fetcher, text: str, index: Dict[str, str],
                        data: Dict, max_add: int, write: bool) -> Tuple[str, int]:
    """把「外站有翻译、搜集库没录入」的歌补进对应赛季的表格 → ``(新文本, 补了几行)``。"""
    contrib = data.get("contrib") or {}
    names = data.get("names") or {}
    if not contrib:
        pywikibot.warning("拿不到活动清单，本轮不补录")
        return text, 0
    missing = missing_songs(text, contrib)
    totals = overall_ranks(contrib)
    pywikibot.output(f"活动清单里有 {len(missing)} 首未录入搜集库（有条目 / 已录入的不算）")
    added = 0
    for song in missing:
        if added >= max_add:
            break
        found = atwiki_song(fetcher, index, names, song.title)
        if not found:
            continue
        pid, translator, producer = found
        if not producer:
            continue                    # 没 P主 就没法补行（P主 那一列是必要的）
        sides = section_sides(dict(split_sections(text, SEASON_HEADING_RE))[song.season])
        if song.track not in sides:
            continue
        side = sides.index(song.track)
        body = dict(split_sections(text, SEASON_HEADING_RE))[song.season]
        rank = str(song.rank)
        overall = totals.get((song.season, title_key(song.title)))
        if song.track == "ROOKIE" and overall and section_uses_note(body, side):
            rank = "{{注|%d|总榜为第%d}}" % (song.rank, overall)
        values = [rank, render_song_title(song.title), render_producer(producer),
                  "{{color|#FF0000|未创建}}",
                  render_source(ATWIKI_PAGE.format(pid=pid), "VOCALOID中文歌词wiki",
                                translator),
                  ""]
        row = build_row(len(sides), side, values)
        text = insert_row(text, song.season, song.track, song.rank, row)
        added += 1
        pywikibot.output(f"  + {song.season} {song.track} {song.rank} {song.title}"
                         f"（{producer}，译文 {translator or '未署名'}）")
    return text, added


def run_once(site, write: bool = False, summary: Optional[str] = None,
             ttl: float = CACHE_TTL, limit: int = 0, refresh: bool = False,
             fetcher: Optional[Fetcher] = None, add_missing: bool = False,
             max_add: int = 10) -> bool:
    """跑一轮。返回页面是否需要（或已经）改动。"""
    fetcher = fetcher or Fetcher()
    if write:
        if not site.logged_in():
            site.login()
        if not site.logged_in():
            raise RuntimeError("登录失败：请检查 user-config.py 与 user-password.py")
    page = Page(site, PAGE_TITLE)
    original = page.text or ""
    songs = songs_from(original)

    rows, _ = parse_rows(original)
    current: Dict[Tuple[int, int], str] = {}
    for row in rows:
        for side in range(row.sides):
            if row.text(side, COLUMNS.index("title")).strip():
                cell = (row.line, side)
                current[cell] = row.text(side, COLUMNS.index("source")).strip()
    # --refresh 只跳过「缓存还有效就不再查」，不丢缓存：要靠 written 认出自己写过的格子
    cache = load_cache()
    index = atwiki_page_index(fetcher)

    fills: Dict[Tuple[int, int], str] = {}
    queried = 0
    for song in songs:
        cell = (song.line, song.side)
        cached = cache.get(song.key)
        existing = current.get(cell, "")
        if cell_state(existing, cached) == "skip":
            continue                    # 别人写的内容：一个字都不动
        if is_current(cached, ttl) and not refresh:
            # 缓存里有结论，但页面可能还没跟上（上次保存失败 / 另一台机器写的）：
            # 只在结论更全时补写，避免两边来回覆盖。
            value = join_sources(cached.get("sources") or [])
            if value and source_count(value) > source_count(existing):
                fills[cell] = value
                cached["written"] = value
            continue
        if limit and queried >= limit:
            break
        queried += 1
        sources = collect_sources(fetcher, song, index, site)
        value = join_sources(sources)
        entry = {"at": time.time(), "v": CACHE_VERSION, "sources": sources,
                 "title": song.title_display, "written": existing}
        if value != existing:
            fills[cell] = value         # 新内容 / 更新 / 清掉自己以前写的
            entry["written"] = value
        cache[song.key] = entry
        if sources:
            pywikibot.output(f"  {song.rank or '-'} {song.title_display}："
                             f"{len(sources)} 个来源")
        else:
            pywikibot.output(f"  {song.rank or '-'} {song.title_display}：没找到")

    save_cache(cache)
    pywikibot.output(f"待查 {len(current)} 行、本轮查了 {queried} 首、"
                     f"改动 {len(fills)} 行")
    text = apply_fills(original, fills)
    added = 0
    if add_missing:
        try:
            text, added = add_missing_entries(site, fetcher, text, index,
                                              season_data(site, fetcher, refresh),
                                              max_add, write)
        except Exception as exc:        # noqa: BLE001 - 补录失败不影响填来源
            pywikibot.warning(f"补录未录入的曲目失败：{exc}")
    if text == original:
        pywikibot.output("页面无需更新。")
        return False
    if not write:
        pywikibot.output("[dry-run] 页面有改动；加 --write 以保存。")
        return True
    page.text = text
    note = summary or f"{DEFAULT_SUMMARY}，补 {len(fills)} 行"
    if added:
        note = summary or f"{DEFAULT_SUMMARY}，补 {len(fills)} 行、补录 {added} 首"
    try:
        page.save(summary=note, minor=True, bot=True, tags="Bot")
    except EditConflictError as exc:
        pywikibot.error(f"页面刚被其他进程编辑，放弃本轮：{exc}")
        return False
    except pywikibot.exceptions.APIError as exc:
        pywikibot.warning(f"带 bot/tags 保存失败，改用普通保存：{exc}")
        page.save(summary=note, minor=True)
    pywikibot.output("已更新页面。")
    return True


def main() -> None:
    parser = argparse.ArgumentParser(description="填充 VOCALOID collection 搜集库的翻译来源")
    parser.add_argument("--write", action="store_true", help="保存页面（默认只干跑）")
    parser.add_argument("--summary", default=None, help="编辑摘要")
    parser.add_argument("--ttl", type=float, default=CACHE_TTL,
                        help="一首歌多久重新核对一次（秒，默认 14 天）")
    parser.add_argument("--limit", type=int, default=0,
                        help="本轮最多查多少首（0 = 不限制）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存的有效期，重新核对（缓存本身保留，用于认出自己写过的格子）")
    parser.add_argument("--add-missing", action="store_true",
                        help="把「外站有翻译、搜集库没录入」的曲目补进对应赛季的表格")
    parser.add_argument("--max-add", type=int, default=10,
                        help="本轮最多补录几首（默认 10，0 = 不限制）")
    args = parser.parse_args()
    run_once(pywikibot.Site(), args.write, args.summary, args.ttl, args.limit,
             args.refresh, add_missing=args.add_missing,
             max_add=args.max_add or 10 ** 6)


if __name__ == "__main__":
    main()
