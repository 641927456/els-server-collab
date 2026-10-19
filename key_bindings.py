"""Compatibility import; implementation lives in els_server.domain.key_bindings."""
import importlib
import sys
sys.modules[__name__] = importlib.import_module('els_server.domain.key_bindings')
