#!/bin/bash
# 填充并维护 [[User:周某不是轴某/VOCALOID collection搜集库]] 的「翻译来源」一栏。
#
# 只填**空**的来源格（不覆盖别人已写的内容），每首歌依次查：
#   * VOCALOID中文歌词wiki（AtWiki）：页面名与歌名精确对上才算；
#   * 网易云音乐：搜到的歌名对上，且 tlyric **和原文对照得上**（译文行落在原文的
#               时间点上）才记 —— 平台自己配的译文和原文各唱各的，不算；
#   * B站：条目里的 {{BilibiliVideo}} 优先，否则用关键词搜索，
#           读视频简介 / 评论区 / 弹幕（弹幕在别的来源都空着时才读）里的
#           「翻译：某人」+ 中文歌词，并顺着简介里的外链找笔记（opus）与巴哈姆特专栏；
#   * 巴哈姆特：站内搜索（bahamut_search）扫出作品页链接再逐个核对，外加从 B站简介
#           里带进来的外链；地址变了用 `--probe-bahamut 歌名` 试一遍就知道该改哪个。
#
# 抓取很慢（一首歌几秒到十几秒），所以复检定成**每周一次**（缓存 7 天有效期）：
# 页面有一百多行待补，第一轮要跑好一会儿；之后每周把整页轮一遍。
# `--limit N` 是**每一届**的预算（十几届互不挤占），`--season` 可只跑其中几届。
#
# 「删掉已经有条目的行」是另一条每小时的任务：run-collection-prune.sh。
#
#   toolforge jobs run translations --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-collection-translations.sh --dry-run"
#
# 除了填「翻译来源」，它还会拿活动清单（[[Vocawiki:贡献列表/The VOCALOID Collection]]
# 的赛季表 + 大家族模板里的日文原名）反查：哪些歌还没有条目、外站查得到翻译、
# 搜集库却没录入 —— 每轮最多补录 10 行（--max-add）。
source "$(dirname "$0")/common.sh"

write=(--write)
extra=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        *)         extra+=("$arg") ;;          # 转给机器人（--limit / --ttl / --refresh）
    esac
done

exec "$VOCA_PYTHON" bots/vocaloid_collection_translations.py \
    ${write[@]+"${write[@]}"} --add-missing --max-add 10 \
    ${extra[@]+"${extra[@]}"} 2>&1
