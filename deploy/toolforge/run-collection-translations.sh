#!/bin/bash
# 填充并维护 [[User:周某不是轴某/VOCALOID collection搜集库]] 的「翻译来源」一栏。
#
# 只填**空**的来源格（不覆盖别人已写的内容），每首歌依次查：
#   * VOCALOID中文歌词wiki（AtWiki）：页面名与歌名精确对上才算；
#   * 网易云音乐：搜到的歌名对上、且确实有译文（tlyric）才记，署名取译文上传者；
#   * B站：条目里的 {{BilibiliVideo}} 优先，否则用关键词搜索，
#           读视频简介 / 评论区 / 弹幕（弹幕在别的来源都空着时才读）里的
#           「翻译：某人」+ 中文歌词，并顺着简介里的外链找笔记（opus）与巴哈姆特专栏；
#   * 巴哈姆特：站内搜索是 JS 渲染的，只能从 B 站简介里的外链进入。
#
# 抓取很慢（一首歌几秒到十几秒，且要读一遍 AtWiki 全ページ一覧），所以每轮限量、
# 逐首缓存：一首歌查过之后 14 天内不再重复查（--ttl / --refresh 可调）。
# 页面有 300 多行、其中一百多行待补，第一轮要跑好一会儿；之后每轮只查新出现的歌。
#
#   toolforge jobs run translations --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-collection-translations.sh --dry-run"
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
    ${write[@]+"${write[@]}"} ${extra[@]+"${extra[@]}"} 2>&1
