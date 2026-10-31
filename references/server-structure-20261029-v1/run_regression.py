"""Run selected unmodified regressions against an explicit server source view."""
from pathlib import Path
import argparse
import importlib.util
import io
import json
import os
import sys
import tempfile
import types
import unittest
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parent

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--runtime', type=Path, required=True)
    parser.add_argument('--output', required=True)
    parser.add_argument('tests', nargs='+')
    args = parser.parse_args()
    runtime = args.runtime.resolve()
    assert (runtime / 'els_server/application.py').is_file()
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime))
    import els_server
    assert Path(els_server.__file__).resolve() == runtime / 'els_server/__init__.py'
    pinned_tests = ROOT / 'pinned-inputs/tests'
    sys.path.insert(0, str(pinned_tests))
    package = types.ModuleType('tests')
    package.__path__ = [str(pinned_tests)]
    sys.modules['tests'] = package
    os.environ['ELS_RUNTIME_ROOT'] = str(runtime)
    temporary = ROOT / 'test-tmp'
    temporary.mkdir(exist_ok=True)
    tempfile.tempdir = str(temporary)
    def audit(event, values):
        if event != 'sqlite3.connect':
            return
        value = os.fsdecode(values[0])
        if value == ':memory:':
            return
        readonly_catalog = (value.startswith('file:') and '?mode=ro&immutable=1' in value)
        if value.startswith('file:'):
            value = unquote(urlparse(value).path).lstrip('/')
        if readonly_catalog and Path(value).resolve() == runtime / 'els_server/data/client/catalog.sqlite3':
            return
        assert Path(value).resolve().is_relative_to(ROOT), f'Non-owned database blocked: {value}'
    sys.addaudithook(audit)
    suite = unittest.TestSuite()
    inputs = []
    for index, name in enumerate(args.tests):
        path = (ROOT / name).resolve()
        assert path.is_relative_to(ROOT)
        spec = importlib.util.spec_from_file_location(f'regression_{index}', path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        suite.addTests(unittest.defaultTestLoader.loadTestsFromModule(module))
        inputs.append(str(path))
    import els_server.application as application
    assert Path(application.__file__).resolve() == runtime / 'els_server/application.py'
    log = io.StringIO()
    result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
    output = ROOT / args.output
    assert output.resolve().is_relative_to(ROOT)
    output.with_suffix('.log').write_text(log.getvalue(), encoding='utf8')
    data = dict(runtime=str(runtime), tests=inputs, tests_run=result.testsRun,
                success=result.wasSuccessful(), failures=[(str(t), trace) for t,trace in result.failures],
                errors=[(str(t), trace) for t,trace in result.errors], skipped=[(str(t),reason) for t,reason in result.skipped],
                sqlite_scope='Owned task directory, :memory:, or explicit readonly immutable static client catalog only')
    output.with_suffix('.json').write_text(json.dumps(data, indent=2) + '\n', encoding='utf8')
    print(json.dumps({k:data[k] for k in ('runtime','tests_run','success','failures','errors')}))
    return not result.wasSuccessful()

if __name__ == '__main__':
    raise SystemExit(main())
