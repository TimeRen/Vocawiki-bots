# -*- coding: utf-8 -*-
"""Maintain [[User:人间百态/贡献]]（[[User:人间百态]] 上那个导航框）。

导航框把「人间百态」在 voca.wiki 建的页面按用途分了组：

* ``Vocawiki时期``  - 在 voca.wiki 上建的歌曲条目（萌百时期之前的那批在另一组，脚本不动）；
* ``歌姬模板`` / ``vocaloid职人模板`` - 歌姬 / P主模板。

每小时（或每天）跑一轮，做三件事：

1. **补新条目**：``list=usercontribs&ucshow=new`` 取这个账号建过的页面，
   注释以「由 Vocawiki条目辅助工具 创建」开头（不含「同名条目消歧义」）的就是
   歌曲条目、``…创建：歌姬模板`` 的就是歌姬模板。已经在清单里的按标题跳过。
   标题末尾带括号消歧后缀的（``希望(Dopamine)``、``Redial(鹤三)``）写成
   ``希望(Dopamine){{!}}希望``，只显示括号前的歌名（用户 2026-10-17 的手改口径）。
2. **清掉不该出现的条目**（用户 2026-10-17 要求）：
   * **重定向**改成它的目标页（目标已在清单里就直接去掉）——导航框里不该出现
     指向重定向的链接（``Boo! Boo! Etranger`` 实际是 ``Boo！Boo！Etranger`` 的重定向）；
   * **消歧义页**（``Category:消歧义页面`` 或挂了 ``{{Disambig}}``）直接去掉，
     它不是歌曲条目。
3. **歌姬模板只列主模板**：工具建的是 ``Template:IA/2026``、``Template:歌爱雪/2011``
   这种按年份拆的子页面，导航框里要的是 ``Template:IA``、``Template:歌爱雪``；
   子页面（名字里带 ``/``）一律不列。

``Vocawiki时期`` 每组 10 条（``1-10`` / ``11-20`` …），补完之后重新编号；
其余分组（萌百时期、列表、职人模板…）原样保留。

Everything is a dry run unless ``--write`` is given.
"""

from __future__ import annotations

import argparse
import re
import time
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pywikibot
from pywikibot import Page
from pywikibot.exceptions import EditConflictError

PAGE_TITLE = "User:人间百态/贡献"
USER_NAME = "人间百态"
# 条目创建工具的编辑摘要（见用户页历史）：只有这种才是「新建的条目」
CREATE_NOTE = "由 Vocawiki条目辅助工具 创建"
DISAMBIG_NOTE = "同名条目消歧义"
SONG_GROUP = "Vocawiki时期"
TEMPLATE_GROUP = "歌姬模板"
GROUP_SIZE = 10
DEFAULT_SUMMARY = "更新贡献页：补 Vocawiki 时期条目与歌姬模板（机器人）"
REQUEST_BATCH = 50

# 分组标题行 / 列表行的缩进（与页面原来的写法一致）
GROUP_INDENT = " " * 19
CLOSING_INDENT = " " * 5

LINKS_PREFIX = "{{links|n=4|"
TEMPLATE_LINK_RE = re.compile(r"\{\{tl\|([^}|]+)\}\}")
# 条目名末尾的括号消歧后缀：`希望(Dopamine)`、`Redial（鹤三）`
PAREN_SUFFIX_RE = re.compile(r"^(?P<base>.+?)\s*[(（][^()（）]+[)）]$")


# ---------------------------------------------------------------- wikitext

def balanced_end(text: str, start: int) -> int:
    """``text[start:]`` 以 ``{{`` 开头时，返回配对 ``}}`` 之后的下标。"""
    depth = 0
    index = start
    while index < len(text):
        if text.startswith("{{", index):
            depth += 1
            index += 2
        elif text.startswith("}}", index):
            depth -= 1
            index += 2
            if depth == 0:
                return index
        else:
            index += 1
    raise ValueError("模板括号不配对")


def list_span(text: str, label: str, single_line: bool = False) -> Tuple[int, int]:
    """``|groupN = <label>`` 之后那个 ``|listN = …`` 的值的区间。

    ``single_line=True`` 时取到行尾（``歌姬模板`` 一行里连着好几个 ``{{tl|…}}``，
    按配对的 ``}}`` 找会只取到第一个）。
    """
    marker = re.search(r"\|\s*group(\d+)\s*=\s*" + re.escape(label), text)
    if not marker:
        raise ValueError(f"找不到分组：{label}")
    item = re.compile(r"\|\s*list%s\s*=" % marker.group(1)).search(text, marker.end())
    if not item:
        raise ValueError(f"找不到 list{marker.group(1)}")
    start = item.end()
    while start < len(text) and text[start] in " \t":
        start += 1
    if single_line or not text.startswith("{{", start):
        return start, text.index("\n", start)
    return start, balanced_end(text, start)


def _split_top_level(body: str) -> List[str]:
    """按**顶层**的 ``|`` 切分（``{{color|…|…}}`` 里的竖线不算分隔符）。"""
    parts: List[str] = []
    current: List[str] = []
    depth = 0
    index = 0
    while index < len(body):
        if body.startswith("{{", index):
            depth += 1
            current.append("{{")
            index += 2
        elif body.startswith("}}", index):
            depth -= 1
            current.append("}}")
            index += 2
        elif body[index] == "|" and depth == 0:
            parts.append("".join(current))
            current = []
            index += 1
        else:
            current.append(body[index])
            index += 1
    parts.append("".join(current))
    return [part.strip() for part in parts if part.strip()]


def parse_links(value: str) -> List[str]:
    """``{{links|n=4|a|b|c}}`` 系列 → 条目列表（保留 ``标题{{!}}显示文字`` 写法）。"""
    entries: List[str] = []
    index = 0
    while True:
        found = value.find(LINKS_PREFIX, index)
        if found < 0:
            break
        end = balanced_end(value, found)
        body = value[found + len(LINKS_PREFIX):end - 2]
        entries.extend(_split_top_level(body))
        index = end
    return entries


def parse_templates(value: str) -> List[str]:
    """``{{tl|甲}}{{w}}{{tl|乙}}`` → ``["甲", "乙"]``。"""
    return [name.strip() for name in TEMPLATE_LINK_RE.findall(value or "") if name.strip()]


def entry_target(entry: str) -> str:
    """``标题{{!}}显示文字`` → 标题。"""
    return entry.split("{{!}}")[0].strip()


def display_entry(title: str) -> str:
    """新条目写进清单的形式：标题带括号消歧后缀时，只显示括号前的名字。

    用户 2026-10-17 手工改的这几条就是这个口径（差异 272789）：
    ``希望(Dopamine)`` → ``希望(Dopamine){{!}}希望``、
    ``我爱你(Mealerrand)`` → ``我爱你(Mealerrand){{!}}我爱你``、
    ``Redial(鹤三)`` → ``Redial(鹤三){{!}}Redial``。
    括号是条目名的一部分（同名曲要加作者区分），但导航框里只要看到歌名。
    """
    match = PAREN_SUFFIX_RE.match(title or "")
    if not match:
        return title
    base = match.group("base").strip()
    if not base or "|" in base:
        return title
    return f"{title}{{{{!}}}}{base}"


def queryable(title: str) -> bool:
    """能不能直接拿标题去查：``Template:…`` 与主名字空间可以，``vcp:…`` 这类跨站链接不行。"""
    return title.startswith("Template:") or ":" not in title


def render_links(entries: Sequence[str], prefix: str = "|list") -> List[str]:
    """条目 → 每 10 条一组的 ``|groupN`` / ``|listN`` 行。"""
    lines: List[str] = []
    for number, start in enumerate(range(0, len(entries), GROUP_SIZE), 1):
        chunk = entries[start:start + GROUP_SIZE]
        first = start + 1
        lines.append(f"{GROUP_INDENT}|group{number} = {first}-{first + len(chunk) - 1}")
        body = "|".join(chunk)
        lines.append(f"{GROUP_INDENT}{prefix}{number}  = " + "{{links|n=4|" + body + "}}")
    return lines


def render_song_group(entries: Sequence[str]) -> str:
    """``Vocawiki时期`` 的整块 ``{{Navbox subgroup …}}``。"""
    lines = ["{{Navbox subgroup", *render_links(entries)]
    lines.append(CLOSING_INDENT + "}}")
    return "\n".join(lines)


def render_template_group(names: Sequence[str]) -> str:
    """``歌姬模板`` 的一行 ``{{tl|甲}}{{w}}{{tl|乙}}``。"""
    return "{{w}}".join("{{tl|%s}}" % name for name in names)


# ---------------------------------------------------------------- 清洗

def is_song_creation(contribution: Dict) -> bool:
    """这条「新建页面」记录是不是一首歌（排除同名条目消歧义页）。"""
    comment = str(contribution.get("comment") or "")
    return (contribution.get("ns") == 0 and comment.startswith(CREATE_NOTE)
            and DISAMBIG_NOTE not in comment)


def template_creations(contributions: Iterable[Dict], kind: str) -> List[str]:
    """``…创建：<kind>`` 的模板名（不带 ``Template:`` 前缀，子页面取主模板）。"""
    names: List[str] = []
    for contribution in contributions:
        if contribution.get("ns") != 10:
            continue
        if f"创建：{kind}" not in str(contribution.get("comment") or ""):
            continue
        title = str(contribution.get("title") or "")
        name = title.split(":", 1)[-1].strip()
        base = name.split("/")[0].strip()          # Template:IA/2026 → IA
        if base and base not in names:
            names.append(base)
    return names


def merge_songs(existing: Sequence[str], creations: Sequence[str],
                status: Dict[str, Dict], redirects: Dict[str, str]) -> List[str]:
    """现有条目 + 新建条目 → 新清单（重定向换成目标页，消歧义页丢掉，按标题去重）。

    顺序保持不变：现有条目在前（保留手写的 ``{{!}}显示文字``），新条目按创建顺序接在后面。
    """
    result: List[str] = []
    seen: set = set()

    def add(entry: str, title: str) -> None:
        key = title.strip()
        if not key or key in seen:
            return
        seen.add(key)
        result.append(entry)

    for entry in existing:
        title = entry_target(entry)
        if not title:
            continue
        if ":" in title:                     # vcp: 之类的跨站链接：查不了，原样保留
            add(entry, title)
            continue
        info = status.get(title, {})
        if info.get("disambig"):             # 消歧义页不是歌曲条目
            continue
        if info.get("redirect"):
            target = redirects.get(title, "")
            if not target or status.get(target, {}).get("disambig"):
                continue
            add(display_entry(target), target)   # 直接写目标页的名字
            continue
        add(entry, title)

    for title in creations:
        info = status.get(title, {})
        if info.get("disambig"):
            continue
        resolution = redirects.get(title, title) if info.get("redirect") else title
        if status.get(resolution, {}).get("disambig"):
            continue
        add(display_entry(resolution), resolution)
    return result


def merge_templates(existing: Sequence[str], creations: Sequence[str],
                    status: Dict[str, Dict]) -> List[str]:
    """现有模板 + 新建模板 → 新清单。

    子页面（``重音Teto/2026``）一律不列：导航框要的是 ``Template:重音Teto``；
    重定向、读不到的页面也去掉。
    """
    result: List[str] = []
    for name in [*existing, *creations]:
        name = str(name or "").strip()
        base = name.split("/")[0].strip()      # Template:IA/2026 只留 IA
        if not base or base in result:
            continue
        info = status.get("Template:" + base, {})
        if info.get("missing") or info.get("redirect"):
            continue
        result.append(base)
    return result


def rebuild(text: str, songs: Sequence[str], templates: Sequence[str]) -> str:
    """把两段新内容写回整页 wikitext（区间从后往前替换，免得下标错位）。"""
    spans = [(list_span(text, SONG_GROUP), render_song_group(songs)),
             (list_span(text, TEMPLATE_GROUP, single_line=True), render_template_group(templates))]
    for (start, end), value in sorted(spans, key=lambda item: item[0][0], reverse=True):
        text = text[:start] + value + text[end:]
    return text


# ---------------------------------------------------------------- 站点

def fetch_creations(site, user: str = USER_NAME) -> List[Dict]:
    """``ucshow=new``：这个账号建过的所有页面（按时间倒序）。"""
    result: List[Dict] = []
    params = {"action": "query", "format": "json", "formatversion": "2",
              "list": "usercontribs", "ucuser": user, "ucshow": "new",
              "uclimit": "500", "ucprop": "title|timestamp|comment"}
    while True:
        data = site.simple_request(**params).submit()
        result.extend(data.get("query", {}).get("usercontribs") or [])
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
    return result


def page_status(site, titles: Sequence[str]) -> Dict[str, Dict]:
    """``{标题: {missing, redirect, disambig}}``。"""
    status: Dict[str, Dict] = {}
    wanted = [title for title in dict.fromkeys(titles) if queryable(title)]
    for start in range(0, len(wanted), REQUEST_BATCH):
        chunk = wanted[start:start + REQUEST_BATCH]
        data = site.simple_request(
            action="query", format="json", formatversion="2",
            titles="|".join(chunk), prop="info|categories|templates",
            cllimit="max", tllimit="max").submit()
        for page in data.get("query", {}).get("pages") or []:
            categories = [item.get("title", "") for item in page.get("categories", [])]
            templates = [item.get("title", "") for item in page.get("templates", [])]
            status[page.get("title", "")] = {
                "missing": bool(page.get("missing")),
                "redirect": bool(page.get("redirect")),
                "disambig": (any("消歧" in name for name in categories)
                             or "Template:Disambig" in templates),
            }
        time.sleep(0.2)
    return status


def redirect_map(site, titles: Sequence[str]) -> Dict[str, str]:
    """``{重定向标题: 目标标题}``。"""
    mapping: Dict[str, str] = {}
    wanted = [title for title in dict.fromkeys(titles) if queryable(title)]
    for start in range(0, len(wanted), REQUEST_BATCH):
        chunk = wanted[start:start + REQUEST_BATCH]
        data = site.simple_request(action="query", format="json", formatversion="2",
                                   titles="|".join(chunk), redirects="1",
                                   prop="info").submit()
        for row in data.get("query", {}).get("redirects") or []:
            mapping[row.get("from", "")] = row.get("to", "")
        time.sleep(0.2)
    return mapping


# ---------------------------------------------------------------- 主流程

def save_page(page: Page, text: str, summary: Optional[str]) -> bool:
    """保存；被别人抢先编辑时放弃本轮。"""
    page.text = text
    summary = summary or DEFAULT_SUMMARY
    try:
        page.save(summary=summary, minor=True, bot=True, tags="Bot")
        return True
    except EditConflictError as exc:
        pywikibot.error(f"页面刚被其他进程编辑，放弃本轮：{exc}")
        return False
    except TypeError:                        # 旧版 pywikibot 把 bot 叫 botflag
        page.save(summary=summary, minor=True, botflag=True)
        return True
    except pywikibot.exceptions.APIError as exc:
        pywikibot.warning(f"带 bot/tags 保存失败，改用普通保存：{exc}")
        page.save(summary=summary, minor=True)
        return True


def run_once(site, write: bool = False, summary: Optional[str] = None) -> bool:
    """更新一轮。返回页面是否需要（或已经）改动。"""
    if write:
        if not site.logged_in():
            site.login()
        if not site.logged_in():
            raise RuntimeError("登录失败：请检查 user-config.py 与 user-password.py")
    page = Page(site, PAGE_TITLE)
    original = page.text or ""

    songs_span = list_span(original, SONG_GROUP)
    template_span = list_span(original, TEMPLATE_GROUP, single_line=True)
    existing_songs = parse_links(original[songs_span[0]:songs_span[1]])
    existing_templates = parse_templates(original[template_span[0]:template_span[1]])

    contributions = fetch_creations(site)
    new_songs = [row["title"] for row in contributions if is_song_creation(row)]
    new_songs.reverse()                      # ucshow=new 是倒序，补在清单末尾要按创建顺序
    new_templates = template_creations(contributions, TEMPLATE_GROUP)

    titles = [entry_target(entry) for entry in existing_songs] + new_songs
    titles += ["Template:" + name for name in [*existing_templates, *new_templates]]
    status = page_status(site, titles)
    redirects = redirect_map(site, titles)
    # 重定向的目标也要看：目标可能是消歧义页，那样整条都不该留
    status.update(page_status(site, [target for target in redirects.values() if target]))

    songs = merge_songs(existing_songs, new_songs, status, redirects)
    templates = merge_templates(existing_templates, new_templates, status)
    text = rebuild(original, songs, templates)

    added_songs = len(songs) - len(existing_songs)
    pywikibot.output(f"Vocawiki时期：{len(existing_songs)} → {len(songs)} 条"
                     f"（新增 {max(0, added_songs)}）")
    pywikibot.output(f"歌姬模板：{existing_templates} → {templates}")

    if text.rstrip() == original.rstrip():
        pywikibot.output("页面无需更新。")
        return False
    if not write:
        pywikibot.output("[dry-run] 页面有改动；加 --write 以保存。")
        return True
    if save_page(page, text, summary):
        pywikibot.output("已更新页面。")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="更新贡献页的「Vocawiki时期」与「歌姬模板」")
    parser.add_argument("--write", action="store_true", help="保存页面（默认只干跑）")
    parser.add_argument("--summary", default=None, help="编辑摘要")
    args = parser.parse_args()
    run_once(pywikibot.Site(), args.write, args.summary)


if __name__ == "__main__":
    main()
