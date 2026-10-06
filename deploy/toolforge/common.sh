#!/bin/bash
# run-once.sh / watch.sh 共用的环境准备：定位仓库、检查 venv。
# 被 source 使用，不单独执行。
set -euo pipefail

VOCA_REPO_DIR="${VOCA_REPO:-$HOME/Vocawiki-bots}"
VOCA_PYTHON="$HOME/pyvenv/bin/python"

if [[ ! -f "$VOCA_REPO_DIR/bots/vocaloid_collection_contributions.py" ]]; then
    cat >&2 <<EOF
找不到仓库：$VOCA_REPO_DIR

job 的工作目录是工具 home（不是仓库目录），代码得先 clone 到 \$HOME/Vocawiki-bots：
  git clone https://github.com/TimeRen/Vocawiki-bots.git "\$HOME/Vocawiki-bots"

放在别处的话，把 VOCA_REPO 环境变量设成那个路径（见 deploy/toolforge/README.md）。
EOF
    exit 1
fi

if [[ ! -x "$VOCA_PYTHON" ]]; then
    cat >&2 <<EOF
找不到 venv：$VOCA_PYTHON

先建一次（必须在 job 容器里做，跳板机没有编译环境装不了 wheel）：
  toolforge jobs run bootstrap-venv --image python3.13 --wait \\
    --command "./Vocawiki-bots/deploy/toolforge/bootstrap_venv.sh"
EOF
    exit 1
fi

# pywikibot 从当前目录读 user-config.py / user-password.py，data/ 缓存也是相对路径
cd "$VOCA_REPO_DIR"

export PYTHONIOENCODING=utf-8
export PYTHONUNBUFFERED=1
