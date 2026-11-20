#!/bin/bash
# 维护 [[Vocawiki:动员令/2027年冬/计分板]] 与 [[…/排行榜]]（每小时一次）。
#
#   toolforge jobs run mobilization --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-mobilization-tally.sh --dry-run"
#
# 活动期 2026-12-01 00:00 ~ 2027-02-15 23:59（+0800）。Toolforge 的 cron 不能指定开始日期，
# 所以闸门写在机器人里：窗口外直接退出 0，到 12-01 自然开始。--ignore-window 可手动越过。
#
# 其它参数原样转给机器人（--limit / --refresh / --out-dir / --state …）。
source "$(dirname "$0")/common.sh"

write=(--write)
extra=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        *)         extra+=("$arg") ;;          # 转给机器人（--limit / --out-dir / --refresh）
    esac
done

exec "$VOCA_PYTHON" -m bots.mobilization_tally \
    ${write[@]+"${write[@]}"} ${extra[@]+"${extra[@]}"} 2>&1
