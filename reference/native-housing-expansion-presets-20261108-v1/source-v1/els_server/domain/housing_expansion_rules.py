"""Current native housing expansion readers and human-approved ED offers."""
import hashlib,struct
from functools import lru_cache
from els_server.game_data import client_data
STEP_ITEMS=(136030,136031,136032,136033)
FLOOR_ITEMS=(136244,136242,136243,136241)
PRESET_ITEMS=(136248,136246,136247,136245)
SHOP_ITEMS=STEP_ITEMS+(136241,136245)
OWNED_ONLY=frozenset(FLOOR_ITEMS+PRESET_ITEMS)-frozenset(SHOP_ITEMS)
ROWS=((136030, 4198408, '89a32789a2ef7906d8bc357b505736684de7bc6356d05c17fd2d32310c4d926e'), (136031, 4198408, '9d100a938c085d2237bb23d08c3b7b2e6553eca009883e06b8507ffe56d3b848'), (136032, 4198408, 'e5227c61421141f5f21a4d0809703ae9445c3ed249bf0131642c487befc6d98f'), (136033, 4198408, '6556f7a56db40b75425f345b8cc97676507d6b9f67f86a97c8021cd84d2ce3e9'), (136241, 4198408, '37b3e9cefd7cfd3f307f50f4eabbe636efda9238364f2efcdbf6526a60bb5820'), (136242, 4198410, 'e3dbc5370f53fa6d059c05e9847ed9c5abce8bc087dc75f2d640c37150caec82'), (136243, 4198410, '8585c5cefd5c48a47115f8ac5575ccedeb5b929e7a86e10bf89002abe2d07aa6'), (136244, 4198410, '743e617e5323e1327a500ed7cd3bb41e78286171fad154132a07213557af9dd8'), (136245, 4198408, 'c9906ac487326919bb1b12c743e8a92175d3f0f66c19609b1016d16f40176051'), (136246, 4198410, '662047b4489e6a8d6a1e9653819fd9e7e027ffad1620366596eace4820545ef0'), (136247, 4198410, 'f034cbe8e0f3e76e92acfbe3a24029c4b2e9c7fd14cd68acc2043acf5a923f5c'), (136248, 4198410, 'd40dc491293485e30316aa2ce81b54f352e33d8c4f2cea86bf75a0f8f4891585'))

@lru_cache(maxsize=1)
def definitions():
 rows=[]
 for t,flags,digest in ROWS:
  i=client_data().item(t)
  if (i['item_type'],i['metadata'],i['flags4'],i['flags8'],struct.unpack_from('<I',i['record'],16)[0])!=(7,0,flags,56,0)or hashlib.sha256(i['record']).hexdigest()!=digest:
   raise ValueError('Housing expansion native item definition')
  rows.append(dict(template=t,metadata=0,group=4,max_stack=1))
 return tuple(rows)
