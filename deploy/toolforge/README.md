# 部署到 Toolforge

前提：已有 Toolforge 成员资格，且能用 SSH 登录 `login.toolforge.org`
（见 [Help:Toolforge/Quickstart](https://wikitech.wikimedia.org/wiki/Help:Toolforge/Quickstart)）。

登录成功只说明密钥配好了，机器人还一步都没跑。下面是把 bot 跑起来的完整流程。

## 1. 建工具账号

在 https://toolsadmin.wikimedia.org/tools/ 点 **Create new tool**，起个名字
（比如 `vocawiki-contrib`，别用大写和点）。建完要**退出 SSH 再重新登录**，
新增的工具组才会生效。

## 2. 进入工具账号并取代码

```bash
ssh <你的shell用户名>@login.toolforge.org
become vocawiki-contrib          # 提示符变成 tools.vocawiki-contrib@...
git clone https://github.com/TimeRen/Vocawiki-bots.git ~/Vocawiki-bots
cd ~/Vocawiki-bots
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

## 4. 建 venv（必须在 job 容器里做）

跳板机没有编译环境，装不了 wheel，所以用一次性 job 引导：

```bash
chmod +x deploy/toolforge/*.sh
toolforge jobs run bootstrap-venv \
  --command "cd $PWD && ./deploy/toolforge/bootstrap_venv.sh" \
  --image python3.13 --wait
```

结束时会打印 `pywikibot <版本> on Python 3.x`。容器里的 `$HOME` 就是工具的
`/data/project/<tool>`，所以 `pyvenv` 建在共享存储上，后续 job 直接复用。

## 5. 先干跑一次确认能登录

不要直接在跳板机上跑 python（那是登录节点，不是跑负载的地方），用一次性 job：

```bash
toolforge jobs run dryrun --image python3.13 --wait \
  --command "./deploy/toolforge/run-once.sh --dry-run"
tail ~/dryrun.out
```

日志里应出现 `已登录：Renjian-bot`。确认没问题再往下走；去掉 `--dry-run`
就是正式写入。

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
tail -f ~/watcher.out        # 或 jobs.yaml 里 filelog-stdout 指定的路径
```

## 更新代码

```bash
cd ~/Vocawiki-bots && git pull
toolforge jobs restart watcher   # 常驻 job 不会自动重载代码
```

## 注意

- 改了 `jobs.yaml` 后重新 `toolforge jobs load`；同名 job 定义有变化会被替换。
- 新增依赖时重跑第 4 步的引导脚本（会重建 venv）。
- `data/` 是创建者缓存，会随仓库目录一起留在共享存储上，别删（删了只是变慢）。
- 想用环境变量传密钥可以用 `toolforge envvars`，但本仓库读的是
  `user-password.py`，两种方式选一种即可。
