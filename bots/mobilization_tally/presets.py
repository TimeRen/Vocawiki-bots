"""2027 年冬动员令的计分规则（`Vocawiki:动员令/2027年冬/计分规则`）。

一个「计分项」= 一条贡献 → 一行计分板文本（`[[页面]]（+1.50）`）或 None。
判定只依赖站内事实（分类、编辑摘要、正文），不做质量判断——「非机翻」「有来源」这些留给评委。

口径出处（2026-11-21 与用户确认）：
  * 创建歌曲 1.5 分；
  * 翻译 = `translated` 字节 / 150；
  * 注音 0.2 分；
  * 周刊 20 分，标题含「周刊UTAU排行榜」（U刊）25 分；
  * 大家族模板 每 10 个（蓝链）链接 1 分，至少要 2 个；
  * P主 / 歌姬 / 引擎 / 演唱会等条目 = 有效字节 / 200；
  * 内容扩充同上，但该笔原始增量要 ≥ 500 字节。
"""
from __future__ import annotations

from typing import Callable, Dict, List, Optional, Sequence

import pywikibot
import wikitextparser as wtp
from pywikibot import Page

from bots.mobilization_tally.utils import (adjust, category_names, count_bytes,
                                           count_bytes_simple, format_points,
                                           get_site)
from utils.utils import find_templates, get_links_in_template

# ---------------------------------------------------------------- 分数线

SONG_POINTS = 1.5
TRANSLATION_BYTES_PER_POINT = 150
FURIGANA_POINTS = 0.2
WEEKLY_POINTS = 20
WEEKLY_U_POINTS = 25
WEEKLY_U_MARKER = "周刊UTAU排行榜"
TEMPLATE_LINKS_PER_POINT = 10
TEMPLATE_MIN_LINKS = 2
ARTICLE_BYTES_PER_POINT = 200
EXPAND_MIN_BYTES = 500

# ---------------------------------------------------------------- 站内分类

# 歌曲：这些分类说明「由虚拟歌手演唱」（与 `utils/name_converter` 的引擎表一致）
SONG_ENGINE_CATEGORIES = {
    "使用VOCALOID的歌曲", "使用UTAU的歌曲", "使用CeVIO的歌曲", "使用初音未来 NT的歌曲",
    "使用DeepVocal的歌曲", "使用MAIDLOID的歌曲", "使用MUTA的歌曲", "使用NEUTRINO的歌曲",
    "使用袅袅虚拟歌手的歌曲", "使用Sharpkey的歌曲", "使用Synthesizer V的歌曲",
    "使用VOICEROID的歌曲", "使用VOICEVOX的歌曲", "使用VocalSharp的歌曲",
    "使用X Studio的歌曲", "使用VOICEPEAK的歌曲", "使用VoiSona的歌曲",
    "使用A.I.VOICE的歌曲", "使用ACE Studio的歌曲",
}
WEEKLY_CATEGORY = "周刊VOCAL Character & UTAU排行榜"
# 大家族模板：P主模板直接在 `Category:P主模板`；歌姬模板是 `Category:<歌姬>模板`，
# 而后者属于 `Category:虚拟歌手模板`（voca.wiki 上没有 moegirl 的「虚拟歌手音乐人模板」）。
NAVBOX_CATEGORIES = {"P主模板", "虚拟歌手音乐人模板"}
VOCALIST_TEMPLATE_CATEGORY = "虚拟歌手模板"

# P主 / 歌姬 / 引擎 / 演唱会等条目（`P主` 是 voca.wiki 上的实际分类，moegirl 那边叫「VOCALOID职人」）
ARTICLE_CATEGORIES = {"P主", "音声合成软件", "演唱会"}
ARTICLE_CATEGORY_SUFFIX = "角色"
ARTICLE_CATEGORY_EXCLUDE = {"P主原创角色"}

TRANSLATION_KEYWORDS = ("翻译歌词", "歌词翻译", "歌詞翻譯", "翻譯歌詞")
FURIGANA_KEYWORD = "歌词注音"
EXPAND_KEYWORD = "内容扩充"


# ---------------------------------------------------------------- 纯计算（可单测）

def translation_points(translated_bytes: int) -> float:
    """翻译得分 = 译文有效字节 / 150，保留两位小数。"""
    return adjust(max(0, translated_bytes) / TRANSLATION_BYTES_PER_POINT)


def weekly_points(title: str) -> float:
    """周刊：U刊（`周刊UTAU排行榜…`）25 分，其余 20 分。"""
    return WEEKLY_U_POINTS if WEEKLY_U_MARKER in (title or "") else WEEKLY_POINTS


def template_points(link_count: int) -> Optional[float]:
    """大家族模板：每 10 个链接 1 分（按比例给分，2 个链接 = 0.20）；不足 2 个链接不计分。"""
    if link_count < TEMPLATE_MIN_LINKS:
        return None
    return adjust(link_count / TEMPLATE_LINKS_PER_POINT)


def article_points(effective_bytes: int) -> float:
    """P主 / 歌姬 / 引擎等条目：有效字节 / 200。"""
    return adjust(max(0, effective_bytes) / ARTICLE_BYTES_PER_POINT)


def expand_points(raw_bytes: int, effective_bytes: int) -> Optional[float]:
    """内容扩充：原始增量 < 500 字节、或有效字节没增加时都不记。"""
    if raw_bytes < EXPAND_MIN_BYTES or effective_bytes <= 0:
        return None
    return article_points(effective_bytes)


def scored_line(title: str, points: float) -> str:
    """计分板里的一行：`[[页面]]（+1.50）`。"""
    return f"[[{title}]]（+{format_points(points)}）"


def is_article_category(categories: Sequence[str]) -> bool:
    for name in categories:
        if name in ARTICLE_CATEGORIES:
            return True
        if name.endswith(ARTICLE_CATEGORY_SUFFIX) and name not in ARTICLE_CATEGORY_EXCLUDE:
            return True
    return False


# ---------------------------------------------------------------- 贡献筛选

def contribution_filter(c, new: bool = True, ns: int = 0) -> bool:
    """这条贡献算不算「这次任务里的编辑」。

    `new=True` 表示只看新建页面；从用户页移动过来的（编辑摘要「移动页面 … [[User:…]]」）
    也算——那是页面主人常用的做法（见 `/计分板` 的说明表格）。
    """
    comment = c.get("comment") or ""
    created = c.get("new") or ("移动页面" in comment and "[[User:" in comment)
    return (not new or created) and c.get("ns") == ns


def is_vj_song(page) -> bool:
    """歌曲条目：属「使用X的歌曲」分类，并且正文里真的有歌词模板。"""
    if not (category_names(page) & SONG_ENGINE_CATEGORIES):
        return False
    parsed = wtp.parse(page.text or "")
    return len(find_templates(parsed.templates, "lyricskai", loose=True)) > 0


# ---------------------------------------------------------------- 各项判定

def vj_create_song(contribution) -> Optional[str]:
    if not contribution_filter(contribution):
        return None
    page: Page = contribution["page"]
    if not is_vj_song(page):
        return None
    return scored_line(page.title(), SONG_POINTS)


def vj_translate(contribution) -> Optional[str]:
    """歌词翻译：摘要里写了「翻译歌词 / 歌词翻译」，按 `translated` 字节 / 150 计分。"""
    if not contribution_filter(contribution, new=False):
        return None
    comment = contribution.get("comment") or ""
    if not any(keyword in comment for keyword in TRANSLATION_KEYWORDS):
        return None
    page: Page = contribution["page"]
    blocks = find_templates(wtp.parse(page.text or "").templates, "LyricsKai", loose=True)
    if not blocks:
        pywikibot.warning(f"{page.title()}：摘要说是翻译，但没找到 {{LyricsKai}}")
        return None
    translated_bytes = 0
    for block in blocks:
        arg = block.get_arg("translated")
        if arg is None:
            continue
        translated_bytes += count_bytes_simple((arg.value or "").strip())
    if translated_bytes == 0:
        return None
    return scored_line(page.title(), translation_points(translated_bytes))


def vj_furigana(contribution) -> Optional[str]:
    """歌词注音：摘要里写了「歌词注音」的歌曲条目编辑。"""
    if not contribution_filter(contribution, new=False):
        return None
    if FURIGANA_KEYWORD not in (contribution.get("comment") or ""):
        return None
    page: Page = contribution["page"]
    if not is_vj_song(page):
        return None
    return scored_line(page.title(), FURIGANA_POINTS)


def vj_create_weekly(contribution) -> Optional[str]:
    """创建周刊条目：U刊 25 分，其余 20 分。"""
    if not contribution_filter(contribution):
        return None
    page: Page = contribution["page"]
    if WEEKLY_CATEGORY not in category_names(page):
        return None
    return scored_line(page.title(), weekly_points(page.title()))


def _is_article_title(site, title: str) -> bool:
    """`页面` / `Re:Dial` 这种条目名 → True；命名空间（`Category:…`）与跨维基前缀
    （`zhmoe:…`）→ False。

    跨维基前缀必须挡掉：`Page(site, "zhmoe:理想之鄉")` 会跑到萌百去查，既慢又会报
    `action-notallowed`（官方站只放行 info 类模块，见 user-config.py 的注释）。
    `Re:Dial` 这类**标题本身带冒号**的条目不能误杀，所以交给 `pywikibot.Link` 解析。
    """
    try:
        link = pywikibot.Link(title, site)
    except Exception:                                # noqa: BLE001  解析不了就跳过
        return False
    if link.site != site:                            # 跨维基链接
        return False
    return link.namespace.id == 0


def article_links_in_template(page: Page) -> List[str]:
    """模板里的条目链接（展开模板后取 ns0、且**确实是蓝链**的去重标题）。

    蓝链是一次批量查的（`site.preloadpages`，每批 50 个）：`Template:IA` 那种有 500 多个
    链接，逐个 `exists()` 要 6 分钟（2026-11-21 实测），批量后几秒。
    """
    site = get_site() or page.site()
    titles: List[str] = []
    seen = set()
    for title in get_links_in_template(page):
        title = (title or "").strip()
        if not title or title in seen:
            continue
        seen.add(title)
        if not _is_article_title(site, title):
            continue
        titles.append(title)
    if not titles:
        return []
    targets = [Page(site, title) for title in titles]
    try:
        # 消费生成器即可：`preloadpages` 会把存在性写回这些 Page 对象（每批 50 个）
        for _ in site.preloadpages(targets, groupsize=50, content=False):
            pass
    except Exception as exc:                         # noqa: BLE001  批量查询失败就别硬算
        pywikibot.warning(f"{page.title()}：批量核对链接失败（{exc}）")
        return []
    result = []
    for target in targets:
        try:
            if target.namespace().id == 0 and target.exists():
                result.append(target.title())
        except Exception as exc:                     # noqa: BLE001
            pywikibot.warning(f"{page.title()}：核对链接 {target.title()} 失败（{exc}）")
    return result


def is_navbox_template(page) -> bool:
    """大家族模板：P主模板（`Category:P主模板`）或歌姬模板（`Category:<歌姬>模板`→`虚拟歌手模板`）。"""
    categories = category_names(page)
    if categories & NAVBOX_CATEGORIES:
        return True
    site = get_site() or page.site()
    if site is None:                                 # 单测 / 离线时只能按分类名判断
        return False
    for name in categories:
        if not name.endswith("模板"):
            continue
        try:
            parent = {c.title(with_ns=False) for c in Page(site, f"Category:{name}").categories()}
        except Exception as exc:                     # noqa: BLE001  读不到分类页就当不是
            pywikibot.warning(f"{page.title()}：核对分类 {name} 失败（{exc}）")
            continue
        if VOCALIST_TEMPLATE_CATEGORY in parent:
            return True
    return False


def vj_create_producer_template(contribution, links: Optional[Sequence[str]] = None) -> Optional[str]:
    """创建大家族模板：每 10 个链接 1 分（`links` 可注入，便于单测）。"""
    if not contribution_filter(contribution, ns=10):
        return None
    page: Page = contribution["page"]
    if not is_navbox_template(page):
        return None
    if links is None:
        links = article_links_in_template(page)
    points = template_points(len(links))
    if points is None:
        return None
    return scored_line(page.title(), points)


def vj_create_producer(contribution) -> Optional[str]:
    """创建 P主 / 歌姬 / 引擎 / 演唱会等条目：有效字节 / 200。"""
    if not contribution_filter(contribution):
        return None
    page: Page = contribution["page"]
    if not is_article_category(category_names(page)):
        return None
    return scored_line(page.title(), article_points(count_bytes(page.text or "")))


def _revision_text(revision) -> str:
    if '*' in revision:
        return revision['*']
    return revision['slots']['main']['*']


def revision_pair(page: Page, revid: Optional[int], limit: int = 100):
    """`(这一版正文, 上一版正文)`；在最近 `limit` 版里找不到时返回 None。"""
    if not revid:
        return None
    revisions = page.revisions(content=True, total=limit)
    for revision in revisions:
        if revision['revid'] == revid:
            current = _revision_text(revision)
            try:
                previous = _revision_text(next(revisions))
            except StopIteration:
                return None
            return current, previous
    return None


def vj_expand_article(contribution, texts=None) -> Optional[str]:
    """扩充 P主 / 歌姬 / 引擎条目：摘要「内容扩充」，原始增量 ≥500 字节才计分。

    `texts` 可注入 `(这一版, 上一版)`，便于单测。
    """
    if not contribution_filter(contribution, new=False):
        return None
    if EXPAND_KEYWORD not in (contribution.get("comment") or ""):
        return None
    page: Page = contribution["page"]
    if not is_article_category(category_names(page)):
        return None
    if texts is None:
        texts = revision_pair(page, contribution.get("revid"))
    if texts is None:
        pywikibot.warning(f"{page.title()}：找不到 revid {contribution.get('revid')} 的上一版，跳过")
        return None
    current, previous = texts
    raw = count_bytes_simple(current) - count_bytes_simple(previous)
    effective = max(0, count_bytes(current) - count_bytes(previous))
    points = expand_points(raw, effective)
    if points is None:
        pywikibot.info(f"{page.title()}：增加 {raw} 字节，未达 {EXPAND_MIN_BYTES} 字节门槛")
        return None
    return scored_line(page.title(), points)


# ---------------------------------------------------------------- 规则表

Preset = Dict[str, Callable[..., Optional[str]]]

# 排行榜的固定列（顺序即规则页的顺序；页面里多出来的类别会追加在后面）
CATEGORY_ORDER = (
    "创建歌曲",
    "歌词翻译",
    "歌词注音",
    "创建周刊",
    "创建大家族模板",
    "创建P主/歌姬/引擎条目",
    "内容扩充",
)

VJ_2027_WINTER: Preset = {
    "创建歌曲": vj_create_song,
    "歌词翻译": vj_translate,
    "歌词注音": vj_furigana,
    "创建周刊": vj_create_weekly,
    "创建大家族模板": vj_create_producer_template,
    "创建P主/歌姬/引擎条目": vj_create_producer,
    "内容扩充": vj_expand_article,
}

PRESETS: Dict[str, Preset] = {"vj2027": VJ_2027_WINTER}


def get_preset_names() -> List[str]:
    return list(PRESETS)


def get_preset(name: str = "vj2027") -> Preset:
    if name not in PRESETS:
        raise RuntimeError("没有名为 " + name + " 的计分规则")
    return PRESETS[name]
