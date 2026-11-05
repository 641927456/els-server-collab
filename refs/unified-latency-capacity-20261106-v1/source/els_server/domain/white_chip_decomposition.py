"""Explicit current-chip decomposition compatibility economics.

CN current Exascale guide qualifies SystemChip->CircuitFragments product.
KR official recovery table documents20 fragments for a dismantled SystemChip.
Quantity20 is compatibility-v1 here, not claimed current CN retail quantity.
No native UI/filter/timing/stat calculation is duplicated.
"""
import hashlib
from els_server.game_data import client_data
POLICY='white-chip-dismantle-compat-v1'
TARGET=118638;REWARD=118445;QUANTITY=20
CN_SOURCE='https://els.ztgame.com/game/m_004-1724-003c7-057857.shtml?ms=805&mt=967'
KR_QUANTITY_SOURCE='https://cs.nexon.com/HelpBoard/popuphelpview/20050'
def quote(item):
 if item['template']!=TARGET:return None
 if item['group']!=1 or item['count']!=1 or item.get('sealed')or item.get('identified')is False or item.get('enhancement',0)<0:raise ValueError('Current unsealed bag system chip required')
 raw=client_data().item(TARGET)['record']
 if hashlib.sha256(raw).hexdigest()!='d78f1bdc700c6c24e048e694c99f853979ac68e10492fb4a3e26f987cd494d96':raise ValueError('Chip decomposition original source')
 # Existing inventory validation already checked all native base/tuning fields.
 # Protection deadlines are checked by the shared quote before this branch.
 return dict(template=REWARD,quantity=QUANTITY,input_template=TARGET,policy_id=POLICY,record_sha256=hashlib.sha256(raw).hexdigest())
def reward_definition():
 from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,TEMPLATE_MAX_STACKS
 d=client_data().item(REWARD)
 if(d['item_type'],d['metadata'])!=(6,2)or hashlib.sha256(d['record']).hexdigest()!='0d22f772a87166be92ba7d153ab6b466fd5ed4a9751d07464c8cbcb7c87f9108':raise ValueError('Circuit fragment original definition')
 if VERIFIED_TEMPLATES.get(REWARD)!=2 or TEMPLATE_BAG_GROUPS.get(REWARD)!=3 or TEMPLATE_MAX_STACKS.get(REWARD,0)<QUANTITY:raise ValueError('Fragment must be existing admitted inventory')
 return dict(template=REWARD,metadata=2,group=3,max_stack=TEMPLATE_MAX_STACKS[REWARD])
