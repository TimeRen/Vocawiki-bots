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

## 6. 载入定时任务

```bash
toolforge jobs delete watcher   # 如果之前部署过旧版常驻 watcher
toolforge jobs load ~/Vocawiki-bots/deploy/toolforge/jobs.yaml
```

会创建或更新 `hourly` / `lyrics-plan` / `contributions` / `translations` 四个任务：

| job | 类型 | 作用 |
| --- | --- | --- |
| `hourly` | schedule（每小时 :17） | 单次完整维护榜单、计数、颜色、报告和统计图；不常驻轮询 |
| `lyrics-plan` | schedule（每天 04:23 UTC） | 比对 AtWiki 歌词页与 voca.wiki 条目，维护「VOCALOID中文歌词wiki补完计划」清单（见第 9 节） |
| `contributions` | schedule（每小时 :53） | 维护贡献页 [[User:人间百态/贡献]]：补新条目、去掉重定向 / 消歧义页，歌姬模板只留主模板（见第 10 节） |
| `translations` | schedule（每天 06:37 UTC） | 填充 [[User:周某不是轴某/VOCALOID collection搜集库]] 的「翻译来源」（只填空格，见第 12 节） |

**四个任务都有 GitHub Actions 兜底**（Toolforge 故障时顶上），详见第 11 节：

| Toolforge | GitHub Actions | 错开的方式 |
| --- | --- | --- |
| `hourly`（每小时 :17） | `update-vocaloid-collection.yml`（每小时 :47） | 差 30 分钟 |
| `contributions`（每小时 :53） | `update-contributions.yml`（每小时 :23） | 差 30 分钟 |
| `lyrics-plan`（每天 04:23） | `update-lyrics-completion.yml`（每天 05:13） | 差 50 分钟 |

GitHub Actions 跑的也是同一份脚本；两处同时在一轮里相遇时靠编辑冲突（`baserevid`）
让后到的那次放弃，不会互相覆盖。Toolforge 的 `schedule` 任务在两次运行之间显示
`Pending` 是正常的。

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
（2026-10-10 的反馈）。还有一类导入干脆不写前缀：首版作者就是**搬运者本人**，
来源只留在编辑摘要里（`搬运自萌娘百科…(by. [[zhmoe:User:某人]])`，2026夏 的
`秘书室` 就是 Zhoumou 这样建的），`is_import_note` 认这种摘要。两类条目都改去
源站查源条目自己的最旧一版：`colour`、`counts`、`stats` 都走这条规则
（见 `page_creator`），源站也查不到时宁可不归属，也不拿导入者顶替。
`moe` 报告会把这类首版标成「（萌百导入）」。

哪些曲目计入统计（`is_counted_track`）：REMIX 赛道不算；二创也不算，但判断看曲目
本身——标题写着 `原曲/创作者` 或 `…＃二次创作` 的直接排除，标题看不出来的读页面
正文（自称翻唱/歌ってみた/二创的就是二创，见 `is_derivative`，结果缓存在
`data/vocaloid_collection_derivatives.pickle`）。**「其他部门」这类分组不能按组名
一刀切**：里面既有本季原创曲（Exhibition 这类不排名模块都收在这一组），也有翻唱
（2025夏 的 `魔法(Murata Shiyuu)` 是原创曲、`少女A/Iyowa` 是翻唱）。2026-10-10
之前整组被当成二创排掉，作者们的数字因此少了一块。

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

已经迁移过的账不能再减一遍（旧账在基准版里早就改好了），所以补做后来才发现的那
一类时，加 `--kinds` 只挑那一类：

```bash
# 只处理「首版摘要里写着搬运者、账号却是搬运者本人」的导入（2026-10-10 发现的）
toolforge jobs run recredit --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-once.sh recredit --from-rev=259438 --kinds=note"
```

`--kinds=prefix` 是首版用户名带 `zhmoe>` 前缀的那种（第一次迁移处理的就是它），
`--kinds=note` 是摘要里点名源站用户的那种，不给就两类都算。

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
那边要把这一条也加进 secret `USER_PASSWORD_PY`。

**但云 IP 登录不上**：2026-10-10 实测，从 Toolforge（Wikimedia 云 IP）发
`action=login` 会被回 `Incorrect username or password entered. Please try again.`
——同一组凭据在本机（住宅网络）是能登进去的（日志会打出对面这句话，看到它就说明
不是密码写错）。所以云上的跑法基本取不到官方站，代码里因此留了一张核对表
`MOEGIRL_FALLBACK`：只在这 25 条「镜像没有、官方站又问不到」的条目上用**查实过
的**结论兜底（表里有它们对应的萌百源条目名与创建者），在线结果永远优先。等哪天云
上也能登录，把那张表删掉即可。表少一条，那一条在云上就会被算成「无归属」，重算图
表时那个数字（连同该减掉的二创）往下走，而本机能登官方站的一轮又把它抬回去，于是
同一位用户的同一格在 1/2 之间反复——改表时务必对照 `moe` 报告里「官方站才查得到」
的那批条目补齐。

官方站的结论缓存在同一个 `data/vocaloid_collection_moegirl.pickle` 里，多存一位
来源（`icu` / `zh` / `table`）：官方站说「没有」才算定论，7 天内不再问。它握手
超时很常见（实测重试一两次就能过），所以每条最多试 `MOEGIRL_OFFICIAL_ATTEMPTS`
次，登录失败也只影响这一轮——问不到就保持「未知」，不会把「没问到」写成「没有」。

每小时任务也会查镜像：跨站导入的条目要靠它找真正的创建者（见上一节），查到的
结果同样缓存在 `data/vocaloid_collection_moegirl.pickle`。镜像不是自己的 wiki，
请保持 `MOEGIRL_DELAY` 这层限速，别把间隔调没。

## 9. VOCALOID中文歌词wiki 补完计划（每天）

`bots/vocaloid_lyrics_completion.py` 维护
[[User:人间百态/VOCALOID中文歌词wiki补完计划]]：Vocaloid 中文歌词wiki
（`w.atwiki.jp/vocaloidchly`）里**还没有** voca.wiki 条目的歌曲页面清单。
`jobs.yaml` 里的 `lyrics-plan` 每天 04:23（UTC）跑一次，也可以手动跑：

```bash
toolforge jobs run lyrics --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-lyrics-completion.sh --dry-run"
cat ~/lyrics.out
```

比对的三条规则：

* **来源**：AtWiki 的「全ページ一覧」（`/list?sort=pagename`，100 条一页，约 86 页）。
  按页面名排序而不是按更新时间，否则抓取过程中更新的页面会漏页 / 重页。
* **对应**：voca.wiki 上所有带 `{{VOCALOID Songbox}}` 的条目，比对名有三种——条目
  标题、条目的全部重定向、Songbox 的 `|歌曲名称=`（`{{lj|…}}` 里的日文名与中文名）。
  AtWiki 页面名是日文、voca 条目标题多是简中，只比标题会把「千本桜」
  （条目标题 `千本樱`）、「卑怯戦隊うろたんだー！」（条目标题 `卑怯战队UROTANDA`）
  当成还没建，其实两者都是条目的重定向。歌名结尾的 `！` / `?` 各站写法不一
  （AtWiki 写「卑怯戦隊うろたんだー！」，条目的重定向只写「卑怯戦隊うろたんだー」），
  所以精确比对落空后还会再去掉**结尾**标点比一次；名字中间的标点不动，
  否则「14」与「1/4」会被并成一条。
* **消歧义页**：正文去掉链接后几乎没有文字（`pages/667`「Alice in Dreamland」
  就只有两个链接），或页面上写着「消歧義頁」的，都不是歌曲，不进清单。
  导航 / 目录 / 站务 / 测试页同理（`歌名な行`、`初音ミク` 这种索引页也靠这条排掉）。

缓存都在 `data/` 下：`..._pages.pickle`（AtWiki 清单）、`..._index.pickle`
（voca 歌名索引）、`..._verdicts.pickle`（逐页判定）。清单与索引默认 12 小时有效，
判定 30 天后重核。**第一次跑**要把还没对应的几千个 AtWiki 页面逐个抓一遍，慢几分钟；
之后每轮只补新页面。抓不到的页面不会写进判定缓存，下一轮接着试（宁可多留一条，
也不会因为一次网络失败把页面从清单里删掉）。

## 10. 贡献页（每小时）

`bots/user_contributions_navbox.py` 维护 [[User:人间百态/贡献]]（[[User:人间百态]]
上那个导航框）。`jobs.yaml` 里的 `contributions` 每小时 :53（UTC）跑一次：

```bash
toolforge jobs run contributions --image python3.13 --wait \
  --command "./Vocawiki-bots/deploy/toolforge/run-contributions.sh --dry-run"
cat ~/contributions.out
```

规则：

* **Vocawiki时期**：用 `list=usercontribs&ucshow=new` 取这个账号建过的页面，注释以
  「由 Vocawiki条目辅助工具 创建」开头（不含「同名条目消歧义」）的就是歌曲条目，
  已经在清单里的按标题跳过，新的接在末尾、每组 10 条重新编号。
  标题末尾带括号消歧后缀的（`希望(Dopamine)`、`Redial(鹤三)`）写成
  `希望(Dopamine){{!}}希望` 这样**只显示括号前的歌名**，与页面上原有的写法一致。
  清单里已有的条目也复核一遍：**重定向**改写成它的目标页（目标已在清单里就直接去掉；
  目标查不到时保留原条目，不凭空删），**消歧义页**直接去掉。
  判定消歧义页只认 `Category:消歧义页` 或 `{{消歧义页}}` / `{{Disambig}}` 本身 ——
  带「消歧」二字的**维护**分类（`消歧义模板链入页面错误` / `消歧义模板链入页面不存在`，
  正文用 `{{About}}` 指向消歧义页时自动加）不算，那是「条目用错了模板」，
  页面仍是正常条目（2026-10-21 `涅槃(HotaRu)` 就是被旧规则误删的）。
* **歌姬模板**：只取 `…创建：歌姬模板` 的**主模板**——`Template:IA/2026`、`Template:歌爱雪/2011`
  这类按年份拆开的子页面归到 `Template:IA`、`Template:歌爱雪`，子模板本身不列。
* 补回来的旧条目按**创建时间**插回原位（清单是按创建顺序编号的），不会排到最末尾。
* 萌百时期、列表、职人模板等其余分组原样不动；内容没变就不保存。

## 11. GitHub Actions 兜底（Toolforge 故障时）

每个机器人各有一份 GitHub Actions 工作流，跑的是同一份脚本，只是时间错开：

| 工作流 | 对应 Toolforge 任务 | 运行时间 |
| --- | --- | --- |
| `.github/workflows/update-vocaloid-collection.yml` | `hourly` | 每小时 :47（Toolforge :17） |
| `.github/workflows/update-contributions.yml` | `contributions` | 每小时 :23（Toolforge :53） |
| `.github/workflows/update-lyrics-completion.yml` | `lyrics-plan` | 每天 05:13（Toolforge 04:23） |
| `.github/workflows/update-collection-translations.yml` | `translations` | 每天 06:43（Toolforge 06:37） |

**唯一的前置条件**是本仓库 Settings > Secrets and variables > Actions 里的
`USER_PASSWORD_PY`（四个工作流共用，写法见工作流文件顶部的注释）；`VOCA_USERNAME`
可选。

Toolforge 挂掉时不用做任何事，他们照常按上表运行。想立刻手动跑一轮：Actions 页面
选中工作流点 **Run workflow**，或用外部心跳（`repository_dispatch`，事件名分别是
`update-vocaloid-collection` / `update-contributions` / `update-lyrics-completion` /
`update-collection-translations`）。

两点差别要知道：

* `update-lyrics-completion.yml` 用 `actions/cache` 保存 `data/`（AtWiki 页面清单、
  voca 歌名索引、逐页判定），并以 `--max-age 90000`（25 小时）复用。实测（2026-10-21，
  冷缓存、GitHub runner）：清单 23 秒、歌名索引 2.5 分钟、逐页判定 3.4 分钟，
  一轮约 6.5 分钟；工作流给了 60 分钟超时作余量。Toolforge 上同一轮要慢得多
  （它的出口到 AtWiki 约 2～3 秒/页）。
  `update-collection-translations.yml` 同理，缓存的是逐首查询结果（见第 12 节）；
  丢了缓存只会慢，不会写错（查不到来源的格子保持空白）。
* GitHub Actions runner 是公网 IP，AtWiki 可能给它 Cloudflare 挑战。挑战页会被判成
  「读不到正文」，机器人对读不到的页面一律**保留**（不删清单条目），清单页本身也
  不会因为抓不到来源而被刷空（`collect_pages` 会直接放弃本轮）——只会少更新，不会写坏。

Toolforge 恢复后如果想停掉某一路，删掉对应工作流里的 `schedule` 触发器（保留
`workflow_dispatch`）即可；反之同理。

## 12. VOCALOID collection 搜集库的「翻译来源」（每天）

> **状态（2026-10-22）**：定时任务已恢复（Toolforge 06:37、GitHub Actions 06:43）。
> 中间短暂停过一阵：自动写的前几版都查错了 P主（同名不同曲），页面主人把那些编辑
> 整笔回退了（274554 / 274591 / 274593）；修好「每个来源都核对 P主」「只认自己写过
> 的格子」之后重新开起来。

`bots/vocaloid_collection_translations.py` 填
[[User:周某不是轴某/VOCALOID collection搜集库]] 表格里的「翻译来源」一栏，
并顺带维护它（每次都是重新读页面、按当前内容算 diff 再保存）。

**只填空白格**：别人已经写过的格子一个字都不动，所以可以和页面主人手工编辑共存。
每首歌按可靠程度依次查四个来源，最多记 3 条：

| 来源 | 判定方式 | 说明 |
| --- | --- | --- |
| ~~VOCALOID中文歌词wiki~~ | **暂停**（`USE_ATWIKI = False`）：2026-10-22 页面主人看到 4 笔同名不同曲后要求「暂时不收录中文歌词wiki」 | 恢复时还要过「投稿年 = 赛季年」那一关，见下 |
| 网易云音乐 | 歌名（含 `alias` / `transNames`）对上**且** P主 出现在歌手 / 专辑名里，`tlyric` 非空 | 只有歌名对上一定不够（见下）；署名取译文上传者 `transUser` |
| B站 | 条目里的 `{{BilibiliVideo}}` 优先，否则关键词搜索；搜来的视频要标题 / 简介里**同时**有歌名和 P主 | 读视频简介、评论区、弹幕里的「`翻译：某人`」+ 中文歌词；弹幕只在别的来源都空着时才读 |
| 巴哈姆特 | 顺着 B站简介里的外链进入 | 站内搜索是 JS 渲染的，抓不到结果页，只能这样发现 |

几点实现细节：

* **每个来源都要核对 P主**，只对歌名远远不够：
  * AtWiki：`Linaria` 那一页（p/7861）是 Mysteka 的、`EDEN`（p/6060）是 真尋P 的、
    `Reboot`（p/4993）是 ジミーサムP 的、`Redial`（p/5279）是 kz 的 —— 四条全错；
  * 网易云：`月之花` 被安上了 Daoko 的 `月の花`、`言灵` 被安上了 V.W.P 的 `言霊`
    （38 条里错 25 条）；
  * B站：`RITA` 记上了 TED 演讲的翻译视频、`亡灵` 记上了有声书、`潘多拉` 记上了
    玩法视频、`狂信者` 记上了黑执事 OP。
  ASCII 的 P主 按词边界比（`Hal` 不会匹配 `halcyon`）；P主 一栏空着就只查 B站弹幕
  之外的可靠来源。
* 署名（`credit_name`）只认**带冒号**的 `翻譯：` / `译者：` / `中文歌詞：` / `嵌字：`，
  并且长度 ≤ 20 字。首版不要求冒号，于是「词句是用**谷歌翻译成英文后根据英文翻译而来**」
  这种句子被当成了译者名（真实案例：`ensemble`）。
* 歌名归一化（`title_key`）会去掉 `{{lj|}}`、链接、注释、末尾的 `(消歧义后缀)`，
  但**不做**模糊匹配——同名不同曲宁可不记，也不能写错来源。
* 只改两种格子：空的，和自己写过的（内容与缓存里记过的 `sources` / `written` 逐字
  相同）。别人写过的格子一个字都不动，**哪怕格式和机器人一模一样**——页面主人也按
  `[链接 说明(by. 译者)]` 写，早先按「格式像机器人写的」认领，把他的
  `巴哈姆特(by. 月勳)`、`B站笔记(by. YUSI雨似)` 覆盖甚至清空了（2026-10-22）。
  缓存丢了就宁可少更新（宁可不认，也不越权）。
* 判定规则一改，把 `CACHE_VERSION` 加一，旧缓存自动作废重查。
* 逐首缓存（`data/vocaloid_collection_translations.pickle`，14 天）与 AtWiki 页面
  清单缓存（`…_atwiki.pickle`，7 天）。所以第一轮最慢（一百多首歌要逐首抓），
  之后每轮只查新出现的歌；`--refresh` 强制重查全部，`--ttl` 改缓存时长。
* 每轮限量：`--limit N` 只查 N 首（Toolforge 的 `translations` 任务和 GitHub Actions
  都固定带 `--limit 60`）。日志里 `待查 / 查了 / 改动` 三个数字就是进度；
  查不到的格子保持空白（中文原创曲本来就没有「翻译来源」可填），实测命中率约
  1/6——**宁可空着也不写错**。被 `--limit` 截住还没查的歌不进缓存，下一轮继续；
  查过但没找到的按 `--ttl` 过期后再查。GitHub runner 出口到 AtWiki / B 站都慢，
  不设上限时一轮容易跑到超时（实测冷缓存 55 分钟还没跑完），所以那边也限 60 首。

### 补录「外站有翻译、搜集库没录入」的曲目（`--add-missing`，随 AtWiki 一起暂停）

> **现状**：`USE_ATWIKI = False` 时不再补录新行（没有可核实的证据源，宁可不补）。
> 下面的实现留着，恢复 AtWiki 后自动生效；`--add-missing` 仍可传，会打印一行
> 「中文歌词wiki 已暂停收录：本轮不补录新行」。
>
> **但「删错行」不受暂停影响**：`drop_wrong_rows` 只做「证明它错」的核对（页面里
> 那支 niconico 视频的投稿年 ≠ 赛季年份），命中且这一行的 P主 正是那一页的 `作曲：`
> 时整行删掉（名次、曲名、P主、来源都是那次错配编出来的）；P主 对不上的只清「翻译来源」。
> 别人手写的行、查不到投稿日的行一律不动。


搜集库只收「外站已经有译文」的歌，所以每轮还会拿活动清单反查一次：

| 数据 | 来源 | 用途 |
| --- | --- | --- |
| 赛季 / 赛道 / 名次 / 曲名 / 是否已有条目 | [[Vocawiki:贡献列表/The VOCALOID Collection]] 的各赛季表格 | `[[曲名\|名次]]` = 还没条目，`{{colorlink\|#色\|曲名\|名次}}` = 已被谁创建 |
| 条目名 ↔ 日文原名 | `Template:The VOCALOID Collection2023春` 等 12 个大家族模板 | 拿日文原名才能和 AtWiki 页面名对上 |
| 译文与 P主 | AtWiki 页面（`作曲：`→P主，`翻譯：`→译者） | 唯一允许自动补录的证据 |

**补录的关卡**（只靠「页面名对上」不算——同名不同曲在歌词wiki 上到处都是）：

1. 这首歌必须出现在**本赛季**的大家族模板里（`navbox_titles`）；
2. 曲名必须是**日文原名**（含假名），或者带括号注记 —— 纯中文 / ASCII 曲名对上的
   多半是别的歌，而且模板里的 `[[Femme Fatale|femme fatale]]` 后半段只是显示文字，
   不能当日文名用；
3. 带括号注记时（`Colors(kouta)`、`月光(春风哈娜)`），AtWiki 的 `作曲：` 必须就是
   括号里那位；
4. **投稿年必须等于赛季年份**（`atwiki_year_ok`）：VCCL 只收新曲，而歌词wiki 上
   大量同名老曲。`死亡フラグ` 的 p/3460 是 コーチP 2011-05-14 的投稿（sm14446365），
   却被补进了 2022秋；同一批里 `PANDORA`（2010）、`リフレイン`（2011）、
   `Femme Fatale`（2011）也是这样。查不到投稿日就不补。`Remix` / `Cover` /
   `再解釈` 这类改曲条目的译文本来就挂在原曲页面上，不做这一项。

2026-10-22 的血泪账：首版只按页面名匹配，补的 10 行里 6 行是「同名不同曲」
（`Colors(kouta)`→骨盤P 的 Colors、`Libra(mira)`→Eon 的、`Yellow(shu)`→kz 的、
`Flashback(暖炉P)`→梅とら 的、`Life(kurara)`→アウトプットP 的、`月光(春风哈娜)`→
はるまきごはん 的）；加上第 2 条以后，`PANDORA` / `Femme Fatale` 也被撤回了
（它们只有同名，核对不了 P主）。两笔都整笔撤回过。第 4 条是最后一轮补齐的：
全量反查 15 首「本赛季模板里有、AtWiki 也有同名页」的候选，只有 `Cowgirl`
（2023春，投稿 2023-03-18）年份对得上，其余 14 首全是 2008–2017 年的同名老曲。

判定「已录入」有四种情况，任一命中就跳过：同赛道名次已存在、`{{注|N|总榜为第M}}`
里记过这个总榜名次（同一首歌用 ROOKIE 行录入过，不能再补一行 TOP100）、曲名在页面上、
贡献列表里已经标成「已创建」（有条目的歌不属于搜集库——2026-10-22 页面上「创建后就
手工删行」的做法就是这样）。

补进去的行按名次顺序插入对应赛季的表格，只写有内容的那一侧（另一侧留空，和页面上
空半边的行一致），`条目状态` 一律 `{{color=#FF0000|未创建}}`。每轮最多补 10 行
（`--max-add`），方便逐条 review。活动清单缓存 7 天（`data/vocaloid_collection_seasons.pickle`）。

```bash
python bots/vocaloid_collection_translations.py --add-missing            # 干跑，看会补哪些
python bots/vocaloid_collection_translations.py --write --add-missing --max-add 3
```

```bash
source ~/pyvenv/bin/activate
cd ~/Vocawiki-bots

# 干跑：只打印将要做的改动
python bots/vocaloid_collection_translations.py

# 小批量试跑，确认结果再放开
python bots/vocaloid_collection_translations.py --write --limit 20

# 正常情况下交给定时任务，手动一般不需要跑全量
python bots/vocaloid_collection_translations.py --write
```

`data/` 里的缓存别随手删：删了下一轮会把整页重查一遍（Toolforge 上要跑很久），
但不会写坏页面。

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

### `Unable to parse yaml file 'deploy/toolforge/jobs.yaml'`

先看是不是**路径**写错了：`toolforge jobs load` 是在**当前目录**找文件，站在工具
home（`~`）下写 `deploy/toolforge/jobs.yaml` 是找不到的，而它把「文件不存在」也报成
「无法解析 YAML」。先 `cd ~/Vocawiki-bots`，或者直接写全路径：

```bash
toolforge jobs load ~/Vocawiki-bots/deploy/toolforge/jobs.yaml
```

确认文件在、内容也正常：

```bash
ls -l ~/Vocawiki-bots/deploy/toolforge/jobs.yaml
grep -c "^- name:" ~/Vocawiki-bots/deploy/toolforge/jobs.yaml    # 现在应该是 3
```

### job 报 `exitcode 126`（Status: Failed for 3s）

和 `127` 不同：文件找到了，但**没有可执行位**（`-rw-r--r--` 而不是 `-rwxr-xr-x`），
shell 报 `Permission denied`。新加的 entry 脚本如果在 Windows 上提交，很容易漏掉
可执行位。仓库里修好并推上去之后，在工具账号里 `git pull` 就会带上权限：

```bash
git update-index --chmod=+x deploy/toolforge/run-once.sh   # 在本地仓库里做
git commit -m "Make the entry scripts executable" && git push
```

临时救急也可以直接在工具账号里 `chmod +x ~/Vocawiki-bots/deploy/toolforge/*.sh`。
核对记录下来的权限：

```bash
git ls-files -s deploy/toolforge/     # 应该是 100755，不是 100644
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
