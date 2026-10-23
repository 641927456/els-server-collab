"""Current no-hammer smith enhancement; old70 XP is an explicit local fallback.

Current material matrix and KR published success table take priority. Ordinary
enhancement, zero-mithril levels, hammers, auto-recovery and scene3 selections
are outside this independent path.
"""
import functools,hashlib,json
from pathlib import Path
from els_server.domain.paid_enhancement import quote as ordinary_quote,RATES,STONES
from els_server.domain.gm_rates import snapshot as gm_snapshot
from els_server.protocol.profession_messages import ProfessionState,state_wire
DATA=Path(__file__).resolve().parents[1]/'data/client'
SOURCE_SHA='c63550c89bae1b79b3f91c5552e57be65c05624ce7acacc6c3ce731b9393d9ef'
DENOMINATOR=100000

@functools.lru_cache(maxsize=1)
def materials():
    raw=(DATA/'professions.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SOURCE_SHA:raise ValueError('Smith profession source changed')
    matrix={};template=None
    for call in json.loads(raw)['__symbolic_calls__']:
        family=call['function'].split('.')[-1]
        if family=='AddSpecialMaterialItemDataByLevel':
            row=call['arguments'][1];target=row['AFTER_ENCHANT_LEVEL']
            matrix[target]={pair['1']:pair['2'] for pair in row['MATERIAL_QUANTITY_BY_LEVEL'].values()}
        elif family=='SetSpecialMaterialItemID':
            template=call['arguments'][1]['SPECIAL_ENCHANT_ITEM_ID']['1']
    if template!=118204 or set(matrix)!=set(range(1,14)) or any(set(row)!=set(range(1,11)) for row in matrix.values()):
        raise ValueError('Smith material matrix')
    return template,matrix

def xp_for_target(target):
    if type(target) is not int or not 1<=target<=13:raise ValueError('Smith XP target')
    # ELS70 GSUserInventory3471..3502: advanced smith, non-debug, real mithril.
    return 100 if target>=13 else 70 if target>=11 else 40 if target>=9 else 20 if target>=7 else 10 if target>=5 else 5

def quote(item,mode,state):
    state_wire(state)
    if not isinstance(state,ProfessionState) or state.profession!=2 or not 1<=state.level<=10:
        raise ValueError('Current blacksmith profession required')
    if state.level<10 and (state.required<=0 or state.progress>=state.required):
        raise ValueError('Unknown or inconsistent saved smith denominator')
    if mode not in (0,1,2):raise ValueError('Unsupported smith enhancement mode')
    q=ordinary_quote(item,mode)
    level=q['level']
    if not 7<=level<=12:raise ValueError('Smith material-positive enhancement scope')
    template,matrix=materials();quantity=matrix[level+1][state.level]
    if type(quantity) is not int or not 1<=quantity<=100:raise ValueError('Positive current mithril quantity required')
    if gm_snapshot()['enhancement'][level] is not None:raise ValueError('Custom GM smith success rule is not qualified')
    # Official guide62: success*1.05, subtract only the extra from no-change.
    # 10->11 is735/100000; never round it to basis points or use old jump procs.
    rates=[n*10 for n in RATES[level]];extra=RATES[level][0]//2
    rates[0]+=extra;rates[1]-=extra
    if any(n<0 for n in rates) or sum(rates)!=DENOMINATOR:raise ValueError('Smith success table')
    return dict(q,material=template,quantity=quantity,rates=rates,denominator=DENOMINATOR,
                xp=xp_for_target(level+1),ore_free=mode==1 and level in (7,8))

def outcome(q,roll):
    if type(roll) is not int or not 0<=roll<q['denominator']:raise ValueError('Smith RNG bound')
    total=0;level=q['level'];mode=q['mode']
    for index,weight in enumerate(q['rates']):
        total+=weight
        if roll<total:
            result,updated=((1,level+1),(3,level),(4,level-1),(5,0),(2,-level))[index]
            if mode==1 and result in (4,5) or mode==2 and result==5:return 3,level
            return result,updated
    raise ValueError('Incomplete smith success table')
