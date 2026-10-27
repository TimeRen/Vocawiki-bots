#!/bin/bash
# 每小时只做一件事：把「已经有条目」的歌从搜集库里删掉（`--prune-only`）。
#
#   toolforge jobs run collection-prune --image python3.13 --wait \
#     --command "./Vocawiki-bots/deploy/toolforge/run-collection-prune.sh --dry-run"
#
# 为什么不和填来源合在一起：填来源要挨个问网易云 / B站 / 巴哈姆特，一周才跑一次
# （见 run-collection-translations.sh）；删行只看站内事实（贡献列表 + 条目是否存在 +
# 条目里的 P主），不联网问外站，所以可以每小时跑，新条目建好后一小时内就能清掉。
source "$(dirname "$0")/common.sh"

write=(--write)
extra=()
for arg in "$@"; do
    case "$arg" in
        --dry-run) write=() ;;                 # 只打印将要做的改动，不保存页面
        *)         extra+=("$arg") ;;          # 转给机器人（--no-prune 之类，慎用）
    esac
done

exec "$VOCA_PYTHON" bots/vocaloid_collection_translations.py --prune-only \
    ${write[@]+"${write[@]}"} ${extra[@]+"${extra[@]}"} 2>&1
