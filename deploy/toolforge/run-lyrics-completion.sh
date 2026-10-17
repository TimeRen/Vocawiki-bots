#!/bin/bash
# 维护「VOCALOID中文歌词wiki补完计划」清单
# （[[User:人间百态/VOCALOID中文歌词wiki补完计划]]）。
#
# 它把 Vocawiki 上还没有条目的 AtWiki 歌词页列出来。每轮重新比对：
#   * AtWiki 的「全ページ一覧」（按页面名排序，100 条一页）
#   * Vocawiki 上所有带 {{VOCALOID Songbox}} 的条目（标题 / 重定向 / Songbox 歌名）
# 消歧义页、目录页、站务页不算歌曲，不进清单。
#
# 每天跑一次就够。两份清单缓存在 data/（12 小时），页面判定缓存 30 天，所以
# **第一次**跑要把还没对应的 AtWiki 页面逐个抓一遍（几千页，几分钟），
# 之后每轮只补新出现的页面。
#
#   toolforge jobs run lyrics --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-lyrics-completion.sh --dry-run"
source "$(dirname "$0")/common.sh"

write=(--write)
extra=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        *)         extra+=("$arg") ;;          # 转给机器人（--refresh / --probe-budget=…）
    esac
done

exec "$VOCA_PYTHON" bots/vocaloid_lyrics_completion.py \
    ${write[@]+"${write[@]}"} ${extra[@]+"${extra[@]}"} 2>&1
