"""Five original selected-event force books; owned forces are not normal skills."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.protocol.protocol_codec import Event

REGISTRY_SHA='e0adb12f1e59a3f3048e7f4896fcc6172751c2f5887ec9bf59bc42025cedf048'

class ForceRuleError(ValueError):
    def __init__(self,result,message):super().__init__(message);self.result=result

@functools.lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).resolve().parents[1]/'data/boosting2026-force-inventory.json';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=REGISTRY_SHA:raise ValueError('Selected force original registry checksum')
    source=json.loads(raw);rows=source['reward_books']
    if len(rows)!=5 or {r['item'] for r in rows}!={295707,295712,306002,295714,306004}:raise ValueError('Selected force inventory scope')
    from els_server.game_data import client_data
    data=client_data()
    for row in rows:
        item=data.item(row['item'])
        if (hashlib.sha256(item['record']).hexdigest()!=row['template_record_sha256'] or
            row['required_stage']!=3 or row['native_rank'] not in (3,5) or
            ((item['flags4']>>20)&15)!=row['native_grade']):raise ValueError('Original force book definition mismatch')
    return {r['item']:r for r in rows}

def owned(character):
    values=(character or {}).get('force_inventory',())
    if not isinstance(values,(list,tuple)) or len(values)>len(catalog()):raise ValueError('Selected force ownership bound')
    result=[];seen=set()
    for row in values:
        if not isinstance(row,dict) or set(row) not in ({'skill','rank','template'},{'skill','rank','template','seal_used'}):raise ValueError('Selected force ownership fields')
        rule=catalog().get(row['template'])
        if rule is None or (row['skill'],row['rank'])!=(rule['skill'],rule['native_rank']):raise ValueError('Selected force ownership identity')
        key=(row['skill'],row['rank'])
        if key in seen:raise ValueError('Duplicate selected force skill and rank')
        seen.add(key);result.append(dict(row,seal_used=seal_used(row['template'],row.get('seal_used',0))))
    return tuple(sorted(result,key=lambda r:(r['skill'],r['rank'])))

def vector(character=None):
    rows=owned(character)
    # D9AD50+196 -> full unit DTO+2E4 -> 87A6E0 ->902B60.
    return struct.pack('>I',len(rows))+b''.join(force_record(r) for r in rows)

def seal_used(template,value):
    rule=catalog().get(template)
    if rule is None:raise ValueError('Selected force seal identity')
    from els_server.game_data import client_data
    maximum=client_data().item(template)['record'][0xd7]
    if maximum not in (0,1) or type(value) is not int or not 0<=value<=maximum:
        raise ValueError('Selected force original seal-history bound')
    return value


def force_record(row):
    # Original902BC0 copies wire+9 to owned-entry+6. The original
    # force tooltip compares that byte with the source-template+D7.
    used=seal_used(row['template'],row.get('seal_used',0))
    return struct.pack('>iBiB',row['skill'],row['rank'],0,used)


def learned_notice(rule,used=0):
    row=owned(dict(force_inventory=[dict(skill=rule['skill'],rank=rule['native_rank'],template=rule['item'],seal_used=used)]))[0]
    return Event(0x201,kind=0x6cb,payload=struct.pack('>i',0)+force_record(row))
