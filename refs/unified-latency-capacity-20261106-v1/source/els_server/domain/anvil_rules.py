"""Modern anvil;100XP/initial-empty are explicitly local server policy.

Official2021 revamp: one noninventory hammer per8h,100000ED, level capacity.
Current client definitions and clock consumers remain authoritative for wire/UI.
No old random equipment pool, old durability recovery, timer or hammer spend.
"""
from els_server.profession_data import profession_data
from els_server.protocol.profession_messages import ProfessionState,state_wire
XP_PER_USE=100  # User-authorized local supplement, not a retail XP claim.
HAMMERS_PER_USE=1
def integer(value,low,high,name):
 if type(value)is not int or not low<=value<=high:raise ValueError(name)
 return value
def policy(state):
 if not isinstance(state,ProfessionState):raise ValueError('Smith state')
 state_wire(state)
 if state.profession!=2 or not 1<=state.level<=10:raise ValueError('Current blacksmith required')
 if state.level<10 and(state.required<=0 or state.progress>=state.required):raise ValueError('Unknown saved blacksmith denominator')
 data=profession_data();cost=data.template(2)['m_CostED'];period=data.registrations('SetResetAnvilPeriod')
 if cost!={'0':None,'1':1,'2':100000}or period!=[[8]]:raise ValueError('Anvil source policy changed')
 rows=data.registrations('AddMaxBlackSmithHammerByLevel');capacities=dict(rows)
 if len(rows)!=10 or capacities!={i:2*i for i in range(1,11)}:raise ValueError('Anvil capacity source changed')
 return dict(ed=cost['2'],cooldown_seconds=period[0][0]*3600,capacity=capacities[state.level],hammer_gain=HAMMERS_PER_USE,requested_xp=XP_PER_USE)
