"""Reuse the qualified owned Job/input-denial harness for one wedding guest."""
from pathlib import Path
import ast, hashlib, json, sys

HERE = Path(__file__).resolve().parent
W = HERE.parents[1]
raw = (W / 'duel-native-game-v1/prepare_attempt.py').read_text('utf8')
raw = raw.replace("parent=HERE.parent/'guild-native-game-v2'", "parent=Path(" + repr(str(W / 'guild-native-game-v2')) + ")")
raw = raw.replace('HERE=Path(__file__).resolve().parent;parent=', 'HERE=Path(' + repr(str(HERE)) + ');parent=')
old = '0x17a2d0:16,0x2d75c90:16,0x2d773e0:16,0x7e3d90:16,0xc97790:16,0x7d57a0:16,0x316c540:16,0x316e410:16,0xc90480:16'
assert raw.count(old) == 1
raw = raw.replace(old, '0xd28770:16,0xdb7cf0:16,0xd9bcc0:16,0x2126820:16,0x2126c20:16,0xd34bd0:16,0xdbfe10:16,0x909b60:16,0x74ffa0:16')
raw = raw.replace('Owned native duel lifecycle qualification', 'Owned native32-person wedding scene qualification')
raw = raw.replace("original_native_accept_function='B77740 caseC21 ->B7B2E7 ->2D773E0',native_project_functions=244",
    "original_native_join_function='D34BD0 complete original admission action ->DAD010 ->DBFE10 with original415 pending registration',native_project_functions=417")
ast.parse(raw)
exec(compile(raw, str(HERE / 'scenario-generator.py'), 'exec'), {'__name__':'__main__', '__file__':str(HERE / 'scenario-generator.py')})
attempt = HERE / sys.argv[2]
backend = (HERE / 'server_owned.py').read_text('utf8').replace('HERE=Path(__file__).resolve().parent', 'HERE=Path(' + repr(str(HERE)) + ')')
ast.parse(backend)
(attempt / 'server_input.py').write_text(backend, 'utf8')
probe = attempt / 'probe_owned.py'
source = probe.read_text('utf8')
for a, b in (("str(N.parent/'server_owned.py')", "str(N/'server_input.py')"),
    ('time.monotonic()-start<240', 'time.monotonic()-start<300'),
    ('deadline=time.monotonic()+40', 'deadline=time.monotonic()+120'),
    ("receipt['candidate_published']=True", "receipt['candidate_published']=False")):
    assert source.count(a) == 1, (a, source.count(a))
    source = source.replace(a, b)
ast.parse(source)
probe.write_text(source, 'utf8')
p = attempt / 'preparation.json'
v = json.loads(p.read_bytes())
v.update(candidate_published=False, harness_sha256=hashlib.sha256(probe.read_bytes()).hexdigest(),
    backend_sha256=hashlib.sha256((attempt/'server_input.py').read_bytes()).hexdigest(),
    total_bound_seconds=300, preparation_bound_seconds=120,
    preparation_bound_reason='31 actual authenticated actors and31 real admissions instead of the parent single actor',
    production_request_timeout_seconds=25, owned_input_controls_unchanged=True, natural_GUI=False,
    town_return_only='--town-return-only'in sys.argv)
p.write_text(json.dumps(v, indent=2)+'\n', 'utf8')
(attempt/'observer-input.js').write_bytes((HERE/'observer.js').read_bytes())
