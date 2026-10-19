import tempfile
import unittest
from pathlib import Path
from tools.headless_result import verify_result


class HeadlessResultTests(unittest.TestCase):
    def test_timeout_and_stale_output_are_not_success(self):
        with tempfile.TemporaryDirectory() as directory:
            root=Path(directory)
            (root/'0x123.c').write_text('void old_function() {}',encoding='utf8')
            bracket='BRACKET before=647 added=1 after=648 cascade=completed\n'
            for log in (bracket, bracket+'DECOMPILED 123 complete=false'):
                with self.assertRaises(ValueError):verify_result(log,[0x123],root)
            success=bracket+'DECOMPILED 123 complete=true'
            verify_result(success,[0x123],root)
            (root/'0x123.c').write_text('ERROR: timeout',encoding='utf8')
            with self.assertRaises(ValueError):verify_result(success,[0x123],root)
            with self.assertRaises(ValueError):
                verify_result(success.replace('after=648','after=649'),[0x123],root)


if __name__=='__main__':unittest.main()
