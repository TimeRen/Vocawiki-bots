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
toolforge jobs run bootstrap-venv --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/bootstrap_venv.sh"
```

（可执行位已经提交在仓库里，不需要再 `chmod +x`；见排错里那条
「would be overwritten by merge」。）

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

## 6. 载入每小时定时任务

```bash
toolforge jobs delete watcher   # 如果之前部署过旧版常驻 watcher
toolforge jobs load ~/Vocawiki-bots/deploy/toolforge/jobs.yaml
```

会创建或更新 `hourly` 任务：

| job | 类型 | 作用 |
| --- | --- | --- |
| `hourly` | schedule（每小时 :17） | 单次完整维护榜单、计数、颜色、报告和统计图；不常驻轮询 |

GitHub Actions 也会在每小时 :47 跑一次完整维护，作为错时的备份。完整扫描而不是
依赖 `recentchanges`，因此即使条目尚未出现在当前列表中，也会由下一次定时任务发现。
Toolforge 的 `schedule` 任务在两次运行之间显示 `Pending` 是正常的。

需要临时整体跑一轮时，用一次性 job 即可（`run-once.sh` 就是为它留的）：

```bash
toolforge jobs run once --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh"
cat ~/once.out
```

## 7. 查看状态与日志

**先 `become <工具名>`**：`toolforge jobs` 只在工具账号下能用，在个人账号下会报
`Failed to load configuration, did you forget to run 'become <mytool>'?`。

```bash
toolforge jobs list
toolforge jobs show hourly
cat ~/hourly.out              # entry 脚本已把 stderr 合并进来
```

要停用定时任务，显式删除即可：

```bash
toolforge jobs delete hourly
```

`jobs.yaml` 里配了 `emails: onfailure`，所以任务失败时会给你发邮件。

查询「创建者」的规则：条目的创建者是页面**最旧一版**的作者。例外是跨站导入的
页面——voca 从萌娘百科导入时，那一版连作者和时间都抄的是**源站最后一版**的
（用户名写作 `zhmoe>某人`），照它算就会把源站最后一位编辑者当成创建者
（2026-10-10 的反馈）。所以这类条目改去源站查源条目自己的最旧一版：
`colour`、`counts`、`stats` 都走这条规则（见 `page_creator`），源站也查不到时
宁可不归属，也不拿导入者顶替。`moe` 报告会把这类首版标成「（萌百导入）」。

图表里已经被写进去的旧数字要靠一次性迁移搬正——图表只会把数字往上抬，
所以「减旧加新」不能每轮都做：

```bash
# 先干跑看 diff（259283 是我的改动落地前的那一版）
toolforge jobs run recredit --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run recredit --from-rev=259283"
# 确认无误后去掉 --dry-run 再跑一次
toolforge jobs run recredit --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh recredit --from-rev=259283"
cat ~/recredit.out
```

`--from-rev` 是**迁移基准**：老数字从那一版取，同一基准重复跑结果一致，
CI 与 Toolforge 各跑一次也不会翻倍。迁移完照常跑 `all`，会打印「页面无需更新」。

## 8. 萌娘百科交叉比对报告（可选，手动）

贡献列表记的是「萌娘百科及 Vocawiki 上」的创建：页面上标的创建者（格子颜色/图例）
与本机页面的首版作者有时不是同一个人。`moe` 动作会去萌娘百科查同名条目的最旧一版
作者，供人工判断——它**只出报告，不上色、不改数字**，也不在每小时任务里跑：

```bash
toolforge jobs run moereport --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh --dry-run moe"
cat ~/moereport.out
```

报告分三类：`标注与 voca 首版作者不符`、`voca 首版作者是机器人/导入账号`、
`voca 还没有页面（红链）`，末尾列出「若照萌娘结果归属，各创建者会得到多少」。
红链里在萌娘也没有同名条目的只报数量，不逐条列出。
结果缓存在 `data/vocaloid_collection_moegirl.pickle`（7 天有效期），同一条重复跑
不会再把萌娘 API 敲一遍。萌娘是别人的 wiki，别把它加进 `hourly` 或
`run-once.sh` 的默认 `all`。

查的是**镜像站** `moegirl.icu`：官方 `zh.moegirl.org.cn` 要登录才给用
`prop=revisions`/`list=search`（匿名直接回 `action-notallowed / Unauthorized API
call`，连 pywikibot 探测模块参数的 `action=paraminfo` 都挡），而且官方站慢得多，
这份报告要问上千条，所以只问镜像。镜像的 pageid 与官方一致、历史也完整
（`moegirl.uk` 就不行，它的历史是后来导入的，最旧一版是镜像自己的搬运账号）。

**镜像有个盲点**：它抓的是匿名可见的版本，萌百「待审核」的条目在它那儿根本不存在，
于是被当成「没有同名条目」。所以每小时任务解析导入条目的真创建者时，镜像找不到
会再去**官方站**确认一次：先按 voca 的标题（含标点变体）找，对不上时用导入版记的
「源站那一版作者 + 时间戳」反查源条目名（voca 常把条目改成自己的消歧写法——
`Flare(PedestrianP)` 在萌百叫 `Flare(初音未来)`；时间戳要完全一致才认）。

官方站要机器人密码。密码文件在工具账号的 `~/Vocawiki-bots/user-password.py`
（仓库里没有，`.gitignore` 挡着），加一条：

```python
('zh', 'zh', '你的账号', BotPassword('后缀', '机器人密码'))
```

`user-config.py`（会提交到仓库）**不填** `usernames['zh']`——账号不进公开仓库，
`bots/vocaloid_collection_contributions.py` 直接从上面这个文件读。GitHub Actions
那边要把这一条也加进 secret `USER_PASSWORD_PY`，CI 才有官方站可用；否则两边都退回
镜像（行为跟以前一样，这些条目继续不归属）。

官方站的结论缓存在同一个 `data/vocaloid_collection_moegirl.pickle` 里，多存一位
来源（`icu` / `zh`）：官方站说「没有」才算定论，7 天内不再问。它握手超时很常见
（实测重试一两次就能过），所以每条最多试 `MOEGIRL_OFFICIAL_ATTEMPTS` 次，登录失败
也只影响这一轮——问不到就保持「未知」，不会把「没问到」写成「没有」。

每小时任务也会查镜像：跨站导入的条目要靠它找真正的创建者（见上一节），查到的
结果同样缓存在 `data/vocaloid_collection_moegirl.pickle`。镜像不是自己的 wiki，
请保持 `MOEGIRL_DELAY` 这层限速，别把间隔调没。

## 更新代码

**先 `become <工具名>`**（同第 7 节）：`~/Vocawiki-bots` 和 `toolforge jobs` 都只
存在于工具账号里。在个人账号下 `cd ~/Vocawiki-bots` 会直接报
`No such file or directory`（那里的 `~` 是你的个人 home），`toolforge jobs` 也会
因为找不到工具账号的 kubeconfig 而失败。

```bash
cd ~/Vocawiki-bots && git pull
toolforge jobs load deploy/toolforge/jobs.yaml
```

如果 `git pull` 报 `Your local changes ... would be overwritten by merge`，看一眼
改动是什么：

```bash
git diff --stat
git diff                         # 只有 "old mode 100644 / new mode 100755" 就放心丢
git checkout -- deploy/toolforge/          # 整个目录一起丢，别只丢报错点名的那两个
git pull
```

那是早前 `chmod +x` 造成的**权限位**改动（仓库里已经带可执行位了，不再需要
手动改）。丢掉它不会有损失；`git pull` 之后脚本仍然是可执行的。

想彻底不再被权限位挡住，可以让这个 clone 忽略它（只影响本地）：

```bash
git config core.fileMode false
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
- GitHub Actions 在每小时 :47 运行；Toolforge 在 :17 运行。两边均单次完整扫描，
  不依赖 `recentchanges` 增量列表，也不会常驻轮询。
- 若部署在普通 Linux 主机而非 Toolforge，可用 `deploy/voca-contributions.service`
  与 `deploy/voca-contributions.timer` 配对；启用 timer，不要再用常驻重启服务。

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

### 定时 job 显示失败

先看任务日志；更新代码或 `jobs.yaml` 后重新载入定义：

```bash
tail -50 ~/hourly.err           # 旧脚本没合并流时错误在这
toolforge jobs load ~/Vocawiki-bots/deploy/toolforge/jobs.yaml
toolforge jobs list
```

如果旧版 `watcher` 仍存在，需先执行 `toolforge jobs delete watcher`，否则它会继续常驻。

### job 显示 `completed` 但 `工具名.out` 是空的

pywikibot 的 `output()` 写 **stderr**，而 Toolforge 的 `filelog-stdout` 只收
stdout，所以内容全在 `工具名.err` 里。entry 脚本现在用 `2>&1` 合并了，但如果你
在用旧版脚本（没 `git pull`），直接看另一个文件：

```bash
tail ~/dryrun.out        # 可能是空的
tail ~/dryrun.err        # 真正的内容在这里
```

### `git pull` 报 `Your local changes ... would be overwritten by merge`

本地对同一批文件有改动，Git 拒绝覆盖。最常见的是**权限位**：早前按旧说明跑了
`chmod +x deploy/toolforge/*.sh`，而仓库里这些脚本当时是 644，于是产生改动。

```bash
git diff --stat
git diff                                  # 确认只有 old mode 100644 / new mode 100755
git checkout -- deploy/toolforge/          # 整个目录一起丢：chmod +x 是批量加的
git pull
git config core.fileMode false             # 可选：以后忽略权限位改动
```

仓库现在已带可执行位（100755），不需要再 `chmod +x`，也就不会再撞上这个。
**`git pull` 失败时不要直接 `toolforge jobs load`**：那会用旧的 `jobs.yaml`
（路径是 `./deploy/...`）重建 job，于是又回到 `exitcode 127`。

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
