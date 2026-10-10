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
#
# 其它参数（如 recredit 的 --from-rev=<版本号>）原样转给机器人脚本，注意用
# = 连写，别写成两个参数，否则版本号会被当成动作名。
source "$(dirname "$0")/common.sh"

# pywikibot.output() 写的是 stderr，合并到一个流里，工具名.out 才是完整日志
action=all
write=(--write)
extra=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        --*)       extra+=("$arg") ;;          # 转给机器人（--from-rev=123）
        *)         action="$arg" ;;
    esac
done

exec "$VOCA_PYTHON" bots/vocaloid_collection_contributions.py "$action" \
    ${write[@]+"${write[@]}"} ${extra[@]+"${extra[@]}"} 2>&1
