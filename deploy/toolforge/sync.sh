#!/bin/bash
# 一键更新 Toolforge 上的机器人：拉代码 + 修脚本权限 + 重载全部定时任务。
#
# 在工具账号里跑（job 定义、kubeconfig 都只在那里）：
#   become vocawiki-cont
#   ~/Vocawiki-bots/deploy/toolforge/sync.sh            # 拉代码 + 重载 jobs
#   ~/Vocawiki-bots/deploy/toolforge/sync.sh --dry-run  # 只看会做什么
#   ~/Vocawiki-bots/deploy/toolforge/sync.sh --verify   # 顺便干跑一轮 translations
#
# 幂等：没有新提交时只会重载一次 jobs（几秒），不会动页面。
# 不碰 user-password.py、不碰 data/ 里的缓存、不重建 venv。
set -uo pipefail

DRY_RUN=0
VERIFY=0
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=1 ;;
        --verify)  VERIFY=1 ;;
        -h|--help) sed -n '2,12p' "$0"; exit 0 ;;
        *) echo "未知参数：$arg（见 --help）" >&2; exit 2 ;;
    esac
done

REPO="${VOCA_REPO:-$HOME/Vocawiki-bots}"
JOBS="$REPO/deploy/toolforge/jobs.yaml"

say()  { printf '%s\n' "$*"; }
step() { printf '\n== %s\n' "$*"; }
run() {
    if [[ "$DRY_RUN" == 1 ]]; then
        printf '   [dry-run] %s\n' "$*"
        return 0
    fi
    "$@"
}

# ---------------------------------------------------------------- 0. 前置检查
step "检查环境"
if [[ ! -d "$REPO/.git" ]]; then
    say "找不到仓库：$REPO"
    say "  git clone https://github.com/TimeRen/Vocawiki-bots.git \"$REPO\""
    exit 1
fi
say "  仓库 $REPO"

if ! command -v toolforge >/dev/null 2>&1; then
    say "  找不到 toolforge 命令 —— 请在跳板机上、或 ssh login.toolforge.org 后运行"
    exit 1
fi
if ! toolforge jobs list >/dev/null 2>&1; then
    say "  toolforge jobs 不可用：多半是还没 become 工具账号"
    say "    become vocawiki-cont"
    exit 1
fi
say "  toolforge CLI 可用"

cd "$REPO" || exit 1

# ---------------------------------------------------------------- 1. 拉代码
step "更新代码（git pull --ff-only）"
if ! git fetch --quiet origin; then
    say "  git fetch 失败：检查网络，或代理设置"
    exit 1
fi
if ! git rev-parse --abbrev-ref --symbolic-full-name '@{upstream}' >/dev/null 2>&1; then
    say "  当前分支没有 upstream（detached？）：git checkout main"
    exit 1
fi
incoming=$(git log --oneline "HEAD..@{upstream}" 2>/dev/null | wc -l)
if [[ "$incoming" == 0 ]]; then
    say "  已是最新（$(git rev-parse --short HEAD)）"
else
    say "  有 $incoming 个新提交："
    git --no-pager log --oneline "HEAD..@{upstream}" | sed 's/^/    /'
    if ! run git pull --ff-only; then
        say "  git pull 失败：本地有改动挡住了合并，看看是什么："
        git status --short | sed 's/^/    /'
        say "  确认可以丢弃的话：git checkout -- . && git pull --ff-only"
        exit 1
    fi
fi
say "  当前版本 $(git rev-parse --short HEAD)  $(git log -1 --format=%s)"

# ---------------------------------------------------------------- 2. 脚本权限
# 100644 的 .sh 会让 job 报 exitcode 126（Status: Failed for 3s）
step "修脚本权限（exitcode 126 的成因）"
fixed=0
for script in "$REPO"/deploy/toolforge/*.sh; do
    [[ -x "$script" ]] && continue
    say "  +x $(basename "$script")"
    run chmod +x "$script"
    fixed=$((fixed + 1))
done
[[ "$fixed" == 0 ]] && say "  都已可执行"

# ---------------------------------------------------------------- 3. 校验 jobs.yaml
step "校验 $JOBS"
if [[ ! -f "$JOBS" ]]; then
    say "  缺少 jobs.yaml"
    exit 1
fi

python_bin=""
for candidate in "$HOME/pyvenv/bin/python" python3 python; do
    if command -v "$candidate" >/dev/null 2>&1; then
        python_bin="$candidate"
        break
    fi
done
if [[ -z "$python_bin" ]]; then
    say "  找不到 python：无法校验 YAML（job 的 image 自带，但这条命令要在跳板机/容器里跑）"
    exit 1
fi

if ! "$python_bin" - "$JOBS" <<'PY'
import sys
try:
    import yaml
except ImportError:
    sys.exit(0)                     # 没装 PyYAML 就跳过语法校验，交给 jobs load
with open(sys.argv[1], encoding="utf-8") as handle:
    data = yaml.safe_load(handle)
print("  任务：" + " / ".join(job.get("name", "?") for job in data))
PY
then
    say "  YAML 解析失败：检查缩进、缩进里不能有 Tab"
    exit 1
fi

# 每个 job 的 command 都是相对**工具 home** 的 ./Vocawiki-bots/...，写错就 exitcode 127
missing=0
while IFS= read -r job_command; do
    script=${job_command%% *}
    script=${script#./Vocawiki-bots/}
    if [[ ! -f "$REPO/$script" ]]; then
        say "  缺失：$script（jobs.yaml 里写着 $job_command）"
        missing=1
    fi
done < <(sed -n 's/^[[:space:]]*command:[[:space:]]*//p' "$JOBS")
[[ "$missing" == 0 ]] && say "  command 指向的脚本都在"

# ---------------------------------------------------------------- 4. 重载任务
step "重载定时任务"
if ! run toolforge jobs load "$JOBS"; then
    say "  jobs load 失败。常见原因："
    say "    · 不在工具账号里（先 become 工具名）"
    say "    · YAML 缩进错 / 用了 Tab"
    exit 1
fi

step "当前任务"
if ! toolforge jobs list; then
    say "  jobs list 失败（不影响已载入的任务）"
fi

# ---------------------------------------------------------------- 5. 可选：干跑
if [[ "$VERIFY" == 1 ]]; then
    step "干跑一轮 translations（不保存页面）"
    run toolforge jobs run translations-check --image python3.13 --wait \
        --command "./Vocawiki-bots/deploy/toolforge/run-collection-translations.sh --dry-run"
    say "  日志：cat ~/translations-check.out"
fi

say ""
say "完成。查看运行情况："
say "  toolforge jobs list"
say "  tail -n 30 ~/translations.out      # 每个任务各有一个 .out"
say "登录 / 密码 / venv 有没有问题，用只读自检确认："
say "  $REPO/deploy/toolforge/preflight.sh"
