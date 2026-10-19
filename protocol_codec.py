"""Compatibility import; implementation lives in els_server.protocol.protocol_codec."""
import importlib
import sys
sys.modules[__name__] = importlib.import_module('els_server.protocol.protocol_codec')
