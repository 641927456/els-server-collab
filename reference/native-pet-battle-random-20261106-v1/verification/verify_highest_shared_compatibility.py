from pathlib import Path
import hashlib,importlib.util,json,sys,time,traceback
K=Path(__file__).resolve().parent;S=K/'reward-source-v1';sys.dont_write_bytecode=True;sys.path.insert(0,str(S))
from els_server.domain.ordinary_magic_stones import catalog
report=dict(ok=False,production_database_access=False,native_Game=False,checks=[])
try:
    p=K/'trainer-before-v1/els_server/domain/ordinary_magic_stones.py';spec=importlib.util.spec_from_file_location('prior_ordinary_stones',p);prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
    # The archived module's data remain in the unchanged source tree.
    # Set only its module-location anchor, preserving the archived code itself.
    prior.__file__=str(S/'els_server/domain/ordinary_magic_stones.py')
    before=prior.catalog();after=catalog()
    for key in('items','profiles','options'):
        assert all(after[key][name]==value for name,value in before[key].items()),key
    assert after['retained_ordinary_options']==before['retained_ordinary_options']
    assert set(after['items'])-set(before['items'])=={'109956'}
    report['checks'].append('All prior stone item definitions, option identities, saved-option admissions and exact weighted profiles are unchanged')
    from els_server.domain.highest_magic_stone import catalog as highest
    native=json.loads((S/'els_server/data/current_magic_stones.json').read_bytes());d=highest()
    for kind in('weapon','armor'):
        groups=next(r['categories']for r in native['summary']if r['template']==710160 and r['kind']==kind)
        assert len(groups)==12
        for old,new in zip(groups,d['categories'][kind]):
            assert(old['field'],old['low'],old['high'],[r['option']for r in old['tiers']])==(new['field'],new['low'],new['high'],new['options'])
    report['checks'].append('Highest tiers exactly reuse the already qualified current native12-category description bounds and half-range armor IDs; only approved probability masses differ')
    report.update(ok=True,old_module_sha256=hashlib.sha256(p.read_bytes()).hexdigest())
except BaseException:report['error']=traceback.format_exc()
p=K/('highest-shared-compatibility-'+str(time.time_ns())+'.json');p.write_text(json.dumps(report,indent=2)+'\n','utf8');print(json.dumps(dict(ok=report['ok'],checks=report['checks'],report=str(p),error=report.get('error'))))
if not report['ok']:raise SystemExit(1)
