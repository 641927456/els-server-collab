"""User-authorized old70 blacksmith XP fallback, not a retail growth curve.

No read-time migration or Alchemy policy changes. Current stored denominators win;
subsequent steps use the explicit old70 local-server table.
"""
from dataclasses import replace
from els_server.protocol.profession_messages import ProfessionState, state_wire

BLACKSMITH_STEPS = {1:400,2:700,3:1100,4:1600,5:5200,6:10800,7:18800,8:29600,9:43600}
MAXIMUM = 2**31-1

def ordinary_blacksmith_xp(item_level):
    if type(item_level) is not int or not 1<=item_level<=80:
        raise ValueError('Unqualified ordinary dismantle item level')
    return 40 if item_level>=70 else 25 if item_level>=50 else 15 if item_level>=30 else 5

def advance_blacksmith(state, requested):
    if not isinstance(state,ProfessionState) or type(requested) is not int or not 0<=requested<=MAXIMUM:
        raise ValueError('Blacksmith XP request')
    state_wire(state)
    if state.profession!=2 or requested==0:return state,0,False
    if not 1<=state.level<=10:raise ValueError('Blacksmith profession level')
    if state.level==10 or state.required==0:return state,0,False
    required=state.required
    if state.progress>=required:raise ValueError('Stored blacksmith progress needs separate recovery')
    remaining=required-state.progress+sum(BLACKSMITH_STEPS[n] for n in range(state.level+1,10))
    granted=min(requested,remaining)
    if state.experience+granted>MAXIMUM or state.progress+granted>MAXIMUM:
        raise ValueError('Blacksmith XP overflow')
    level,progress=state.level,state.progress+granted
    while level<10 and progress>=required:
        progress-=required;level+=1
        required=BLACKSMITH_STEPS.get(level,0)
    if level==10:progress=required=0
    updated=replace(state,level=level,experience=state.experience+granted,progress=progress,required=required)
    state_wire(updated)
    return updated,granted,level!=state.level
