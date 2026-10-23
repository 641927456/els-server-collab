"""One official deterministic Essence pouch, using the existing cube ledger."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA
DATA=Path(__file__).resolve().parents[1]/'data/ep_essence_bag.json'
SHA='12c2c87dcd4691b42fb68a1e1ed7c94f6bd9bbbc533881451c0ce85af24dcb34'

@functools.lru_cache(maxsize=1)
def definitions():
    raw=DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('Essence pouch source changed')
    source=json.loads(raw);data=client_data()
    if (source['client_sha256']!=CLIENT_SHA or source['catalog_sha256']!=data.manifest['catalog_sha256']
            or (source['input_template'],source['output_template'],source['quantity'],source['selection_count'],source['extra_ED'],source['extra_key'],source['output_deadline'])!=(723604,723609,100,0,0,0,None)):
        raise ValueError('Essence pouch source identity')
    proof=source['native']
    if not proof['passed'] or proof['live_process_access'] is not False or proof['new_templates']!=2:raise ValueError('Essence pouch native evidence')
    native={r['template']:r for r in proof['rows']};result=[]
    for row in source['inventory']:
        template=row['template'];item=data.item(template);w=native[template]
        expected=(0,4,1,0) if template==723604 else (2,4,1000,1000) if template==723609 else None
        if (expected is None or (row['metadata'],row['group'],row['max_stack'],struct.unpack_from('<i',item['record'],0x10)[0])!=expected
                or (item['name'],item['metadata'],item['flags4'],item['flags8'])!=(row['name'],row['metadata'],row['flags4'],row['flags8'])
                or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or w['record_sha256']!=row['record_sha256'] or w['native_group']!=4
                or any((c['ok'],c['consumed'],c['template'],c['metadata'])!=(1,304,template,row['metadata']) for c in w['cases'])):
            raise ValueError('Essence pouch item metadata')
        with data.connect() as db:
            if db.execute('SELECT id FROM items WHERE name=?',(row['name'],)).fetchall()!=[(template,)]:raise ValueError('Ambiguous Essence pouch item')
        result.append(row)
    if [r['template']for r in result]!=[723604,723609]:raise ValueError('Essence pouch inventory scope')
    return tuple(result)

def entry():
    bag,reward=definitions()
    return dict(bag,selection_count=0,entries=[dict(template=reward['template'],quantity=100,name=reward['name'])])
