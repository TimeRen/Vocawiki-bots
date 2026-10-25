#!/bin/bash
# 查「任务为什么没动页面」：任务状态、最近日志、代码版本、缓存年龄，一次全打出来。
#
# 在控制节点（become 之后）跑：
#   ./Vocawiki-bots/deploy/toolforge/diagnose.sh
# 只查某一个任务：
#   ./Vocawiki-bots/deploy/toolforge/diagnose.sh hourly
#
# 页面靠定时任务维护，任务「在跑但没保存」和「根本没跑」在 wiki 上都只表现为
# 页面不动，所以这里把两边的线索放在一起：任务列表与日志给出前者，代码版本与
# 缓存年龄给出后者（例如缓存被清空后，一轮要重查几百条萌百，跑不完就永远轮不到保存）。
set -uo pipefail

JOB="${1:-}"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

if ! command -v toolforge >/dev/null 2>&1; then
    echo "找不到 toolforge 命令：请在 Toolforge 控制节点上跑（先 become <工具名>）。" >&2
    exit 1
fi

echo "=== 工具与仓库 ==="
if [[ "$HOME" != /data/project/* ]]; then
    echo "警告：HOME=$HOME 不像工具 home（become 不会改 HOME），任务日志可能读不到。"
fi
echo "HOME=$HOME"
echo "仓库=$REPO_DIR"
if git -C "$REPO_DIR" rev-parse --git-dir >/dev/null 2>&1; then
    git -C "$REPO_DIR" --no-pager log -1 --format='版本=%h (%ci) %s'
    git -C "$REPO_DIR" --no-pager status --short --branch | head -3
else
    echo "警告：$REPO_DIR 不是 git 仓库，代码不会自动更新。"
fi

echo
echo "=== 任务列表 ==="
toolforge jobs list 2>&1 || echo "toolforge jobs list 失败"

if [[ -n "$JOB" ]]; then
    echo
    echo "=== $JOB 的定义 ==="
    toolforge jobs show "$JOB" 2>&1 || echo "toolforge jobs show 失败"
    echo
    echo "=== $JOB 最近的日志（末 60 行）==="
    toolforge jobs logs "$JOB" 2>&1 | tail -60 || echo "toolforge jobs logs 失败"
fi

echo
echo "=== 缓存（data/）==="
if [[ -d "$REPO_DIR/data" ]]; then
    find "$REPO_DIR/data" -name '*.pickle' -printf '%TY-%Tm-%Td %TH:%TM  %10s  %f\n' 2>/dev/null \
        | sort || ls -l "$REPO_DIR/data"
else
    echo "没有 data/ 目录：本轮要从零查一遍创建者，慢得多。"
fi

echo
echo "=== 定时任务自检（不写页面）==="
echo "在 job 容器里跑一次干跑，能看出是「没东西可改」还是「跑不完/报错」："
cat <<EOF
  toolforge jobs run diagnose --image python3.13 --wait --mem 512Mi \\
    --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run"
EOF
