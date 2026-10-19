"""Compatibility import; implementation lives in els_server.domain.skill_state."""
import importlib
import sys
sys.modules[__name__] = importlib.import_module('els_server.domain.skill_state')
