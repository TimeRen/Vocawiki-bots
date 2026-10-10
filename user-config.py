import os

family_files['library'] = 'https://library.moegirl.org.cn/api.php'
# change this to zh/mzh
family_files['voca'] = 'https://voca.wiki/api.php'
family_files['commons'] = 'https://commons.moegirl.org.cn/api.php'
family_files['en'] = 'https://en.moegirl.org.cn/api.php'
# 萌娘百科主站（官方站）：family 'zh'，即 pywikibot.Site('zh', 'zh')。
# 官方站对匿名调用只放行 prop=info / titles= 这类模块：prop=revisions 回
# action-notallowed，连 pywikibot 探测模块参数的 action=paraminfo 也被挡
# （实测 2026-10-10），pywikibot 自己的登录流程因此走不通。机器人的萌百查询走
# HTTP，账号与机器人密码都从 user-password.py 读：
#     ('zh', 'zh', '账号', BotPassword('后缀', '机器人密码'))
# 本文件（会提交到仓库）不填 usernames['zh']。见 vocaloid_collection_contributions.py
# 的 MOEGIRL_OFFICIAL 与 deploy/toolforge/README.md。
family_files['zh'] = 'https://zh.moegirl.org.cn/api.php'
family_files['mirror'] = 'https://moegirl.uk/api.php'
family_files['icu'] = 'https://moegirl.icu/api.php'
family_files['icu_cm'] = 'https://commons.moegirl.icu/api.php'
mylang = 'voca'
family = 'voca'

usernames['mirror']['*'] = 'Lihb'
usernames['*']['*'] = 'LihaohongBot'
# voca.wiki 的机器人账号；可用环境变量 VOCA_USERNAME 覆盖（CI 用 secret VOCA_USERNAME）
usernames['voca']['*'] = os.environ.get('VOCA_USERNAME') or 'Renjian-bot'
password_file = "user-password.py"

# increase if WAF is frequently encountered
minthrottle = 0
# keep the next two for non-bots
maxthrottle = 20
put_throttle = 20

noisysleep = 1

user_agent_format = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
