"""Bind legacy family-coded custom books to their source-consistent base class."""
from pathlib import Path
import hashlib,json,re,sys
W=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(W/'candidate'))
from els_server.game_data import client_data
from els_server.storage.characters import BASE_CLASSES
scope=json.loads((W/'candidate-scope.json').read_bytes())
changes=[]
for channel in ('candidate','local-candidate'):
    root=W/channel;p=root/'els_server/data/character_custom_permanent.json'
    d=json.loads(p.read_bytes());updated=[]
    for row in d['books']:
        if row['book']not in scope['added_books']:continue
        raw=client_data().item(row['book'])['record'];role=row['unit_type']
        if role>=10 and raw[211]==role:
            assert raw[210]==role and row['units']==[role]
            row['required_class']=BASE_CLASSES[role]
            updated.append(dict(book=row['book'],native_class_byte=raw[211],custom_source_unit=role,effective_base_class=BASE_CLASSES[role]))
    assert [r['book']for r in updated]==[470338],updated
    p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n','utf8')
    domain=root/'els_server/domain/character_custom.py';s=domain.read_text('utf8')
    s,n=re.subn(r"hexdigest\(\)!='[a-f0-9]{64}'","hexdigest()!='"+hashlib.sha256(p.read_bytes()).hexdigest()+"'",s,count=1)
    assert n==1;domain.write_text(s,'utf8');changes.append(dict(channel=channel,changes=updated))
(W/'book-class-correction.json').write_text(json.dumps(dict(changes=changes,
    basis='Native type14 SIT_MOTION UNIT_TYPE11 and item D2=11 agree. The old D3=11 conflicts with current class11(Elsword); current Rose base class is201. Preserve unit authority and bind only this qualified source to201, following existing per-book required_class mechanism. No level/stage restriction removed or class flags forged.'),ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,book=470338,source_role=11,effective_base_class=201)))
