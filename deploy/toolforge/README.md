# 部署到 Toolforge

前提：已有 Toolforge 成员资格，且能用 SSH 登录 `login.toolforge.org`
（见 [Help:Toolforge/Quickstart](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Quickstart)）。

登录成功只说明密钥配好了，机器人还一步都没跑。下面是把 bot 跑起来的完整流程。

## 1. 建工具账号

在 https://toolsadmin.wikimedia.org/tools/ 点 **Create new tool**，起个名字
（比如 `vocawiki-contrib`，别用大写和点）。建完要**退出 SSH 再重新登录**，
新增的工具组才会生效。

## 2. 进入工具账号并取代码

**先 `become` 再干活**：`toolforge jobs` 要读工具账号里的 kubeconfig
（`/data/project/<工具名>/.kube/config`），而且 job 的工作目录就是工具 home。
在跳板机个人账号下跑，既建不了 job，clone 出来的代码 job 也看不到。

```bash
ssh <你的shell用户名>@login.toolforge.org
become vocawiki-contrib          # 提示符变成 tools.vocawiki-contrib@...
pwd                              # 应该是 /data/project/vocawiki-contrib
git clone https://github.com/TimeRen/Vocawiki-bots.git ~/Vocawiki-bots
cd ~/Vocawiki-bots
ls bots/vocaloid_collection_contributions.py   # 确认 clone 真的成功
```

如果之前在个人 home 里 clone 过，删掉那份，别留着混淆。**注意先 `cd ~` 再删**，
站在目录里删掉它会让 shell 找不到当前目录（`getcwd: cannot access parent directories`）：

```bash
cd ~ && rm -rf ~/Vocawiki-bots           # 在 become 之前、个人账号下执行
```

## 3. 放机器人密码

`user-password.py` 不在仓库里（已 gitignore），要手工建。**Toolforge 上默认所有
文件都是公开可读的**，所以权限必须收紧：

```bash
cat > ~/Vocawiki-bots/user-password.py <<'EOF'
('Renjian-bot', BotPassword('后缀', '机器人密码'))
EOF
chmod 600 ~/Vocawiki-bots/user-password.py
```

后缀是 Special:BotPasswords 里 "Renjian-bot@后缀" 中 `@` 后面的部分，别写成
`Renjian-bot@后缀` 当用户名。

## 自检（下一步之前、或任何时候卡住时）

先让脚本自己检查缺什么：

```bash
cd ~/Vocawiki-bots && ./deploy/toolforge/preflight.sh
```

它会逐项报告仓库、`user-password.py`（含权限）、`pyvenv`、工具账号
kubeconfig 是否就位，并直接打印该补的命令。全绿再往下走。

## 4. 建 venv（必须在 job 容器里做）

跳板机没有编译环境，装不了 wheel，所以用一次性 job 引导：

```bash
chmod +x ~/Vocawiki-bots/deploy/toolforge/*.sh
toolforge jobs run bootstrap-venv --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/bootstrap_venv.sh"
```

**注意 command 里的路径是相对工具 home 的**：job 的工作目录是
`/data/project/<tool>`，不是仓库目录，所以必须带 `Vocawiki-bots/` 这一层，
写成 `./deploy/...` 会报 `exitcode 127`。

结束时会打印 `pywikibot <版本> on Python 3.x`。容器里的 `$HOME` 就是工具的
`/data/project/<tool>`，所以 `pyvenv` 建在共享存储上，后续 job 直接复用。

## 5. 干跑确认链路，再去掉 `--dry-run` 确认登录

**干跑不会登录**：`run_once()` 只在 `write=True` 时才 `ensure_login()`，所以
`--dry-run` 只验证脚本路径、venv、pywikibot 能跑通并读到页面，日志里**不会**
出现 `已登录：Renjian-bot`：

```bash
toolforge jobs run dryrun --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run"
cat ~/dryrun.out
```

期望看到 `统计: 依据 listed 重算图表`、`异常报告:`，最后是 `页面无需更新。`；
页面若真有改动，会打印 diff 和 `[dry-run] 加 --write 以保存。`

链路通了之后，**去掉 `--dry-run` 再跑一次**，这一步才会登录：

```bash
toolforge jobs run logincheck --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh"
cat ~/logincheck.out
```

应出现 `已登录：Renjian-bot（权限组：bot, *, user）`。登录失败会直接以非零退出码
报错，并提示检查 `user-config.py` / `user-password.py`。页面本来就无需更新时，
这一跑不会写任何东西。

> **日志位置**：entry 脚本已把 stderr 合并进 stdout（`pywikibot.output()` 写的是
> stderr，不合并则 `工具名.out` 是空的、内容全在 `工具名.err`）。还在用旧版脚本
> 就直接看 `工具名.err`。

## 6. 载入常驻任务

```bash
toolforge jobs load ~/Vocawiki-bots/deploy/toolforge/jobs.yaml
```

会创建两个 job：

| job | 类型 | 作用 |
| --- | --- | --- |
| `watcher` | continuous | 常驻监听 recentchanges，近实时维护；退出后自动重启 |
| `hourly` | cron `@hourly` | 每小时整体跑一轮，兜底重算图表 |

## 7. 查看状态与日志

```bash
toolforge jobs list
toolforge jobs show watcher
cat ~/watcher.out            # entry 脚本已把 stderr 合并进来
```

`tail -f ~/watcher.out` 可以实时跟着看。

## 更新代码

```bash
cd ~/Vocawiki-bots && git pull
toolforge jobs restart watcher   # 常驻 job 不会自动重载代码
```

## 注意

- **job 的工作目录是工具 home**（`/data/project/<tool>`），所以 command 里的
  路径都要以 `./Vocawiki-bots/` 开头；脚本内部会自己 `cd` 进仓库。
- 代码必须 clone 在 `~/Vocawiki-bots`。想放别处就设 `VOCA_REPO` 环境变量
  （`toolforge envvars create VOCA_REPO /data/project/<tool>/某目录`）。
- 改了 `jobs.yaml` 后重新 `toolforge jobs load`；同名 job 定义有变化会被替换。
- 新增依赖时重跑第 4 步的引导脚本（会重建 venv）。
- `data/` 是创建者缓存，会随仓库目录一起留在共享存储上，别删（删了只是变慢）。
- 想用环境变量传密钥可以用 `toolforge envvars`，但本仓库读的是
  `user-password.py`，两种方式选一种即可。

## 排错

### `KubernetesConfigFileNotFoundException` / `Failed to load configuration, did you forget to run 'become <mytool>'?`

`toolforge jobs` 是在**个人账号**下跑的，读的是个人 home 里不存在的
`/mnt/nfs/labstore-secondary-tools-home/<用户名>/.kube/config`。先切进工具账号：

```bash
become <工具名>
toolforge jobs list          # 能看到任务才算进去了
```

`become: no such tool '<工具名>'` 说明工具还没建好，等几分钟；刚建完工具还要
**退出 SSH 重登**一次。

### `You were added to the group tools.<工具名> after you started this login session.`

工具组建好之前你就登录了，当前这轮 SSH 会话里还没有这个组，所以 `become` 用不了。
**退出 SSH 再重新登录**即可（`exit` 后重新 `ssh ...@login.toolforge.org`）。
在跳板机上 `newgrp` 之类是无效的，必须重开会话。

### `shell-init: error retrieving current directory: getcwd: ...`

当前目录已经被删掉了（比如站在 `~/Vocawiki-bots` 里执行了 `rm -rf ~/Vocawiki-bots`）。
先 `cd ~` 回到 home 就好，之后的相对路径也会重新变正确。

### `chmod: cannot access '.../user-password.py': No such file or directory`

那一行是**重定向失败**，不是 `chmod` 的问题：目录 `~/Vocawiki-bots` 不存在，
bash 连文件都建不出来，后面的 `chmod` 自然找不到它。通常是代码没 clone 到工具
home（clone 到了个人 home 就会被 `become` 挡在外面），或者 clone 那一步根本没成功：

```bash
ls ~/Vocawiki-bots/bots/vocaloid_collection_contributions.py
```

没有就先 clone，再 `./deploy/toolforge/preflight.sh` 复核：

```bash
git clone https://github.com/TimeRen/Vocawiki-bots.git ~/Vocawiki-bots
```

### 干跑日志里没有 `已登录：Renjian-bot`

正常。`--dry-run` 不登录（`run_once()` 只在 `--write` 时才 `ensure_login()`），
它只验证链路能不能跑通。要确认凭据，去掉 `--dry-run` 再跑一次（见第 5 步）。

### 日志开头有一句 `./deploy/toolforge/...: not found`

日志文件是**跨次运行追加**的，那句话是之前用错路径那次的残留。重新跑一次看
文件末尾，或先删掉再跑：

```bash
rm -f ~/dryrun.out ~/dryrun.err
```

### job 显示 `completed` 但 `工具名.out` 是空的

pywikibot 的 `output()` 写 **stderr**，而 Toolforge 的 `filelog-stdout` 只收
stdout，所以内容全在 `工具名.err` 里。entry 脚本现在用 `2>&1` 合并了，但如果你
在用旧版脚本（没 `git pull`），直接看另一个文件：

```bash
tail ~/dryrun.out        # 可能是空的
tail ~/dryrun.err        # 真正的内容在这里
```

### job 报 `exitcode 127`（Status: Failed for 3s）

命令找不到。job 的工作目录是**工具 home**，不是仓库目录，所以
`--command "./deploy/toolforge/run-once.sh"` 找不到文件。要带上仓库那一层：

```bash
toolforge jobs run dryrun --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run"
```

同样的原因也适用于 `jobs.yaml` 里的 `command`（已写成 `./Vocawiki-bots/...`）。
先看错误日志确认：

```bash
cat ~/dryrun.err
```

### `找不到仓库：/data/project/<tool>/Vocawiki-bots`

脚本找不到代码。要么没 clone，要么 clone 到了个人 home：

```bash
ls ~/Vocawiki-bots/bots/vocaloid_collection_contributions.py
git clone https://github.com/TimeRen/Vocawiki-bots.git ~/Vocawiki-bots
```

### `找不到 venv：/data/project/<tool>/pyvenv/bin/python`

重跑第 4 步的 `bootstrap-venv`。

### `bad interpreter: No such file or directory`

脚本带了 Windows 的 CRLF。仓库里 `.gitattributes` 已经强制 `*.sh` 用 LF，
但如果是在 Windows 上改完再拷上去的，在服务器上修一下：

```bash
sed -i 's/\r$//' deploy/toolforge/*.sh
```

### `No module named 'pywikibot'`

venv 没建好或没被复用。job 里用的是 `$HOME/pyvenv/bin/python`，
重跑第 4 步的 `bootstrap-venv` 即可。
