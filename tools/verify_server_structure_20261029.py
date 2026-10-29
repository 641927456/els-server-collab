"""Pinned structural successor and portable owned-runtime contract runner."""
from pathlib import Path
import argparse,copy,hashlib,json,os,shutil,subprocess,sys,tempfile

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from tools.materialize_formal_runtime import bound,load_manifest,materialize,plan
RID='server-structure-20261029-v1'
F=ROOT/'references'/RID
PROJECTION='els_server/storage/seal_quests.py'
HELPER='els_server/storage/character_projection.py'
read=lambda p:json.loads(p.read_bytes())
sha=lambda data:hashlib.sha256(data).hexdigest()

def files(profile,mode):return {r['path']:r for r in profile['channels'][mode]['files']}

def checked_source(entry,path):
    assert Path(path).resolve()==bound(ROOT,entry['source']), 'Unqualified source location'
    raw=Path(path).read_bytes()
    assert sha(raw)==entry['sha256'] and len(raw)==entry['size'], 'Qualified source bytes changed'
    return raw

def candidate_predecessor(mode,entry,path):
    """Check this candidate's exact extraction; this is not runtime acceptance."""
    d=read(F/'delta.json');q=read(F/'qualification.json')
    assert sha(bound(ROOT,d['parent']).read_bytes())==d['parent_sha256']==q['parent_profile_sha256']
    candidate=read(bound(ROOT,d['candidate_profile']));parent=read(bound(ROOT,d['parent']))
    assert candidate['candidate'] is True and candidate['actual_dual_delivery_verified'] is False
    expected=files(candidate,mode)[PROJECTION];change=d['channels'][mode][PROJECTION]
    assert entry==expected and all(entry[k]==change[k]for k in ('source','sha256','size')), 'Unqualified projection entry'
    raw=checked_source(entry,path)
    helper=files(candidate,mode)[HELPER]
    assert all(helper[k]==q['qualified_helper'][mode][k]for k in ('source','sha256','size')), 'Unqualified helper'
    checked_source(helper,bound(ROOT,helper['source']))
    inverse_raw=(F/'projection-inverse.json').read_bytes()
    assert sha(inverse_raw)==q['projection_inverse_sha256'], 'Changed extraction inverse'
    inverse=json.loads(inverse_raw)[mode]
    assert inverse['after_sha256']==entry['sha256']==change['sha256']
    lines=raw.decode('utf8').splitlines(keepends=True)
    for h in reversed(inverse['hunks']):
        assert lines[h['start']:h['end']]==h['new'], 'Extraction inverse mismatch'
        lines[h['start']:h['end']]=h['old']
    prior=files(parent,mode)[PROJECTION];before=bound(ROOT,prior['source'])
    original=checked_source(prior,before)
    assert prior['source']==change['before_source'] and prior['sha256']==change['before_sha256']==inverse['before_sha256']
    assert ''.join(lines).encode('utf8')==original, 'Nonqualified parent projection change'
    return prior,before

def verified_structure_predecessor(profile,mode,entry,path):
    """Only a delivered exact successor may feed the historical verifier."""
    d=read(F/'delta.json');change=d['channels'][mode].get(PROJECTION)
    if entry['path']!=PROJECTION or entry['sha256']!=change['sha256']:
        return entry,path
    assert profile.get('candidate') is False and profile.get('actual_dual_delivery_verified') is True, 'Uninstalled structural successor'
    accepted=read(bound(ROOT,d['accepted_profile']));receipt=read(F/'accepted-delivery.json')
    assert accepted['candidate'] is False and accepted['actual_dual_delivery_verified'] is True
    assert receipt['ok'] is True and receipt['candidate_manifest_sha256']==d['candidate_manifest_sha256']
    assert profile['accepted_heads']==accepted['accepted_heads'], 'Unaccepted installation heads'
    assert files(profile,mode)==files(accepted,mode), 'Selected profile is not the accepted successor'
    for channel in ('online','local'):
        assert accepted['accepted_heads'][channel]=={k:receipt['channels'][channel][k]for k in ('release','formal_manifest_sha256')}
    assert entry==files(accepted,mode)[PROJECTION]
    assert files(accepted,mode)==files(read(bound(ROOT,d['candidate_profile'])),mode)
    return candidate_predecessor(mode,entry,path)

def verify():
    d=read(F/'delta.json');q=read(F/'qualification.json')
    candidate=read(bound(ROOT,d['candidate_profile']));parent=read(bound(ROOT,d['parent']))
    assert sha(bound(ROOT,d['parent']).read_bytes())==d['parent_sha256']==q['parent_profile_sha256']
    assert d['candidate_manifest_sha256']==q['candidate_manifest_sha256']
    assert q['new_schema'] is False and q['client_delta']==0 and q['tests_per_channel']==169
    assert candidate['candidate'] is True and candidate['actual_dual_delivery_verified'] is False
    assert candidate['delta_business_files']==27 and candidate['new_modules']==7
    for mode in ('online','local'):
        old,new=files(parent,mode),files(candidate,mode);delta=d['channels'][mode]
        assert len(delta)==27 and len(set(new)-set(old))==7 and set(old)<=set(new)
        assert {p for p in old.keys()|new.keys()if old.get(p)!=new.get(p)}==set(delta)
        for path,row in delta.items():
            assert (old[path]['sha256']if path in old else None)==row['before_sha256']
            assert (old[path]['source']if path in old else None)==row['before_source']
            assert all(new[path][k]==row[k]for k in ('source','sha256','size'))
            checked_source(new[path],bound(ROOT,new[path]['source']))
        plan(ROOT,candidate,mode)
        entry=new[PROJECTION];candidate_predecessor(mode,entry,bound(ROOT,entry['source']))
    inputs=read(ROOT/'references/settlement-replay-fixture-20261030-v1/test-inputs.json')
    assert inputs['runtime_counts']=={'online':169,'local':169} and inputs['baseline_mode'] is False
    for target,row in inputs['files'].items():
        bound(ROOT,target)
        raw=bound(ROOT,row['source']).read_bytes()
        assert sha(raw)==row['sha256'] and len(raw)==row['size']
    return candidate,d,inputs

def runtime_tests(candidate,d,inputs,assets_root):
    cache=ROOT/'.runtime-cache';cache.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix='server-structure-',dir=cache)as folder:
        task=Path(folder).resolve();(task/'runtimes').mkdir()
        for target,row in inputs['files'].items():
            dest=bound(task,target);dest.parent.mkdir(parents=True,exist_ok=True)
            shutil.copyfile(bound(ROOT,row['source']),dest)
        for target,value in inputs['synthetic_expected'].items():bound(task,target).write_text(json.dumps(value),encoding='utf8')
        shutil.copyfile(F/'run_regression.py',task/'run_regression.py')
        for mode in ('online','local'):
            runtime=task/'runtimes'/mode
            materialize(ROOT,candidate,mode,runtime,assets_root=assets_root,link_assets=True)
            for path,row in d['channels'][mode].items():
                dest=task/'candidate'/mode/path;dest.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(bound(ROOT,row['source']),dest)
            environment=dict(os.environ,ELS_INITIALIZATION_BASELINE='0')
            subprocess.run([sys.executable,'-B',str(task/'run_regression.py'),'--runtime',str(runtime),
                            '--output','result-'+mode,*inputs['tests']],cwd=task,env=environment,check=True)
            result=read(task/('result-'+mode+'.json'))
            assert result['success'] and result['tests_run']==inputs['runtime_counts'][mode]
            print(json.dumps({'ok':True,'channel':mode,'owned_runtime_tests':result['tests_run']}))

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--with-runtime',action='store_true')
    parser.add_argument('--assets-root',type=Path,default=ROOT);args=parser.parse_args()
    candidate,d,inputs=verify()
    subprocess.run([sys.executable,'-B','-m','unittest','tests.test_server_structure_source_contract'],cwd=ROOT,check=True)
    if args.with_runtime:runtime_tests(candidate,d,inputs,args.assets_root)
    print(json.dumps({'ok':True,'delta_leaves_per_channel':27,'new_modules_per_channel':7,'runtime_tests':args.with_runtime,'production_actions':False}))

if __name__=='__main__':main()
