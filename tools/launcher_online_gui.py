"""在线 GM 启动器入口（根目录「艾尔之光在线启动器.pyw」按此路径加载）。

历史原因与 tools/launcher_gui.py 相同：根目录引导壳按
`els-server-collab/tools/launcher_online_gui.py` 的 `main()` 找界面。
界面实现在 `launcher_online/` 包（`python -m launcher_online`）。

界面容器优先用 Edge/Chrome 的 --app 窗口（--browser-app），因为便携运行时里
没有 pywebview/pythonnet 时，原生无边框窗口不可用。
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]  # 仓库根目录
CLIENT_NAME = 'x2_dx11.exe'


def find_client() -> Path:
    """定位客户端 x2_dx11.exe：环境变量 > 仓库同级 data > 仓库内 data。"""
    explicit = os.environ.get('ELS_SHARE_CLIENT')
    if explicit:
        candidate = Path(explicit)
        if candidate.is_file():
            return candidate.resolve()

    for base in (ROOT.parent, ROOT, ROOT / 'client'):
        candidate = base / 'data' / CLIENT_NAME
        if candidate.is_file():
            return candidate.resolve()
        candidate = base / CLIENT_NAME
        if candidate.is_file():
            return candidate.resolve()

    for candidate in ROOT.parent.rglob(CLIENT_NAME):
        return candidate.resolve()

    raise SystemExit(
        '找不到客户端 %s。\n请确认它位于仓库同级的 data 目录，例如：\n  %s'
        % (CLIENT_NAME, ROOT.parent / 'data' / CLIENT_NAME)
    )


def interpreter() -> Path:
    """优先用同目录的 pythonw.exe，避免弹控制台。"""
    current = Path(sys.executable)
    if current.name.lower() == 'python.exe':
        candidate = current.with_name('pythonw.exe')
        if candidate.is_file():
            return candidate
    return current


def main() -> int:
    client = find_client()
    env = dict(os.environ)
    env['ELS_SHARE_CLIENT'] = str(client)
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    env.setdefault('PYTHONPATH', str(ROOT))

    args = [str(interpreter()), '-m', 'launcher_online', '--browser-app']
    creation = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
    return subprocess.run(args, cwd=str(ROOT), env=env, creationflags=creation).returncode


if __name__ == '__main__':
    raise SystemExit(main())
