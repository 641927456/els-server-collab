"""本地发布通道解析（最小实现）。

`tools/launch_integrated_local.py` 启动前会调用 `local_release(BASE)` 解析当前应
使用的本地发布目录；返回的目录与本仓库相同时就地启动，不同则转到该目录执行。

本机只有这一个本地发布目录（仓库根），因此直接返回 base。
若以后存在 `channels/` 下的独立发布目录，可在这里按需扩展解析规则。
"""
from __future__ import annotations

from pathlib import Path


def local_release(base):
    """返回应当作为本地启动根的目录。"""
    base = Path(base).resolve()
    return base
