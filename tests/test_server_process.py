"""Exercise the real CLI, save preservation and graceful restart in a child process."""
from contextlib import closing
import json
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='service-process-',dir=ROOT/'analysis') as folder:
    root=Path(folder)
    source=ROOT/'analysis/server-refactor-20261014/integrated-before.sqlite3'
    state=root/'save.sqlite3'
    with closing(sqlite3.connect(source.as_uri()+'?mode=ro',uri=True)) as src,closing(sqlite3.connect(state)) as dst:
        src.backup(dst)
        tables=[r[0] for r in dst.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
        before={t:sorted(dst.execute('SELECT * FROM "'+t+'"').fetchall(),key=repr) for t in tables}
    migrated=None
    config=root/'server.toml'
    config.write_text('[server]\nport=0\nprofile="integrated_dx11"\nstate_file="save.sqlite3"\nlog_dir="logs"\n',encoding='utf8')
    stop=root/'stop'
    for cycle in range(2):
        if stop.exists():stop.unlink()
        logdir=root/f'logs-{cycle}'
        process=subprocess.Popen([sys.executable,'-m','els_server','--config',str(config),
                                  '--stop-file',str(stop),'--log-dir',str(logdir)],cwd=ROOT,
                                  stdout=subprocess.DEVNULL,stderr=subprocess.PIPE)
        try:
            deadline=time.monotonic()+15
            path=logdir/'server.jsonl'
            while time.monotonic()<deadline and process.poll() is None:
                if path.exists() and '"event": "listening"' in path.read_text(encoding='utf8'):break
                time.sleep(.05)
            else:raise AssertionError('Server readiness failed')
            stop.write_text('test graceful shutdown',encoding='utf8')
            _,stderr=process.communicate(timeout=20)
            assert process.returncode==0,stderr.decode(errors='replace')
            events=[json.loads(line) for line in path.read_text(encoding='utf8').splitlines()]
            assert any(e['event']=='finished' and e['active']==0 for e in events)
            assert any(e['event']=='database_checkpoint' and e['result'][0]==0 for e in events)
            with closing(sqlite3.connect(state)) as db:
                assert db.execute('PRAGMA quick_check').fetchone()==('ok',)
                for table,rows in before.items():
                    assert sorted(db.execute('SELECT * FROM "'+table+'"').fetchall(),key=repr)==rows,table+' lost or changed saved rows'
                assert db.execute('SELECT uid,name,unit_type,unit_class FROM characters').fetchall()==[(1001,'LocalElsword',1,1)]
                assert db.execute('SELECT COUNT(*) FROM character_artifacts').fetchone()==(0,)
                dump=list(db.iterdump())
                if migrated is not None:assert dump==migrated,'Repeated startup changed migrated save'
                migrated=dump
        finally:
            if process.poll() is None:
                stop.write_text('cleanup',encoding='utf8')
                try:process.communicate(timeout=20)
                except subprocess.TimeoutExpired:process.terminate();process.communicate(timeout=5)
print('PASS: real service starts/stops twice, legacy rows preserved, character migration idempotent, clean WAL checkpoint and lock release.')
