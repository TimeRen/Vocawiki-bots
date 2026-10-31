# -*- coding: utf-8 -*-
"""Maintain [[User:人间百态/VOCALOID中文歌词wiki补完计划]].

「补完计划」是 VOCALOID 中文歌词wiki（``w.atwiki.jp/vocaloidchly``）里**还没有**
对应 Vocawiki 条目的歌曲页面清单。机器人每次重新比对一遍：

* 来源清单：AtWiki 的「全ページ一覧」（``/list?sort=pagename``，100 条一页）。
  页面名就是歌曲名，所以不需要抓每个页面的标题。
* 对应关系：Vocawiki 上所有带 ``{{VOCALOID Songbox}}`` 的条目。比对用的名字有三种：
  条目标题、条目的所有重定向、以及 Songbox 的 ``|歌曲名称=``（``{{lj|…}}`` 里的日文名
  与中文名）。AtWiki 的页面名是日文，Vocawiki 的条目标题多是简中，只比标题会把
  「千本桜」「卑怯戦隊うろたんだー！」这类当成「还没有条目」——两者其实都是条目
  「千本樱」「卑怯战队UROTANDA」的重定向。
* 消歧义页：AtWiki 的消歧义页（如 ``pages/667``「Alice in Dreamland」）正文只有
  一个指向各版本的链接列表，不是歌曲，永远不会对应到条目。导航 / 站务 / 测试页同理。
  判断办法是抓页面正文、去掉链接后看还剩多少字：消歧义页几乎没有文字（有的直接写着
  「這是一個消歧義頁」），歌曲页至少还有作詞 / 作曲 / 歌词。这类页面不进清单。
* 站务页：导航 / 目录 / 日志 / 留言页（``pages/2``「メニュー」、``pages/1557``「LOG下半年」
  之类）正文以链接或留言为主，按 pid 白名单（``NON_SONG_PIDS``）直接排掉；「歌曲以外的翻譯」
  （``pages/448``）列出的页面（广播剧、小剧场、散文…）同样不是歌曲，每轮跟着它的清单排除。
* 「曲名/作者」：AtWiki 的页面名常写成 ``曲名/作者`` 或 ``曲名(作者)``，Vocawiki 的条目名却是
  「中文曲名(作者)」。整串比不上时把作者拆出来当佐证（Songbox 的 ``|P主=``）；一个歌名对到
  好几个条目时（``シンデレラ`` 既是 `灰姑娘(DECO*27)` 也是 `灰姑娘(zig)` 的歌名）靠它消歧。

判定结果与两个来源清单都缓存在 ``data/`` 下，所以第一次跑要抓上千个 AtWiki 页面
（几分钟），之后每轮只补新出现的页面；判定过期（默认 30 天）的页面会重新抓一次。

歌名索引用 1 小时的 TTL（``INDEX_MAX_AGE``）而不是跟页面清单共用一个：复用的索引还会用
``list=recentchanges`` 把「建索引之后新建 / 移动过的条目」补进去，所以今天新建的条目今天
就能认出来。另外，本轮算出的「已匹配」如果比页面上写的少，机器人**不保存**
（``--allow-shrink`` 可以强行保存）——那是缓存不全的信号，宁可这一轮不写。

Everything is a dry run unless ``--write`` is given.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import html
import pickle
import re
import time
import unicodedata
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

import pywikibot
from pywikibot import Page
from pywikibot.exceptions import EditConflictError

PAGE_TITLE = "User:人间百态/VOCALOID中文歌词wiki补完计划"
ATWIKI_BASE = "https://w.atwiki.jp/vocaloidchly"
ATWIKI_LIST = ATWIKI_BASE + "/list?sort=pagename"
ATWIKI_PAGE = ATWIKI_BASE + "/pages/{pid}.html"
# AtWiki 前面挂着 Cloudflare：用默认 User-Agent（含 python-urllib）会直接吃 403
ATWIKI_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
             "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")
ATWIKI_ATTEMPTS = 3
ATWIKI_TIMEOUT = 30
# 抓页面正文的并发数：AtWiki 一个页面要 2～3 秒（其中多半是它自己的延迟），
# 并发 6 路约 2 页/秒。这是个很小的 wiki，别再往上调。
PROBE_WORKERS = 6
# 每抓这么多页就把判定写一次缓存（中途断掉不用从头再来）
PROBE_CHUNK = 100
# 翻页上限（现在约 86 页；翻页条坏掉时别无限翻下去）
ATWIKI_MAX_PAGES = 500

DATA_DIR = Path("data")
PAGES_CACHE = DATA_DIR / "vocaloid_lyrics_completion_pages.pickle"
INDEX_CACHE = DATA_DIR / "vocaloid_lyrics_completion_index.pickle"
VERDICT_CACHE = DATA_DIR / "vocaloid_lyrics_completion_verdicts.pickle"
# 缓存格式变了就换这个号：旧缓存会被丢掉重建（这份索引重建一次约五分钟）
# 3：索引里多了 ``aliases``（歌名 → ``[(条目标题, P主)]``），用来消歧「曲名/作者」
INDEX_VERSION = 3
# 页面清单的格式版本（标题做过 NFC 规范化；3：多了 ``linked`` 非歌曲页清单）
PAGES_VERSION = 3

DEFAULT_MAX_AGE = 12 * 3600        # AtWiki 页面清单多久重建一次（秒）
# 歌名索引自己的有效期：条目一建好就该被认出来，别等一天的缓存过期
INDEX_MAX_AGE = 3600
# 复用的索引最多补多少个改动过的条目；超过就整体重建（重建约五分钟，别硬撑）
INDEX_PATCH_LIMIT = 500
DEFAULT_RECHECK = 30 * 24 * 3600   # 判定多久重新核一次（秒）
DEFAULT_SUMMARY = "更新 VOCALOID中文歌词wiki 补完计划（机器人自动比对）"

# 正文去掉链接后少于这么多字 → 不是歌曲页（消歧义、目录、站务、测试页）
MIN_SONG_TEXT = 60
# 只有链接的目录页：正文区里链接 ≥ 12 个、去掉链接后不足 120 字
LINK_ONLY_MIN_LINKS = 12
LINK_ONLY_MAX_TEXT = 120
# 页面自己写着「消歧义」的直接排除，不看字数
DISAMBIG_MARKERS = ("消歧義頁", "消歧义页", "消歧義", "消歧义", "曖昧さ回避")
# 这个 wiki 自己的页面（首页、目录、讨论区、插件页…）：正文可能写得挺长，
# 但永远不会有对应条目，直接按标题排掉
NON_SONG_TITLES = (
    "首頁", "メニュー2", "tw連結", "wiki管理討論", "翻譯討論", "求翻譯用頁面",
    "求翻譯完成曲", "求翻譯完成曲2", "其他", "派生", "合唱", "投票備分",
    "更新履歴(full)", "VOCALOID一覽", "中文歌詞列表VOCALOID別", "歌詞格式", "Q&A",
    "歌名あ行", "歌名か行", "歌名さ行", "歌名た行", "歌名な行", "歌名は行",
    "歌名ま行", "歌名や行", "歌名ら行", "歌名わ行", "歌名英數",
)
# 站务 / 目录 / 日志 / 留言页：按 pid 排（改名也不影响），比按标题猜稳得多。
# 核实过 3518「合唱コンクール」、3609「未完成人間」、2727「○○離れ」是真歌，
# 所以这里只列确认过的页面，不按关键词批量删。
NON_SONG_PIDS = frozenset({
    "2",                            # メニュー
    "15",                           # 其他原創曲（目录）
    "20",                           # 歌詞template
    "127", "128", "129",            # 作者別英數 / あ～な行 / は～わ行（作者目录）
    "130",                          # V廢海外組出品2008上半年埋沒曲發掘特集（特集页）
    "171", "236",                   # 求翻譯log / 求翻譯討論log
    "224",                          # VOCALOID Supporter（支援者名录）
    "264",                          # 作者認領區
    "448",                          # 歌曲以外的翻譯（下面那份清单的来源）
    "463",                          # コメント/wiki管理討論
    "829",                          # 求翻譯認領頁
    "1554", "1557", "1558", "1559",  # LOG-2008 / LOG下半年 / LOG上半年 / 舊留言區LOG
})
# 这些页面的正文是一份「不是歌」的清单（广播剧 / 小剧场 / 散文 / 视频解说…）：
# 它们列出的页面同样不该进清单。每轮抓一次，结果跟着页面清单一起缓存。
NON_SONG_LIST_SOURCES = ("448",)
# 站点导航（侧边栏）里的 pid：从来源页抽链接时先减掉这些，免得把导航当成清单
SITE_NAV_PIDS = frozenset({
    "1", "88", "127", "128", "129", "165", "176", "185", "186", "187", "188", "189",
    "190", "191", "192", "193", "194", "195", "196", "224", "265", "296", "448",
    "581", "752", "4035",
})

LIST_TABLE_RE = re.compile(r'<table class="pagelist">(.*?)</table>', re.S)
LIST_ROW_RE = re.compile(
    r'<a href="(?:https?:)?//w\.atwiki\.jp/vocaloidchly/pages/(\d+)\.html"[^>]*>\s*(.*?)\s*</a>',
    re.S)
LIST_LAST_PAGE_RE = re.compile(r"\?sort=pagename&(?:amp;)?pp=(\d+)")
# 正文容器：`<div id="wikibody">` 之后到「ウィキ内検索」那一行为止，不含侧边栏。
# 首页（TOP）没有那个检索块，退回页脚 / 广告位当结束标记。
BODY_RE = re.compile(
    r'<div id="wikibody"[^>]*>\s*(?:<!--@@@@@-->)?(.*?)'
    r'(?:<div class="atwiki-page-keyword">|<div id="ads">|<div id="body_footer">)', re.S)
LINK_TAG_RE = re.compile(r"<a\b[^>]*>.*?</a>", re.S)
SCRIPT_RE = re.compile(r"<script.*?</script>", re.S)
TAG_RE = re.compile(r"<[^>]+>")

SONGBOX_RE = re.compile(r"\{\{\s*VOCALOID Songbox\b(.*?)\n\s*\}\}", re.S)
SONG_NAME_RE = re.compile(r"\|\s*歌曲名称\s*=\s*([^\n]*)")
BR_RE = re.compile(r"<br\s*/?>", re.IGNORECASE)
LJ_RE = re.compile(r"\{\{lj\|([^{}]*)\}\}")
BOLD_RE = re.compile(r"'{2,}")
LINK_RE = re.compile(r"\[\[([^\]|]*\|)?([^\]]*)\]\]")
PRODUCER_RE = re.compile(r"\|\s*P主\s*=\s*([^\n]*)")
# 正文区里指向本站其他页面的链接（判断目录页、抽「歌曲以外的翻譯」的清单都用它）
PAGE_LINK_RE = re.compile(
    r'href="(?:https?:)?//w\.atwiki\.jp/vocaloidchly/pages/(\d+)\.html"[^>]*>(.*?)</a>', re.S)
# 「曲名/作者」里的作者串按这些符号切开
HINT_SPLIT_RE = re.compile(r"[×✕✖/／、,&＆+＋・\s]+")
# 页面表头注释里的「已匹配 N 個」：挡住「索引不全导致已匹配变少」的那一轮保存
MATCHED_RE = re.compile(r"已匹配\s*(\d+)\s*個")
# C0 控制字符（MediaWiki 拒收）：标题里偶尔混进来，渲染前清掉
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def clean_title(text: str) -> str:
    """页面名 / 显示文字的标准写法：NFC + 去掉控制字符。

    MediaWiki 存盘时会把正文规范化成 NFC；AtWiki 的页面名有的带着组合浊点
    （`カ` + U+3099）。不先规范化的话，存进去的版本和机器人算出来的永远差一点，
    于是每轮都判成「有改动」、反复保存。
    """
    text = unicodedata.normalize("NFC", str(text or ""))
    return CONTROL_RE.sub("", text).strip()

# ---------------------------------------------------------------- 名字归一化

def name_key(text: str) -> str:
    """比对用的页面名：全半角统一、去掉标记与空白、拉丁字母转小写。

    AtWiki 的页面名与 Vocawiki 的条目标题 / 重定向只差写法（全角 `／` 与半角、
    `{{lj|…}}`、加粗、多余空格），归一化之后才能直接比。**不去标点**：
    「14」与「1/4」是两首歌，去掉 `/` 会把它们并成一条。
    """
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = BOLD_RE.sub("", text)
    text = LJ_RE.sub(lambda match: match.group(1), text)
    text = LINK_RE.sub(lambda match: match.group(2), text)
    text = TAG_RE.sub("", text)
    text = re.sub(r"\s+", "", text)
    return text.lower()


def loose_key(text: str) -> str:
    """``name_key`` 再去掉**结尾**的标点符号。

    歌名结尾的 `！`/`?`/`…` 各站写法不一：AtWiki 是「卑怯戦隊うろたんだー！！」，
    voca 的重定向只写「卑怯戦隊うろたんだー」，精确比对就会漏。只去结尾的标点
    （不动中间），否则「1/4」这种名字会被拆坏。
    """
    return name_key(text).rstrip("!?.,;:…~-–—、。，；：・「」『』【】()（）[]{}\"'“”‘’")


# NON_SONG_TITLES 的归一化形式（按页面名比，不受全半角 / 空格影响）
NON_SONG_KEYS = frozenset(name_key(name) for name in NON_SONG_TITLES)


def song_names(lead: str) -> List[str]:
    """``{{VOCALOID Songbox}}`` 的 ``|歌曲名称=`` → 名字列表（日文名 + 中文名）。

    ``|歌曲名称 = {{lj|千本桜}}<br>'''千本樱'''`` 两种写法都是条目的名字，
    拆分后各自也要拆掉 ``{{lj|…}}`` / 加粗，所以这里同时给出整段与内层写法。
    """
    box = SONGBOX_RE.search(lead or "")
    if not box:
        return []
    value = SONG_NAME_RE.search(box.group(1))
    if not value:
        return []
    names: List[str] = []
    for piece in BR_RE.split(value.group(1)):
        piece = piece.strip()
        if not piece:
            continue
        names.append(piece)
        names.extend(part.strip() for part in LJ_RE.findall(piece) if part.strip())
    return names


def build_name_index(pages: Dict[str, Dict[str, object]]) -> Dict[str, str]:
    """``{条目名: {redirects, lead}}`` → ``{比对名: 条目标题}``。

    条目标题、所有重定向、Songbox 里的歌名都算条目名。同名条目（「Alice」这类）
    先到先得：清单只关心「这个名字已经有条目了」。

    每个名字先按**精确**键登记，再补一个「去掉结尾标点」的键（``loose_key``）：
    歌名结尾的 `！` / `?` 各站写法不一。精确键全部先登记完再补，所以一个精确标题
    永远不会被别人的宽松键顶掉。
    """
    names: Dict[str, str] = {}
    loose: List[Tuple[str, str]] = []

    def add(name: str, title: str) -> None:
        key = name_key(name)
        if not key:
            return
        names.setdefault(key, title)
        trimmed = loose_key(name)
        if trimmed and trimmed != key:
            loose.append((trimmed, title))

    for title, data in pages.items():
        add(title, title)
        for redirect in data.get("redirects") or []:
            add(str(redirect), title)
        for name in song_names(str(data.get("lead") or "")):
            add(name, title)
    for key, title in loose:
        names.setdefault(key, title)
    return names


def lookup_song(names: Dict[str, str], title: str) -> Optional[str]:
    """页面名 → 对应的条目标题（先精确、再去掉结尾标点）。"""
    return names.get(name_key(title)) or names.get(loose_key(title))


def song_producer(lead: str) -> str:
    """``{{VOCALOID Songbox}}`` 的 ``|P主=`` 原文（没写就是空串）。

    拆掉 ``{{lj|…}}`` / ``[[a|b]]`` / 加粗之后拼回去，用来跟 AtWiki 页面名里
    括号中的作者比：``|P主 = [[DECO*27]]、[[堀江晶太]](kemu)`` → ``DECO*27、堀江晶太(kemu)``。
    """
    box = SONGBOX_RE.search(lead or "")
    if not box:
        return ""
    value = PRODUCER_RE.search(box.group(1))
    if not value:
        return ""
    text = BR_RE.sub(" ", value.group(1))
    text = LJ_RE.sub(lambda match: match.group(1), text)
    text = LINK_RE.sub(lambda match: match.group(2), text)
    text = BOLD_RE.sub("", text)
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", "", text)


def strip_trailing_paren(text: str) -> Optional[Tuple[str, str]]:
    """从右剥掉一层配对的括号 → ``(括号前, 括号里)``；没有配对的括号时返回 None。

    ``セカイ(DECO*27×堀江晶太(kemu))`` 里套着括号，所以要从右往左数配平，
    不能简单地砍到第一个 ``(``。
    """
    text = str(text or "").rstrip()
    if not text or text[-1] not in ")）":
        return None
    depth = 0
    for index in range(len(text) - 1, -1, -1):
        char = text[index]
        if char in (")", "）"):
            depth += 1
        elif char in ("(", "（"):
            depth -= 1
            if depth == 0:
                base = text[:index].strip()
                inner = text[index + 1:-1].strip()
                return (base, inner) if base and inner else None
            if depth < 0:
                return None
    return None


def hint_tokens(hint: str) -> List[str]:
    """作者串 → token：``DECO*27×堀江晶太(kemu)`` → ``DECO*27`` / ``堀江晶太`` / ``kemu``。"""
    tokens: List[str] = []
    for piece in HINT_SPLIT_RE.split(hint or ""):
        piece = piece.strip()
        while piece:
            nested = strip_trailing_paren(piece)
            if nested is None:
                break
            tokens.append(nested[0])
            piece = nested[1].strip()
        if piece:
            tokens.append(piece)
    return [token for token in dict.fromkeys(tokens) if token]


def title_splits(title: str) -> List[Tuple[str, List[str]]]:
    """「曲名/作者」「曲名(作者)」→ ``[(曲名, [作者 token…])]``。

    AtWiki 的页面名常把作者挂在曲名后面，Vocawiki 的条目名却是「中文曲名(作者)」，
    整串比当然对不上，得把作者拆出来单独当佐证。
    """
    text = str(title or "").strip()
    splits: List[Tuple[str, List[str]]] = []
    if "/" in text:
        base, _sep, hint = text.rpartition("/")
        base = base.strip()
        if base:
            splits.append((base, hint_tokens(hint)))
    nested = strip_trailing_paren(text)
    if nested is not None:
        splits.append((nested[0], hint_tokens(nested[1])))
    return splits


def producer_matches(producer: str, hints: Sequence[str]) -> bool:
    """条目的作者原文里有没有某个 hint token（``Crusher-P`` / ``DECO*27`` …）。"""
    text = name_key(producer)
    if not text:
        return False
    for hint in hints:
        key = name_key(hint)
        if len(key) < 2:
            continue
        if key in text or (len(text) >= 2 and text in key):
            return True
    return False


def build_alias_index(
        pages: Dict[str, Dict[str, object]]) -> Dict[str, List[Tuple[str, str]]]:
    """歌名 → ``[(条目标题, 作者原文)]``，只收**有 Songbox 的歌曲条目**。

    一个歌名可能对到好几个条目（``シンデレラ`` 同时是 `灰姑娘(DECO*27)` 与
    `灰姑娘(zig)` 的歌名），所以这里保留全部候选，交给 ``match_song()`` 用作者消歧。
    """
    aliases: Dict[str, List[Tuple[str, str]]] = {}
    for title, data in pages.items():
        lead = str(data.get("lead") or "")
        names = song_names(lead)
        if not names:
            continue
        nested = strip_trailing_paren(title)
        producer = " ".join(part for part in (song_producer(lead),
                                             nested[1] if nested else "") if part)
        for name in [title] + [str(item) for item in data.get("redirects") or []] + names:
            key = name_key(name)
            if not key:
                continue
            entries = aliases.setdefault(key, [])
            if all(entry[0] != title for entry in entries):
                entries.append((title, producer))
    return aliases


def match_song(names: Dict[str, str], aliases: Dict[str, List[Tuple[str, str]]],
               title: str) -> Optional[str]:
    """AtWiki 页面名 → 对应的条目标题（整串 → 拆作者 → 作者佐证）。

    整串名字先按老办法比（标题 / 重定向 / Songbox 歌名 + 结尾标点宽松），对不上再把
    「曲名/作者」「曲名(作者)」拆开：曲名在 Songbox 歌名里出现过，**并且**括号里的作者
    跟条目的 ``P主`` 对上，才算匹配。作者佐证是必须的——``1/4`` 这种名字拆开就变成
    ``1``，没有佐证会误配到别的歌。
    """
    exact = lookup_song(names, title)
    if exact is not None:
        return exact
    for base, hints in title_splits(title):
        candidates = aliases.get(name_key(base)) or aliases.get(loose_key(base)) or []
        if not candidates:
            continue
        if len(candidates) == 1 and not hints:
            return candidates[0][0]
        matched = [entry for entry in candidates
                   if hints and producer_matches(entry[1], hints)]
        if len(matched) == 1:
            return matched[0][0]
        if len(matched) > 1:
            continue                       # 作者也对得上好几个：不猜
        # 作者对不上：只有当这些候选根本拿不到作者信息时才退回「先到先得」
        if all(not entry[1] for entry in candidates):
            return candidates[0][0]
    return None


# ---------------------------------------------------------------- AtWiki

def fetch_text(url: str, attempts: int = ATWIKI_ATTEMPTS,
               timeout: int = ATWIKI_TIMEOUT) -> str:
    """GET 一个页面（带浏览器 UA 与重试）。失败返回空串，由调用方决定怎么办。"""
    for attempt in range(attempts):
        try:
            request = urllib.request.Request(
                url, headers={"User-Agent": ATWIKI_UA, "Accept-Language": "ja,en;q=0.9"})
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001 - 单个页面失败不该中断整轮
            if attempt == attempts - 1:
                pywikibot.warning(f"读取 AtWiki 页面失败：{url}（{exc}）")
                return ""
            time.sleep(2 * (attempt + 1))
    return ""


def parse_page_list(markup: str) -> Tuple[Dict[str, str], int]:
    """一页「全ページ一覧」→ ``({pid: 页面名}, 总页数)``。

    条目在 ``<table class="pagelist">`` 里；侧边栏（首頁 / 目錄 …）也在页面里，
    所以只认这张表。总页数取自翻页条最后一个 ``pp=``。
    """
    pages: Dict[str, str] = {}
    table = LIST_TABLE_RE.search(markup or "")
    if table:
        for pid, name in LIST_ROW_RE.findall(table.group(1)):
            name = clean_title(html.unescape(TAG_RE.sub("", name)))
            if pid and name:
                pages.setdefault(pid, name)
    last = max((int(value) for value in LIST_LAST_PAGE_RE.findall(markup or "")), default=0)
    return pages, last


def atwiki_pages(fetcher=fetch_text) -> Dict[str, str]:
    """抓完整的「全ページ一覧」→ ``{pid: 页面名}``。

    按页面名排序（``sort=pagename``）而不是按更新时间：抓完 86 页要好一会儿，
    按更新时间排的话中途更新的页面会把后面的条目挤到已经抓过的那一页里，
    于是漏页 / 重页。翻到最后一页（总页数取自翻页条）为止。
    """
    pages: Dict[str, str] = {}
    total = 0
    number = 1
    while True:
        url = ATWIKI_LIST + ("" if number == 1 else f"&pp={number}")
        markup = fetcher(url)
        if not markup:
            break
        batch, last = parse_page_list(markup)
        total = total or last
        if not batch:
            break
        unseen = batch_not_seen(batch, pages)
        pages.update(batch)
        if total:
            if number >= min(total, ATWIKI_MAX_PAGES):
                break
        elif number > 1 and not unseen:
            break                       # 翻页条没给总数：翻到没有新条目为止
        number += 1
    return pages


def batch_not_seen(batch: Dict[str, str], pages: Dict[str, str]) -> Dict[str, str]:
    """这一页里**之前没见过**的条目（翻页条没给总数时，用它判断要不要继续翻）。"""
    return {pid: title for pid, title in batch.items() if pid not in pages}


def page_stats(markup: str) -> Optional[Tuple[str, int]]:
    """正文去掉链接 / 标签后剩下的文字 + 正文区里指向本站其他页面的链接数。

    认不出正文时返回 None。
    """
    body = BODY_RE.search(markup or "")
    if not body:
        return None
    region = body.group(1)
    links = len(PAGE_LINK_RE.findall(region))
    text = SCRIPT_RE.sub(" ", region)
    text = LINK_TAG_RE.sub(" ", text)          # 链接整个丢掉：消歧义页的字全在链接里
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", "", html.unescape(text)), links


def page_plaintext(markup: str) -> Optional[str]:
    """AtWiki 页面正文去掉链接 / 标签后剩下的文字；认不出正文时返回 None。"""
    stats = page_stats(markup)
    return None if stats is None else stats[0]


def is_song_page(plain: Optional[str], links: Optional[int] = None) -> bool:
    """正文够不够长、像不像一首歌（而不是消歧义 / 目录 / 站务 / 测试页）。

    给了 ``links``（正文区里的内部链接数）时多看一条：只剩链接、几乎没有文字的
    就是目录页（``pages/2``「メニュー」是 26 个链接、68 字）。
    认不出正文时返回 True：宁可留在清单里，也不要因为一次抓取失败把它删掉。
    """
    if plain is None:
        return True
    if any(marker in plain for marker in DISAMBIG_MARKERS):
        return False
    if links is not None and links >= LINK_ONLY_MIN_LINKS and len(plain) < LINK_ONLY_MAX_TEXT:
        return False
    return len(plain) >= MIN_SONG_TEXT


def is_song_title(title: str) -> bool:
    """页面名本身像不像一首歌（这个 wiki 自己的首页 / 目录页按标题就能认出来）。"""
    return name_key(title) not in NON_SONG_KEYS


def is_song_pid(pid: str) -> bool:
    """pid 不在站务 / 目录 / 日志白名单里。

    按 pid 排是为了稳：这个 wiki 的页面会改名，而 ``pages/1557`` 永远是那份 log；
    反过来也不能按标题里的关键词猜 —— ``合唱コンクール``、``未完成人間`` 都是真歌。
    """
    return str(pid) not in NON_SONG_PIDS


def page_links(markup: str) -> List[str]:
    """正文区里指向本站其他页面的 pid（去重、按出现顺序）。"""
    body = BODY_RE.search(markup or "")
    if not body:
        return []
    return list(dict.fromkeys(pid for pid, _text in PAGE_LINK_RE.findall(body.group(1))))


def linked_exclusions(fetcher=fetch_text) -> List[str]:
    """「歌曲以外的翻譯」这类页面列出的 pid：它们同样不是歌曲。

    只取正文区（侧边栏在正文区之外），再减掉站务白名单与站点导航。抓不到就返回空清单
    —— 宁可多留一行，也不要误删一行。
    """
    found: List[str] = []
    for pid in NON_SONG_LIST_SOURCES:
        markup = fetcher(ATWIKI_PAGE.format(pid=pid))
        if not markup:
            pywikibot.warning(f"读不到非歌曲清单页 pages/{pid}，本轮不排除它列出的页面")
            continue
        for other in page_links(markup):
            if other in NON_SONG_PIDS or other in SITE_NAV_PIDS:
                continue
            if other not in found:
                found.append(other)
    return found


def probe_page(pid: str, fetcher=fetch_text) -> Optional[bool]:
    """抓一个 AtWiki 页面，判断它是不是歌曲页；抓不到时返回 None（不下结论）。"""
    markup = fetcher(ATWIKI_PAGE.format(pid=pid))
    if not markup:
        return None
    stats = page_stats(markup)
    if stats is None:
        return None
    return is_song_page(*stats)


def probe_pages(pids: Iterable[str], fetcher=fetch_text,
                workers: int = PROBE_WORKERS) -> Dict[str, bool]:
    """并发抓一批页面，返回 ``{pid: 是不是歌曲页}``（抓不到的页面不在结果里）。"""
    wanted = list(dict.fromkeys(pids))
    verdicts: Dict[str, bool] = {}
    if not wanted:
        return verdicts
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        for pid, verdict in zip(wanted, pool.map(lambda p: probe_page(p, fetcher), wanted)):
            if verdict is not None:
                verdicts[pid] = verdict
    return verdicts


def probe_in_chunks(pids: Sequence[str], fetcher=fetch_text, workers: int = PROBE_WORKERS,
                    chunk_size: int = PROBE_CHUNK,
                    on_chunk=None) -> Dict[str, bool]:
    """分块并发抓页面；每抓完一块就回调一次，好把结果落盘。

    第一次跑要抓几千个页面，中途断网 / 超时不该让前面抓到的白费，所以按块存。
    """
    verdicts: Dict[str, bool] = {}
    for start in range(0, len(pids), max(1, chunk_size)):
        chunk = pids[start:start + chunk_size]
        verdicts.update(probe_pages(chunk, fetcher=fetcher, workers=workers))
        if on_chunk is not None:
            on_chunk(verdicts)
    return verdicts


# ---------------------------------------------------------------- Vocawiki

def song_pages(site, batch_size: int = 50) -> Dict[str, Dict[str, object]]:
    """Vocawiki 上所有条目的 ``{标题: {redirects, lead}}``。

    用 ``generator=allpages`` 一页页走：``rvsection=0`` 只要首段（Songbox 就在首段，
    整篇歌词不必下载），``redirects`` 顺带把重定向一起取回来。重定向本身也会出现在
    ``allpages`` 里，但它们会解析成目标页面，于是同一目标被取到两次——合并即可。
    """
    pages: Dict[str, Dict[str, object]] = {}
    params = {
        "action": "query", "format": "json", "formatversion": "2",
        "generator": "allpages", "gapnamespace": "0", "gaplimit": str(batch_size),
        "prop": "revisions|redirects", "rvprop": "content", "rvslots": "main",
        "rvsection": "0", "rdlimit": "max",
    }
    while True:
        data = site.simple_request(**params).submit()
        for page in data.get("query", {}).get("pages") or []:
            title = str(page.get("title") or "")
            if not title:
                continue
            entry = pages.setdefault(title, {"redirects": [], "lead": ""})
            for redirect in page.get("redirects") or []:
                name = str(redirect.get("title") or "")
                if name and name not in entry["redirects"]:
                    entry["redirects"].append(name)
            revisions = page.get("revisions") or []
            if revisions:
                lead = (revisions[0].get("slots", {}).get("main", {}) or {}).get("content", "")
                if lead and not entry["lead"]:
                    entry["lead"] = str(lead)
        cont = data.get("continue")
        if not cont:
            break
        params.update(cont)
    return pages


# ---------------------------------------------------------------- 缓存

def load_cache(path: Path) -> Dict:
    try:
        with path.open("rb") as handle:
            data = pickle.load(handle)
    except (OSError, pickle.PickleError, EOFError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def save_cache(path: Path, cache: Dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        pickle.dump(cache, handle)


def is_fresh(stamp: object, max_age: float) -> bool:
    try:
        age = time.time() - float(stamp)
    except (TypeError, ValueError):
        return False
    return 0 <= age < max_age


# ---------------------------------------------------------------- 页面

def link_text(title: str) -> str:
    """外链语法里的显示文字：``]`` 会把链接提前截断，写成 ``&#93;``。"""
    text = clean_title(html.unescape(str(title or "")).replace("\n", " "))
    return text.replace("]", "&#93;")


def render_page(listed: Sequence[Tuple[str, str]], source_total: int, matched: int,
                excluded: int, today: Optional[str] = None) -> str:
    """整页 wikitext：一行说明注释 + 一句统计 + 清单。"""
    today = today or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    header = (f"<!-- 比對日期：{today}；來源共 {source_total} 個不同頁面；"
              f"已匹配 {matched} 個 Vocawiki 歌曲條目；"
              f"排除 {excluded} 個消歧義／站務／目錄／非歌曲翻譯頁。 -->")
    intro = ("本列表列出來源頁面標題尚未對應到 Vocawiki 歌曲條目的項目"
             "（依標題、重定向及 Songbox 的歌名比對；已排除消歧義頁、明確的"
             "站務、目錄、討論及測試頁，以及「歌曲以外的翻譯」列出的頁面）。"
             f"共 '''{len(listed)}''' 頁。")
    lines = [header, intro, ""]
    for pid, title in listed:
        lines.append(f"* [{ATWIKI_PAGE.format(pid=pid)} {link_text(title)}]")
    return "\n".join(lines).rstrip("\n") + "\n"


def sort_listed(pairs: Iterable[Tuple[str, str]]) -> List[Tuple[str, str]]:
    """按页面名排序（与页面上的旧清单同一口径：大小写不敏感、码位顺序）。"""
    return sorted(pairs, key=lambda pair: pair[1].lower())


def save_page(page: Page, text: str, summary: Optional[str]) -> bool:
    """保存；被别人抢先编辑时放弃本轮（下一轮定时任务会接着比）。"""
    page.text = text
    summary = summary or DEFAULT_SUMMARY
    try:
        page.save(summary=summary, minor=True, bot=True, tags="Bot")
        return True
    except EditConflictError as exc:
        pywikibot.error(f"页面刚被其他进程编辑，放弃本轮：{exc}")
        return False
    except TypeError:  # 旧版 pywikibot 把 bot 叫 botflag
        page.save(summary=summary, minor=True, botflag=True)
        return True
    except pywikibot.exceptions.APIError as exc:
        pywikibot.warning(f"带 bot/tags 保存失败，改用普通保存：{exc}")
        page.save(summary=summary, minor=True)
        return True


# ---------------------------------------------------------------- 主流程

def collect_pages(max_age: float = DEFAULT_MAX_AGE, refresh: bool = False,
                  fetcher=fetch_text, cache: Optional[Dict] = None) -> Tuple[Dict[str, str], Dict]:
    """AtWiki 的页面清单（带缓存）→ ``({pid: 页面名}, 缓存)``。

    缓存里同时放 ``linked``：「歌曲以外的翻譯」列出的 pid（同样不是歌曲）。
    它跟页面清单一起重建——那份清单几个月才变一次，重建时才会重新抓。
    """
    cache = load_cache(PAGES_CACHE) if cache is None else cache
    if (not refresh and cache.get("pages") and cache.get("version") == PAGES_VERSION
            and is_fresh(cache.get("built"), max_age)):
        return dict(cache["pages"]), cache
    pages = atwiki_pages(fetcher)
    if not pages:                      # 一页也没抓到：别拿空清单把页面刷空
        raise RuntimeError("抓不到 AtWiki 的页面清单（全ページ一覧），本轮放弃")
    linked = linked_exclusions(fetcher)
    cache = {"built": time.time(), "pages": pages, "linked": linked,
             "version": PAGES_VERSION}
    save_cache(PAGES_CACHE, cache)
    pywikibot.output(f"AtWiki 页面清单：{len(pages)} 页；"
                     f"「歌曲以外的翻譯」列出 {len(linked)} 页")
    return pages, cache


def changed_titles(site, since: float, limit: int = INDEX_PATCH_LIMIT) -> Optional[List[str]]:
    """``since`` 之后新建 / 移动过的条目名；出问题或条数超过 ``limit`` 时返回 None。

    条数超限说明缓存已经太旧，补不如重建 —— 交给调用方走整体重建。
    """
    start = datetime.fromtimestamp(since, timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    params = {"action": "query", "format": "json", "formatversion": "2",
              "list": "recentchanges", "rctype": "new|log", "rcdir": "newer",
              "rcstart": start, "rcnamespace": "0", "rclimit": "max"}
    titles: List[str] = []
    try:
        while True:
            data = site.simple_request(**params).submit()
            for change in data.get("query", {}).get("recentchanges") or []:
                title = clean_title(change.get("title") or "")
                if title and title not in titles:
                    titles.append(title)
                if len(titles) > limit:
                    return None
            cont = data.get("continue")
            if not cont:
                return titles
            params.update(cont)
    except Exception as exc:  # noqa: BLE001 - 补丁失败只是退回重建，不该中断一轮
        pywikibot.warning(f"读不到 recentchanges，歌名索引整体重建：{exc}")
        return None


def patch_names(site, cache: Dict) -> Optional[Dict]:
    """给复用的歌名索引补上「建索引之后新建 / 移动过的条目」。

    索引缓存可能已经放了几个小时（`--max-age` 只管 AtWiki 清单），这期间新建的条目
    如果看不见，就会把已经有条目的页面重新列进清单 —— 277313 那次就是这么来的。
    """
    built = cache.get("built")
    names = dict(cache.get("names") or {})
    aliases = dict(cache.get("aliases") or {})
    if not names or not isinstance(built, (int, float)):
        return None
    titles = changed_titles(site, float(built))
    if titles is None:
        return None
    fresh = {title: {"redirects": [], "lead": ""} for title in titles}
    if titles:
        for start in range(0, len(titles), 50):
            batch = titles[start:start + 50]
            params = {"action": "query", "format": "json", "formatversion": "2",
                      "titles": "|".join(batch), "prop": "revisions|redirects",
                      "rvprop": "content", "rvslots": "main", "rvsection": "0",
                      "rdlimit": "max"}
            data = site.simple_request(**params).submit()
            for page in data.get("query", {}).get("pages") or []:
                title = str(page.get("title") or "")
                if not title or page.get("missing"):
                    continue
                entry = fresh.setdefault(title, {"redirects": [], "lead": ""})
                for redirect in page.get("redirects") or []:
                    name = str(redirect.get("title") or "")
                    if name and name not in entry["redirects"]:
                        entry["redirects"].append(name)
                revisions = page.get("revisions") or []
                if revisions and not entry["lead"]:
                    entry["lead"] = str(
                        (revisions[0].get("slots", {}).get("main", {}) or {}).get("content", ""))
    # 精确键优先：补进来的名字不覆盖已有判定，只填空位
    for key, title in build_name_index(fresh).items():
        names.setdefault(key, title)
    for key, entries in build_alias_index(fresh).items():
        merged = aliases.setdefault(key, [])
        for title, producer in entries:
            if all(entry[0] != title for entry in merged):
                merged.append((title, producer))
    patched = {"built": time.time(), "names": names, "aliases": aliases,
               "pages": cache.get("pages", 0), "version": INDEX_VERSION}
    save_cache(INDEX_CACHE, patched)
    pywikibot.output(f"歌名索引增量补齐：{len(titles)} 个新条目，"
                     f"歌名 {len(names)} 个")
    return patched


def collect_names(site, max_age: float = DEFAULT_MAX_AGE, refresh: bool = False,
                  cache: Optional[Dict] = None,
                  index_max_age: float = INDEX_MAX_AGE) -> Tuple[Dict[str, str], Dict]:
    """Vocawiki 的歌名索引（带缓存）→ ``({比对名: 条目标题}, 缓存)``。

    有效期按 ``index_max_age``（默认 1 小时）算，跟 AtWiki 清单的 12 小时分开；
    太旧但还能用的时候先用 ``recentchanges`` 打补丁，补不动再整体重建。
    """
    cache = load_cache(INDEX_CACHE) if cache is None else cache
    usable = (not refresh and cache.get("names") and cache.get("version") == INDEX_VERSION)
    if usable and is_fresh(cache.get("built"), index_max_age):
        return dict(cache["names"]), cache
    if usable:
        patched = patch_names(site, cache)
        if patched is not None:
            return dict(patched["names"]), patched
    pages = song_pages(site)
    if not pages:
        raise RuntimeError("读不到 Vocawiki 的条目（list=allpages 返回空），本轮放弃")
    names = build_name_index(pages)
    cache = {"built": time.time(), "names": names, "aliases": build_alias_index(pages),
             "pages": len(pages), "version": INDEX_VERSION}
    save_cache(INDEX_CACHE, cache)
    pywikibot.output(f"Vocawiki 条目：{len(pages)} 个，歌名 {len(names)} 个")
    return names, cache


def classify(pages: Dict[str, str], names: Dict[str, str], verdicts: Dict[str, Dict],
             recheck: float = DEFAULT_RECHECK, probe_budget: int = 0,
             fetcher=fetch_text, on_progress=None,
             aliases: Optional[Dict[str, List[Tuple[str, str]]]] = None,
             excluded_pids: Iterable[str] = ()
             ) -> Tuple[List[Tuple[str, str]], int, int, Dict[str, Dict]]:
    """把 AtWiki 页面分成「已匹配 / 不是歌曲 / 要补的」三类。

    返回 ``(清单, 已匹配数, 排除数, 判定缓存)``。判定缓存里只放抓到结果的页面；
    抓不到的下一轮再试，本轮先按「是歌曲」保守处理。``on_progress`` 在每抓完一批
    页面后被调用（用来把判定落盘）。``excluded_pids`` 是「歌曲以外的翻譯」列出的页面。
    """
    skipped = {str(pid) for pid in excluded_pids}
    candidate = {pid: title for pid, title in pages.items()
                 if is_song_pid(pid) and pid not in skipped and is_song_title(title)}
    unmatched = [(pid, title) for pid, title in candidate.items()
                 if match_song(names, aliases or {}, title) is None]
    now = time.time()
    pending: List[str] = []
    for pid, _title in unmatched:
        verdict = verdicts.get(pid)
        if verdict is None or not is_fresh(verdict.get("at"), recheck):
            pending.append(pid)
    if probe_budget:
        pending = pending[:probe_budget]
    fresh = probe_in_chunks(pending, fetcher=fetcher,
                            on_chunk=lambda found: _record(verdicts, found, now, on_progress))
    for pid in pending:
        if pid in fresh:
            continue
        # 抓不到正文：这一轮不下结论，保留上一次的判定（没有就当它是歌），
        # 时间戳留 0 让下一轮再试 —— 写 now 会把「没抓到」冻住整整一个 recheck 周期
        verdicts.setdefault(pid, {"song": True, "at": 0})
    if on_progress is not None:
        on_progress(verdicts)
    listed = [(pid, title) for pid, title in unmatched
              if verdicts.get(pid, {}).get("song", True)]
    excluded = (len(unmatched) - len(listed)) + (len(pages) - len(candidate))
    matched = len(candidate) - len(unmatched)
    return sort_listed(listed), matched, excluded, verdicts


def _record(verdicts: Dict[str, Dict], found: Dict[str, bool], now: float,
            on_progress) -> None:
    """把这一批判定写进缓存，并回调（落盘）。"""
    for pid, is_song in found.items():
        verdicts[pid] = {"song": bool(is_song), "at": now}
    if on_progress is not None:
        on_progress(verdicts)


def reported_matched(text: str) -> Optional[int]:
    """页面上写着的「已匹配 N 个」。"""
    match = MATCHED_RE.search(text or "")
    return int(match.group(1)) if match else None


def run_once(site, write: bool = False, summary: Optional[str] = None,
             max_age: float = DEFAULT_MAX_AGE, recheck: float = DEFAULT_RECHECK,
             refresh: bool = False, probe_budget: int = 0,
             fetcher=fetch_text, index_max_age: float = INDEX_MAX_AGE,
             allow_shrink: bool = False) -> bool:
    """比一轮、按需要更新页面。返回页面是否需要（或已经）改动。"""
    if write:
        if not site.logged_in():
            site.login()
        if not site.logged_in():
            raise RuntimeError("登录失败：请检查 user-config.py 与 user-password.py")
    pages, page_cache = collect_pages(max_age, refresh, fetcher)
    names, index_cache = collect_names(site, max_age, refresh, index_max_age=index_max_age)
    aliases = index_cache.get("aliases") or {}
    verdicts = load_cache(VERDICT_CACHE)
    verdicts = {pid: value for pid, value in verdicts.items() if pid in pages}
    listed, matched, excluded, verdicts = classify(
        pages, names, verdicts, recheck, probe_budget, fetcher,
        on_progress=lambda found: save_cache(VERDICT_CACHE, found),
        aliases=aliases, excluded_pids=page_cache.get("linked") or ())
    save_cache(VERDICT_CACHE, verdicts)

    text = render_page(listed, len(pages), matched, excluded)
    pywikibot.output(
        f"来源 {len(pages)} 页：已匹配 {matched}，非歌曲页 {excluded}，"
        f"待补 {len(listed)} 页")
    pywikibot.output(f"自洽核对：已匹配 {matched} + 排除 {excluded} + 待补 {len(listed)}"
                     f" = {matched + excluded + len(listed)}（来源 {len(pages)}）")

    page = Page(site, PAGE_TITLE)
    original = page.text or ""
    previous = reported_matched(original)
    if previous is not None and matched < previous and not allow_shrink:
        pywikibot.error(f"本轮只匹配到 {matched} 个（页面上是 {previous} 个）："
                        "歌名索引可能不全，放弃本轮（--allow-shrink 可强行保存）")
        return False
    # MediaWiki 存盘时会把结尾的空行去掉，所以只比到最后一个非空行
    if text.rstrip() == original.rstrip():
        pywikibot.output("页面无需更新。")
        return False
    if not write:
        pywikibot.output(f"[dry-run] 页面将从 {len(original.splitlines())} 行变为 "
                         f"{len(text.splitlines())} 行；加 --write 以保存。")
        return True
    if save_page(page, text, summary):
        pywikibot.output("已更新页面。")
        return True
    return False


def main() -> None:
    parser = argparse.ArgumentParser(
        description="比对 AtWiki 歌词页与 Vocawiki 条目，维护「补完计划」清单")
    parser.add_argument("--write", action="store_true", help="保存页面（默认只干跑）")
    parser.add_argument("--summary", default=None, help="编辑摘要")
    parser.add_argument("--max-age", type=float, default=DEFAULT_MAX_AGE,
                        help="AtWiki 来源清单的缓存有效期（秒，默认 12 小时）")
    parser.add_argument("--index-max-age", type=float, default=INDEX_MAX_AGE,
                        dest="index_max_age",
                        help="歌名索引的缓存有效期（秒，默认 1 小时；超时先增量补齐）")
    parser.add_argument("--recheck", type=float, default=DEFAULT_RECHECK,
                        help="页面判定多久重新核一次（秒，默认 30 天）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存，重新抓来源清单与歌名索引")
    parser.add_argument("--probe-budget", type=int, default=0, dest="probe_budget",
                        help="本轮最多抓多少个 AtWiki 页面（0 = 不限制）")
    parser.add_argument("--allow-shrink", action="store_true", dest="allow_shrink",
                        help="即使「已匹配」比页面上少也照样保存（默认不保存）")
    args = parser.parse_args()

    site = pywikibot.Site()
    run_once(site, args.write, args.summary, args.max_age, args.recheck,
             args.refresh, args.probe_budget, index_max_age=args.index_max_age,
             allow_shrink=args.allow_shrink)


if __name__ == "__main__":
    main()
