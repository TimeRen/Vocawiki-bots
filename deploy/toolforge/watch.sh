#!/bin/bash
# 常驻监听（近实时维护）：由 Toolforge 的 continuous job 拉起，
# 进程退出（含异常）后 Kubernetes 会自动重启，所以不需要 --max-runtime。
#
# --sweep-interval 就是原先 GitHub Actions 那条 30 分钟兜底：现在由 watcher
# 自己每 30 分钟无条件整体跑一轮（含图表），不再依赖它不可靠的 schedule。
source "$(dirname "$0")/common.sh"

# pywikibot.output() 写的是 stderr，合并到一个流里，工具名.out 才是完整日志
exec "$VOCA_PYTHON" bots/vocaloid_collection_contributions.py \
    watch --interval 30 --settle 15 --sweep-interval 1800 --write 2>&1
