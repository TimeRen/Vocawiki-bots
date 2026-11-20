"""计分板 / 排行榜的**文本处理**：解析、追加记分行、生成排行榜表格。

这里只跟字符串打交道（`wikitextparser` 只用来认节标题里的用户名），
不联网、不读页面，方便单测。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional, Sequence, Tuple

import wikitextparser as wtp

from bots.mobilization_tally.presets import CATEGORY_ORDER
from bots.mobilization_tally.utils import adjust, format_points, username_to_section_title

USERNAME_SECTION_LEVEL = 2
SCORE_SECTION_LEVEL = 3
TOTAL_COLUMN = "总分"
RANKING_SECTION = "排行榜"

# 计分行里的分数：`（+1.50）` / `(+1.5)`；一行里出现多次时求和（上游就支持一行多个）
SCORE_RE = re.compile(r"[(（]\s*\+?\s*([0-9]+(?:\.[0-9]+)?)\s*[)）]")
HEADING_RE = re.compile(r"^(={1,6})\s*(.+?)\s*\1\s*$")


# ---------------------------------------------------------------- 用户名 / 节

def parse_section_title_username(title: str) -> Optional[str]:
    """`-{[[U:人间百态|人间百态]]}-` → `人间百态`；不是用户链接返回 None。

    用链接**目标**判断，显示名只作参考：有人写 `[[U:x|x]]`，也有人写 `[[U:x]]`。
    """
    links = wtp.parse(title or "").wikilinks
    if not links:
        return None
    target = (links[0].title or "").strip()
    lowered = target.lower()
    for prefix in ("user:", "u:"):
        if lowered.startswith(prefix):
            return target[len(prefix):].strip() or None
    return None


def _heading(line: str) -> Optional[Tuple[int, str]]:
    match = HEADING_RE.match(line)
    if not match:
        return None
    return len(match.group(1)), match.group(2).strip()


def _find_section(lines: Sequence[str], level: int, start: int = 0,
                  stop: Optional[int] = None,
                  username: Optional[str] = None,
                  title: Optional[str] = None) -> Optional[Tuple[int, int, int]]:
    """找 `(标题行下标, 正文开始, 正文结束)`；正文到下一个同级或更高级标题为止。"""
    stop = len(lines) if stop is None else stop
    for index in range(start, stop):
        heading = _heading(lines[index])
        if not heading or heading[0] != level:
            continue
        if username is not None and parse_section_title_username(heading[1]) != username:
            continue
        if title is not None and heading[1] != title:
            continue
        end = stop
        for probe in range(index + 1, stop):
            following = _heading(lines[probe])
            if following and following[0] <= level:
                end = probe
                break
        return index, index + 1, end
    return None


# ---------------------------------------------------------------- 计分板

def collect_scores(text: str) -> Dict[str, Dict[str, float]]:
    """计分板文本 → `{用户名: {类别: 分数}}`（只统计 `== 用户 ==` / `=== 类别 ===` 里的 `（+X）`）。

    手写的行与机器人写的一样处理：评委直接在页面上改分、加行都会被算进总分。
    """
    scores: Dict[str, Dict[str, float]] = {}
    current: Optional[str] = None
    for line in (text or "").split("\n"):
        heading = _heading(line)
        if heading is None:
            continue
        level, title = heading
        if level == USERNAME_SECTION_LEVEL:
            current = parse_section_title_username(title)
            if current:
                scores.setdefault(current, {})
            continue
        if level <= USERNAME_SECTION_LEVEL:                 # 其他二级节：不再是某个人的
            current = None
            continue
        if level != SCORE_SECTION_LEVEL or not current:
            continue
        scores[current].setdefault(title, 0.0)
    # 第二遍：按节归属把分数累加进去
    current = None
    category = None
    for line in (text or "").split("\n"):
        heading = _heading(line)
        if heading is not None:
            level, title = heading
            if level == USERNAME_SECTION_LEVEL:
                current, category = parse_section_title_username(title), None
                continue
            if level <= USERNAME_SECTION_LEVEL:
                current, category = None, None
                continue
            category = title if (level == SCORE_SECTION_LEVEL and current) else None
            continue
        if current is None or category is None:
            continue
        for match in SCORE_RE.finditer(line):
            scores[current][category] += float(match.group(1))
    return scores


def ranking_columns(scores: Dict[str, Dict[str, float]]) -> List[str]:
    """固定 7 列在前，页面里多出来的类别按出现顺序追加。"""
    columns = list(CATEGORY_ORDER)
    for user in scores.values():
        for name in user:
            if name not in columns:
                columns.append(name)
    return columns


def _cell(value: float) -> str:
    return format_points(value)


def render_ranking(scores: Dict[str, Dict[str, float]]) -> str:
    """把分数渲染成 `wikitable sortable`（按总分降序，同分按用户名）。"""
    columns = ranking_columns(scores)
    totals = {name: 0.0 for name in [*columns, TOTAL_COLUMN]}
    rows: List[str] = []
    order = sorted(scores, key=lambda user: (-adjust(sum(scores[user].values())), user))
    for rank, user in enumerate(order, start=1):
        values = []
        for name in columns:
            value = scores[user].get(name, 0.0)
            totals[name] += value
            values.append(_cell(value))
        total = adjust(sum(scores[user].values()))
        totals[TOTAL_COLUMN] += total
        rows.append(f"| {rank} || -{{[[U:{user}|{user}]]}}- || "
                    + " || ".join([*values, _cell(total)]))

    table = ["{| class=\"wikitable sortable\"", "|-",
             "! 排名 !! 用户名 !! " + " !! ".join([*columns, TOTAL_COLUMN])]
    for row in rows:
        table.extend(["|-", row])
    table.extend(["|- class=\"sortbottom\"",
                  "! 总和 !! !! " + " !! ".join(_cell(totals[name])
                                                for name in [*columns, TOTAL_COLUMN]),
                  "|}"])
    return "\n".join(table)


def set_section_body(text: str, level: int, title: str, body: str) -> str:
    """把 `level` 级、标题为 `title` 的节的正文换成 `body`；没有这个节就追加到末尾。"""
    lines = (text or "").split("\n")
    found = _find_section(lines, level, title=title)
    if found is None:
        equal = "=" * level
        stripped = (text or "").rstrip("\n")
        return f"{stripped}\n\n{equal} {title} {equal}\n{body}\n"
    start, body_start, body_end = found
    new_lines = lines[:body_start] + ["", *body.split("\n"), ""] + lines[body_end:]
    return "\n".join(new_lines)


def rebuild_ranking(ranking_text: str, scoreboard_text: str) -> str:
    """由计分板文本重建排行榜页面（保留导语与其他节）。"""
    scores = collect_scores(scoreboard_text)
    return set_section_body(ranking_text, USERNAME_SECTION_LEVEL, RANKING_SECTION,
                            render_ranking(scores))


# ---------------------------------------------------------------- 追加记分行

def _add_lines_to_category(lines: List[str], user: str, category: str,
                           new_lines: Sequence[str]) -> int:
    """给某个用户的某个类别追加 `#...` 行，返回实际新增条数（整行相同则跳过）。"""
    found = _find_section(lines, USERNAME_SECTION_LEVEL, username=user)
    if found is None:
        lines.extend(["", f"{'=' * USERNAME_SECTION_LEVEL} "
                           f"{username_to_section_title(user)} "
                           f"{'=' * USERNAME_SECTION_LEVEL}"])
        found = _find_section(lines, USERNAME_SECTION_LEVEL, username=user)
    _, body_start, body_end = found

    inside = _find_section(lines, SCORE_SECTION_LEVEL, start=body_start, stop=body_end,
                           title=category)
    if inside is None:
        lines[body_end:body_end] = ["", f"{'=' * SCORE_SECTION_LEVEL} {category} "
                                        f"{'=' * SCORE_SECTION_LEVEL}"]
        found = _find_section(lines, USERNAME_SECTION_LEVEL, username=user)
        _, body_start, body_end = found
        inside = _find_section(lines, SCORE_SECTION_LEVEL, start=body_start, stop=body_end,
                               title=category)
    _, cat_start, cat_end = inside

    existing = {line.strip().lstrip("#*").strip() for line in lines[cat_start:cat_end]}
    added = 0
    payload = []
    for line in new_lines:
        key = line.strip().lstrip("#*").strip()
        if not key or key in existing:
            continue
        existing.add(key)
        payload.append("#" + key)
        added += 1
    if payload:
        # 追加到该类别正文的末尾（去掉尾部空行再补一个空行）
        insert_at = cat_end
        while insert_at > cat_start and not lines[insert_at - 1].strip():
            insert_at -= 1
        lines[insert_at:insert_at] = payload
        if insert_at + len(payload) < len(lines):
            lines[insert_at + len(payload):insert_at + len(payload)] = [""]
    return added


def add_score_lines(scoreboard_text: str,
                    additions: Dict[str, Dict[str, Sequence[str]]]) -> Tuple[str, int]:
    """把 `{用户名: {类别: [行]}}` 追加进计分板文本，返回 `(新文本, 新增行数)`。

    只追加、不删除也不改顺序；已经存在的同一行会被跳过（重跑不会翻倍）。
    """
    lines = (scoreboard_text or "").split("\n")
    total_added = 0
    for user, categories in additions.items():
        for category in [*CATEGORY_ORDER,
                         *[name for name in categories if name not in CATEGORY_ORDER]]:
            new_lines = categories.get(category)
            if not new_lines:
                continue
            total_added += _add_lines_to_category(lines, user, category, new_lines)
    text = "\n".join(lines)
    return text, total_added
