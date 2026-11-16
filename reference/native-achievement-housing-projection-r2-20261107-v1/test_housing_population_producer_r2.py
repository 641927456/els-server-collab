"""Call the actual housing population producer and replay its original reader."""
from pathlib import Path
from contextlib import closing
import hashlib,importlib, json,sqlite3,sys,tempfile,time,traceback
A=Path(__file__).resolve().parent;F=A/'release-integration-v1/housing-projection-r2'
sys.path.insert(0,str(A/'release-integration-v1/qa'))
from test_full_unit_projection import Characters,state,UnitReplay,status,stream
import els_server.storage
els_server.storage.__path__.insert(0,str(F/'source-v1/els_server/storage'))
from els_server.storage import housing_rooms
housing_rooms=importlib.reload(housing_rooms)
assert Path(housing_rooms.__file__).resolve()==(F/'source-v1/els_server/storage/housing_rooms.py').resolve()
from els_server.storage.game_schema import prepare
from els_server.domain.achievement_catalog import achievement
report=dict(ok=False,production_database_access=False,native_Game=False,natural_GUI=False,original_native_reader=True,checks=[])
try:
    with tempfile.TemporaryDirectory(prefix='owned-housing-projection-',dir=F)as folder:
        path=Path(folder)/'own.sqlite3';prepare(path)
        first=Characters(path,1).create('HouseStatA',1,'owned-house-status')['uid']
        other=Characters(path,2).create('HouseStatB',2,'owned-house-other')['uid']
        with closing(sqlite3.connect(path))as db,db:
            db.execute('BEGIN IMMEDIATE')
            state.record(db,1,first,[dict(achievement=19,condition=c['id'],value=1,complete=True)for c in achievement(19)['conditions']],
                'owned-housing-completion',int(time.time()))
            state.toggle_display(db,1,first,19,'owned-housing-display')
        replay=UnitReplay()
        with closing(sqlite3.connect(path))as db:
            db.execute('BEGIN');before=list(db.iterdump())
            actual=[]
            for owner,account,expected in((first,1,dict(points=[10,0,0,0],watched=[19],state_flag=False)),
                (other,2,dict(points=[0,0,0,0],watched=[],state_flag=False))):
                for _ in range(2):
                    packet=housing_rooms.population(db,owner,account,[1.,2.,3.])
                    assert packet.kind==0x92f and packet.payload[:8]==bytes.fromhex('0000000000000001')
                    raw=packet.payload[8:-12];source,buffer=stream(replay,raw)
                    dto=replay.alloc(0x13d);replay.call(0x2c44880,dto)
                    assert replay.call(0xda4eb0,source,dto)&255==1
                    assert int.from_bytes(replay.read(buffer+32,4),'little')==len(raw)
                    observed=status(replay,dto+0xa6);actual.append(observed)
                    assert observed==expected,(observed,expected)
            try:housing_rooms.population(db,first,2,[1.,2.,3.])
            except ValueError:pass
            else:raise AssertionError('Housing wrong account accepted')
            assert before==list(db.iterdump())
        report.update(ok=True,observed=actual,checks=['Actual housing population92F producer preserves existing account points and character display',
            'OriginalDA4EB0 consumes every member byte on repeat; a foreign account has four zero scores and no display',
            'Wrong account is rejected; all reads leave the private database unchanged'])
except BaseException:report['error']=traceback.format_exc()
report['housing_source_sha256']=hashlib.sha256((F/'source-v1/els_server/storage/housing_rooms.py').read_bytes()).hexdigest()
output=F/('actual-housing-population-'+str(time.time_ns())+'.json');output.write_text(json.dumps(report,ensure_ascii=False,indent=2),'utf8')
print(json.dumps(report,ensure_ascii=False));raise SystemExit(not report['ok'])
