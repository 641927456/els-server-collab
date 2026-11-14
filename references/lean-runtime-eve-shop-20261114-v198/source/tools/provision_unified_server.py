"""Initialize a private deployment without changing the existing game save."""
import argparse, ctypes, hashlib, json, os, secrets, shutil, sqlite3, subprocess, sys, uuid
from contextlib import closing
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT));sys.path.insert(0,str(ROOT/'tools'))
from els_server.config import ServerConfig
from els_server.storage.accounts import Accounts

ENTROPY=b'ELS unified server owner v1'
class Blob(ctypes.Structure):
    _fields_=[('size',ctypes.c_ulong),('data',ctypes.POINTER(ctypes.c_ubyte))]

def protect(raw,decode=False):
    def blob(data):
        buffer=ctypes.create_string_buffer(data)
        return buffer,Blob(len(data),ctypes.cast(buffer,ctypes.POINTER(ctypes.c_ubyte)))
    data_buffer,data=blob(raw);entropy_buffer,entropy=blob(ENTROPY);out=Blob()
    api=ctypes.windll.crypt32.CryptUnprotectData if decode else ctypes.windll.crypt32.CryptProtectData
    args=(ctypes.byref(data),None,ctypes.byref(entropy),None,None,1,ctypes.byref(out))
    if not api(*args):raise ctypes.WinError()
    try:return ctypes.string_at(out.data,out.size)
    finally:ctypes.windll.kernel32.LocalFree(out.data)

def toml(values):
    return '[server]\n'+''.join(k+' = '+(str(v).lower()if type(v)is bool else json.dumps(v))+'\n'for k,v in values.items())

def business_settings(home):
    settings=json.loads((ROOT/'config/gm-settings.json').read_bytes())
    from els_server.domain.gm_rates import validate as validate_rates
    from els_server.domain.gm_events import configure as configure_events, validate as validate_events
    values={'rates.json':validate_rates(settings['rates']),'events.json':validate_events(settings['events'])}
    directory=home/'gm'
    for parent in (directory,*directory.parents):
        assert not parent.is_symlink()and not parent.is_junction(),'Linked business settings path'
    directory.mkdir(exist_ok=True)
    for name,value in values.items():
        target=directory/name;raw=json.dumps(value,ensure_ascii=False,indent=2)+'\n'
        assert not target.is_symlink()and not target.is_junction(),'Linked business settings file'
        if target.exists():
            if name == 'events.json':
                configure_events(target)
            else:
                validate_rates(json.loads(target.read_bytes()))
            continue
        temp=directory/(name+'.'+uuid.uuid4().hex+'.tmp');temp.write_text(raw,'utf8');os.replace(temp,target)

def provision(workspace,game,host='127.0.0.1',*,operation_token=None):
    workspace=Path(workspace).resolve();game=Path(game).resolve()
    home=workspace/'state/unified-server';endpoint=home/'endpoint.json'
    for parent in (home,*home.parents):
        assert not parent.is_symlink()and not parent.is_junction(),'Linked private deployment path'
    if endpoint.exists():
        config=ServerConfig.load(home/'server.toml');assert config.state_file==game and config.host==host
        identity=json.loads(protect((home/'owner.dpapi').read_bytes(),True))
        account=Accounts(config.accounts_file).authenticate(identity['name'],identity['token']);assert account['id']==1
        settings=json.loads((ROOT/'config/server-settings.json').read_bytes())
        settings.update(host=host,state_file=str(game),accounts_file=str(config.accounts_file),tls_cert=str(config.tls_cert),tls_key=str(config.tls_key),log_dir=str(config.log_dir))
        raw=toml(settings);changed=(home/'server.toml').read_text('utf8')!=raw
        if changed:
            temp=home/('server.toml.'+uuid.uuid4().hex+'.tmp');temp.write_text(raw,'utf8');os.replace(temp,home/'server.toml')
        business_settings(home)
        return dict(ok=True,reused=True,account_id=1,home=str(home),configuration_updated=changed)
    assert not home.exists(),'Refusing a partial or foreign deployment directory'
    if not game.exists():
        from els_server.storage.game_schema import prepare
        from els_server.storage.characters import Characters
        game.parent.mkdir(parents=True,exist_ok=True);prepare(game);Characters(game,1)
    with closing(sqlite3.connect(game.as_uri()+'?mode=ro',uri=True))as db:
        owners={r[0]for r in db.execute('SELECT DISTINCT account_id FROM character_owners')}
        assert owners<={1},'Legacy owner identity must be established before provisioning'
    token=operation_token or uuid.uuid4().hex
    assert uuid.UUID(token).hex==token
    stage=home.with_name('unified-server.stage-'+token)
    assert stage.resolve().is_relative_to(workspace) and not stage.exists()
    stage.mkdir(parents=True)
    try:
        who=os.environ['USERDOMAIN']+'\\'+os.environ['USERNAME']
        subprocess.run(['icacls',str(stage),'/inheritance:r','/grant:r',who+':(OI)(CI)F','*S-1-5-18:(OI)(CI)F'],capture_output=True,check=True)
        from create_friends_certificate import create
        pin=create(stage,host)
        registry=Accounts(stage/'accounts.sqlite3');token=secrets.token_urlsafe(32)
        with closing(registry.connect())as db,db:
            db.execute('INSERT INTO accounts VALUES (1,?,?,1)',('local',hashlib.sha256(token.encode()).hexdigest()))
        registry.close()
        (stage/'owner.dpapi').write_bytes(protect(json.dumps(dict(name='local',token=token)).encode()))
        settings=json.loads((ROOT/'config/server-settings.json').read_bytes())
        settings.update(host=host,state_file=str(game),accounts_file=str(home/'accounts.sqlite3'),
            tls_cert=str(home/'server-cert.pem'),tls_key=str(home/'server-key.pem'),log_dir=str(home/'logs'))
        (stage/'server.toml').write_text(toml(settings),'utf8')
        (stage/'endpoint.json').write_text(json.dumps(dict(schema='els-unified-server-v1',host=host,port=settings['port'],certificate_sha256=pin))+'\n','utf8')
        business_settings(stage)
        os.rename(stage,home)
        return dict(ok=True,reused=False,account_id=1,home=str(home),game_save_changed=False)
    finally:
        if stage.exists():
            for parent in (stage,*stage.parents):
                assert not parent.is_symlink()and not parent.is_junction(),'Linked private staging path'
            assert stage.resolve().parent==home.parent.resolve() and stage.resolve().is_relative_to(workspace)
            assert not stage.is_symlink()and not stage.is_junction()
            assert all(not p.is_symlink()and not p.is_junction()for p in stage.rglob('*'))
            shutil.rmtree(stage)

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--workspace',type=Path,required=True);p.add_argument('--game-save',type=Path,required=True)
    args=p.parse_args();print(json.dumps(provision(args.workspace,args.game_save)))
