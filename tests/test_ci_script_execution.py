"""Run real child scripts with the import policy used by isolated Python."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from tools import ci_checks


class ScriptExecution(unittest.TestCase):
    def test_sibling_import_and_arguments_with_safe_path(self):
        with tempfile.TemporaryDirectory(prefix='ci script ',dir=ci_checks.ROOT)as folder:
            root=Path(folder)
            (root/'fixture_sibling.py').write_text('VALUE=37\n',encoding='utf-8')
            script=root/'entry.py'
            target=root/'result.json'
            script.write_text(
                'import json,sys\nfrom pathlib import Path\n'
                'from fixture_sibling import VALUE\n'
                'assert sys.flags.safe_path\n'
                'Path(sys.argv[1]).write_text(json.dumps([VALUE,sys.argv[2:],'
                '__name__,str(Path(__file__).resolve()),sys.path[0]]))\n',
                encoding='utf-8',
            )
            original=subprocess.run(
                [sys.executable,'-I','-B',str(script),str(target),'qty=3','two words'],
                cwd=ci_checks.ROOT,capture_output=True,text=True,
            )
            self.assertNotEqual(original.returncode,0)
            self.assertIn("No module named 'fixture_sibling'",original.stderr)
            with patch.dict(os.environ,{'PYTHONSAFEPATH':'1'}):
                ci_checks.run([sys.executable,'-B',str(script),str(target),'qty=3','two words'])
            self.assertEqual(json.loads(target.read_bytes()),
                [37,['qty=3','two words'],'__main__',str(script.resolve()),str(root.resolve())])

    def test_failed_script_still_fails_the_ci_command(self):
        with tempfile.TemporaryDirectory(prefix='ci-script-failure-',dir=ci_checks.ROOT)as folder:
            script=Path(folder)/'failure.py'
            script.write_text('raise SystemExit(23)\n',encoding='utf-8')
            with self.assertRaises(subprocess.CalledProcessError)as failure:
                ci_checks.run([sys.executable,'-B',str(script)])
            self.assertEqual(failure.exception.returncode,23)


if __name__=='__main__':
    unittest.main()
