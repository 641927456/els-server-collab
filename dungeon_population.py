"""Compatibility import; implementation lives in els_server.domain.dungeon_population."""
import importlib
import sys
sys.modules[__name__] = importlib.import_module('els_server.domain.dungeon_population')
