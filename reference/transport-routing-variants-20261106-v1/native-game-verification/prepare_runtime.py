"""Private signed client transport fixture; installed runtimes stay immutable."""
from pathlib import Path
import ast, base64, hashlib, json, os, zipfile

R = Path('G:/els')
W = Path(__file__).resolve().parent
OUT = W / 'native-game-v1'
PARENT = R / 'releases/local/unified-server-566743b0f3babdfb-749ffeb2e0ca'
ENVELOPE = W.parent / 'shared-delivery-v81-r2/signedFriends.signed.json'
SOURCE = W.parent / 'transport-routing-variants-v1/full-source-v1'
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
save = lambda p, v: Path(p).write_text(json.dumps(v, indent=2) + '\n', 'utf8')

assert not OUT.exists()
old = json.loads(ENVELOPE.read_bytes())
payload = base64.b64decode(old['payload'])
definition = json.loads(payload)
assert len(definition['files']) == 2196
import sys
sys.dont_write_bytecode = True
sys.path.insert(0, str(R / 'tools/pylibs'))
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding
key = serialization.load_pem_private_key((Path(os.environ['LOCALAPPDATA']) /
    'ElsFriends-Publisher/launcher-update-signing.pem').read_bytes(), None)
key.public_key().verify(base64.b64decode(old['signature']), payload, padding.PKCS1v15(), hashes.SHA256())
for row in definition['files']:
    p = PARENT / row['path']
    assert not p.is_symlink() and not p.is_junction()
    assert p.stat().st_size == row['size'] and sha(p) == row['sha256'], row['path']

OUT.mkdir()
runtime = OUT / 'runtime'
runtime.mkdir()
for row in definition['files']:
    p = runtime / row['path']
    p.parent.mkdir(parents=True, exist_ok=True)
    os.link(PARENT / row['path'], p)
relative = 'els_server/friends_relay.py'
target = runtime / relative
parent_sha = sha(target)
target.unlink()  # Unlink only this owned hard link before copying the candidate.
target.write_bytes((W / 'candidate' / relative).read_bytes())
assert target.stat().st_nlink == 1 and sha(PARENT / relative) == parent_sha
ast.parse(target.read_bytes())
rows = [dict(row, size=(runtime / row['path']).stat().st_size,
             sha256=sha(runtime / row['path'])) for row in definition['files']]
delta = [r['path'] for r, p in zip(rows, definition['files']) if r != p]
assert delta == [relative], delta
archive = OUT / 'owned-signed-runtime.zip'
with zipfile.ZipFile(archive, 'x', zipfile.ZIP_DEFLATED, compresslevel=1) as z:
    for row in rows:
        z.write(runtime / row['path'], row['path'])
with zipfile.ZipFile(archive) as z:
    assert z.testzip() is None
    assert set(z.namelist()) == {r['path'] for r in rows}
definition.update(files=rows, archive=dict(file=archive.name, size=archive.stat().st_size, sha256=sha(archive)))
payload = json.dumps(definition, separators=(',', ':')).encode()
signature = key.sign(payload, padding.PKCS1v15(), hashes.SHA256())
key.public_key().verify(signature, payload, padding.PKCS1v15(), hashes.SHA256())
envelope = OUT / 'owned-signed-runtime.signed.json'
save(envelope, dict(payload=base64.b64encode(payload).decode(), signature=base64.b64encode(signature).decode()))
source_rows = {p.relative_to(SOURCE).as_posix(): sha(p) for p in SOURCE.rglob('*') if p.is_file()}
save(OUT / 'server-source-pins.json', source_rows)
save(OUT / 'runtime-binding.json', dict(ok=True, runtime=str(runtime), selected_signed=True,
    published=False, selected_signed_payload=sha(archive), signed_members=len(rows),
    envelope=str(envelope), envelope_sha256=sha(envelope), parent=str(PARENT),
    parent_envelope_sha256=sha(ENVELOPE), client_delta=delta, client_parent_sha256=parent_sha,
    candidate_server_overlay=str(SOURCE / 'els_server'), source_pins_sha256=sha(OUT / 'server-source-pins.json'),
    source_pin_count=len(source_rows), installed=False, game_started=False,
    scenario='One owned original Game joins31 authenticated protocol actors as public guest32'))
print(json.dumps(dict(ok=True, directory=str(OUT), signed_members=len(rows), client_delta=delta,
    signed_archive_sha256=sha(archive), source_pin_count=len(source_rows), game_started=False)))
