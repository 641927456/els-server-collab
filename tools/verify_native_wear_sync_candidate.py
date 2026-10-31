"""Verify an unselected native104/105 support candidate without a game or save."""
import hashlib
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REF=ROOT/'references/native-wear-sync-20261031-v1'


def verify(root=ROOT):
    reference=root/'references/native-wear-sync-20261031-v1'
    candidate=json.loads((reference/'candidate.json').read_bytes())
    assert candidate['candidate'] is True and candidate['selected'] is False
    assert candidate['installed'] is False and candidate['automatic_deployment'] is False
    assert candidate['server_delta']==0 and candidate['new_hook_sites']==1
    files=candidate['runtime_files']
    assert {r['path'] for r in files}=={'tools/native_cache_sync.py','tools/native_wear_sync.py','tools/native_wear_sync.js'}
    contents={}
    for row in files:
        path=(root/row['source']).resolve()
        assert path.is_relative_to(reference.resolve())
        raw=path.read_bytes()
        assert len(raw)==row['size'] and hashlib.sha256(raw).hexdigest()==row['sha256']
        contents[row['path']]=raw.decode('utf8').replace('\r\n','\n')
        if path.suffix=='.py':compile(raw,str(path),'exec')
    tuples=[(r['path'],r['sha256']) for r in files]
    assert hashlib.sha256(json.dumps(tuples,separators=(',',':')).encode()).hexdigest()==candidate['source_set_sha256']
    parent=root/'references/native-shared-repair-20261030-v1/source/225d321ef32563a5736513dd4030118aa669ac2e49cf8a3f7ac7344f4ef21856/native_cache_sync.py'
    assert hashlib.sha256(parent.read_bytes()).hexdigest()==files[0]['before_sha256']
    inverse=contents['tools/native_cache_sync.py']
    a='clearInterval(timer);\\n  installElsWearSync();\\n  {try{installElsRelationSourceSync();}'
    b='clearInterval(timer);\\n  {try{installElsRelationSourceSync();}'
    assert inverse.count(a)==1
    inverse=inverse.replace(a,b)
    a="    from native_wear_sync import source as wear_source\n    return wear_source(snapshot,executable_sha256)+'\\n'+raw+'\\n'+result"
    b="    return raw+'\\n'+result"
    assert inverse.count(a)==1
    inverse=inverse.replace(a,b)
    assert inverse==parent.read_text('utf8')
    verification=json.loads((reference/'verification.json').read_bytes())
    assert verification['source_self_check'] is True and verification['not_independent_review'] is True
    assert verification['original_native_wait']['passed']
    assert verification['frida_owned_ABI']['passed'] and len(verification['frida_owned_ABI']['cases'])==12
    assert verification['composition']['passed']
    return dict(passed=True,runtime_files=3,existing_compositor_inverse_exact=True,unselected=True,installed=False)


if __name__=='__main__':
    print(json.dumps(verify()))
