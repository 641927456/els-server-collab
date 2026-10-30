"""Original selected-event and four existing manufacture force books; no new source."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.protocol.protocol_codec import Event

REGISTRY_SHA='444b3ef5b5a82fc59777496eaef4ca043bfad2aa216450642863d7f39251355b'

class ForceRuleError(ValueError):
    def __init__(self,result,message):super().__init__(message);self.result=result

@functools.lru_cache(maxsize=1)
def catalog():
    path=Path(__file__).resolve().parents[1]/'data/boosting2026-force-inventory.json';raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=REGISTRY_SHA:raise ValueError('Selected force original registry checksum')
    source=json.loads(raw);rows=source['reward_books']+source['upgrade_books']
    if len(rows)!=21 or {r['item'] for r in rows}!={295707,295712,306002,295714,306004,295708,295713,306003,295709,295729,295739,295744,311066,311515,311521,295762,311512,311518,311524,311527,295750}:raise ValueError('Selected force inventory scope')
    from els_server.game_data import client_data
    data=client_data()
    native={(r['arguments'][1]['m_iSkillID'],int(rank)):template
        for r in source['related_native_skill_rows']
        for rank,template in r['arguments'][1]['m_iItemIDList'].items() if rank!='0'}
    for row in rows:
        item=data.item(row['item'])
        if (hashlib.sha256(item['record']).hexdigest()!=row['template_record_sha256'] or
            row['required_stage']!=3 or (row['native_rank'] not in (3,4,5) and (row['item'],row['native_rank'],row['native_grade'])not in((295762,6,6),(295750,6,6))) or
            native.get((row['skill'],row['source_list_index']))!=row['item'] or
            ((item['flags4']>>20)&15)!=row['native_grade']):raise ValueError('Original force book definition mismatch')
    from els_server.domain.change_force_inventory import catalog as change_catalog
    changes=change_catalog(include_starters=True)
    if set(changes)&{r['item'] for r in rows}:raise ValueError('Original force catalog collision')
    from els_server.domain.promotion_reward_boxes import common_force
    from els_server.domain.native_force_catalog import catalog as native_catalog
    native={r['item']:r for r in native_catalog()['books'] if r['native_common']}
    return {**{r['item']:r for r in rows},**native,**changes,295734:common_force()}

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
    if maximum not in (0,1,3) or type(value) is not int or not 0<=value<=maximum:
        raise ValueError('Selected force original seal-history bound')
    return value


def force_record(row):
    # Original902BC0 copies wire+9 to owned-entry+6. The original
    # force tooltip compares that byte with the source-template+D7.
    used=seal_used(row['template'],row.get('seal_used',0))
    return struct.pack('>iBiB',row['skill'],row['rank'],0,used)


def learned_notice(rule,used=0,*,owner=None):
    row=owned(dict(force_inventory=[dict(skill=rule['skill'],rank=rule['native_rank'],template=rule['item'],seal_used=used)]))[0]
    event=Event(0x201,kind=0x6cb,payload=struct.pack('>i',0)+force_record(row))
    if owner is None:return event
    from els_server.domain.native_skill_production import record as record_native_skill
    return record_native_skill(event,owner)
