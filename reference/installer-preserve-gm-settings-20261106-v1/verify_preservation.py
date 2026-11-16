"""Real first/reused private provision, preserving valid nondefault GM files."""
from contextlib import closing
from pathlib import Path
import ctypes,hashlib,importlib.util,json,os,shutil,sqlite3,sys,tempfile,time,traceback
W=Path(__file__).resolve().parent;R=W.parent/'shared-delivery-v82/runtime';C=W/'candidate'
sys.dont_write_bytecode=True;sys.path[:0]=[str(R),str(R/'tools'),str(R/'vendor'),'G:/els/tools/pylibs']
_sqlite=ctypes.WinDLL(str(R/'python/sqlite3.dll'))
spec=importlib.util.spec_from_file_location('owned_provision_candidate',C/'tools/provision_unified_server.py')
module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
from els_server.domain.gm_rates import validate as rates
from els_server.domain.gm_events import validate as events
report=dict(ok=False,checks=[],installed=False,production_database_access=False,
    source_sha256=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest())
root=Path(tempfile.mkdtemp(prefix='owned-installer-preserve-',dir=W)).resolve()
sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
try:
    game=root/'save/game.sqlite3'
    first=module.provision(root,game)
    assert first['ok']and first['reused']is False
    home=root/'state/unified-server';settings=json.loads((C/'config/gm-settings.json').read_bytes())
    assert json.loads((home/'gm/rates.json').read_bytes())==rates(settings['rates'])
    assert json.loads((home/'gm/events.json').read_bytes())==events(settings['events'])
    report['checks'].append('Real first provision creates only the owned private deployment, DPAPI owner, certificate and both packaged validated business defaults')
    nondefault_rates=rates(dict(revision=91,drops=dict(ordinary=725,boss=1975,chest=3650,ed=8888),
        enhancement=[10000,9999,9000,8500,7777,6500,5000,3333,2500,1777,1000,500,17],experience_bp=37500))
    nondefault_events=events(dict(revision=47,events={str(k):dict(enabled=index%2==0,start=1793900000+index,end=1794900000+index)
        for index,k in enumerate(events(settings['events'])['events'])}))
    # Deliberate formatting and past file times detect reserialization too.
    for name,value in [('rates.json',nondefault_rates),('events.json',nondefault_events)]:
        p=home/'gm'/name;p.write_text(json.dumps(value,ensure_ascii=False,separators=(',',':'))+'\n\n','utf8')
        os.utime(p,ns=(1600000000000000000,1600000000000000000))
    files=[home/'gm/rates.json',home/'gm/events.json',home/'owner.dpapi',home/'accounts.sqlite3',
        home/'server-cert.pem',home/'server-key.pem',home/'endpoint.json',game]
    before={str(p.relative_to(root)):(sha(p),p.stat().st_mtime_ns)for p in files}
    again=module.provision(root,game);assert again['ok']and again['reused']is True
    assert {str(p.relative_to(root)):(sha(p),p.stat().st_mtime_ns)for p in files}==before
    assert module.provision(root,game)['reused']is True
    assert {str(p.relative_to(root)):(sha(p),p.stat().st_mtime_ns)for p in files}==before
    report['checks'].append('Actual existing-endpoint path and repeated provision preserve nondefault drop/enhancement/experience values, event switches/windows and original bytes/mtime; owner, account DB, certificates, endpoint and isolated game save are unchanged')
    # Make a server config update pending; invalid existing business input
    # must fail before it can reset or alter another private setting.
    server_config=home/'server.toml';original_config=server_config.read_bytes()
    server_config.write_bytes(original_config.replace(b'max_connections = 192',b'max_connections = 191'))
    pending_config=server_config.read_bytes()
    event_path=home/'gm/events.json';valid_event=event_path.read_bytes();event_path.write_bytes(b'{invalid existing event configuration')
    failed_snapshot={str(p.relative_to(root)):sha(p)for p in files}
    try:module.provision(root,game)
    except (ValueError,json.JSONDecodeError):pass
    else:raise AssertionError('Invalid existing business input was silently replaced')
    assert server_config.read_bytes()==pending_config
    assert {str(p.relative_to(root)):sha(p)for p in files}==failed_snapshot
    event_path.write_bytes(valid_event)
    missing_path=home/'gm/rates.json';missing_data=missing_path.read_bytes();missing_path.unlink()
    try:module.provision(root,game)
    except FileNotFoundError:pass
    else:raise AssertionError('Existing missing private rates were silently defaulted')
    assert not missing_path.exists()and server_config.read_bytes()==pending_config
    missing_path.write_bytes(missing_data)
    report['checks'].append('Invalid or missing existing business settings fail explicitly before a pending server-config update; no automatic reset or default substitution occurs')
    report.update(ok=True,nondefault_example=dict(rate_revision=91,experience_bp=37500,event_revision=47),
        source_is_isolated_review_candidate=True,final_peer_source_not_yet_reviewed=True)
except BaseException:report['error']=traceback.format_exc()
finally:
    if report['ok']:
        assert root.parent==W.resolve()and root.name.startswith('owned-installer-preserve-')
        assert not root.is_symlink()and not root.is_junction()
        assert all(not p.is_symlink()and not p.is_junction()for p in root.rglob('*'))
        shutil.rmtree(root);report['fixture_cleaned']=not root.exists()
    else:report['owned_fixture_retained_for_readonly_diagnosis']=str(root)
    out=W/('preservation-'+str(time.time_ns())+'.json');out.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf8')
    print(json.dumps(report|dict(evidence=str(out)),ensure_ascii=False))
raise SystemExit(not report['ok'])
