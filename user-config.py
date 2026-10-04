import os

family_files['library'] = 'https://library.moegirl.org.cn/api.php'
# change this to zh/mzh
family_files['voca'] = 'https://voca.wiki/api.php'
family_files['commons'] = 'https://commons.moegirl.org.cn/api.php'
family_files['en'] = 'https://en.moegirl.org.cn/api.php'
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
