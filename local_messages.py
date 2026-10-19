"""Compatibility import; implementation lives in els_server.protocol.local_messages."""
import importlib
import sys
sys.modules[__name__] = importlib.import_module('els_server.protocol.local_messages')
