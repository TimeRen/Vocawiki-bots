#!/bin/bash
# 跑一轮完整维护：按赛季模板补名次 + 上色 + 计数 + 异常报告 + 重算图表。
#
# pywikibot 从当前目录读 user-config.py / user-password.py，所以必须先 cd 进仓库；
# data/ 的创建者缓存也相对当前目录，放在仓库里即可。
set -euo pipefail

REPO="${VOCA_REPO:-$HOME/Vocawiki-bots}"
cd "$REPO"

export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1

# 传 --dry-run 就只打印将要做的改动，不保存页面
args=(entries,counts,colour,report,stats)
if [[ "${1:-}" == "--dry-run" ]]; then
    shift
else
    args+=(--write)
fi

exec "$HOME/pyvenv/bin/python" bots/vocaloid_collection_contributions.py "${args[@]}" "$@"
