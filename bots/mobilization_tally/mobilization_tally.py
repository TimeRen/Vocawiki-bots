"""维护 [[Vocawiki:动员令/2027年冬/计分板]] 与 [[…/排行榜]]。

按 `/计分板` 页面上那张说明表格约定的方式识别得分点（新建 / 移动 / 编辑摘要关键字），
再把每个人的得分写进计分板、把汇总写进排行榜。

    python -m bots.mobilization_tally                     # 预演：只打印，不写维基
    python -m bots.mobilization_tally --out-dir output/x   # 预演 + 把两个页面写成文件
    python -m bots.mobilization_tally --write              # 真正写回维基

活动窗口是 2026-12-01 00:00 ~ 2027-02-15 23:59（+0800）；窗口外脚本直接退出，
所以 cron 可以一直挂着，到点自然开始（`--ignore-window` 可以手动越过）。
"""
from __future__ import annotations

import argparse
import pickle
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import pywikibot
from pywikibot import Page
from pywikibot.exceptions import EditConflictError

from bots.mobilization_tally.presets import get_preset
from bots.mobilization_tally.update_scoreboard import (add_score_lines, collect_scores,
                                                       rebuild_ranking)
from bots.mobilization_tally.utils import CST, adjust, link_titles, set_site

TARGET_DEFAULT = "Vocawiki:动员令/2027年冬"
STATE_PATH = Path("data/vj2027winter_mobilization.pickle")

EVENT_START = datetime(2026, 12, 1, 0, 0, tzinfo=CST)
EVENT_END = datetime(2027, 2, 15, 23, 59, tzinfo=CST)

SIGNUP_SUFFIX = "/报名"
SCOREBOARD_SUFFIX = "/计分板"
RANKING_SUFFIX = "/排行榜"

SCOREBOARD_SUMMARY = "更新计分板"
RANKING_SUMMARY = "更新排行榜"

DEFAULT_EDIT_LIMIT = 500
EVENT_START_KEY = "__EVENT_START"


# ---------------------------------------------------------------- 小工具

def parse_time(value: Optional[str]) -> Optional[datetime]:
    """`2026-12-01` / `2026-12-01T00:00:00+08:00` → 带时区的 datetime（默认东八区）。"""
    if not value:
        return None
    text = value.strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        parsed = datetime.strptime(text, "%Y-%m-%d")
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=CST)
    return parsed.astimezone(CST)


def participants(site, target: str) -> List[str]:
    """报名区里的用户名（`*-{[[U:某某]]}-` 这种链接），去重保序。"""
    text = Page(site, target + SIGNUP_SUFFIX).text or ""
    result: List[str] = []
    for title in link_titles(text):
        lowered = title.lower()
        if lowered.startswith("user:"):
            name = title[len("user:"):].strip()
        elif lowered.startswith("u:"):
            name = title[len("u:"):].strip()
        else:
            continue
        if name and name not in result:
            result.append(name)
    return result


def parse_timestamp(value) -> Optional[datetime]:
    """把 pywikibot 的时间戳（11.x 里是 ISO 字符串，旧版是 Timestamp）统一成 datetime。"""
    if isinstance(value, datetime):
        return value.astimezone(CST) if value.tzinfo else value.replace(tzinfo=CST)
    if not value:
        return None
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed.astimezone(CST) if parsed.tzinfo else parsed.replace(tzinfo=CST)


def user_contributions(site, username: str, limit: int = DEFAULT_EDIT_LIMIT) -> List[dict]:
    """最近 `limit` 笔编辑，转成计分规则认识的形状（按时间正序）。

    ⚠️ pywikibot 11 起 `site.usercontribs()` 给的 `timestamp` 是 **ISO 字符串**
    （旧版是 `Timestamp` 对象），这里统一解析成 datetime——不解析的话时间比较
    会让每一条都落空（2026-11-21 实测：500 笔编辑一条都没进窗口）。
    """
    rows = []
    for item in site.usercontribs(user=username, total=limit):
        rows.append({
            "page": Page(site, item["title"]),
            "title": item["title"],
            "ns": item["ns"],
            "timestamp": parse_timestamp(item.get("timestamp")),
            "new": "new" in item,
            "minor": "minor" in item,
            "comment": item.get("comment") or "",
            "revid": item.get("revid"),
        })
    rows.sort(key=lambda row: row["timestamp"] or datetime.min.replace(tzinfo=CST))
    return rows


def load_state(path: Path) -> Dict:
    try:
        with Path(path).open("rb") as handle:
            data = pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_state(path: Path, state: Dict) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(state, handle)


def in_window(stamp, start: datetime, end: datetime) -> bool:
    return start < stamp <= end


def _as_datetime(value) -> Optional[datetime]:
    return parse_timestamp(value)


def collect_additions(contributions: Sequence[dict], preset,
                      since: datetime, until: datetime) -> Dict[str, List[str]]:
    """跑一遍所有计分项，返回 `{类别: [计分行]}`（按时间顺序）。"""
    additions: Dict[str, List[str]] = {}
    for contribution in contributions:
        stamp = _as_datetime(contribution.get("timestamp"))
        if stamp is None or not in_window(stamp, since, until):
            continue
        for category, score in preset.items():
            try:
                line = score(contribution)
            except Exception as exc:                    # noqa: BLE001  单条失败不能中断整轮
                pywikibot.error(f"{contribution.get('title')} 的「{category}」判定失败：{exc}")
                continue
            if line:
                additions.setdefault(category, []).append(line)
                pywikibot.output(f"  + [{category}] {line}")
    return additions


def save_page(site, title: str, text: str, summary: str) -> bool:
    """内容有变化才保存；编辑冲突时重读一次再写。"""
    page = Page(site, title)
    original = page.text or ""
    if original.strip() == (text or "").strip():
        pywikibot.output(f"{title}：没有变化，跳过")
        return False
    for attempt in (1, 2):
        try:
            page.text = text
            page.save(summary=summary, minor=True, bot=True, tags="Bot")
            pywikibot.output(f"{title}：已保存")
            return True
        except EditConflictError:
            if attempt == 2:
                raise
            pywikibot.warning(f"{title}：编辑冲突，重读后再写")
            page = Page(site, title)
            page.text = text
    return False


def write_preview(out_dir: Path, ranking: str, scoreboard: str) -> None:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for name, text in (("排行榜.wikitext", ranking), ("计分板.wikitext", scoreboard)):
        (out_dir / name).write_text(text, encoding="utf-8")
    pywikibot.output(f"预览已写入 {out_dir}（排行榜.wikitext / 计分板.wikitext）")


# ---------------------------------------------------------------- 主流程

def run_once(site, target: str = TARGET_DEFAULT, write: bool = False,
             out_dir: Optional[str] = None, state_path: Path = STATE_PATH,
             edit_limit: int = DEFAULT_EDIT_LIMIT,
             event_start: Optional[datetime] = None,
             event_end: Optional[datetime] = None,
             refresh: bool = False, ignore_window: bool = False,
             preset_name: str = "vj2027", now: Optional[datetime] = None) -> int:
    """跑一轮。返回本轮新增的计分行数。"""
    now = now or datetime.now(CST)
    start = event_start or EVENT_START
    end = event_end or EVENT_END
    if not ignore_window:
        if now < start:
            pywikibot.output(f"活动还没开始（{start:%Y-%m-%d %H:%M %z}），本轮不处理。")
            return 0
        if now > end:
            pywikibot.output(f"活动已结束（{end:%Y-%m-%d %H:%M %z}），本轮不处理。")
            return 0

    set_site(site)
    preset = get_preset(preset_name)
    state = load_state(state_path)
    users = participants(site, target)
    pywikibot.output(f"报名者 {len(users)} 人：" + ("、".join(users) or "（空）"))

    scoreboard_page = Page(site, target + SCOREBOARD_SUFFIX)
    ranking_page = Page(site, target + RANKING_SUFFIX)
    scoreboard_text = scoreboard_page.text or ""
    ranking_text = ranking_page.text or ""
    state.setdefault(EVENT_START_KEY, time.mktime(start.timetuple()))

    additions: Dict[str, Dict[str, List[str]]] = {}
    for username in users:
        stored = None if refresh else _as_datetime(state.get(username))
        since = max(stored or start, start)
        contributions = user_contributions(site, username, edit_limit)
        pywikibot.output(f"{username}: {len(contributions)} 笔最近编辑，从 {since:%Y-%m-%d %H:%M} 起算")
        found = collect_additions(contributions, preset, since, min(now, end))
        if found:
            additions[username] = found
        state[username] = now.timestamp()

    scoreboard_text, added = add_score_lines(scoreboard_text, additions)
    ranking_text = rebuild_ranking(ranking_text, scoreboard_text)
    scores = collect_scores(scoreboard_text)
    pywikibot.output(f"本轮新增 {added} 行；计分板共 {len(scores)} 人")
    for user, values in sorted(scores.items(),
                               key=lambda item: -adjust(sum(item[1].values()))):
        pywikibot.output(f"  {user}：总分 {adjust(sum(values.values()))}")

    if out_dir:
        write_preview(Path(out_dir), ranking_text, scoreboard_text)

    if write:
        save_page(site, scoreboard_page.title(), scoreboard_text, SCOREBOARD_SUMMARY)
        save_page(site, ranking_page.title(), ranking_text, RANKING_SUMMARY)
        save_state(state_path, state)          # 只在真写过之后推进进度
    else:
        pywikibot.output("预演模式：没有写回维基（加 --write 才会保存）。")
    return added


def main(argv: Optional[Sequence[str]] = None) -> None:
    parser = argparse.ArgumentParser(description="维护 2027 年冬动员令的计分板与排行榜")
    parser.add_argument("--target", default=TARGET_DEFAULT, help="活动主页（子页面按 /计分板 等拼）")
    parser.add_argument("--write", action="store_true", help="真正写回维基")
    parser.add_argument("--dry-run", action="store_true", help="只看结果，不写维基（默认行为）")
    parser.add_argument("--out-dir", help="把两个页面的完整 wikitext 写到这个目录，便于人工核对")
    parser.add_argument("--state", default=str(STATE_PATH), help="增量进度文件")
    parser.add_argument("--event-start", help="覆盖活动开始时间（默认 2026-12-01 00:00 +0800）")
    parser.add_argument("--event-end", help="覆盖活动结束时间（默认 2027-02-15 23:59 +0800）")
    parser.add_argument("--limit", type=int, default=DEFAULT_EDIT_LIMIT,
                        help="每人最多回看多少笔编辑")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略上次进度，从活动开始重新扫（不会重复写行）")
    parser.add_argument("--ignore-window", action="store_true", help="忽略活动时间窗口")
    parser.add_argument("--preset", default="vj2027", help="计分规则（目前只有 vj2027）")
    args = parser.parse_args(argv)

    if args.write and args.dry_run:
        parser.error("--write 与 --dry-run 不能同时用")

    site = pywikibot.Site()
    if args.write:
        if not site.logged_in():
            site.login()
        if not site.logged_in():
            raise RuntimeError("登录失败：请检查 user-config.py 与 user-password.py")

    run_once(site, target=args.target, write=args.write, out_dir=args.out_dir,
             state_path=Path(args.state), edit_limit=args.limit,
             event_start=parse_time(args.event_start), event_end=parse_time(args.event_end),
             refresh=args.refresh, ignore_window=args.ignore_window,
             preset_name=args.preset)


if __name__ == "__main__":
    main()
