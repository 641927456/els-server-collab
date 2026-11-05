"""Verified native element vectors; independent of transaction eligibility."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
from els_server.game_data import client_data,CLIENT_SHA


@functools.lru_cache(maxsize=1)
def inventory_definitions():
    catalog=json.loads((PROJECT_ROOT/'els_server/data/equipment_attribute_items.json').read_text(encoding='utf8'))
    raw=(PROJECT_ROOT/catalog['proof']).read_bytes();proof=json.loads(raw)
    if (catalog['client_sha256']!=CLIENT_SHA or proof['client_sha256']!=CLIENT_SHA
        or hashlib.sha256(raw).hexdigest()!=catalog['proof_sha256'] or proof['all_passed'] is not True
        or proof['count']!=43 or len(proof['rows'])!=43):raise ValueError('Attribute item native proof')
    result=[]
    for row in catalog['items']:
        definition=client_data().item(row['template']);evidence=[r for r in proof['rows'] if r['template']==row['template']]
        if not evidence or hashlib.sha256(definition['record']).hexdigest()!=row['record_sha256']:raise ValueError('Attribute item definition identity')
        for witness in evidence:
            if (witness['ok']!=1 or witness['applied_to_game'] is not False or not witness['fields_match']
                or not witness['other_vectors_empty'] or witness['consumed']!=304+4*len(witness['expected'])
                or witness['size']!=witness['consumed'] or witness['actual']!=witness['expected']
                or witness['object_slots']!=witness['expected']+[0]*(4-len(witness['expected']))
                or witness['native_group']!=row['group'] or witness['metadata']!=row['metadata']
                or witness['record_sha256']!=row['record_sha256']):raise ValueError('Attribute item body mismatch')
        if row['metadata']!=definition['metadata'] or row['max_stack']!=(1 if definition['item_type'] in (1,2) else 99):raise ValueError('Attribute item policy mismatch')
        result.append(dict(row))
    if len(result)!=10 or len({r['template'] for r in result})!=10:raise ValueError('Attribute item coverage')
    return tuple(result)


def validate_slots(template,slots):
    if not isinstance(slots,(list,tuple)) or len(slots)!=4 or any(type(s) is not int or not 0<=s<=6 for s in slots):raise ValueError('Four equipment elements required')
    definition=client_data().item(template)
    if definition['item_type'] not in (1,2) or sum(s>0 for s in slots)>definition['record'][0xd8]:raise ValueError('Equipment attribute capacity')
    elements=set(slots)
    if len(elements&{1,2,3})>1 or len(elements&{4,5,6})>1:raise ValueError('Incompatible equipment elements')
    return list(slots)
