#!/bin/bash
# 维护贡献页 [[User:人间百态/贡献]]（[[User:人间百态]] 上的导航框）：
#   * 「Vocawiki时期」补上这个账号新建的歌曲条目，重定向换成目标页、消歧义页去掉；
#   * 「歌姬模板」补上新建的歌姬模板，子模板（Template:IA/2026 这类）不列。
#
#   toolforge jobs run contributions --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-contributions.sh --dry-run"
source "$(dirname "$0")/common.sh"

write=(--write)
extra=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        *)         extra+=("$arg") ;;          # 转给机器人（--summary=…）
    esac
done

exec "$VOCA_PYTHON" bots/user_contributions_navbox.py \
    ${write[@]+"${write[@]}"} ${extra[@]+"${extra[@]}"} 2>&1
