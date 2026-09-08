#!/bin/zsh
# =============================================================================
#  Da-image Studio Pack - SubTools 启动器（macOS 双击版）
#  说明：
#    1. 把本文件与 subs_gui.py 放在同一个目录
#    2. 本文件可以移动到 / 桌面 / 任意文件夹 / 软链接到别处
#    3. 双击即可启动 SubTools GUI，无需手动 cd 到某个目录
#
#  首次使用：如果双击提示「无法打开」，先在终端运行一次：
#      chmod +x "/路径/到/SubTools启动.command"
#  或：右键 → 打开 → 允许。
# =============================================================================

# ---------- 1. 定位 launcher 自身所在目录（支持软链接、任意位置） ----------
#    $0 指向本 .command 文件；用 `readlink -f` 递归解析符号链接到绝对路径
SELF="${(%):-%x}"                   # zsh 下更可靠：得到当前脚本的真实路径
if [[ -z "$SELF" || ! -e "$SELF" ]]; then
  SELF="$0"
fi
# 解析软链接到真实文件路径（兼容 alias / 替身）
while [[ -L "$SELF" ]]; do
  TGT="$(readlink "$SELF")"
  if [[ "$TGT" = /* ]]; then
    SELF="$TGT"
  else
    SELF="$(cd "$(dirname "$SELF")" && pwd)/$TGT"
  fi
done
SCRIPT_DIR="$(cd "$(dirname "$SELF")" && pwd)"

# ---------- 2. GUI 脚本路径（必须与本 launcher 同目录或父目录有 subs.py） ----------
GUI_SCRIPT="$SCRIPT_DIR/subs_gui.py"

if [[ ! -f "$GUI_SCRIPT" ]]; then
  osascript -e "display dialog \"找不到 subs_gui.py\\n\\n请把本启动器与 subs_gui.py 放在同一个目录，然后再次双击。\" buttons {\"好\"} default button 1 with title \"SubTools 启动失败\" with icon stop" >/dev/null 2>&1
  echo "❌ 找不到 GUI 脚本：$GUI_SCRIPT"
  echo "   请把 SubTools启动.command 与 subs_gui.py 放在同一目录。"
  read -r -s -k $'?按回车键退出…' 2>/dev/null || read -r
  exit 1
fi

# ---------- 2b. 定位 subs.py（支持 SubTools/ 子目录发布 layout） ----------
#   - 如果 SCRIPT_DIR 里有 subs.py → 直接用它（正常布局）
#   - 如果 SCRIPT_DIR 父目录（或更高）里有 subs.py → 也加入 PYTHONPATH（发布子目录布局）
SUBS_DIR=""
_d="$SCRIPT_DIR"
while [[ -n "$_d" && "$_d" != "/" ]]; do
  if [[ -f "$_d/subs.py" ]]; then
    SUBS_DIR="$_d"
    break
  fi
  _d="$(dirname "$_d")"
done

if [[ -z "$SUBS_DIR" ]]; then
  # Hard error — no subs.py anywhere upward; this is fatal because from subs import will fail
  osascript -e "display dialog \"找不到核心引擎 subs.py。\\n\\n请确认：\\n• 启动器与 subs_gui.py 同目录\\n• subs.py 与它们同目录，或在它的上级目录中（例如 milestone 根目录）\" buttons {\"好\"} default button 1 with title \"SubTools 启动失败\" with icon stop" >/dev/null 2>&1
  echo "❌ 无法在 $SCRIPT_DIR 或其任何父目录中找到 subs.py。"
  echo "   subs.py 是匹配 & 导出核心引擎，必须存在。"
  read -r -s -k $'?按回车键退出…' 2>/dev/null || read -r
  exit 1
fi

# Shell 侧双保险：把 subs.py 所在目录注入 PYTHONPATH（即使 Python 端 bootstrap 漏了也能跑）
if [[ -n "$PYTHONPATH" ]]; then
  export PYTHONPATH="$SUBS_DIR:$SCRIPT_DIR:$PYTHONPATH"
else
  export PYTHONPATH="$SUBS_DIR:$SCRIPT_DIR"
fi

# ---------- 3. 选择 Python 解释器（兼容 python / python3 / pyenv / venv） ----------
PY=""
for cand in python3.14 python3.13 python3.12 python3.11 python3.10 python3 python; do
  if command -v "$cand" >/dev/null 2>&1; then
    # 验证这个 python 能跑 Tk（最小化测试，避免空 pyenv shell）
    if "$cand" -c "import tkinter" >/dev/null 2>&1; then
      PY="$cand"
      break
    fi
  fi
done

if [[ -z "$PY" ]]; then
  osascript -e "display dialog \"找不到可用的 Python（带 Tkinter）。\\n请确认已安装 Python 3（例如 python.org 安装包）。\" buttons {\"好\"} default button 1 with title \"SubTools 启动失败\" with icon stop" >/dev/null 2>&1
  echo "❌ 没有找到带 Tkinter 的 python3 / python。"
  read -r -s -k $'?按回车键退出…' 2>/dev/null || read -r
  exit 1
fi

# ---------- 4. 切换到脚本目录 → 启动 GUI ----------
#    虽然 subs_gui.py 自己已经有 sys.path 注入，这里 cd 一次作为双保险；
#    并且保证任何相对路径输入（例如文件选择器默认目录、临时文件）都行为一致。
cd "$SCRIPT_DIR" || {
  echo "❌ 无法进入目录：$SCRIPT_DIR"
  read -r -s -k $'?按回车键退出…' 2>/dev/null || read -r
  exit 1
}

echo "🚀 启动 SubTools …"
echo "   Launcher: $SELF"
echo "   SCRIPT_DIR : $SCRIPT_DIR"
echo "   SUBS_DIR   : $SUBS_DIR (核心引擎 subs.py 所在)"
echo "   GUI_SCRIPT : $GUI_SCRIPT"
echo "   Python     : $PY   ($(command -v "$PY"))"
echo "   PYTHONPATH : $PYTHONPATH"
echo "   (关闭窗口或 GUI 窗口即退出)"
echo "--------------------------------------------------------------------"

exec "$PY" "$GUI_SCRIPT"

# 理论上 exec 不会返回；下面仅为兜底
read -r -s -k $'?按回车键退出…' 2>/dev/null || read -r
