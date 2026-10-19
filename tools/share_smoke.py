"""Check relocation and graceful startup only; never opens a game or owner save."""
from pathlib import Path
from contextlib import closing
import json,subprocess,sys,tempfile,time,sqlite3
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from els_server.config import ServerConfig
from els_server.game_data import client_data
cfg=ServerConfig.load(ROOT/'config/server.toml')
assert cfg.state_file.is_relative_to(ROOT/'state')
with tempfile.TemporaryDirectory(prefix='els-share-smoke-') as folder:
    tmp=Path(folder);stop=tmp/'server.stop'
    conf=tmp/'server.toml'
    content='[server]\nhost="127.0.0.1"\nport=0\nprofile="integrated_dx11"\nstate_file="save.sqlite3"\nlog_dir="logs"\nattribute_enchant_enabled=true\nnormal_equipment_moves_enabled=true\nequipment_repair_enabled=true\n'
    if cfg.selected2026_pair_file is not None:
        content+='selected2026_pair_file='+json.dumps(str(cfg.selected2026_pair_file))+'\n'
    conf.write_text(content,encoding='utf8')
    out=tmp/'stdout.txt';err=tmp/'stderr.txt'
    with out.open('w',encoding='utf8') as stdout,err.open('w',encoding='utf8') as stderr:
        proc=subprocess.Popen([sys.executable,'-B','-m','els_server','--config',str(conf),'--stop-file',str(stop)],cwd=ROOT,stdout=stdout,stderr=stderr)
        try:
            log=tmp/'logs/server.jsonl';deadline=time.monotonic()+120
            while time.monotonic()<deadline and proc.poll() is None:
                if log.exists() and '"event": "listening"' in log.read_text(encoding='utf8'):break
                time.sleep(.1)
            else:raise RuntimeError('Server did not become ready: '+err.read_text(encoding='utf8'))
            stop.write_text('share smoke test',encoding='utf8')
            proc.wait(timeout=25)
            if proc.returncode:raise RuntimeError(err.read_text(encoding='utf8'))
            events=[json.loads(line) for line in log.read_text(encoding='utf8').splitlines()]
            assert any(e['event']=='finished' and e['active']==0 for e in events)
            assert any(e['event']=='database_checkpoint' and e['result'][0]==0 for e in events)
            with closing(sqlite3.connect(tmp/'save.sqlite3')) as db:
                assert db.execute('pragma quick_check').fetchone()==('ok',)
                roles=db.execute('select name from characters').fetchall()
                assert ('Player8',) not in roles
        finally:
            if proc.poll() is None:
                stop.write_text('cleanup',encoding='utf8')
                try:proc.wait(timeout=25)
                except subprocess.TimeoutExpired:
                    proc.terminate();proc.wait(timeout=10)
print(json.dumps(dict(ok=True,check='relocated-server-empty-disposable-save-graceful-stop',client_started=False,owner_database_accessed=False),indent=2))
