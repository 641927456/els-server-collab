"""Verified owned-item use, independent of attendance/growth enrollment and switches."""
import threading
from pathlib import Path
_lock=threading.Lock()
_installed=False

def install():
    global _installed
    if _installed:return
    with _lock:
        if _installed:return
        from els_server.domain.published_2026_bundles import enable
        from els_server.domain.boosting_2026_force_rewards import register
        enable((Path(__file__).resolve().parents[1]/'data/published2026-bundles.json').read_bytes())
        register()
        from els_server.domain.boosting_2026_force_extraction import register as register_extraction
        register_extraction()
        _installed=True
