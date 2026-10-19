"""Reject private runtime state and credentials before commit or CI upload."""
from pathlib import Path
import argparse,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
BLOCKED_ROOTS={'state','logs','backups','run','analysis','python','vendor','.asset-cache','.runtime-cache','.venv'}
BLOCKED_SUFFIXES={'.sqlite','.sqlite3','.db','.pem','.key','.pfx','.p12','.exe','.pyd','.dll','.bin','.zip','.7z','.rar','.dmp','.jsonl','.log'}
SYNTHETIC_PASSWORD_TESTS={'tests/test_registration.py','tests/test_friends_character_creation.py'}
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
    if b'\0' in data:errors.append('binary data')
    try:text=data.decode('utf-8-sig')
    except UnicodeDecodeError:return errors+['non-UTF8 source']
    if PEM.search(text):errors.append('private key block')
    for match in CREDENTIAL.finditer(text):
        field,value=match.groups()
        if field.lower() in {'password','passwd'} and name in SYNTHETIC_PASSWORD_TESTS:continue
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
