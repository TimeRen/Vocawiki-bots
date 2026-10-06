#!/bin/bash
# 跑一轮完整维护：按赛季模板补名次 + 上色 + 计数 + 异常报告 + 重算图表。
#
# job 的工作目录是工具 home，所以从工具 home 里这样调用：
#   toolforge jobs run dryrun --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run"
source "$(dirname "$0")/common.sh"

args=(entries,counts,colour,report,stats)
if [[ "${1:-}" == "--dry-run" ]]; then
    shift            # 只打印将要做的改动，不保存页面
else
    args+=(--write)
fi

exec "$VOCA_PYTHON" bots/vocaloid_collection_contributions.py "${args[@]}" "$@"
