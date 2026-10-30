"""Reject private runtime state and credentials before commit or CI upload."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
BLOCKED_ROOTS={'state','logs','backups','run','analysis','python','vendor','.asset-cache','.runtime-cache','.launcher-cache','.venv'}
BLOCKED_SUFFIXES={'.sqlite','.sqlite3','.db','.pem','.key','.pfx','.p12','.exe','.pyd','.dll','.bin','.zip','.7z','.rar','.dmp','.jsonl','.log'}
SYNTHETIC_PASSWORD_TESTS={'tests/test_registration.py','tests/test_friends_character_creation.py'}
FROZEN_MODE_FIXTURES={
    'launchers/friends-v45/ModeDesign.cs':'64911997a6db2f18b8d116380fa2b6f83caa9fabe86c3ce51a97f821f1b651cf',
    'launchers/friends-v43/ModeDesign.cs':'64911997a6db2f18b8d116380fa2b6f83caa9fabe86c3ce51a97f821f1b651cf',
    'launchers/friends-v42/ModeDesign.cs':'64911997a6db2f18b8d116380fa2b6f83caa9fabe86c3ce51a97f821f1b651cf',
    'launchers/friends-v37/ModeDesign.cs':'833b34b05d207b028b89b0415795a246144f7384a8b26f778d7600de8e1e605a',
    'launchers/friends-v38/ModeDesign.cs':'d2fa60f75a8a4f3c45e759c233ac0f63fb570961203c15c3c69b1855540cefb6',
}
FROZEN_RANDOM_PASSWORD_PROGRAMS={
    'launchers/friends-v45/Program.cs':'053ba6945902a6ca0038fd8eceb419f74ada426e97ff2d9a0736a106e430d30d',
    'launchers/friends-v43/Program.cs':'516a4567d763799a75ad8e2ad975f465704476bfbd2b519a469772702460f719',
    'launchers/friends-v42/Program.cs':'516a4567d763799a75ad8e2ad975f465704476bfbd2b519a469772702460f719',
    'launchers/friends-v41/Program.cs':'6daceeda897578c71bfb56e16c945f8784d042da3bfb8c9c8e2ab2433605ae0f',
}
FROZEN_UI_IMAGES={
    # Exact reviewed V45 build input, identical to the released V44 background.
    # This is not a general PNG or launcher-directory exemption.
    'launchers/friends-v45/assets/ruben.png':(2030054,'190d47330f4cc12bb74c6dc32b4c3eec21d3604eb8cf8d020cee17705de99654'),
}
CREDENTIAL=re.compile(r'''(?i)(?:["']?(password|passwd|token|access_token|refresh_token|auth_token|api_key|admin_key|management_key|ssh_password)["']?\s*[:=]\s*["'])([^"'\r\n]{8,})''')
PEM=re.compile(r'(?m)^-----BEGIN (?:RSA |EC |DSA |OPENSSH |ENCRYPTED )?PRIVATE KEY-----\s*$')

def violations(name,data):
    path=Path(name);parts=path.parts;errors=[]
    if path.is_absolute() or '..' in parts or not parts:return ['unsafe path']
    if parts[0] in BLOCKED_ROOTS or name.startswith('tools/pylibs/') or name.startswith('launcher/assets/'):
        errors.append('generated/runtime/private directory')
    if path.suffix.lower() in BLOCKED_SUFFIXES or path.name.endswith(('-wal','-shm')):errors.append('binary, database, key or runtime log')
    if path.name.casefold().startswith('.env') or path.name.casefold() in {'friends-owner.json','friends-client.json','id_ed25519','id_rsa'} or 'invites' in parts:
        errors.append('private configuration or credential filename')
    if len(data)>50*1024*1024:errors.append('large file belongs in locked runtime assets')
    if (name in FROZEN_UI_IMAGES and data.startswith(b'\x89PNG\r\n\x1a\n')
            and FROZEN_UI_IMAGES[name]==(len(data),hashlib.sha256(data).hexdigest())):
        return errors
    if b'\0' in data:errors.append('binary data')
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:return errors+['non-UTF8 source']
    if PEM.search(text):errors.append('private key block')
    for match in CREDENTIAL.finditer(text):
        field,value=match.groups()
        if field.lower() in {'password','passwd'} and name in SYNTHETIC_PASSWORD_TESTS:continue
        if (field.lower()=='password' and value=='Fixture-Only-'
                and FROZEN_RANDOM_PASSWORD_PROGRAMS.get(name)==hashlib.sha256(data).hexdigest()
                and text[match.end():].startswith('"+Guid.NewGuid().ToString("N"),name="proof_password";')):continue
        # The released C# self-test generates a fresh random fixture value.
        # Permit only this exact non-secret prefix/context; other literals in
        # the same file still fail the guard.
        if (name in {'launchers/friends-v29/Program.cs','launchers/friends-v31/Program.cs','launchers/friends-v32/Program.cs','launchers/friends-v33/Program.cs','launchers/friends-v35/Program.cs','launchers/friends-v36/Program.cs','launchers/friends-v37/Program.cs','launchers/friends-v38/Program.cs'} and field.lower()=='password'
                and value=='Fixture-Only-' and text[match.end():].startswith('"+Guid.NewGuid().ToString("N"),name="proof_password";')):continue
        # These two historical mode-switch self-tests deliberately use a dummy
        # token to prove it is cleared. Permit that one non-secret literal only
        # in the exact frozen whole-file bytes; edits require a fresh review.
        if (field.lower()=='token' and value=='fixture-token-only'
                and FROZEN_MODE_FIXTURES.get(name)==hashlib.sha256(data).hexdigest()):continue
        # Four historical uuid4 message-correlation IDs, never credentials.
        # Exact path, whole-file and value hashes only; edited literals fail.
        if (field.lower()=='token' and name=='references/current-obtainable-consumables-phase-20261028-v1/source/4980b900c7473042644be0623b8e0967436fd420b8ee11a5a85b8bcab63d0348/native-ui-acceptance.json'
                and hashlib.sha256(data).hexdigest()=='4980b900c7473042644be0623b8e0967436fd420b8ee11a5a85b8bcab63d0348'
                and hashlib.sha256(value.encode()).hexdigest()in {'41f3be4b137bf035cf0eb05c0e32ebe0e787ced16abc8e24dc413dba763b79c5', '5d21f0d0603df055a8847839b1eceba1f73b080f07bb0f64ef8cf9ce39a36334', 'ff4098f6f8153a26a372f0f0f76c9a1bfce9968d0a99070ddff78125ed35dd68', 'a8ebd6ee9ff4591d4a4e0e7bcf31b8556dc8b6d547324b08fa61f0af763c0ba9'}):continue
        if value.lower() in {'placeholder','replace_me','your_token_here','example_only'}:continue
        errors.append('literal credential candidate; review required');break
    return errors

def git(args):return subprocess.run(['git',*args],cwd=ROOT,check=True,capture_output=True).stdout

def main(argv=None):
    parser=argparse.ArgumentParser();parser.add_argument('--staged',action='store_true');args=parser.parse_args(argv)
    if args.staged:names=git(['diff','--cached','--name-only','--diff-filter=ACMRT','-z']).decode('utf8').split('\0')
    else:names=git(['ls-files','-z']).decode('utf8').split('\0')
    failures=[];checked=0
    for name in filter(None,names):
        checked+=1
        data=git(['show',':'+name]) if args.staged else (ROOT/name).read_bytes()
        issues=violations(name,data)
        if issues:failures.append(dict(path=name,reasons=issues))
    print(json.dumps(dict(ok=not failures,checked_files=checked,failures=failures),ensure_ascii=True,indent=2))
    return bool(failures)

if __name__=='__main__':raise SystemExit(main())
