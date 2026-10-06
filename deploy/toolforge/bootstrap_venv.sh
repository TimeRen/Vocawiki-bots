#!/bin/bash
# 在工具 home 里建好 venv 并装 pywikibot。
#
# 必须在 job 容器里跑：跳板机（bastion）没有编译环境，装不了 wheel；
# 容器里的 $HOME 就是工具的 /data/project/<tool>，所以 venv 会落在共享存储上，
# 后续所有 job 直接复用。
#
#   toolforge jobs run bootstrap-venv \
#     --command "cd $PWD && ./deploy/toolforge/bootstrap_venv.sh" \
#     --image python3.13 --wait
set -euo pipefail

cd "$HOME"

rm -rf pyvenv
python3 -m venv pyvenv
source pyvenv/bin/activate
pip install --disable-pip-version-check -U pip wheel
pip install --disable-pip-version-check pywikibot

python -c "import pywikibot, sys; print('pywikibot', pywikibot.__version__, 'on Python', sys.version.split()[0])"
