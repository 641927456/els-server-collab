"""Read one original UI resource offline, without any live process or archive write."""
from pathlib import Path
import hashlib,json,sys,zlib
R=Path('G:/els');F=Path(__file__).resolve().parent;B=R/'releases/online/native-achievement-spa-buff-history-20261107-v2'
sys.dont_write_bytecode=True;sys.path[:0]=[str(B),str(R/'tools'),str(R/'tools/pylibs'),str(R)]
from els_server.game_data import client_data
with client_data().connect()as db:print(json.dumps(dict(existing_related_resources=[r[0]for r in db.execute("SELECT name FROM resources WHERE name LIKE '%House%'OR name LIKE '%World%'OR name LIKE '%Noah%Memo%'")]),ensure_ascii=False),flush=True)
from seal_quest_resources import ResourceReplay,IMAGE_SHA
from extract_launcher_assets import index
from read_kl_bytecode import read
archive=Path('D:/艾尔之光/data/data039.kom');sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
before=sha(archive);entries=index(archive,(R/'analysis/x2-runtime.bin').read_bytes());name='UI_NPC_NOAH_MEMO.lua';e=next(e for e in entries if e['Name']==name)
mapping=json.loads((R/'analysis/seal-quests-20261015/mapped-key-witness.json').read_bytes())
with archive.open('rb')as stream:stream.seek(e['offset']);blob=stream.read(int(e['CompressedSize']))
token=e['MappedID'].encode();rotate=int(e['Size'])%8
if rotate:token=token[-rotate:]+token[:-rotate]
keys=[r['key']for r in mapping if r['token'].encode()==token];assert keys
for key in keys:
    decoded=ResourceReplay().decode(blob,key)
    for skip in(0,4):
        try:plain=zlib.decompress(decoded[skip:])
        except zlib.error:continue
        if len(plain)==int(e['Size'])and plain[:4]==b'\x1bKL\x82':break
    else:continue
    break
else:raise ValueError('No matching original UI transform')
assert sha(archive)==before
(F/name).write_bytes(plain);dump=read(plain,max_prototype_entries=2000000)
(F/(name+'.bytecode.json')).write_bytes((json.dumps(dump,ensure_ascii=False,indent=2)+'\n').encode())
proof=dict(name=name,archive=str(archive),archive_sha256=before,source=e,key=key,skip=skip,sha256=sha(F/name),image_sha256=IMAGE_SHA,live_process_access=False,lua_evaluated=False,original_archive_modified=False)
(F/'resource-proof.json').write_bytes((json.dumps(proof,ensure_ascii=False,indent=2)+'\n').encode());print(json.dumps(proof),flush=True)
