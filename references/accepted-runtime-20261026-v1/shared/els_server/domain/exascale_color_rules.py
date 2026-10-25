"""Original explicit color triples; transaction and voucher admission stay separate."""
import functools,hashlib,json,copy
from pathlib import Path
from els_server.domain.equipment_circuit_rules import target,validate_grid,active_slots,uniform_color

POLICY_SHA='7a11d27f537177bc6b97e8c877d7010ee36a653cf4b5d53039346ede569b0ce0'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/exascale_color.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=POLICY_SHA:raise ValueError('Color policy identity changed')
    return json.loads(raw)

@functools.lru_cache(maxsize=1)
def color_map():return {value:tuple(row) for row in catalog()['triples'] for value in row}

def voucher_rule(template):
    row=catalog()['targets'].get(str(template))
    if row is None or target(template)!= {k:v for k,v in row.items() if k!='reforge_class'}:
        raise ValueError('Unqualified color armor')
    return next(r for r in catalog()['rows'] if (r['reforge_class'],r['part'])==(row['reforge_class'],row['part']))

def recolor(template,groups,color):
    if type(color) is not int or color not in (1,2,3):raise ValueError('Color enum')
    voucher_rule(template)
    if not isinstance(groups,dict):raise ValueError('Color option groups')
    grid=validate_grid(template,groups.get('28',[]));old_color=uniform_color(template,grid)
    if not old_color or old_color==color:raise ValueError('Activated different-color set required')
    slots=active_slots(template,grid);mapping=color_map()
    for slot in slots:
        if grid[slot] not in mapping:raise ValueError('No original color conversion triple')
        grid[slot]=mapping[grid[slot]][color-1]
    if active_slots(template,grid)!=slots or uniform_color(template,grid)!=color:raise ValueError('Color conversion changed connectivity')
    result=copy.deepcopy(groups);result['28']=grid
    return result
