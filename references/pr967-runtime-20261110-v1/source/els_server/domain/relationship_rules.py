"""Current native UnitType binding plus current official couple eligibility.

CN current guide: 10-second acceptance, opposite roles, Elsword/Elesis and
LuCiel/LuCiel excluded. Current LuCiel guide explicitly lists all15 roles.
https://els.ztgame.com/game/005-1687-0037c-677990.shtml?mf=892&ms=780&mt=890
https://els.ztgame.com/game/m_000-1582-001dd-878755.shtml?ms=471&mt=477
IDs below match current pinned Enum.UNIT_TYPE, not a legacy gender table.
"""
RING=269710
MALE=frozenset((1,4,6,9,12,14));FEMALE=frozenset((2,3,5,7,8,11,13,15))
def eligible(a,b):
 x,y=a['unit_type'],b['unit_type']
 if a['uid']==b['uid']or x not in MALE|FEMALE|{10}or y not in MALE|FEMALE|{10}:raise ValueError('Current couple character identities')
 if{x,y}=={1,8}or x==y==10:raise ValueError('Native current family/coupled-dual role exclusion')
 if 10 not in(x,y)and not((x in MALE and y in FEMALE)or(x in FEMALE and y in MALE)):raise ValueError('Current opposite-role couple eligibility')
 return True
