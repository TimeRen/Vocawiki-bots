#!/bin/bash
# 第一次部署（或换了新工具账号）时用一次：把仓库装到工具 home，然后交给 sync.sh。
#
#   ssh <用户名>@login.toolforge.org \
#     'become vocawiki-contrib -- bash -lc "curl -fsSL \
#        https://raw.githubusercontent.com/TimeRen/Vocawiki-bots/main/deploy/toolforge/bootstrap.sh | bash"'
#
# 之后每次更新只要跑 sync.sh（bootstrap 只多做一件「没有仓库就 clone」）。
#
# 之所以要单独一个脚本：从外面一行调用时，`~` 会展开成你的**个人 home**（become
# 不重置 HOME），工具账号读不了那里；这里改成用 getent 取工具账号真正的 home，
# 并把 HOME 纠回去，clone 才有地方写、toolforge CLI 才找得到 kubeconfig。
set -uo pipefail

say() { printf '%s\n' "$*"; }

me="$(id -un)"
tool_home="$(getent passwd "$me" 2>/dev/null | cut -d: -f6)"
if [[ -z "${tool_home:-}" || ! -d "$tool_home" ]]; then
    tool_home="/data/project/$me"           # getent 不给/不对时退回约定路径
fi
if [[ ! -d "$tool_home" ]]; then
    say "找不到工具 home（试过 getent 与 /data/project/$me）"
    say "确认一下：id -un / getent passwd \$(id -un) / ls -d /data/project/*"
    exit 1
fi

say "工具账号：$me"
say "工具 home：$tool_home"
export HOME="$tool_home"

REPO="$tool_home/Vocawiki-bots"
URL="https://github.com/TimeRen/Vocawiki-bots.git"

# 目录在、但没有 .git：不是 git 仓库（clone 被中断、或别人拷过去的文件）。
# 这时不能 pull，只能挪到一旁重新 clone —— 但要把密码和缓存搬回来。
if [[ -d "$REPO" && ! -d "$REPO/.git" ]]; then
    backup="$REPO.bak-$(date +%Y%m%d%H%M%S)"
    say "$REPO 存在但不是 git 仓库（没有 .git）"
    say "  挪到 $backup，然后重新 clone"
    if ! mv "$REPO" "$backup"; then
        say "  挪不动：目录不可写？确认工具 home 对不对"
        exit 1
    fi
    if ! git clone "$URL" "$REPO"; then
        say "clone 失败。原来的目录在 $backup（没丢东西），修好网络后重跑本脚本"
        exit 1
    fi
    if [[ -f "$backup/user-password.py" ]]; then
        cp -p "$backup/user-password.py" "$REPO/" && say "  已搬回 user-password.py"
    fi
    if [[ -d "$backup/data" ]]; then
        mkdir -p "$REPO/data" && cp -a "$backup/data/." "$REPO/data/" \
            && say "  已搬回 data/（缓存）"
    fi
    say "  旧目录保留在 $backup，确认没问题后可以删掉"
fi

if [[ -d "$REPO/.git" ]]; then
    say "已有仓库：$REPO"
    if [[ ! -f "$REPO/deploy/toolforge/sync.sh" ]]; then
        say "这个仓库比较旧，里面还没有 sync.sh —— 先拉一次代码"
        if ! git -C "$REPO" pull --ff-only; then
            say "git pull 失败，本地有什么改动："
            git -C "$REPO" status --short | head -20
            say "只有权限位（old mode / new mode）的话可以丢掉："
            say "  git -C \"$REPO\" checkout -- . && git -C \"$REPO\" pull --ff-only"
            exit 1
        fi
    fi
else
    say "出口网络检查（GitHub 能不能连上）："
    if command -v curl >/dev/null 2>&1; then
        say "  github.com         -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://github.com || echo 失败)"
        say "  raw.githubusercontent.com -> $(curl -s -o /dev/null -w '%{http_code}' --max-time 15 https://raw.githubusercontent.com || echo 失败)"
    else
        say "  没有 curl，跳过"
    fi
    say "克隆到 $REPO"
    if ! git clone "$URL" "$REPO"; then
        say ""
        say "克隆失败。按上面的报错处理："
        say "  · Could not resolve host / Connection timed out -> 工具没有出口网络，问一下 Toolforge 状态"
        say "  · Permission denied -> 目录不可写（工具 home 不对？）"
        say "  · destination path ... already exists -> 目录非空，改用 git pull（本脚本开头已处理）"
        say "  · 要账号密码 -> 仓库是私有的，用带 token 的地址重试："
        say "      git clone https://<token>@github.com/TimeRen/Vocawiki-bots.git \"$REPO\""
        exit 1
    fi
fi

if [[ ! -f "$REPO/deploy/toolforge/sync.sh" ]]; then
    say "仓库里没有 deploy/toolforge/sync.sh —— clone 不完整，删掉重来："
    say "  rm -rf \"$REPO\""
    exit 1
fi

exec "$REPO/deploy/toolforge/sync.sh" "$@"
