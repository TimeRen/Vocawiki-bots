#!/bin/bash
# 跑一轮完整维护：按赛季模板补名次 + 上色 + 计数 + 异常报告 + 重算图表。
#
# job 的工作目录是工具 home，所以从工具 home 里这样调用：
#   toolforge jobs run dryrun --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run"
#
# 也可以只跑某个动作（默认 all），例如萌娘百科交叉比对报告：
#   toolforge jobs run moereport --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run moe"
source "$(dirname "$0")/common.sh"

# pywikibot.output() 写的是 stderr，合并到一个流里，工具名.out 才是完整日志
action=all
write=(--write)
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        --*)       echo "未知参数：$arg" >&2; exit 2 ;;
        *)         action="$arg" ;;
    esac
done

exec "$VOCA_PYTHON" bots/vocaloid_collection_contributions.py "$action" ${write[@]+"${write[@]}"} 2>&1
