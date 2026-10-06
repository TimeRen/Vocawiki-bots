#!/bin/bash
# 常驻监听（近实时维护）：由 Toolforge 的 continuous job 拉起，
# 进程退出（含异常）后 Kubernetes 会自动重启，所以不需要 --max-runtime。
source "$(dirname "$0")/common.sh"

# pywikibot.output() 写的是 stderr，合并到一个流里，工具名.out 才是完整日志
exec "$VOCA_PYTHON" bots/vocaloid_collection_contributions.py \
    watch --interval 30 --settle 15 --stats-interval 1800 --write 2>&1
