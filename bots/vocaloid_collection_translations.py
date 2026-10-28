# -*- coding: utf-8 -*-
"""维护 [[User:周某不是轴某/VOCALOID collection搜集库]] 的「翻译来源」一栏。

页面是《The VOCALOID Collection》各季榜单的表：每行一首「还没有条目」的歌，
列是 名次 / 曲名 / P主 / 条目状态 / 翻译来源 / 备注。机器人只填**空着的**
「翻译来源」，从不覆盖别人写的内容。

一首歌去哪里找译文（按可靠程度排序，最多记三条）：

* **VOCALOID中文歌词wiki（AtWiki）** —— **目前停用**（``USE_ATWIKI = False``）。
  页面主人 2026-10-22 看到 4 笔同名不同曲的补录后说「暂时不收录中文歌词wiki」，
  所以不拿它填「翻译来源」、也不拿它补录新行；**但配错的旧行照样按投稿年核对删掉**
  （删错不是收录，见下）。改 ``USE_ATWIKI = True`` 即可全部恢复。原来的规则：
  拿页面名去比「全ページ一覧」的 8553 个页面名
  （名字完全一致才算），**并且页面正文的作詞 / 作曲里要有这首歌的 P主**——同名的
  不同曲太多（`Linaria` 那一页是 Mysteka 的、`EDEN` 是 真尋P 的）。再读页面里的
  ``翻譯：某人`` 作署名。这是最可靠的来源。
* **网易云音乐**：`/api/search/get` 搜日文名 / 中文名，标题对上**且** P主 出现在
  歌手或专辑名里才用（只有标题对上不够：同名不同曲太多）；`/api/song/lyric` 里有
  ``tlyric``、而且**译文和原文对得上**（同一句落在同一个时间点，
  `translation_matches_original`）才记。网易云给没有译者投稿的歌也会配一条
  ``tlyric``，但那和原文各唱各的 —— 用户 2026-10-28 指出的 ``Self Decision``
  （id 1945588853）46 行没有一行对得上，站点上就是「没有翻译」；有译文的
  ``walker`` / ``liar`` 虽然没人署名，52 行却一一合上。署名只用来写
  ``(by. 译者)``，不参与判断。
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

**删掉「已经有条目」的行**（默认开启，``--no-prune`` 关掉）：页面主人就是这么做
的——某首歌的条目建好之后，把搜集库里对应那一行删掉（274610 删了 `Maison` /
`Tokyo Nighthawk` / `Equivalent`）。机器人每轮先做这一步，再填「翻译来源」，
省得给马上要删的行白查一遍。证据两条，都是站内事实：

* [[Vocawiki:贡献列表/The VOCALOID Collection]] 里那一格标成「已创建」
  （``{{colorlink|#色|曲名|名次}}`` 而不是 ``[[曲名|名次]]``）；
* 条目真的存在（跟重定向、排除消歧义页），**并且条目的 ``|P主 =`` 和这一行一致**。

标题按 ``strict_key()`` 比 —— 它和 ``title_key()`` 一样归一化，但**保留**
``(消歧义后缀)``：``[[EDEN(酔シグレ)|EDEN]]`` 不能因为剥掉括号就对上了
みつばちぼっち 的 ``EDEN``，``[[言灵(PiroP)|言灵]]`` 也不能对上 kamome sano 的
``言灵``（2026-10-25 实测这两条都会误删）。条目里没写 P主 时一律不认——
删错比漏删糟得多。

一行两侧都有歌、只有一侧有条目时，只清那一侧；两侧都有条目才整行删（连它前面的
``|-`` 一起）。

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

补录前一定过四道关（`atwiki_song` + `navbox_titles`）：这首歌要在**本赛季**的大家族
模板里；曲名要是日文原名（含假名）或带括号注记；带括号时 AtWiki 的 ``作曲`` 必须是
括号里那位；**AtWiki 页面里那支 niconico 视频的投稿年必须等于赛季年份**（`atwiki_year_ok`）。
2026-10-22 只按页面名匹配过，补的 10 行里 6 行是「同名不同曲」
（`Libra(mira)` 对上了 Eon 的 Libra 等），随后 4 行里的 2 行也只能靠同名，
两笔都已整笔撤回——宁可漏，不能错。

**投稿年是最后一道关**（启用 AtWiki 时）：日文曲名不加核对，等于把「同名」当「同一首」。2026-10-22
补进 2022秋的 `死亡フラグ` 就是这样错的——AtWiki 的 p/3460 是 コーチP 2011-05-14
投稿（sm14446365）的老曲，和 2022 年的榜单（`PANDORA`、`リフレイン`、`Femme Fatale`
同样中招）毫无关系。所以补录前读页面里的 niconico 链接，用 ``getthumbinfo`` 取
``first_retrieve``，年份对不上就不补；查不到投稿日也不补（宁缺毋滥）。
标题里带 ``Remix`` / ``Cover`` / ``再解釈`` 的不做这一项——那类条目的译文本来就
挂在原曲页面上。

同一项核对也用来**收拾已经配错的行**（`drop_wrong_rows`；这一项不随 ``USE_ATWIKI``
停用，因为它只删不加）：页面上某行引的 AtWiki 页面投稿年是别的年份、而这一行的 P主
又恰好是那一页的作曲时，整行都是那次错配的产物，删掉；P主 对不上的只清「翻译来源」
一格。别人手写的行（P主 不是那一页的作曲）不会被删，查不到投稿日的行也不动。

**维护自己的写法**：机器人只改两种格子——空的，和自己写过的（内容与缓存里记过的
``sources`` / ``written`` 逐字相同）。这些格子会随新结论更新 / 清空；别人写过的
格子一个字都不碰，**哪怕格式和机器人一模一样**（页面主人也按
``[链接 说明(by. 译者)]`` 写）。判定规则变化时把 ``CACHE_VERSION`` 加一。

缓存丢了（换了运行环境）就认不出自己写过的格子，那些格子会被当成「别人的」不动
——这是有意的：宁可少更新，也不能覆盖别人的来源。``--refresh`` 只跳过「缓存还有效
就不再查」，不会丢缓存。

结果（含「查过、没有」）缓存在 ``data/vocaloid_collection_translations.pickle``：
查到来源的 14 天后重新核对，**没查到的 3 天后再试**（``--miss-ttl``）——「查不到」占
绝大多数，一律按 14 天算的话页面会连着几周都不动。AtWiki 页面清单缓存 7 天。

Everything is a dry run unless ``--write`` is given.
"""

from __future__ import annotations

import argparse
import bisect
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
from collections import Counter
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

CACHE_TTL = 7 * 24 * 3600           # 查到来源的歌：每周复检一次（再看看有没有新翻译）
MISS_TTL = 7 * 24 * 3600            # 没查到来源的歌：也是每周再搜一遍
ATWIKI_TTL = 7 * 24 * 3600          # AtWiki 页面清单多久重建一次
CACHE_VERSION = 7                   # 判定规则变了就 +1，旧缓存自动作废
REQUEST_TIMEOUT = 25
FAILURE_LIMIT = 5                   # 同一个站连错几次就整轮不再查
MAX_SOURCES = 3
ARTICLE_BATCH = 50                  # 查条目是否存在时一次问几个标题
DISAMBIG_CATEGORIES = ("消歧义页", "消歧義頁", "Disambiguation pages")
ARTICLE_PRODUCER_RE = re.compile(r"\|\s*(?:P主|職人|职人|作者)\s*=\s*([^\n]*)")

# 2026-10-22 页面主人：「这四个都不对，暂时不收录中文歌词wiki」。
# 歌词wiki 的页面名太容易和同名的老曲撞上（`Linaria`→Mysteka、`死亡フラグ`→コーチP
# 2011 年的投稿……），所以暂时既不用它填「翻译来源」，也不拿它补录新行。
# 配错的旧行仍按投稿年核对删掉（`drop_wrong_rows`：只删不加，不算「收录」）。
# 要恢复收录的话把这里改成 True。
USE_ATWIKI = False

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
ATWIKI_LINK_RE = re.compile(r"atwiki\.jp/vocaloidchly/pages/(\d+)\.html")

# niconico 的缩略图 API 还在，能给出投稿日（``first_retrieve``）——判断「这一页是不是
# 那一季那首歌」就看它：VCCL 只收新曲，投稿年和赛季年份必须一致。
NICO_INFO = "https://ext.nicovideo.jp/api/getthumbinfo/{vid}"
NICO_ID_RE = re.compile(r"nicovideo\.jp/watch/(sm\d+)")
NICO_UPLOAD_RE = re.compile(r"<first_retrieve>(\d{4})-\d{2}-\d{2}")

NETEASE_SEARCH = "https://music.163.com/api/search/get?s={kw}&type=1&limit=10"
NETEASE_LYRIC = "https://music.163.com/api/song/lyric?os=pc&id={id}&lv=-1&kv=-1&tv=-1"
NETEASE_SONG = "https://music.163.com/#/song?id={id}"

# 译文是不是「和原文对得上」（同一句、同一个时间点）：网易云对没有译者投稿的歌也会配一条
# `tlyric`，但它的时间轴和原文各唱各的（`Self Decision`，id 1945588853：46 行译文没有
# 一行落得回去，开头就差了 5 秒）。有人投稿的 `walker` / `liar` 则 52 行全部合得上。
LYRIC_STAMP_RE = re.compile(r"^\[(\d+):(\d+)(?:[.:](\d+))?\]\s*(.*)$")
LYRIC_META_RE = re.compile(r"^\[(?:by|ti|ar|al|offset|length|re|ve|total)\s*[:：]", re.I)
LYRIC_CREDIT_RE = re.compile(r"作\s*[词詞曲]|編\s*曲|编\s*曲|調\s*教|调\s*教|混\s*音|"
                             r"曲\s*[绘繪]|母\s*带|演\s*唱|歌\s*[:：]")
TRANSLATION_MATCH_RATIO = 0.5          # 译文行里至少一半要落在原文的时间点上
TRANSLATION_MIN_LINES = 3              # 行数太少（纯音乐 / 只有署名行）判断不了
TRANSLATION_MATCH_TOLERANCE = 200      # 同一时间点的允许误差（毫秒）

BILIBILI_SEARCH = ("https://api.bilibili.com/x/web-interface/search/type"
                   "?search_type=video&keyword={kw}&page=1")
BILIBILI_VIEW = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
BILIBILI_REPLY = "https://api.bilibili.com/x/v2/reply?type=1&oid={oid}&ps=20&pn={pn}&sort=2"
BILIBILI_DANMAKU = "https://api.bilibili.com/x/v1/dm/list.so?oid={cid}"
BILIBILI_VIDEO = "https://www.bilibili.com/video/{bvid}"

# 巴哈姆特：作品页有两种写法——新的 ``home.gamer.com.tw/artwork.php?sn=…`` 与旧的
# ``home.gamer.com.tw/creationDetail.php?sn=…``，两种都算（同一篇文章）。
#
# 怎么找到作品页（2026-10-28 用 `--probe-bahamut 千本桜` 逐个试出来的）：
#
# | 地址 | 结果 |
# | --- | --- |
# | `html.duckduckgo.com` + `site:home.gamer.com.tw` | **200、31534 字节、10 个作品链接** ✓ |
# | `search.gamer.com.tw/?q=…` 等 6 个组合 | SSL EOF（TLS 握手被掐） |
# | `home.gamer.com.tw/search.php?…` | 200，但 58–77KB 全是 JS 空壳、0 个链接 |
# | `home.gamer.com.tw/creationSearch.php?…` | 200、1968 字节、0 个链接 |
# | `www.bing.com/search` | 200、122238 字节、0 个链接 |
#
# 所以默认走搜索引擎（它给出的正是 `home.gamer.com.tw` 作品页），站内矩阵留作后备；
# 哪天对方改成服务端渲染，矩阵会自动接上。命中的地址记进 data/ 30 天。
BAHAMUT_ARTWORK = "https://home.gamer.com.tw/artwork.php?sn={sn}"
BAHAMUT_LINK_RE = re.compile(
    r"home\.gamer\.com\.tw/(?:artwork|creationDetail)\.php\?sn=(\d+)")
WEB_SEARCH_URLS = (
    "https://html.duckduckgo.com/html/?q=site%3Ahome.gamer.com.tw+{kw}",
    "https://www.bing.com/search?q=site%3Ahome.gamer.com.tw+{kw}",
)
BAHAMUT_SEARCH_BASES = (
    "https://search.gamer.com.tw/?{param}={kw}&p=1&t=3",     # 站内搜索 · 創作
    "https://search.gamer.com.tw/?{param}={kw}&p=1",          # 站内搜索 · 全部
    "https://home.gamer.com.tw/search.php?{param}={kw}",      # 小屋创作搜索
    "https://home.gamer.com.tw/creationSearch.php?{param}={kw}",
)
BAHAMUT_SEARCH_PARAMS = ("q", "keyword", "kw")
BAHAMUT_SEARCH_MAX = 8              # 搜索命中的作品页最多核对几个（搜索引擎一次给 10 个）
BAHAMUT_SEARCH_CACHE = DATA_DIR / "bahamut_search.pickle"
BAHAMUT_SEARCH_TTL = 30 * 24 * 3600  # 记住的地址 30 天内不再重找
# 站内搜索是前端渲染的：结果由 XHR 拉回来，接口地址只写在打包后的 JS 里。这两条
# 正则用来「照页面引用的脚本找接口」（`bahamut_api_templates`）。
SCRIPT_SRC_RE = re.compile(r"<script[^>]+src=[\"']([^\"']+)[\"']", re.I)
API_HINT_RE = re.compile(
    r"""["']((?:https?:)?//[^"'\s]*?(?:api|ajax)[^"'\s]*|/?[A-Za-z0-9_\-./]*(?:api|ajax)[A-Za-z0-9_\-./]*)["']""",
    re.I)


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


def strict_key(text: str) -> str:
    """``title_key`` 的严格版：**不**去掉末尾的 ``(消歧义后缀)``。

    「这首歌有没有条目」必须按完整标题认：``[[EDEN(酔シグレ)|EDEN]]`` 不能因为
    剥掉括号就对上了 みつばちぼっち 的 ``EDEN``，``[[言灵(PiroP)|言灵]]`` 也一样
    （``言灵`` 是 kamome sano 的歌）。其余归一化与 ``title_key`` 相同。
    """
    text = unicodedata.normalize("NFKC", str(text or ""))
    text = COMMENT_RE.sub("", text)
    text = LJ_RE.sub(lambda m: m.group(1), text)
    text = LINK_RE.sub(lambda m: (m.group(1) or m.group(2) or ""), text)
    text = TAG_RE.sub("", text)
    text = re.sub(r"'{2,}", "", text)
    text = re.sub(r"\s+", "", text)
    return text.strip("*").lower()


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
            rows.append(Row(index, cells, row_sides(cells, sides)))
            sides_of[index] = per_side
    return rows, sides_of


def row_sides(cells: Sequence[Cell], declared: int) -> int:
    """这一行有几侧：表头说的和**实际单元格数**取大的那个。

    光看表头不行：某张表若漏了 ``! colspan=`` 那一行，表头会算出「1 侧 12 列」，
    于是按 1 侧读，右半边整片看不见——那一节的歌就永远轮不到查询
    （2026-10-28 反馈：2022秋 一行都没补过）。单元格数是硬事实：12 格就是 2 侧。
    表头说 2 侧而这一行只写了 6 格（右侧整半格省略）时仍按表头的 2 侧算。
    """
    if not cells or len(cells) % PER_SIDE:
        return declared
    return max(declared, min(len(cells) // PER_SIDE, 4))


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
SEASONS_VERSION = 2                 # 缓存结构变了就 +1（旧格式会自动重建）

SEASON_HEADING_RE = re.compile(
    r"^={2,4}\s*([^=\n]*?(?:ボカコレ|VOCALOID\s*Collection)[^=\n]*?)\s*={2,4}\s*$", re.M)
SEASON_YEAR_RE = re.compile(r"(20\d{2})")
SEASON_LABEL_RE = re.compile(r"(20\d{2})\s*([春夏秋冬])")
# 「原曲页面上挂着译文」的改曲条目：不做投稿年核对
VARIANT_RE = re.compile(r"remix|リミックス|cover|カバー|再解釈|アレンジ", re.I)
CONTRIB_HEADING_RE = re.compile(r"^===\s*([^=\n]+?)\s*===\s*$", re.M)
TRACK_SPLIT_RE = re.compile(r";(TOP\d+|ROOKIE|REMIX)[^\n]*")
NOTE_OVERALL_RE = re.compile(r"\{\{注\|\s*\d+\s*\|\s*总榜为第?\s*(\d+)")
COLORLINK_CELL_RE = re.compile(r"\{\{colorlink\|[^|]*\|(?P<title>.+?)\|(?P<rank>\d+)\}\}")
RANK_LINK_CELL_RE = re.compile(r"\[\[(?P<title>[^\]|]+)\|(?P<rank>\d+)\]\]")
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


def season_token(name: str) -> str:
    """任意写法 → ``2022秋``（``[[…|ボカコレ2022秋]]`` / ``2022 秋`` 都行）。"""
    match = SEASON_LABEL_RE.search(str(name or ""))
    return f"{match.group(1)}{match.group(2)}" if match else str(name or "").strip()


def normalise_season(name: str) -> str:
    """标题 → 规范赛季名 ``ボカコレ2022秋``。

    页面的小节标题写法并不统一：``== ボカコレ2022秋 ==``、``=== ボカコレ2022秋 ===``、
    ``== [[某条目|ボカコレ2022秋]] ==`` 都可能出现。以前只认第一种，认不出的那些小节
    会被算进**上一个**小节——2026-10-28 就是这样：``--season 2022秋`` 匹配到 0 行，
    而 2021秋 莫名其妙有 91 行。
    """
    text = str(name or "")
    link = LINK_PAIR_RE.search(text)
    if link:
        text = link.group("alias") or link.group("target")
    text = text.replace("[", "").replace("]", "").strip()
    if SEASON_LABEL_RE.search(text):
        return f"ボカコレ{season_token(text)}"
    return text


def season_sections(text: str) -> List[Tuple[str, str]]:
    """页面 → ``[(规范赛季名, 正文)]``（标题写法随便）。"""
    return [(normalise_season(name), body)
            for name, body in split_sections(text, SEASON_HEADING_RE)]


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


def navbox_titles(text: str) -> Set[str]:
    """大家族模板里出现过的曲名（条目名与日文原名）→ ``{归一化曲名}``。

    只做「这首歌确实在这个赛季的清单里」这一项核对；模板里的 ``[[条目|显示文字]]``
    后半段有时只是显示文字，所以不拿它当翻译名用。
    """
    titles: Set[str] = set()
    for match in LINK_PAIR_RE.finditer(text):
        for name in (match.group("target"), match.group("alias") or ""):
            key = title_key(name)
            if key:
                titles.add(key)
    return titles


def page_season_songs(text: str) -> Dict[str, Dict[str, Set[int]]]:
    """搜集库页面 → ``{赛季: {赛道: {已录入的名次}}}``。"""
    result: Dict[str, Dict[str, Set[int]]] = {}
    for name, body in season_sections(text):
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
    for name, body in season_sections(text):
        found = {int(value) for value in NOTE_OVERALL_RE.findall(body)}
        if found:
            result[name] = found
    return result


def is_disambig_category(category: str) -> bool:
    """``Category:消歧义页`` 这类分类才算消歧义（``消歧义模板链入页面错误`` 不算）。"""
    name = str(category or "").split(":", 1)[-1].strip()
    return name in DISAMBIG_CATEGORIES


def created_after_redirects(query: dict) -> Set[str]:
    """API 的 query 结果 → 已经有正式条目的标题（原标题、重定向源都算）。

    缺页不算；消歧义页也不算（``pageprops.disambiguation``，或分类是
    ``Category:消歧义页``）——页面主人在消歧义，不是建了条目。
    """
    chain: Dict[str, str] = {}
    for key in ("normalized", "redirects"):
        for item in query.get(key) or []:
            source, target = item.get("from"), item.get("to")
            if source and target:
                chain[source] = target
    alive: Set[str] = set()
    for page in (query.get("pages") or {}).values():
        if "pageid" not in page or page.get("missing") is not None:
            continue
        if "disambiguation" in (page.get("pageprops") or {}):
            continue
        if any(is_disambig_category(item.get("title") or "")
               for item in page.get("categories") or []):
            continue
        title = page.get("title") or ""
        if title:
            alive.add(title)

    def final(title: str) -> str:
        seen: Set[str] = set()
        while title in chain and title not in seen:
            seen.add(title)
            title = chain[title]
        return title

    result = set(alive)
    for title in list(chain):
        if final(title) in alive:
            result.add(title)
    return result


def article_keys(site, titles: Sequence[str]) -> Set[str]:
    """这些标题里哪些已经有正式条目 → ``strict_key`` 集合（一次查 50 个，跟重定向）。"""
    wanted: List[str] = []
    for title in titles:
        text = str(title or "").strip()
        if text and text not in wanted:
            wanted.append(text)
    keys: Set[str] = set()
    for start in range(0, len(wanted), ARTICLE_BATCH):
        batch = wanted[start:start + ARTICLE_BATCH]
        try:
            data = site.simple_request(
                action="query", titles="|".join(batch), redirects=1,
                prop="info|pageprops|categories", ppprop="disambiguation",
                clshow="!hidden", cllimit=50).submit()
        except Exception as exc:        # noqa: BLE001 - 查不到就当没条目，不删
            pywikibot.warning(f"查条目是否存在失败：{exc}")
            continue
        for title in created_after_redirects(data.get("query") or {}):
            key = strict_key(title)
            if key:
                keys.add(key)
    return keys


def created_keys_from_contrib(contrib: Dict[str, Dict[str, Dict[int, Tuple[str, bool]]]]
                              ) -> Set[str]:
    """[[Vocawiki:贡献列表/The VOCALOID Collection]] 里标成「已创建」的曲名 key。

    同样用 ``strict_key``：清单里的 ``言灵`` / ``EDEN`` 和搜集库里的
    ``言灵(PiroP)`` / ``EDEN(酔シグレ)`` 是两首不同的歌，不能混。
    """
    keys: Set[str] = set()
    for tracks in (contrib or {}).values():
        for cells in tracks.values():
            for title, created in cells.values():
                key = strict_key(title)
                if created and key:
                    keys.add(key)
    return keys


def article_producer(site, title: str) -> str:
    """条目 Songbox 里的 ``|P主 =`` / ``|職人 =``；读不到就返回空串。"""
    try:
        text = Page(site, title).text or ""
    except Exception as exc:            # noqa: BLE001 - 读不到就不删
        pywikibot.warning(f"读取条目失败（{title}）：{exc}")
        return ""
    match = ARTICLE_PRODUCER_RE.search(text)
    return match.group(1).strip() if match else ""


def article_is_ours(site, title: str, producer: str) -> bool:
    """条目里写的 P主 和这一行的 P主 是同一个人才算「这首歌的条目」。

    条目没写 P主（列表页、消歧义模板等）就一律不认——删错比漏删糟得多。
    """
    found = article_producer(site, title)
    if not found or not str(producer or "").strip():
        return False
    return person_key(found) == person_key(producer)


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
    names = [normalise_season(m.group(1)) for m in SEASON_HEADING_RE.finditer(text)]
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


def is_current(entry: Optional[Dict], ttl: float, miss_ttl: float = 0) -> bool:
    """这条缓存还能直接用（同版本、没过期）。规则一改就靠版本号整体作废。

    ``miss_ttl``：没查到来源的结论用更短的有效期。查不到的歌占绝大多数（134/161），
    一律 14 天不复核的话，页面会连着几周一点都不变——那不是「没东西可填」，
    只是没再去问。
    """
    if not isinstance(entry, dict) or entry.get("v") != CACHE_VERSION:
        return False
    limit = ttl
    if miss_ttl and not entry.get("sources"):
        limit = min(ttl, miss_ttl) if ttl else miss_ttl
    return is_fresh(entry.get("at"), limit)


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
    markup = _atwiki_markup(fetcher, pid)
    if not markup:
        return ""
    body = ATWIKI_BODY_RE.search(markup)
    if not body:
        return ""
    return urllib.parse.unquote(TAG_RE.sub("\n", body.group(1)))


def _atwiki_markup(fetcher: Fetcher, pid: str) -> str:
    """AtWiki 页面 HTML（同一次运行里同一页只抓一次：正文、投稿年都要看它）。"""
    cache = getattr(fetcher, "atwiki_markup", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            fetcher.atwiki_markup = cache       # type: ignore[attr-defined]
        except AttributeError:                  # 只读的假 fetcher：不缓存也行
            cache = {}
    if pid not in cache:
        cache[pid] = fetcher.text(ATWIKI_PAGE.format(pid=pid))
    return cache[pid]


def atwiki_upload_year(fetcher: Fetcher, pid: str) -> Optional[int]:
    """页面里那支 niconico 视频的投稿年；页面没有链接、或查不到就返回 ``None``。"""
    video = NICO_ID_RE.search(_atwiki_markup(fetcher, pid))
    if not video:
        return None
    found = NICO_UPLOAD_RE.search(fetcher.text(NICO_INFO.format(vid=video.group(1))))
    return int(found.group(1)) if found else None


def atwiki_year_ok(fetcher: Fetcher, pid: str, year: int, title: str = "") -> bool:
    """AtWiki 这一页的歌是不是 ``year`` 年那一届的作品。

    VCCL 只收新曲，所以投稿年和赛季年份必须一致：``死亡フラグ`` 的 p/3460 是
    2011-05-14 的投稿，却被 2022秋 的同名行引用了——年份就是判据。查不到投稿日
    一律不认（宁缺毋滥）；``Remix`` / ``Cover`` / ``再解釈`` 之类标题跳过这项，
    因为它们的译文本来就挂在原曲页面上。
    """
    if is_variant_title(title):
        return True
    return atwiki_upload_year(fetcher, pid) == year


def atwiki_translator(fetcher: Fetcher, pid: str) -> str:
    """AtWiki 页面正文里的 ``翻譯：某人``；没有就返回空串。"""
    return credit_name(atwiki_body(fetcher, pid))


def lookup_atwiki(fetcher: Fetcher, song: Song, index: Dict[str, str],
                  season: str = "") -> List[str]:
    """页面名精确匹配**且**正文里出现这首歌的 P主，才认。

    同名不同曲在歌词wiki 上很常见：``Linaria`` 那一页是 Mysteka 的（翻译 kyroslee），
    不是子牛的；``EDEN`` 那一页是真尋P 的，不是酔シグレ 的；``Redis``/``Redial``、
    ``Reboot`` 同理（2026-10-22 实测四条全错）。页面开头的「作詞：/作曲：」就是
    判据，对不上就不记；知道赛季时再核对投稿年（``atwiki_year_ok``）。

    ``USE_ATWIKI`` 现在是 ``False``（页面主人要求暂时不收录中文歌词wiki），
    这个函数留给以后恢复时用。
    """
    tried = set()
    year = season_year(season)
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
        if year is not None and not atwiki_year_ok(fetcher, pid, year, name):
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


def netease_translator(payload: dict) -> str:
    """这条译文的署名：``transUser``，其次 ``lyricUser``；空串 = 没有署名。

    **署名只决定写不写 ``(by. 译者)``，不用来判断有没有译文**（用户 2026-10-28）：
    ``walker`` / ``liar`` 这类早期投稿的译文没有 ``transUser``，却是一一对照的译文；
    有没有译文看 `translation_matches_original()`。占位词（「暂无」等）由 `clean_name` 滤掉。
    """
    user = payload.get("transUser") or payload.get("lyricUser") or {}
    return clean_name(user.get("nickname") or "")


def timed_lyrics(text: str) -> List[Tuple[int, str]]:
    """LRC 文本 → ``[(毫秒, 歌词行)]``；``[by:]`` 这类元信息与「作词 : X」署名行不算。

    网易云有两种时间轴写法，两种都要认：``[mm:ss.xx]``（多数）和 ``[mm:ss:cc]``
    （``walker`` / ``Day Dreamer!`` 这类早期上传，秒与百分秒之间是**冒号**）——
    只认一种的话，有译文的歌会被判成「译文对不上」。
    """
    rows: List[Tuple[int, str]] = []
    for line in (text or "").split("\n"):
        line = line.strip()
        if not line or LYRIC_META_RE.match(line):
            continue
        match = LYRIC_STAMP_RE.match(line)
        if not match:
            continue
        minutes, seconds, fraction, body = match.groups()
        body = body.strip()
        if not body or LYRIC_CREDIT_RE.search(body):
            continue
        millis = int(minutes) * 60000 + int(seconds) * 1000
        fraction = (fraction or "")[:3]
        if fraction:                                   # .39 = 390ms；:17 = 170ms
            millis += int(fraction) * 10 ** (3 - len(fraction))
        rows.append((millis, body))
    return rows


def _near_time(times: Sequence[int], value: int) -> bool:
    """``value``（毫秒）附近 ``TRANSLATION_MATCH_TOLERANCE`` 内有没有原文的时间点。"""
    index = bisect.bisect_left(times, value)
    for probe in (index - 1, index):
        if 0 <= probe < len(times) and abs(times[probe] - value) <= TRANSLATION_MATCH_TOLERANCE:
            return True
    return False


def translation_matches_original(payload: dict) -> bool:
    """``tlyric`` 是不是**和原文对照**的译文（用户 2026-10-28 定的口径）。

    判定只看时间轴：译文行要落在原文某一行的同一时间点上（允许
    ``TRANSLATION_MATCH_TOLERANCE`` 的误差），至少一半对得上才算。

    * ``Self Decision``（1945588853）：46 行译文**没有一行**对得上原文（开头差 5 秒，
      后面一路错开）—— 页面主人说「这首根本就没有翻译」，就该当没有；
    * ``walker``（1914894430）/ ``liar``：52 行一一合上（旧格式 ``[mm:ss:cc]``），
      虽然没人署名，但它们确实是翻译。

    允许译者合并 / 拆分行，所以门槛是一半而不是全部；行数太少（纯音乐、只有署名行）
    一律不算，因为没有可对照的东西。
    """
    original = timed_lyrics((payload.get("lrc") or {}).get("lyric", ""))
    translated = timed_lyrics((payload.get("tlyric") or {}).get("lyric", ""))
    # 原文太短（纯音乐、只有署名行）就没有可对照的东西；译文至少要两行，
    # 一行的话对上对不上都说明不了什么（译者也可能几行并成一行译）。
    if len(original) < TRANSLATION_MIN_LINES or len(translated) < 2:
        return False
    times = sorted(time for time, _ in original)
    matched = sum(1 for time, _ in translated if _near_time(times, time))
    return matched / len(translated) >= TRANSLATION_MATCH_RATIO


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


def netease_queries(song: Song) -> List[str]:
    """去网易云搜什么。先用歌名，再用「P主 歌名」。

    只搜歌名会漏：同名曲太热门时，正确的那首排在十几位之后（``hubble`` /
    ``walker`` / ``次世代`` 就是这样漏的）。带上 P主 之后，前几条基本就是他本人的
    投稿。两个词都试，代价只是多几次请求。
    """
    wanted: List[str] = []
    for word in (song.title_target, song.title_display):
        word = str(word or "").strip()
        if word and word not in wanted:
            wanted.append(word)
    producer = str(song.producer or "")
    for _ in range(3):                  # {{lj|歩く人}} → 歩く人
        replaced = re.sub(r"\{\{[^{}]*\|([^{}]*)\}\}", lambda m: m.group(1), producer)
        if replaced == producer:
            break
        producer = replaced
    producer = re.sub(r"\{\{|\}\}", "", producer).strip()
    if producer:
        for word in (song.title_target, song.title_display):
            word = str(word or "").strip()
            joined = f"{producer} {word}".strip()
            if word and joined not in wanted:
                wanted.append(joined)
    return wanted


def lookup_netease(fetcher: Fetcher, song: Song) -> List[str]:
    """歌名对上、P主 出现在歌手 / 专辑里、**译文和原文对照得上**才记。

    只有歌名对上是不够的：``月之花`` 能搜到 Daoko 的 ``月の花``，``言灵`` 能搜到
    V.W.P 的 ``言霊``，都是同名不同曲。网易云上 Vocaloid 曲一般由 P主 自己上传，
    所以「歌手或专辑里有 P主」是个便宜又准的判据；查不到 P主 就干脆不记。

    同一首歌的 remix / cover 不算（``Silver Lining`` 对上了 ``Silver Lining
    (Yandere VIP Remix)``）：歌词可能被改过，宁可不记。

    译文光有 ``tlyric`` 也不算：要看它和原文对不对得上（见
    `translation_matches_original`）——``Self Decision`` 那种各唱各的不算，
    ``walker`` 这种没人署名但一一对照的算。
    """
    wanted = {title_key(song.title_target), title_key(song.title_display)}
    wanted.discard("")
    producer = person_key(song.producer)
    if not producer:
        return []
    own_variant = is_variant_title(song.title_target) or is_variant_title(song.title_display)
    for keyword in netease_queries(song):
        for candidate in netease_search(fetcher, keyword):
            if not (netease_titles(candidate) & wanted):
                continue
            if producer not in netease_credits(candidate):
                continue
            if not own_variant and is_variant_title(str(candidate.get("name") or "")):
                continue
            payload = netease_lyrics(fetcher, str(candidate.get("id")))
            if not payload or not (payload.get("tlyric") or {}).get("lyric"):
                continue                    # 没有译文：不记（原歌词不是翻译来源）
            if not translation_matches_original(payload):
                continue                    # 译文和原文对不上：不是这首歌的翻译
            return [render_source(NETEASE_SONG.format(id=candidate.get("id")),
                                  "网易云音乐", netease_translator(payload))]
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
    # 「翻译」是最常见的写法；没结果时再试「中字」「字幕」——不少译文视频标题只写这两个
    for word in (song.title_display, song.title_target):
        if not str(word or "").strip():
            continue
        for suffix in ("翻译", "中字", "字幕"):
            keyword = f"{word} {suffix}"
            for hit in bilibili_search(fetcher, keyword)[:4]:
                bvid = str(hit.get("bvid") or "")
                if bvid and bvid not in candidates:
                    candidates.append(bvid)
            if len(candidates) >= 4 or sources:
                break
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


def bahamut_artwork_urls(markup: str) -> List[str]:
    """页面或 JSON 里出现的作品页链接，按出现顺序去重。

    搜索页的作品链接可能写成相对路径、``%3Fsn%3D`` 这种转义形式、或者包在 JSON
    字符串里（``"url":"https:\\/\\/home.gamer.com.tw\\/artwork.php?sn=6103400"``），
    所以先整体反转义再扫一遍；新旧两种地址（``artwork.php`` / ``creationDetail.php``）
    都认。
    """
    text = urllib.parse.unquote(str(markup or "")).replace("\\/", "/")
    found: List[str] = []
    for match in BAHAMUT_LINK_RE.finditer(text):
        url = BAHAMUT_ARTWORK.format(sn=match.group(1))
        if url not in found:
            found.append(url)
    return found


def bahamut_search_templates() -> List[str]:
    """站内搜索的「基址 × 参数名」全部组合（``{kw}`` 留给调用方填关键字）。"""
    return [base.format(param=param, kw="{kw}")
            for base in BAHAMUT_SEARCH_BASES
            for param in BAHAMUT_SEARCH_PARAMS]


def bahamut_search_chain() -> List[str]:
    """按**实测效果**排好的搜索顺序（``{kw}`` 留给调用方）。

    2026-10-28 用 ``--probe-bahamut 千本桜`` 试出来：

    | 地址 | 结果 |
    | --- | --- |
    | ``html.duckduckgo.com`` + ``site:home.gamer.com.tw`` | **200、31534 字节、10 个作品链接** ✓ |
    | ``search.gamer.com.tw/?q=…`` 等 6 个组合 | SSL EOF（TLS 握手被掐） |
    | ``home.gamer.com.tw/search.php?…`` | 200，但 58–77KB 全是 JS 空壳、0 个链接 |
    | ``home.gamer.com.tw/creationSearch.php?…`` | 200、1968 字节、0 个链接 |
    | ``www.bing.com/search`` | 200、122238 字节、0 个链接 |

    所以把搜索引擎放最前（它拿到的就是 ``home.gamer.com.tw`` 的作品页，正是需要的），
    站内矩阵留在后面当后备——万一哪天对方给了服务端渲染的版本，就不用改代码。
    """
    return list(WEB_SEARCH_URLS) + bahamut_search_templates()


def load_bahamut_search() -> str:
    """上次管用的搜索地址（过期或没记录就返回空串）。"""
    entry = load_cache(BAHAMUT_SEARCH_CACHE)
    template = str(entry.get("url") or "") if isinstance(entry, dict) else ""
    if not template or not is_fresh(entry.get("at"), BAHAMUT_SEARCH_TTL):
        return ""
    return template


def save_bahamut_search(template: str) -> None:
    save_cache({"url": template, "at": time.time(), "v": 1}, BAHAMUT_SEARCH_CACHE)


# 这一轮里哪个搜索地址回得出作品链接（存进 data/，下一个进程直接用）
_BAHAMUT_SEARCH_WORKING = ""
# 全部组合都扫不出链接：这一轮别再为每首歌白试十来次
_BAHAMUT_SEARCH_DEAD = False


def _try_bahamut_templates(fetcher: Fetcher, templates: Sequence[str], quoted: str
                           ) -> Tuple[str, List[str], str, str]:
    """按顺序试模板 → ``(命中的模板, 作品链接, 留作接口发现的页面, 那一页的 URL)``。

    「那一页」只从巴哈姆特自己的搜索结果里留（``gamer.com.tw`` 且引了 JS）：站内搜索
    是前端渲染时，接口地址就写在它引用的 bundle 里，``bahamut_api_templates`` 要用。
    """
    page = ""
    page_url = ""
    for template in templates:
        url = template.replace("{kw}", quoted)
        if fetcher.is_blocked(url):
            continue
        markup = fetcher.text(url, attempts=1)
        if not markup:
            continue
        found = bahamut_artwork_urls(markup)
        if found:
            return template, found, markup, url
        if not page and "gamer.com.tw" in url and SCRIPT_SRC_RE.search(markup):
            page, page_url = markup, url
    return "", [], page, page_url


def bahamut_api_templates(fetcher: Fetcher, page: str, page_url: str = "") -> List[str]:
    """从搜索页引用的 JS 里找出结果接口，拼成 ``…?参数={kw}`` 模板。

    站内搜索是前端渲染的，结果由 XHR 拉回来；接口地址只写在打包后的 JS 里。
    这里读前几个 bundle、把像接口的路径挑出来，交给调用方挨个试（挑错也无所谓：
    试不出作品链接就丢掉）。只在搜索引擎与静态组合都失败时才做。
    """
    host = "https://search.gamer.com.tw"
    if page_url:
        parts = urllib.parse.urlsplit(page_url)
        if parts.scheme and parts.netloc:
            host = f"{parts.scheme}://{parts.netloc}"
    templates: List[str] = []
    for src in SCRIPT_SRC_RE.findall(page or "")[:4]:
        bundle = fetcher.text(urllib.parse.urljoin(host + "/", src), attempts=1)
        if not bundle:
            continue
        for hint in API_HINT_RE.findall(bundle):
            hint = hint.replace("\\/", "/")
            if hint.startswith("/"):
                base = host + hint
            elif "gamer.com.tw" in hint:
                base = hint
            elif re.fullmatch(r"[A-Za-z0-9_\-./]+", hint):
                base = host + "/" + hint          # 少了前导斜杠的相对路径
            else:
                continue
            base = base.split("?")[0]
            if not base or base.endswith("/"):
                continue
            for param in BAHAMUT_SEARCH_PARAMS:
                template = f"{base}?{param}={{kw}}"
                if template not in templates:
                    templates.append(template)
    return templates[:12]


def bahamut_search(fetcher: Fetcher, keyword: str) -> List[str]:
    """找巴哈姆特作品页 → URL 列表（最多 ``BAHAMUT_SEARCH_MAX`` 条）。

    顺序见 ``bahamut_search_chain``：搜索引擎（实测唯一能扫出链接的）→ 站内矩阵 →
    照搜索页引用的 JS 找接口。命中的组合记进 ``data/bahamut_search.pickle``（30 天），
    之后的歌只先试它，不再把十来个地址挨个敲一遍。全都失败就整轮停手，
    只保留「从 B站简介里找外链」这条老路。
    """
    global _BAHAMUT_SEARCH_WORKING, _BAHAMUT_SEARCH_DEAD
    if not str(keyword or "").strip() or _BAHAMUT_SEARCH_DEAD:
        return []
    quoted = urllib.parse.quote(keyword)
    if not _BAHAMUT_SEARCH_WORKING:
        _BAHAMUT_SEARCH_WORKING = load_bahamut_search()
    templates = bahamut_search_chain()
    if _BAHAMUT_SEARCH_WORKING in templates:
        templates.remove(_BAHAMUT_SEARCH_WORKING)
        templates.insert(0, _BAHAMUT_SEARCH_WORKING)
    winner, urls, page, page_url = _try_bahamut_templates(fetcher, templates, quoted)
    if not winner:
        winner, urls, _, _ = _try_bahamut_templates(
            fetcher, bahamut_api_templates(fetcher, page, page_url), quoted)
    if winner:
        if winner != _BAHAMUT_SEARCH_WORKING:
            _BAHAMUT_SEARCH_WORKING = winner
            save_bahamut_search(winner)
            pywikibot.output(f"巴哈姆特搜索可用：{winner}")
        return urls[:BAHAMUT_SEARCH_MAX]
    _BAHAMUT_SEARCH_DEAD = True
    pywikibot.warning("巴哈姆特搜索一个作品页都没搜到（搜索引擎与站内地址都空），"
                      "本轮只用 B站简介里的外链；想复查请跑 --probe-bahamut 歌名")
    return []


def lookup_bahamut_search(fetcher: Fetcher, song: Song) -> List[str]:
    """搜到的作品页逐个核对（标题对得上、正文有译文署名），对得上才记。"""
    sources: List[str] = []
    keyword = song.title_target or song.title_display
    for url in bahamut_search(fetcher, keyword):
        try:
            found = lookup_bahamut(fetcher, url, song)
        except Exception as exc:        # noqa: BLE001 - 单个页面出错不影响别的
            pywikibot.warning(f"巴哈姆特查询失败（{url}）：{exc}")
            continue
        for item in found:
            if item not in sources:
                sources.append(item)
        if len(sources) >= 2:
            break
    return sources


def probe_bahamut(keyword: str) -> None:
    """``--probe-bahamut 歌名``：把每个搜索组合都试一遍，打印状态与作品链接数。

    全都扫不出链接时会顺手看一眼搜索页里引了哪些 JS、里面又写了哪些 API 地址——
    站内搜索换成新的 XHR 接口时，照着这些行改 ``BAHAMUT_SEARCH_BASES`` 就行。
    """
    fetcher = Fetcher()
    quoted = urllib.parse.quote(keyword)
    page = ""
    page_url = ""
    winner = ""
    for template in bahamut_search_chain():
        url = template.replace("{kw}", quoted)
        try:
            with fetcher.opener.open(url, timeout=REQUEST_TIMEOUT) as response:
                status = getattr(response, "status", 200)
                raw = response.read().decode("utf-8", "replace")
        except Exception as exc:        # noqa: BLE001 - 探测就是把失败打出来
            pywikibot.output(f"✗ {url}\n    {type(exc).__name__}: {exc}")
            continue
        if not page and "gamer.com.tw" in url and SCRIPT_SRC_RE.search(raw):
            page, page_url = raw, url
        found = bahamut_artwork_urls(raw)
        pywikibot.output(f"{'✓' if found else '·'} {url}\n"
                         f"    HTTP {status}、{len(raw)} 字节、作品链接 {len(found)} 个"
                         + (f"：{found[0]} …" if found else ""))
        if found and not winner:
            winner = template

    if winner:
        pywikibot.output(f"结论：用 {winner}")
        return
    pywikibot.output("结论：全部扫不出作品链接。下面是搜索页引用的 JS 里出现的接口地址，"
                     "把能返回结果的地址发给维护者即可加进 BAHAMUT_SEARCH_BASES：")
    host = "https://search.gamer.com.tw"
    if page_url:
        parts = urllib.parse.urlsplit(page_url)
        if parts.scheme and parts.netloc:
            host = f"{parts.scheme}://{parts.netloc}"
    scripts = [urllib.parse.urljoin(host + "/", src)
               for src in SCRIPT_SRC_RE.findall(page)][:6]
    for script in scripts:
        pywikibot.output(f"  · {script}")
        try:
            with fetcher.opener.open(script, timeout=REQUEST_TIMEOUT) as response:
                bundle = response.read().decode("utf-8", "replace")
        except Exception as exc:        # noqa: BLE001
            pywikibot.output(f"      读不到：{exc}")
            continue
        hints: List[str] = []
        for hint in API_HINT_RE.findall(bundle):
            if hint not in hints:
                hints.append(hint)
        for hint in hints[:12]:
            pywikibot.output(f"      {hint}")


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
                    site=None, season: str = "",
                    only: Sequence[str] = ()) -> List[str]:
    """一首歌全部能查到的来源（最多 ``MAX_SOURCES`` 条，按可靠程度排序）。

    ``only``：只查其中几个来源（``("bahamut",)`` = 只用巴哈姆特），用来单独补某一
    来源新找到的译文，不去敲别的站。
    """
    want = {item for item in only if item}
    sources: List[str] = []
    if USE_ATWIKI and (not want or "atwiki" in want):
        try:
            sources.extend(lookup_atwiki(fetcher, song, index, season))
        except Exception as exc:        # noqa: BLE001 - 单个来源出错不影响其他来源
            pywikibot.warning(f"AtWiki 查询失败（{song.title_display}）：{exc}")
    if not want or "netease" in want:
        try:
            sources.extend(lookup_netease(fetcher, song))
        except Exception as exc:        # noqa: BLE001
            pywikibot.warning(f"网易云查询失败（{song.title_display}）：{exc}")

    bb_id = ""
    if site is not None:
        bb_id = article_video(site, song)
    gamer_links: List[str] = []
    opus_links: List[str] = []
    if not want or "bilibili" in want:
        try:
            found, gamer_links, opus_links = lookup_bilibili(fetcher, song, bb_id)
            sources.extend(found)
        except Exception as exc:        # noqa: BLE001
            pywikibot.warning(f"B站查询失败（{song.title_display}）：{exc}")
        for url in opus_links[:2]:
            try:
                sources.extend(bilibili_opus(fetcher, url, song))
            except Exception as exc:    # noqa: BLE001
                pywikibot.warning(f"B站笔记查询失败（{url}）：{exc}")
    if not want or "bahamut" in want:
        for url in gamer_links[:3]:
            try:
                sources.extend(lookup_bahamut(fetcher, url, song))
            except Exception as exc:    # noqa: BLE001
                pywikibot.warning(f"巴哈姆特查询失败（{url}）：{exc}")
        if not sources:
            # 别的来源都没结果时，再去巴哈姆特搜一遍（拿到的页面照样要过
            # 标题 + 署名的核对，认错的风险和别的来源一样低）。只在没别的来源时才搜，
            # 免得每首歌都多敲对方一次。
            try:
                sources.extend(lookup_bahamut_search(fetcher, song))
            except Exception as exc:    # noqa: BLE001
                pywikibot.warning(f"巴哈姆特搜索失败（{song.title_display}）：{exc}")

    unique: List[str] = []
    for item in sources:
        if item not in unique:
            unique.append(item)
    return unique[:MAX_SOURCES]


def season_data(site, fetcher: Fetcher, refresh: bool = False,
                with_titles: Optional[bool] = None) -> Dict:
    """活动清单（贡献列表，必要时再加 12 个大家族模板）缓存 7 天。

    ``with_titles``：要不要读大家族模板（只有补录需要日文原名）。默认看
    ``USE_ATWIKI``，所以仅仅为了「删掉已有条目的行」时不会白读 12 个模板。
    """
    with_titles = USE_ATWIKI if with_titles is None else with_titles
    cache = load_cache(SEASONS_CACHE)
    if (not refresh and cache.get("v") == SEASONS_VERSION and cache.get("data")
            and is_fresh(cache.get("built"), SEASONS_TTL)
            and (not with_titles or cache["data"].get("titles")
                 or not cache["data"].get("contrib"))):
        return cache["data"]
    data: Dict = {"contrib": {}, "titles": {}}
    try:
        contrib = Page(site, CONTRIB_PAGE).text or ""
        data["contrib"] = parse_contrib_seasons(contrib)
    except Exception as exc:            # noqa: BLE001
        pywikibot.warning(f"读取贡献列表失败：{exc}")
    titles: Dict[str, List[str]] = {}
    if with_titles:
        for season in data["contrib"]:
            template = NAVBOX_TEMPLATE.format(season=season.replace("ボカコレ", ""))
            try:
                markup = Page(site, template).text or ""
            except Exception as exc:    # noqa: BLE001
                pywikibot.warning(f"读取大家族模板失败（{template}）：{exc}")
                continue
            titles[season] = sorted(navbox_titles(markup))
    data["titles"] = titles
    if data["contrib"]:
        save_cache({"v": SEASONS_VERSION, "built": time.time(), "data": data},
                   SEASONS_CACHE)
    return data


def title_hint(title: str) -> str:
    """``Colors(kouta)`` / ``月光(春风哈娜)`` 里括号中的 P主 —— 用来核对同名不同曲。"""
    match = re.match(r"^(?P<base>.+?)\s*[(（](?P<hint>[^()（）]{1,40})[)）]$", str(title or "").strip())
    if not match:
        return ""
    hint = match.group("hint").strip()
    if not hint or hint.isdigit() or hint.startswith("无翻译"):
        return ""
    return hint


def has_kana(text: str) -> bool:
    return bool(re.search(r"[\u3040-\u30ff]", str(text or "")))


def season_year(season: str) -> Optional[int]:
    """``ボカコレ2022秋`` → ``2022``；标题里没有年份就返回 ``None``。"""
    match = SEASON_YEAR_RE.search(str(season or ""))
    return int(match.group(1)) if match else None


def is_variant_title(title: str) -> bool:
    """``… (XX Remix)`` / ``… COVER`` / ``… 再解釈`` —— 译文本就挂在原曲页面上的改曲。"""
    return bool(VARIANT_RE.search(str(title or "")))


def season_of_lines(text: str) -> Dict[int, str]:
    """每一行属于哪个赛季（按它上方最近的赛季标题，标题写法随便）。"""
    result: Dict[int, str] = {}
    season = ""
    for index, line in enumerate(text.split("\n")):
        heading = SEASON_HEADING_RE.search(line)
        if heading:
            season = normalise_season(heading.group(1))
        result[index] = season
    return result


def list_seasons(text: str) -> List[str]:
    """``--list-seasons``：把页面里的赛季标题与行数打出来（排查「为什么这届查不到」）。

    同时列出**没被认出**的可疑标题（标题里有「2022秋」这类年份季节、却没被当成赛季），
    以及像子页面引用的行——那两种都是「这一节对机器人隐形」的常见原因。
    """
    lines = text.split("\n")
    seasons = season_of_lines(text)
    rows, _ = parse_rows(text)
    row_counts: Counter = Counter()
    filled: Counter = Counter()
    for row in rows:
        name = seasons.get(row.line, "") or "（无赛季）"
        if any(row.text(side, column).strip()
               for side in range(row.sides) for column in range(PER_SIDE)):
            row_counts[name] += 1
        for side in range(row.sides):
            if row.text(side, COLUMNS.index("source")).strip():
                filled[name] += 1
    out: List[str] = []
    for index, line in enumerate(lines):
        heading = SEASON_HEADING_RE.search(line)
        if heading:
            name = normalise_season(heading.group(1))
            level = len(line.strip()) - len(line.strip().lstrip("="))
            out.append(f"第 {index + 1} 行  {'=' * level} {heading.group(1)} → {name}："
                       f"{row_counts.get(name, 0)} 行、已填来源 {filled.get(name, 0)}")
            continue
        if line.lstrip().startswith("=") and SEASON_LABEL_RE.search(line):
            out.append(f"第 {index + 1} 行  ⚠ 标题里有年份季节但没被认成赛季："
                       f"{line.strip()[:60]}")
        elif SEASON_LABEL_RE.search(line) and ("{{" in line or "}}" in line
                                               or line.lstrip().startswith(("#", "*"))):
            out.append(f"第 {index + 1} 行  ⚠ 可能是子页面引用：{line.strip()[:60]}")
    if not out:
        out.append("页面里没有找到任何赛季标题")
    return out


def atwiki_song(fetcher: Fetcher, index: Dict[str, str],
                title: str, season: str = "") -> Optional[Tuple[str, str, str]]:
    """核实一首「还没录入」的歌在 AtWiki 有没有译文 → ``(页面 id, 译者, P主)``。

    只靠「页面名对上」不算——同名不同曲在歌词wiki 上到处都是。所以：

    * 曲名必须是**日文原名**（含假名）才查：纯中文 / ASCII 曲名对上的多半是别的歌，
      而且中文名在 贡献列表 / 模板里的对应关系不可靠（``[[Femme Fatale|femme fatale]]``
      这种「显示文字」会被当成日文名）；
    * 曲名带括号注记时（``Colors(kouta)``、``月光(春风哈娜)``），AtWiki 的作曲必须
      就是括号里那位；
    * 给了赛季就核对**投稿年**（``atwiki_year_ok``）：``死亡フラグ`` 那一页是 2011 年
      的老曲，2022秋 的同名行不该引它——日文曲名不加这一关，等于把「同名」当「同一首」；
    * 页面里读不到作曲 / 译者就跳过。

    2026-10-22 首版没这些限制，补的 10 行里 6 行是「同名不同曲」，已整笔撤回。
    """
    hint = title_hint(title)
    if not has_kana(title) and not hint:
        return None                     # 纯中文 / ASCII 又没法核对 P主：不认
    pid = index.get(title_key(title))
    if not pid:
        return None
    body = atwiki_body(fetcher, pid)
    if not body:
        return None
    producer = atwiki_credits(body)
    translator = credit_name(body)
    if hint and person_key(producer) != person_key(hint):
        return None                     # 同名不同曲
    if not producer and not translator:
        return None
    year = season_year(season)
    if year is not None and not atwiki_year_ok(fetcher, pid, year, title):
        pywikibot.output(f"  - {title}：AtWiki p/{pid} 不是 {season} 的歌"
                         f"（投稿年 {atwiki_upload_year(fetcher, pid)}），跳过")
        return None
    return pid, translator, producer


# 歌姬 / 音源名：网易云的「歌手」位常常挂的是音源而不是 P主，遇到这些就不当 P主 用
VOCAL_SYNTHS = (
    "初音ミク", "初音未来", "初音未來", "鏡音リン", "鏡音レン", "巡音ルカ", "MEIKO",
    "KAITO", "GUMI", "IA", "可不", "星界", "flower", "v flower", "鳴花ヒメ",
    "鳴花ミコト", "裏声クリスタル", "ずんだもん", "東北ずん子", "重音テト", "重音teto",
    "弱音ハク", "亞北ネル", "鏡音", "ミク", "リン", "レン", "ルカ", "ボカロ",
    "vocaloid", "cevio", "ボイスロイド", "synthv", "synthesizer v",
)


def is_vocal_synth(name: str) -> bool:
    """这个名字是不是音源 / 歌姬名（而不是 P主）。"""
    key = person_key(name)
    if not key:
        return True
    return any(key == person_key(item) or person_key(item) in key
               for item in VOCAL_SYNTHS)


def producer_from_netease(candidate: dict) -> str:
    """网易云搜索结果里的 P主：取第一个不是音源的歌手名（没有就空）。"""
    for artist in candidate.get("artists") or []:
        name = clean_name(str(artist.get("name") or ""))
        if name and not is_vocal_synth(name):
            return name
    return ""


def netease_candidate(fetcher: Fetcher, title: str) -> Optional[Tuple[str, str]]:
    """「搜集库没录入」的歌：网易云能不能确认它有译文、以及 P主 是谁 → ``(来源, P主)``。

    这条是给**表格是空的**赛季补行用的：活动清单告诉我们「这一届第 N 名是这首歌」，
    但没有 P主；网易云上这类投稿由 P主 自己上传，歌手位就是 P主，所以拿它当 P主。
    判据一条都不放宽：歌名对上、译文和原文对得上、歌手不是音源名。
    """
    wanted = {title_key(title)}
    wanted.discard("")
    if not wanted or is_variant_title(title):
        return None
    for candidate in netease_search(fetcher, str(title or "")):
        if not (netease_titles(candidate) & wanted):
            continue
        if is_variant_title(str(candidate.get("name") or "")):
            continue
        producer = producer_from_netease(candidate)
        if not producer:
            continue                    # 只有音源名：P主 说不清，不补这一行
        payload = netease_lyrics(fetcher, str(candidate.get("id")))
        if not payload or not (payload.get("tlyric") or {}).get("lyric"):
            continue
        if not translation_matches_original(payload):
            continue
        return (render_source(NETEASE_SONG.format(id=candidate.get("id")),
                              "网易云音乐", netease_translator(payload)), producer)
    return None


def add_missing_entries(site, fetcher: Fetcher, text: str, index: Dict[str, str],
                        data: Dict, max_add: int, write: bool,
                        wanted: Sequence[str] = ()) -> Tuple[str, int]:
    """把「外站有翻译、搜集库没录入」的歌补进对应赛季的表格 → ``(新文本, 补了几行)``。

    表格是空的赛季（页面只有表头、一行数据都没有）也靠它补：``missing_songs`` 会说
    这一届有 200 首没录入，逐首去核实哪些真的外站有译文。
    ``wanted`` 给了就只补这几届。
    """
    contrib = data.get("contrib") or {}
    season_titles = {season: set(titles) for season, titles
                     in (data.get("titles") or {}).items()}
    if not contrib:
        pywikibot.warning("拿不到活动清单，本轮不补录")
        return text, 0
    missing = missing_songs(text, contrib)
    if wanted:
        tokens = {season_token(word) for word in wanted}
        missing = [song for song in missing if season_token(song.season) in tokens]
    totals = overall_ranks(contrib)
    pywikibot.output(f"活动清单里有 {len(missing)} 首未录入搜集库（有条目 / 已录入的不算）")
    added = 0
    for song in missing:
        if added >= max_add:
            break
        producer = ""
        source = ""
        translated = False
        if USE_ATWIKI:
            if title_key(song.title) not in season_titles.get(song.season, set()):
                continue                # 本赛季大家族模板里没有这首歌：不敢认
            found = atwiki_song(fetcher, index, song.title, song.season)
            if found:
                pid, translator, producer = found
                if producer:
                    source = render_source(ATWIKI_PAGE.format(pid=pid),
                                           "VOCALOID中文歌词wiki", translator)
                    translated = True
        if not translated:
            # 歌词wiki 暂停时改看网易云：确认有译文，并从歌手位拿到 P主
            try:
                hit = netease_candidate(fetcher, song.title)
            except Exception as exc:    # noqa: BLE001 - 单首查不到不影响别的
                pywikibot.warning(f"网易云核实失败（{song.title}）：{exc}")
                hit = None
            if not hit:
                continue
            source, producer = hit
        if not producer:
            continue                    # 没 P主 就没法补行（P主 那一列是必要的）
        bodies = dict(season_sections(text))
        if song.season not in bodies:
            continue
        body = bodies[song.season]
        sides = section_sides(body)
        if song.track not in sides:
            continue
        side = sides.index(song.track)
        rank = str(song.rank)
        overall = totals.get((song.season, title_key(song.title)))
        if song.track == "ROOKIE" and overall and section_uses_note(body, side):
            rank = "{{注|%d|总榜为第%d}}" % (song.rank, overall)
        values = [rank, render_song_title(song.title), render_producer(producer),
                  "{{color|#FF0000|未创建}}", source, ""]
        row = build_row(len(sides), side, values)
        text = insert_row(text, song.season, song.track, song.rank, row)
        added += 1
        pywikibot.output(f"  + {song.season} {song.track} {song.rank} {song.title}"
                         f"（{producer}）← {source}")
    return text, added


def clear_sides(text: str, line: int, sides: Sequence[int]) -> str:
    """把某一行的指定侧清空（另一侧的单元格与空白原样保留）。"""
    lines = text.split("\n")
    cells = split_row(lines[line])
    for side in sides:
        for column in range(PER_SIDE):
            index = side * PER_SIDE + column
            if index < len(cells):
                cells[index].value = ""
    lines[line] = join_row(cells)
    return "\n".join(lines)


def remove_row(text: str, line: int) -> str:
    """整行删掉，连同它前面那行 ``|-``。"""
    lines = text.split("\n")
    del lines[line]
    if line > 0 and lines[line - 1].strip() == "|-":
        del lines[line - 1]
    return "\n".join(lines)


def blank_row(row: Row) -> bool:
    """这一行是不是整行空白（只剩一堆 ``||``）。"""
    return not any(row.text(side, column).strip()
                   for side in range(row.sides) for column in range(PER_SIDE))


def _side_cells(row: Row, side: int) -> List[Cell]:
    """某一行某一侧的 6 个单元格（列数不够时补空）。"""
    cells: List[Cell] = []
    for column in range(PER_SIDE):
        index = side * PER_SIDE + column
        cells.append(row.cells[index] if index < len(row.cells) else Cell(" ", "", ""))
    return cells


def _put_side_cells(row: Row, side: int, cells: Sequence[Cell]) -> None:
    while len(row.cells) < (side + 1) * PER_SIDE:
        row.cells.append(Cell(" ", "", ""))
    for column, cell in enumerate(cells):
        row.cells[side * PER_SIDE + column] = cell


def _row_blocks(text: str) -> List[List[Row]]:
    """把行按表格分组（同一张表里相邻的行只隔着 ``|-``）。"""
    lines = text.split("\n")
    rows, _ = parse_rows(text)
    blocks: List[List[Row]] = []
    for row in rows:
        if blocks and all(lines[i].strip() == "|-"
                          for i in range(blocks[-1][-1].line + 1, row.line)):
            blocks[-1].append(row)
        else:
            blocks.append([row])
    return blocks


def compact_sides(text: str) -> Tuple[str, int]:
    """每侧的空位挪到表尾，别在表格中间留一块空白 → ``(新文本, 挪动的行数)``。

    ``prune`` 只清一侧时（另一侧还没条目），那一行就空出半格；页面主人看到的是
    表格中间凭空多出一条空白带（2026-10-25 反馈）。这里把同一侧后面的曲目依次
    上移补位：顺序不变、曲目一个不丢，空位移到表尾——表尾本来就长短不一。
    """
    lines = text.split("\n")
    moved = 0
    for block in _row_blocks(text):
        if any(row.sides != 2 for row in block):
            continue
        touched = False
        for side in (0, 1):
            slots = [_side_cells(row, side) for row in block]
            filled = [cells for cells in slots
                      if any(cell.value.strip() for cell in cells)]
            if len(filled) == len(slots):
                continue                       # 这一侧没有空位
            if not filled:
                continue                       # 全空：交给 remove_blank_rows
            template = next(cells for cells in slots
                            if not any(cell.value.strip() for cell in cells))
            shifted = [filled[i] if i < len(filled) else template
                       for i in range(len(slots))]
            if all(new is old for new, old in zip(shifted, slots)):
                continue
            for row, cells in zip(block, shifted):
                _put_side_cells(row, side, cells)
            touched = True
        if touched:
            for row in block:
                new_line = join_row(row.cells)
                if new_line != lines[row.line]:
                    lines[row.line] = new_line
                    moved += 1
    return "\n".join(lines), moved


def remove_blank_rows(text: str) -> Tuple[str, int]:
    """删掉整行空白的行 → ``(新文本, 删掉的行数)``。

    只清一侧的旧版本会留下「有行没内容」的空壳，页面上的表现就是表格中间多出
    一条空白带（2026-10-25 反馈）。
    """
    rows, _ = parse_rows(text)
    removed = 0
    for row in sorted(rows, key=lambda item: item.line, reverse=True):
        if blank_row(row):
            text = remove_row(text, row.line)
            removed += 1
    return text, removed


def prune_created_rows(text: str, keys: Set[str]) -> Tuple[str, List[str]]:
    """删掉「这首歌已经有条目」的行 → ``(新文本, 删掉的曲名列表)``。

    页面主人的做法就是这样（274610：`Maison` / `Tokyo Nighthawk` / `Equivalent`
    有条目之后，对应的行整行删掉）。两侧都有歌、只有一侧有条目时，只清那一侧
    —— 另一侧还没条目，留着继续待补。
    """
    if not keys:
        return text, []
    seasons = season_of_lines(text)
    rows, _ = parse_rows(text)
    notes: List[str] = []
    for row in sorted(rows, key=lambda item: item.line, reverse=True):
        titles = {side: row.text(side, COLUMNS.index("title")).strip()
                  for side in range(row.sides)}
        titles = {side: value for side, value in titles.items() if value}
        hit = [side for side, value in titles.items()
               if strict_key(link_target(value)) in keys]
        if not hit:
            continue
        for side in hit:
            notes.append(f"{seasons.get(row.line, '')} {link_display(titles[side])}")
        if len(hit) == len(titles):
            text = remove_row(text, row.line)
        else:
            text = clear_sides(text, row.line, hit)
    return text, notes


def drop_row(text: str, row: Row, side: int) -> str:
    """删掉一行；另一侧还有内容时只清这一侧，别把别人的半边也删了。"""
    others = [other for other in range(row.sides)
              if other != side and row.text(other, COLUMNS.index("title")).strip()]
    if others:
        return clear_sides(text, row.line, [side])
    return remove_row(text, row.line)


def drop_wrong_rows(text: str, fetcher: Fetcher) -> Tuple[str, List[str]]:
    """删掉「引的 AtWiki 页面根本不是这一季那首歌」的行 → ``(新文本, 说明列表)``。

    判据只有一条：页面里那支 niconico 视频的投稿年和这一行的赛季年份对不上
    （``死亡フラグ`` 的行引了 2011 年的 p/3460）。这种引用本身就是错的，所以：

    * 这一行的 P主 又是那一页的 ``作曲`` —— 整行都是那次错配的产物（暂名、P主、
      来源一起编出来的），删掉；
    * P主 对不上 —— 只清「翻译来源」一格，别人填的 P主 不动。

    查不到投稿日的行一律不动（没法证明它错）。投稿年本来就该和赛季不同
    （``Remix`` / ``Cover`` / ``再解釈``：译文本就挂在原曲页面上）的也跳过。
    """
    seasons = season_of_lines(text)
    rows, _ = parse_rows(text)
    notes: List[str] = []
    for row in sorted(rows, key=lambda item: item.line, reverse=True):
        season = seasons.get(row.line, "")
        year = season_year(season)
        if year is None:
            continue
        for side in range(row.sides):
            title = row.text(side, COLUMNS.index("title")).strip()
            link = ATWIKI_LINK_RE.search(row.text(side, COLUMNS.index("source")))
            if not title or not link or is_variant_title(title):
                continue
            pid = link.group(1)
            upload = atwiki_upload_year(fetcher, pid)
            if upload is None or upload == year:
                continue
            producer = row.text(side, COLUMNS.index("producer")).strip()
            credits = atwiki_credits(atwiki_body(fetcher, pid))
            who = link_display(title)
            why = f"AtWiki p/{pid} 是 {upload} 年的另一首"
            if person_key(producer) and person_key(producer) == person_key(credits):
                text = drop_row(text, row, side)
                notes.append(f"{season} {who}（{why}，整行删除）")
            else:
                text = apply_fills(text, {(row.line, side): ""})
                notes.append(f"{season} {who}（{why}，只清来源）")
            break
    return text, notes


def prune_entries(site, fetcher: Fetcher, text: str, refresh: bool = False,
                  lookup=article_keys, ours=article_is_ours) -> Tuple[str, List[str]]:
    """把「这首歌已经有条目」的行清掉 → ``(新文本, 删掉的曲名)``。

    证据两条，都是站内事实，且都用 ``strict_key``（保留 ``(消歧义后缀)``）：

    1. [[Vocawiki:贡献列表/The VOCALOID Collection]] 里那一格已经标成「已创建」
       （``{{colorlink|…}}``）——页面主人维护的清单；
    2. 条目真的存在（跟重定向、排除消歧义页），**并且条目的 P主 和这一行一致**
       —— 光有同名页面不算：``EDEN`` 是 みつばちぼっち 的，跟 ``EDEN(酔シグレ)``
       无关；``言灵`` 是 kamome sano 的，跟 ``言灵(PiroP)`` 无关。
    """
    rows, _ = parse_rows(text)
    entries: Dict[str, Tuple[str, str]] = {}      # strict_key -> (标题, P主)
    for row in rows:
        for side in range(row.sides):
            title = row.text(side, COLUMNS.index("title")).strip()
            if not title:
                continue
            target = link_target(title)
            producer = row.text(side, COLUMNS.index("producer")).strip()
            key = strict_key(target)
            if key:
                entries.setdefault(key, (target, producer))
    keys: Set[str] = set()
    try:
        data = season_data(site, fetcher, refresh, with_titles=False)
        keys |= created_keys_from_contrib(data.get("contrib") or {})
    except Exception as exc:            # noqa: BLE001 - 读不到清单就只按条目判断
        pywikibot.warning(f"读取活动清单失败：{exc}")
    pending = {key: value for key, value in entries.items() if key not in keys}
    if pending:
        try:
            existing = lookup(site, [target for target, _ in entries.values()])
        except Exception as exc:        # noqa: BLE001
            pywikibot.warning(f"查条目是否存在失败：{exc}")
            existing = set()
        for key in sorted(existing & set(pending)):
            target, producer = pending[key]
            try:
                if ours(site, target, producer):
                    keys.add(key)
            except Exception as exc:    # noqa: BLE001
                pywikibot.warning(f"核对条目 P主 失败（{target}）：{exc}")
    return prune_created_rows(text, keys)


def query_order(songs: Sequence[Song], cache: Dict) -> List[Song]:
    """按「上次核对的时间」排：从没查过的排最前，其次是最久没查的。

    ``--limit`` 是按顺序截断的，一直按页面顺序截，就永远只查最上面那几个赛季
    （2026-10-28：搜集库最后一节 2022秋 一行都没查过，前面几节却查了好几遍）。
    改按核对时间轮转之后，整页都会轮到，最后几节不会再垫底。
    """
    def stamp(song: Song) -> float:
        entry = cache.get(song.key)
        at = entry.get("at") if isinstance(entry, dict) else None
        return float(at) if isinstance(at, (int, float)) else -1.0

    # sorted 是稳定排序：一样的时间就保持页面顺序
    return sorted(songs, key=stamp)


def season_coverage(songs: Sequence[Song], cache: Dict,
                    seasons: Dict[int, str],
                    current: Dict[Tuple[int, int], str]) -> List[str]:
    """每个赛季的进度，用来一眼看出哪一节被落下了 → 每节一句话。"""
    totals: Counter = Counter()
    filled: Counter = Counter()
    known: Counter = Counter()
    order: List[str] = []
    for song in songs:
        season = seasons.get(song.line, "") or "（无赛季）"
        if season not in totals:
            order.append(season)
        totals[season] += 1
        if (current.get((song.line, song.side)) or "").strip():
            filled[season] += 1
        if isinstance(cache.get(song.key), dict):
            known[season] += 1
    return [f"{season} {totals[season]} 行：页面已填 {filled[season]}、"
            f"核对过 {known[season]}、没核对过 {totals[season] - known[season]}"
            for season in order]


def season_groups(songs: Sequence[Song], seasons: Dict[int, str],
                  wanted: Sequence[str] = ()) -> List[Tuple[str, List[Song]]]:
    """按赛季分组（保持页面顺序）→ ``[(赛季名, [歌…]), …]``。

    ``wanted`` 给定时只留匹配的赛季：``--season 2022秋`` 与 ``--season ボカコレ2022秋``
    等价（比 ``2022秋`` 这个标记，标题写法不同也认得）。
    """
    tokens = {season_token(word) for word in wanted if str(word or "").strip()}
    groups: Dict[str, List[Song]] = {}
    for song in songs:
        name = seasons.get(song.line, "") or "（无赛季）"
        if tokens and season_token(name) not in tokens:
            continue
        groups.setdefault(name, []).append(song)
    return list(groups.items())


def run_once(site, write: bool = False, summary: Optional[str] = None,
             ttl: float = CACHE_TTL, limit: int = 0, refresh: bool = False,
             fetcher: Optional[Fetcher] = None, add_missing: bool = False,
             max_add: int = 10, prune: bool = True,
             miss_ttl: float = MISS_TTL, season: Sequence[str] = (),
             fill: bool = True, only: Sequence[str] = ()) -> bool:
    """跑一轮。返回页面是否需要（或已经）改动。

    ``season``：只查这些赛季（``--season 2022秋``，可写多个）；默认每一届都查。
    ``fill``：False 时只做「删掉已经有条目的行」+ 收尾，不联网查来源（``--prune-only``）。
    ``only``：只查这几个来源（``--only-source bahamut``）；这时新结论会和缓存里
    已有的来源合并，不会把以前查到的更全的结果冲掉。
    """
    fetcher = fetcher or Fetcher()
    if write:
        if not site.logged_in():
            site.login()
        if not site.logged_in():
            raise RuntimeError("登录失败：请检查 user-config.py 与 user-password.py")
    page = Page(site, PAGE_TITLE)
    original = page.text or ""

    # 先删「已经有条目」的行，再填来源：省得给马上要删的行白查一遍（--limit 也不浪费）
    pruned: List[str] = []
    moved = 0
    blanks = 0
    text = original
    # --season 是「只补这几届」，别的届一个字都不动：连删行/补录也一起跳过，
    # 免得用户只想补 2022秋 却发现别的赛季少了几行。
    wanted = [season] if isinstance(season, str) else [s for s in season if s]
    if prune and not wanted:
        text, pruned = prune_entries(site, fetcher, text, refresh)
        for note in pruned:
            pywikibot.output(f"  - 已有条目，删掉：{note}")
        if pruned:
            pywikibot.output(f"本轮删掉 {len(pruned)} 个已有条目的条目")

    songs = songs_from(text)
    seasons = season_of_lines(text)
    rows, _ = parse_rows(text)
    # 有表格行却认不出曲名 = 那一节对机器人是隐形的（表头被改过之类），要吵一声，
    # 否则只表现为「这一节永远不补」。
    row_counts: Counter = Counter(seasons.get(row.line, "") or "（无赛季）"
                                 for row in rows
                                 if any(row.text(side, column).strip()
                                        for side in range(row.sides)
                                        for column in range(PER_SIDE)))
    song_counts: Counter = Counter(seasons.get(song.line, "") or "（无赛季）"
                                   for song in songs)
    for name, count in row_counts.items():
        if count and not song_counts[name]:
            pywikibot.warning(f"{name}：有 {count} 行却认不出任何曲名，"
                              f"表格结构可能变了，这一节不会被补充")
    groups = season_groups(songs, seasons, wanted)
    if wanted and not groups:
        # 静默 0 行最坑：用户以为在补 2022秋，其实那个标题没被认出来。
        detected = "、".join(name for name, _ in season_groups(songs, seasons)) or "（无）"
        pywikibot.error(f"没有匹配的赛季：{'、'.join(wanted)}。"
                        f"页面里的赛季是：{detected}；"
                        f"跑 --list-seasons 看看标题到底怎么写的。")
        return False
    if wanted:
        pywikibot.output("只查 " + "、".join(name for name, _ in groups)
                         + f"：{sum(len(group) for _, group in groups)} 行")

    rows, _ = parse_rows(text)
    current: Dict[Tuple[int, int], str] = {}
    for row in rows:
        for side in range(row.sides):
            if row.text(side, COLUMNS.index("title")).strip():
                cell = (row.line, side)
                current[cell] = row.text(side, COLUMNS.index("source")).strip()
    # --refresh 只跳过「缓存还有效就不再查」，不丢缓存：要靠 written 认出自己写过的格子
    cache = load_cache()
    # 不查歌词wiki 时不必读「全ページ一覧」（8 千多个页面名，冷缓存要几分钟）：
    # 补录要用它、`drop_wrong_rows` 不用（它只按行里已有的 AtWiki 链接核对投稿年）
    index = atwiki_page_index(fetcher) if USE_ATWIKI else {}

    fills: Dict[Tuple[int, int], str] = {}
    queried = 0
    if not fill:
        pywikibot.output("只删行：本轮不查来源（--prune-only）")
    # 每一届各自排队、各自用掉一份 --limit：整页十几届不会互相饿死（见 query_order）。
    for name, group in (groups if fill else []):
        asked = 0
        for song in query_order(group, cache):
            cell = (song.line, song.side)
            cached = cache.get(song.key)
            existing = current.get(cell, "")
            if cell_state(existing, cached) == "skip":
                continue                # 别人写的内容：一个字都不动
            # --only-source 是「现在就把这个来源查一遍」，所以不看缓存有效期
            if is_current(cached, ttl, miss_ttl) and not refresh and not only:
                # 缓存里有结论，但页面可能还没跟上（上次保存失败 / 另一台机器写的）：
                # 只在结论更全时补写，避免两边来回覆盖。
                value = join_sources(cached.get("sources") or [])
                if value and source_count(value) > source_count(existing):
                    fills[cell] = value
                    cached["written"] = value
                continue
            if limit and asked >= limit:
                continue                # 这一届的预算用完了，剩下的留到下一轮
            asked += 1
            queried += 1
            sources = collect_sources(fetcher, song, index, site,
                                      seasons.get(song.line, ""), only)
            if only:
                # 只查了某几个来源：和缓存里已有的结论合并，别把别的来源的结果冲掉
                merged: List[str] = []
                for item in list((cached or {}).get("sources") or []) + list(sources):
                    if item not in merged:
                        merged.append(item)
                sources = merged[:MAX_SOURCES]
            value = join_sources(sources)
            entry = {"at": time.time(), "v": CACHE_VERSION, "sources": sources,
                     "title": song.title_display, "written": existing}
            if value != existing:
                fills[cell] = value     # 新内容 / 更新 / 清掉自己以前写的
                entry["written"] = value
            cache[song.key] = entry
            if sources:
                pywikibot.output(f"  {name} {song.rank or '-'} "
                                 f"{song.title_display}：{len(sources)} 个来源")
            else:
                pywikibot.output(f"  {name} {song.rank or '-'} "
                                 f"{song.title_display}：没找到")
        if fill and group:
            pywikibot.output(f"  {name}：本轮查了 {asked} 首（共 {len(group)} 行）")

    save_cache(cache)
    pywikibot.output(f"待查 {len(current)} 行、本轮查了 {queried} 首、"
                     f"改动 {len(fills)} 行")
    for line in season_coverage(songs, cache, seasons, current):
        pywikibot.output(f"  {line}")
    text = apply_fills(text, fills)
    added = 0
    dropped: List[str] = []
    if add_missing and fill:
        # 清理配错的旧行只做「证明它错」的核对（投稿年对不上），不新增任何内容，
        # 所以 ``USE_ATWIKI = False`` 时也照跑——那是删错，不是收录。
        if not wanted:
            text, dropped = drop_wrong_rows(text, fetcher)
            for note in dropped:
                pywikibot.output(f"  - 配错的行：{note}")
        # --add-missing 是显式要求补行，所以 --season 只限定范围、不取消这一步
        # （2026-10-28：2022秋 的表格是空的，不补行那届永远没有可填的格子）。
        try:
            text, added = add_missing_entries(site, fetcher, text, index,
                                              season_data(site, fetcher, refresh),
                                              max_add, write, wanted)
        except Exception as exc:        # noqa: BLE001 - 补录失败不影响填来源
            pywikibot.warning(f"补录未录入的曲目失败：{exc}")
        if not USE_ATWIKI:
            pywikibot.output("中文歌词wiki 已暂停收录：补行时只看网易云等外站")
    if prune and not wanted:
        # 只清了一侧的行会把那一侧空出半格：同侧后面的曲目上移补位，再把整行
        # 空白的空壳删掉，表格中间就不会留一条空白带（2026-10-25 反馈）。
        text, moved = compact_sides(text)
        if moved:
            pywikibot.output(f"  {moved} 行的曲目上移补位")
        text, blanks = remove_blank_rows(text)
        if blanks:
            pywikibot.output(f"  删掉 {blanks} 个整行空白的行")
    if text == original:
        pywikibot.output("页面无需更新。")
        return False
    if not write:
        pywikibot.output("[dry-run] 页面有改动；加 --write 以保存。")
        return True
    page.text = text
    parts: List[str] = []
    if fill:
        parts.append(f"补 {len(fills)} 行")
    if pruned:
        parts.append(f"删掉 {len(pruned)} 个已有条目的行")
    if added:
        parts.append(f"补录 {added} 首")
    if dropped:
        parts.append(f"删掉 {len(dropped)} 行配错的补录")
    if moved:
        parts.append(f"曲目上移补位 {moved} 行")
    if blanks:
        parts.append(f"删掉 {blanks} 个空行")
    body = "、".join(parts) or "无改动"
    note = summary or (f"{DEFAULT_SUMMARY}，{body}" if fill else f"清理搜集库：{body}")
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
                        help="查到来源的歌多久复检一次（秒，默认 7 天）")
    parser.add_argument("--miss-ttl", type=float, default=MISS_TTL,
                        help="没查到来源的歌多久再搜一次（秒，默认 7 天）")
    parser.add_argument("--limit", type=int, default=0,
                        help="每一届最多查多少首（0 = 不限制）；每一届各有一份预算")
    parser.add_argument("--refresh", action="store_true",
                        help="忽略缓存的有效期，重新核对（缓存本身保留，用于认出自己写过的格子）")
    parser.add_argument("--add-missing", action="store_true",
                        help="把「外站有翻译、搜集库没录入」的曲目补进对应赛季的表格")
    parser.add_argument("--max-add", type=int, default=10,
                        help="本轮最多补录几首（默认 10，0 = 不限制）")
    parser.add_argument("--no-prune", action="store_true",
                        help="不删「已经有条目」的行（默认会删，和页面主人的做法一致）")
    parser.add_argument("--prune-only", action="store_true",
                        help="只删「已经有条目」的行，不联网查来源（每小时跑这一档）")
    parser.add_argument("--only-source", action="append", default=[],
                        choices=("atwiki", "netease", "bilibili", "bahamut"),
                        help="只查这几个来源，例如 --only-source bahamut"
                             "（新结论会和缓存里已有的来源合并）")
    parser.add_argument("--season", action="append", default=[],
                        help="只查这几届，例如 --season 2022秋 --season 2023春"
                             "（也可写成 --season 2022秋,2023春）；默认每一届都查")
    parser.add_argument("--probe-bahamut", default="",
                        help="试一试各个巴哈姆特搜索地址能不能扫出作品链接，然后退出")
    parser.add_argument("--list-seasons", action="store_true",
                        help="打印页面里认出来的赛季标题与行数，然后退出（排查某届查不到）")
    args = parser.parse_args()

    if args.probe_bahamut:
        probe_bahamut(args.probe_bahamut)
        return
    if args.list_seasons:
        text = Page(pywikibot.Site(), PAGE_TITLE).text or ""
        pywikibot.output(f"{PAGE_TITLE} 里的赛季（共 {len(text.splitlines())} 行）：")
        for line in list_seasons(text):
            pywikibot.output("  " + line)
        return

    wanted: List[str] = []
    for item in args.season:
        wanted.extend(part.strip() for part in re.split(r"[,，]", item) if part.strip())
    only: List[str] = []
    for item in args.only_source:
        only.extend(part.strip() for part in re.split(r"[,，]", item) if part.strip())
    run_once(pywikibot.Site(), args.write, args.summary, args.ttl, args.limit,
             args.refresh, add_missing=args.add_missing and not args.prune_only,
             max_add=args.max_add or 10 ** 6, prune=not args.no_prune,
             miss_ttl=args.miss_ttl, season=wanted, fill=not args.prune_only,
             only=only)


if __name__ == "__main__":
    main()
