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

判定结果与两个来源清单都缓存在 ``data/`` 下，所以第一次跑要抓上千个 AtWiki 页面
（几分钟），之后每轮只补新出现的页面；判定过期（默认 30 天）的页面会重新抓一次。

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
INDEX_VERSION = 2
# 页面清单的格式版本（标题做过 NFC 规范化）
PAGES_VERSION = 2

DEFAULT_MAX_AGE = 12 * 3600        # 来源清单 / 歌名索引多久重建一次（秒）
DEFAULT_RECHECK = 30 * 24 * 3600   # 判定多久重新核一次（秒）
DEFAULT_SUMMARY = "更新 VOCALOID中文歌词wiki 补完计划（机器人自动比对）"

# 正文去掉链接后少于这么多字 → 不是歌曲页（消歧义、目录、站务、测试页）
MIN_SONG_TEXT = 60
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


def page_plaintext(markup: str) -> Optional[str]:
    """AtWiki 页面正文去掉链接 / 标签后剩下的文字；认不出正文时返回 None。"""
    body = BODY_RE.search(markup or "")
    if not body:
        return None
    text = SCRIPT_RE.sub(" ", body.group(1))
    text = LINK_TAG_RE.sub(" ", text)          # 链接整个丢掉：消歧义页的字全在链接里
    text = TAG_RE.sub(" ", text)
    return re.sub(r"\s+", "", html.unescape(text))


def is_song_page(plain: Optional[str]) -> bool:
    """正文够不够长、像不像一首歌（而不是消歧义 / 目录 / 站务 / 测试页）。

    认不出正文时返回 True：宁可留在清单里，也不要因为一次抓取失败把它删掉。
    """
    if plain is None:
        return True
    if any(marker in plain for marker in DISAMBIG_MARKERS):
        return False
    return len(plain) >= MIN_SONG_TEXT


def is_song_title(title: str) -> bool:
    """页面名本身像不像一首歌（这个 wiki 自己的首页 / 目录页按标题就能认出来）。"""
    return name_key(title) not in NON_SONG_KEYS


def probe_page(pid: str, fetcher=fetch_text) -> Optional[bool]:
    """抓一个 AtWiki 页面，判断它是不是歌曲页；抓不到时返回 None（不下结论）。"""
    markup = fetcher(ATWIKI_PAGE.format(pid=pid))
    if not markup:
        return None
    plain = page_plaintext(markup)
    if plain is None:
        return None
    return is_song_page(plain)


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
              f"排除 {excluded} 個消歧義／站務／目錄／測試頁。 -->")
    intro = ("本列表列出來源頁面標題尚未對應到 Vocawiki 歌曲條目的項目"
             "（依標題、重定向及 Songbox 的歌名比對；已排除消歧義頁與明確的"
             f"站務、目錄、討論及測試頁）。共 '''{len(listed)}''' 頁。")
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
    """AtWiki 的页面清单（带缓存）→ ``({pid: 页面名}, 缓存)``。"""
    cache = load_cache(PAGES_CACHE) if cache is None else cache
    if (not refresh and cache.get("pages") and cache.get("version") == PAGES_VERSION
            and is_fresh(cache.get("built"), max_age)):
        return dict(cache["pages"]), cache
    pages = atwiki_pages(fetcher)
    if not pages:                      # 一页也没抓到：别拿空清单把页面刷空
        raise RuntimeError("抓不到 AtWiki 的页面清单（全ページ一覧），本轮放弃")
    cache = {"built": time.time(), "pages": pages, "version": PAGES_VERSION}
    save_cache(PAGES_CACHE, cache)
    pywikibot.output(f"AtWiki 页面清单：{len(pages)} 页")
    return pages, cache


def collect_names(site, max_age: float = DEFAULT_MAX_AGE, refresh: bool = False,
                  cache: Optional[Dict] = None) -> Tuple[Dict[str, str], Dict]:
    """Vocawiki 的歌名索引（带缓存）→ ``({比对名: 条目标题}, 缓存)``。"""
    cache = load_cache(INDEX_CACHE) if cache is None else cache
    if (not refresh and cache.get("names") and cache.get("version") == INDEX_VERSION
            and is_fresh(cache.get("built"), max_age)):
        return dict(cache["names"]), cache
    pages = song_pages(site)
    if not pages:
        raise RuntimeError("读不到 Vocawiki 的条目（list=allpages 返回空），本轮放弃")
    names = build_name_index(pages)
    cache = {"built": time.time(), "names": names, "pages": len(pages),
             "version": INDEX_VERSION}
    save_cache(INDEX_CACHE, cache)
    pywikibot.output(f"Vocawiki 条目：{len(pages)} 个，歌名 {len(names)} 个")
    return names, cache


def classify(pages: Dict[str, str], names: Dict[str, str], verdicts: Dict[str, Dict],
             recheck: float = DEFAULT_RECHECK, probe_budget: int = 0,
             fetcher=fetch_text, on_progress=None
             ) -> Tuple[List[Tuple[str, str]], int, int, Dict[str, Dict]]:
    """把 AtWiki 页面分成「已匹配 / 不是歌曲 / 要补的」三类。

    返回 ``(清单, 已匹配数, 排除数, 判定缓存)``。判定缓存里只放抓到结果的页面；
    抓不到的下一轮再试，本轮先按「是歌曲」保守处理。``on_progress`` 在每抓完一批
    页面后被调用（用来把判定落盘）。
    """
    candidate = {pid: title for pid, title in pages.items() if is_song_title(title)}
    unmatched = [(pid, title) for pid, title in candidate.items()
                 if lookup_song(names, title) is None]
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


def run_once(site, write: bool = False, summary: Optional[str] = None,
             max_age: float = DEFAULT_MAX_AGE, recheck: float = DEFAULT_RECHECK,
             refresh: bool = False, probe_budget: int = 0,
             fetcher=fetch_text) -> bool:
    """比一轮、按需要更新页面。返回页面是否需要（或已经）改动。"""
    if write:
        if not site.logged_in():
            site.login()
        if not site.logged_in():
            raise RuntimeError("登录失败：请检查 user-config.py 与 user-password.py")
    pages, _ = collect_pages(max_age, refresh, fetcher)
    names, _ = collect_names(site, max_age, refresh)
    verdicts = load_cache(VERDICT_CACHE)
    verdicts = {pid: value for pid, value in verdicts.items() if pid in pages}
    listed, matched, excluded, verdicts = classify(
        pages, names, verdicts, recheck, probe_budget, fetcher,
        on_progress=lambda found: save_cache(VERDICT_CACHE, found))
    save_cache(VERDICT_CACHE, verdicts)

    text = render_page(listed, len(pages), matched, excluded)
    pywikibot.output(
        f"来源 {len(pages)} 页：已匹配 {matched}，非歌曲页 {excluded}，"
        f"待补 {len(listed)} 页")

    page = Page(site, PAGE_TITLE)
    original = page.text or ""
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
                        help="来源清单 / 歌名索引的缓存有效期（秒，默认 12 小时）")
    parser.add_argument("--recheck", type=float, default=DEFAULT_RECHECK,
                        help="页面判定多久重新核一次（秒，默认 30 天）")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存，重新抓来源清单与歌名索引")
    parser.add_argument("--probe-budget", type=int, default=0, dest="probe_budget",
                        help="本轮最多抓多少个 AtWiki 页面（0 = 不限制）")
    args = parser.parse_args()

    site = pywikibot.Site()
    run_once(site, args.write, args.summary, args.max_age, args.recheck,
             args.refresh, args.probe_budget)


if __name__ == "__main__":
    main()
