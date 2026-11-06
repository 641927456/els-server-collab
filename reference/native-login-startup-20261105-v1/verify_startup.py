"""Verify the exact signed startup composition without starting a game or bridge."""
from pathlib import Path
import base64
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import zipfile

sys.dont_write_bytecode = True
WORK = Path(__file__).resolve().parent
ROOT = Path('G:/els')
BASE = Path(os.environ['LOCALAPPDATA']) / 'ElsFriends/component-runtimes/cbdfa0b3dadc8b5e-c15d2a1599e5'
MANIFEST = ROOT / 'analysis/unified-server-ip-20261104-v2/publication/launcher-v76-r3/signedFriends.signed.json'
PRIOR_ARCHIVE = ROOT / 'analysis/plegas-pillar-20261104-v1/publication/launcher-v75/runtime-90c9d9e65fed4e6e1592868d9fb3d2aeb452aeb01c64350ceb62a795722f9723.zip'
TRACE_HASH = 'a155d2c5b8ab7197340eae32364a48d598ec6b7bffbe5523c443f9f1f0a20a08'
checks = []


def digest(data):
    return hashlib.sha256(data).hexdigest()


def check(name, condition):
    assert condition, name
    checks.append(name)


def module(name, source):
    spec = importlib.util.spec_from_file_location(name, source)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    # The only changed file is Python. Its unchanged JS sibling and every
    # imported composer must resolve to the verified, immutable signed inputs.
    value.__file__ = str(BASE / 'tools/native_cache_sync.py')
    return value


definition = json.loads(base64.b64decode(json.loads(MANIFEST.read_bytes())['payload']))
rows = {row['path']: row for row in definition['files']}
sys.path[:0] = [str(BASE / 'tools'), str(BASE / 'tools/pylibs'), str(BASE)]
# Avoid importing similarly named files from the mutable workspace.
os.chdir(BASE)
loaded = json.loads((WORK / 'parent.json').read_bytes())
check('exact_parent_runtime', loaded['payload_sha256'] == definition['archive']['sha256'])
check('signed_composition_inputs', all(
    digest((BASE / row['path']).read_bytes()) == row['sha256']
    for row in definition['files']
    if row['path'].startswith('tools/') and row['path'].endswith(('.py', '.js'))
))
snapshot = (BASE / 'analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
template = (BASE / 'tools/trace_dx11_login.js').read_text(encoding='utf8')
before = module('login_cache_before', BASE / 'tools/native_cache_sync.py')
after = module('login_cache_after', WORK / 'source/tools/native_cache_sync.py')
check('snapshot_identity_unchanged', digest(snapshot) == before.IMAGE_SHA == after.IMAGE_SHA)
check('client_identity_unchanged', before.EXE_SHA == after.EXE_SHA)
check('all_previous_trace_identities_retained', before.TRACE_TEXT_SHAS < after.TRACE_TEXT_SHAS)
check('only_reviewed_trace_identity_added', after.TRACE_TEXT_SHAS - before.TRACE_TEXT_SHAS == {TRACE_HASH})
check('exact_published_trace_identity', digest(template.replace('\r\n', '\n').encode()) == TRACE_HASH)
with zipfile.ZipFile(PRIOR_ARCHIVE) as archive:
    prior = archive.read('tools/trace_dx11_login.js').decode('utf8').replace('\r\n', '\n')
check('prior_signed_trace_was_already_accepted', digest(prior.encode()) in before.TRACE_TEXT_SHAS)
reviewed = prior.replace('[2,0,0x4b,0xc8,127,0,0,1,0,0,0,0,0,0,0,0]',
                         '[2,0,0x4b,0xc8,127,0,0,2,0,0,0,0,0,0,0,0]')
reviewed = reviewed.replace("local_host:'127.0.0.1',local_port:19400",
                            "local_host:'127.0.0.2',local_port:19400")
check('reviewed_trace_delta_is_only_bootstrap_loopback_address', reviewed == template)


def rejected(composer, image, executable, trace, expected):
    try:
        composer.compose(image, executable, trace)
    except ValueError as error:
        return str(error) == expected
    return False


check('published_failure_reproduced', rejected(before, snapshot, before.EXE_SHA, template,
      'Native power cache parent trace changed; explicit merge required'))
code = after.compose(snapshot, after.EXE_SHA, template)
check('complete_composition_succeeds', isinstance(code, str) and len(code) > len(template))
check('preserved_bootstrap_address', "local_host:'127.0.0.2'" in code)
check('cache_composition_present', 'native_cache_sync_prepared' in code)
check('source_pin_placeholders_resolved', '__CACHE_SYNC_PINS__' not in code and '__RELATION_SOURCE_PINS__' not in code)
prior_code = after.compose(snapshot, after.EXE_SHA, prior)
check('previous_trace_composition_retained', 'native_cache_sync_prepared' in prior_code)
check('modified_trace_still_rejected', rejected(after, snapshot, after.EXE_SHA, template + '\n// unreviewed change\n',
      'Native power cache parent trace changed; explicit merge required'))
check('wrong_client_still_rejected', rejected(after, snapshot, '0' * 64, template,
      'Native power cache client identity'))
check('wrong_image_still_rejected', rejected(after, snapshot[:-1], after.EXE_SHA, template,
      'Native power cache client identity'))
compile((WORK / 'source/tools/native_cache_sync.py').read_bytes(), 'tools/native_cache_sync.py', 'exec')
check('python_syntax', True)
node = shutil.which('node')
check('javascript_parser_available', node is not None)
for name, text in [('current', code), ('previous', prior_code)]:
    result = subprocess.run([node, '--check'], input=text.encode(), capture_output=True,
                            timeout=30, creationflags=0x08000000)
    check(name + '_complete_javascript_syntax', result.returncode == 0)

report = dict(ok=True, passed=len(checks), checks=checks,
              parent_payload_sha256=definition['archive']['sha256'],
              candidate_sha256=digest((WORK / 'source/tools/native_cache_sync.py').read_bytes()),
              composed_current_sha256=digest(code.encode()),
              composed_current_bytes=len(code.encode()),
              composed_previous_sha256=digest(prior_code.encode()),
              original_EXE_KOM_changed=False, game_started=False,
              account_or_database_changed=False, published=False)
(WORK / 'verification.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf8')
print(json.dumps(report, ensure_ascii=False))
