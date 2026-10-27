"""Existing hunter coin conversion, explicit20261024 local economic policy.

Current wire, coins and fee are reused. Two modern material weights, quantities,
XP5/10/20 and subsequent hunter step costs are local choices, not retail facts.
No coin/chest source or hunter selection is created by this independent unit.
"""
from dataclasses import replace
import functools,hashlib,struct
from els_server.game_data import client_data
from els_server.protocol.profession_messages import ProfessionState,state_wire

FEE=100000
COINS={117527:(80,1,5),117528:(50,1,10),118092:(50,2,20)}
STEPS={1:400,2:700,3:1100,4:1600,5:5200,6:10800,7:18800,8:29600,9:43600}
RECORDS={
117527:(7,4,300,'caa9c86fb31774c9d96398d398a6e029fbd0880a3c9fa1c0a6fded519a1df15f'),
117528:(7,4,300,'c63d24bf2e577066c960d2c1fbaaadf7f202dd601c13787cabbbe46394d23bfc'),
118092:(7,4,300,'e47d6d7f3afaf50c9fec7dcb330c2ca58a49c35a2e4956ba737bbe8a67311b48'),
118204:(6,3,1000,'35a2511b9161e41d6675d3111e99b2b4815ec2c898e9362ecb5c0d620de898b1'),
118205:(6,3,1000,'499d4530345dfa0e1156cd9a20e45f710026bbce79a0aa8b2a3e33a159336ff4')}

@functools.lru_cache(maxsize=1)
def definitions():
    rows=[]
    for template,(kind,group,maximum,digest) in RECORDS.items():
        d=client_data().item(template);raw=d['record']
        if (d['item_type'],d['metadata'],struct.unpack_from('<I',raw,16)[0])!=(kind,2,maximum) or hashlib.sha256(raw).hexdigest()!=digest:
            raise ValueError('Hunter sphere current item definition changed')
        rows.append(dict(template=template,metadata=2,group=group,max_stack=maximum))
    return rows

def plans(coin):
    definitions()
    if type(coin)is not int or coin not in COINS:raise ValueError('Current sphere coin ID')
    weight,quantity,xp=COINS[coin]
    return [dict(template=t,metadata=2,group=3,quantity=quantity)for t in (118204,118205)]

def reward(coin,roll):
    if type(roll)is not int or not 0<=roll<100:raise ValueError('Sphere RNG bound')
    return plans(coin)[0 if roll<COINS[coin][0]else 1]

def advance(state,coin):
    if not isinstance(state,ProfessionState):raise ValueError('Sphere profession state')
    state_wire(state)
    if state.profession!=1 or not 1<=state.level<=10:raise ValueError('Existing hunter required')
    requested=COINS[coin][2]
    if state.level==10:return state,0
    if state.required<=0 or state.progress>=state.required:raise ValueError('Unknown hunter saved denominator')
    delta=min(requested,state.required-state.progress+sum(STEPS[n]for n in range(state.level+1,10)))
    if state.experience+delta>=2**31:raise ValueError('Hunter XP overflow')
    level,progress,required=state.level,state.progress+delta,state.required
    while level<10 and progress>=required:
        progress-=required;level+=1;required=STEPS.get(level,0)
    if level==10:progress=required=0
    updated=replace(state,level=level,experience=state.experience+delta,progress=progress,required=required)
    state_wire(updated);return updated,delta
