#!/bin/bash
# 部署前自检，在工具账号下运行：
#   ./deploy/toolforge/preflight.sh
#
# 只做检查、不改任何东西，缺什么就把要补的命令打出来。
set -uo pipefail

REPO="${VOCA_REPO:-$HOME/Vocawiki-bots}"
PASSWORD="$REPO/user-password.py"
PYTHON="$HOME/pyvenv/bin/python"
missing=0

report() { printf '  %-4s %s\n' "$1" "$2"; }

# 1. 代码：必须在工具 home 里，job 才看得到
if [[ -f "$REPO/bots/vocaloid_collection_contributions.py" ]]; then
    report OK "仓库 $REPO"
else
    report 缺失 "仓库 $REPO（没有这个目录，或 clone 到了个人 home）"
    echo "       修复： git clone https://github.com/TimeRen/Vocawiki-bots.git \"$REPO\""
    missing=1
fi

# 2. 密码：文件要在，权限必须是 600（Toolforge 上默认全世界可读）
if [[ -f "$PASSWORD" ]]; then
    perms=$(stat -c '%a' "$PASSWORD" 2>/dev/null || stat -f '%Lp' "$PASSWORD" 2>/dev/null)
    if [[ "$perms" == "600" ]]; then
        report OK "user-password.py（权限 $perms）"
    else
        report 警告 "user-password.py 权限是 ${perms:-未知}，应改成 600"
        echo "       修复： chmod 600 \"$PASSWORD\""
    fi
else
    report 缺失 "user-password.py"
    echo "       修复： 见 deploy/toolforge/README.md 第 3 步"
    missing=1
fi

# 3. venv：装 pywikibot 用的，必须在 job 容器里建
if [[ -x "$PYTHON" ]]; then
    report OK "pyvenv（$PYTHON）"
    version=$("$PYTHON" -c 'import pywikibot, sys; print("pywikibot", pywikibot.__version__, "on Python", sys.version.split()[0])' 2>&1)
    if [[ $? -eq 0 ]]; then
        report OK "$version"
    else
        report 缺失 "pyvenv 里没有 pywikibot：$version"
        missing=1
    fi
else
    report 缺失 "pyvenv（$PYTHON）"
    echo "       修复： toolforge jobs run bootstrap-venv --image python3.13 --wait \\"
    echo "                --command \"cd $REPO && ./deploy/toolforge/bootstrap_venv.sh\""
    missing=1
fi

# 4. 工具账号：kubeconfig 只在 become 之后才有
if [[ -f "$HOME/.kube/config" ]]; then
    report OK "工具账号 kubeconfig（$HOME/.kube/config）"
else
    report 缺失 "工具账号 kubeconfig —— 当前不在工具账号里"
    echo "       修复： become <工具名>（若提示组未生效，先 exit 再重新 ssh）"
    missing=1
fi

echo
if [[ "$missing" == 0 ]]; then
    echo "自检通过，可以继续： toolforge jobs load \"$REPO/deploy/toolforge/jobs.yaml\""
else
    echo "上面缺的东西补齐后再继续。"
fi
exit "$missing"
