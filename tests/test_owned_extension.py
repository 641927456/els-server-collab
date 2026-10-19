import unittest
from tools.owned_extension import OwnedExtension

class Script:
    def __init__(self,source):self.source=source;self.loaded=False;self.destroyed=False
    def on(self,*args):pass
    def load(self):
        if self.source=='load-error':raise RuntimeError('load failed')
        self.loaded=True
    def unload(self):
        if self.destroyed:raise RuntimeError('script is destroyed')
        self.destroyed=True;self.loaded=False

class Session:
    def create_script(self,source):
        if source=='syntax-error':raise SyntaxError('invalid source')
        return Script(source)

class OwnedExtensionTests(unittest.TestCase):
    def test_syntax_error_preserves_previous_and_next_reload_recovers(self):
        slot=OwnedExtension(Session(),lambda *a:None,lambda *a:None);slot.load('first');first=slot.script
        with self.assertRaises(SyntaxError):slot.load('syntax-error')
        self.assertIs(slot.script,first);self.assertTrue(first.loaded)
        slot.load('second');self.assertTrue(first.destroyed);self.assertTrue(slot.script.loaded)

    def test_failed_load_or_destroyed_handle_cannot_poison_next_reload(self):
        errors=[];slot=OwnedExtension(Session(),lambda *a:None,lambda *a:errors.append(a));slot.load('first')
        with self.assertRaises(RuntimeError):slot.load('load-error')
        self.assertIsNone(slot.script);slot.load('second');slot.script.unload()
        slot.load('third');self.assertTrue(slot.script.loaded);self.assertEqual(errors[0][0],'extension_unload_error')
