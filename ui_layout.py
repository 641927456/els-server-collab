"""Compatibility import; implementation lives in els_server.domain.ui_layout."""
import importlib
import sys
sys.modules[__name__] = importlib.import_module('els_server.domain.ui_layout')
