"""Original481/483 ordinary pages; missing economic values are local policy.

Source: dx11_260923 9BDFE0/9BE350/9BE930/9BEC10,13A34F0,DE14C0.
Policy: ordinary-skill-pages-local-20261024-v1; these are not retail fees/caps.
"""
import struct,sqlite3,uuid
from pathlib import Path
from els_server.protocol.protocol_codec import Event

POLICY='ordinary-skill-pages-local-20261024-v1'
MAX_PAGES=3
EXPAND_ED=10000000

def request(kind,payload):
 if type(payload)is not bytes:raise ValueError('Ordinary page request bytes')
 if kind==0x481:
  if payload:raise ValueError('Ordinary expansion request must be empty')
  return None
 if kind!=0x483 or len(payload)!=4:raise ValueError('Ordinary page selection request')
 value=struct.unpack('>i',payload)[0]
 if not 1<=value<=MAX_PAGES:raise ValueError('Ordinary page index')
 return value

def page_character(character,snapshot):
 from els_server.domain.boosting_2026_force_inventory import owned
 from els_server.domain.boosting_2026_force_equipment import slots
 # Ownership is shared, equipment selection is per page. Extracted grades
 # cannot be recreated by a dormant page's older snapshot.
 pairs={(r['skill'],r['rank'])for r in owned(character)}
 force=[tuple(p)if tuple(p)in pairs else (0,0)for p in snapshot['force']]
 from els_server.domain.boosting_2026_force_equipment import active_skill
 for index in range(3,11):
  current=tuple(character['force_slots'][index])
  if current[0] and active_skill(current[0]):
   if force[index]!=(0,0) and force[index]!=current:raise ValueError('Dormant change force would overwrite preserved type20 reference')
   force[index]=current
 from els_server.domain.skill_traits import visible
 result=dict(character,skill_traits=visible(character,snapshot['traits']),force_slots=force)
 slots(result)
 return result

def page_slots(character,snapshot):
 from els_server.domain.skill_rules import upgraded_slots,equippable_skills
 from els_server.domain.role_progression import known_skills
 from els_server.domain.skill_state import validate_slots
 #Use the existing career writer's learned/upgrade projection. A dormant
 #same-character previous-route ID is valid stored input, but never grants a
 #skill unavailable to the current route. Unknown/other-character IDs reject.
 from els_server.domain.character_rules import CLASSES
 cls=character['unit_class'];base=CLASSES[cls]['base_class']
 known=set().union(*(known_skills(k)for k,v in CLASSES.items()if v['base_class']==base))
 values=tuple(snapshot['slots'])
 if any(v and v not in known for v in values):raise ValueError('Dormant page contains foreign skill')
 return validate_slots(upgraded_slots(values,character),equippable_skills(character),character)

def initialization(slots,uid,allowed,ranks,character):
 from els_server.domain.skill_state import preset_payload,record
 from els_server.domain.skill_unlocks import ids_wire
 state=character['ordinary_skill_pages'];selected=state['selected'];count=state['count']
 if not 1<=selected<=count<=MAX_PAGES:raise ValueError('Ordinary page initialization state')
 u32=lambda n:struct.pack('>I',n)
 maps=[]
 for page in range(1,count+1):
  if page==selected:values=slots;c=character
  else:
   saved=state['pages'][page];c=page_character(character,saved);values=page_slots(c,saved)
  from els_server.domain.skill_rules import equippable_skills
  maps.append(bytes([page-1])+preset_payload(values,equippable_skills(c),c))
 learned=u32(len(ranks))+b''.join(record(v,level)for v,level in ranks.items())
 #13A3841..13A3865: first byte selects1-based, second is count.
 return struct.pack('>Q',uid)+u32(count)+b''.join(maps)+learned+u32(0)*2+b'\0'+u32(0)*2+bytes([selected,count])+ids_wire(character)

def expanded(ed=0,count=1,result=0):
 #9BE350: result,i64wallet,3i32,2vector<i32>,bool. Unnamed fields0;
 # neither vector supplies entitlements. 55B carries complete page state.
 return Event(0x201,kind=0x482,payload=struct.pack('>iQiiiIIB',result,ed,count,0,0,0,0,1))

def selected(character=None,slots=None,page=1,result=0):
 from els_server.domain.skill_state import preset_payload,record
 from els_server.domain.skill_rules import equippable_skills
 from els_server.domain.skill_traits import map_wire
 from els_server.domain.boosting_2026_force_equipment import vectors
 character=character or {};slots=tuple(slots or (0,)*22)
 if result:
  #Full failure shape is still readable by DE14C0/DAF6E0. No state applied.
  fixed=struct.pack('>I',22)+bytes(220)+bytes(4)+bytes(12)
  preset=bytes(16)
 else:
  allowed=equippable_skills(character)
  preset=preset_payload(slots,allowed,character)
  fixed=struct.pack('>I',22)+b''.join(record(v)for v in slots)+bytes(4)+map_wire(character)
  fixed+=vectors(character)
 #DE14C0 fixed22 records is a separate DTO, not a map. Two unnamedu16=0.
 return Event(0x201,kind=0x484,payload=struct.pack('>iiii',result,page,0,0)+fixed+preset)

def handle(s,event,sequence):
 if event.event_id!=0x202 or event.kind not in (0x481,0x483):return None
 kind=event.kind;refusal=lambda:[expanded(result=-1)]if kind==0x481 else [selected(result=-1)]
 try:
  request(kind,event.payload)
  account=s.account;root=account.root;store=account.store;characters=account.characters
  app=getattr(s,'application',None);identity=getattr(s,'identity',None)
  owner=account.uid;account_id=account.account_id;token=s.shop_session_id
  path=Path(store.path).resolve()
  captured=(account,root,store,characters,app,identity,owner,account_id,token,path)
  def validate():
   from els_server.domain.local_session import LocalAccount
   from els_server.storage.local_state import LocalState
   from els_server.storage.characters import Characters
   from els_server.domain.equipment_chip_flow import current_lease
   from els_server.domain.roster_account import RosterAccount
   if (type(account)is not LocalAccount or type(root)not in(LocalAccount,RosterAccount)
       or type(store)is not LocalState or type(characters)is not Characters
       or s.role!='game' or s.phase!='town_ready' or not s.item_test or s.client_build!='dx11_260923'
       or type(sequence)is not int or not 1<=sequence<2**32
       or event.performers not in((),(0,))or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0
       or s.account is not account or account.root is not root or account.store is not store or account.characters is not characters
       or root.root is not root or root.characters is not characters or root.character_accounts.get(owner)is not account
       or (account.uid,account.account_id,s.shop_session_id)!=(owner,account_id,token)
       or root.account_id!=account_id or characters.account_id!=account_id or store.uid!=owner
       or Path(store.path).resolve()!=path or Path(characters.path).resolve()!=path
       or getattr(s,'application',None)is not app or getattr(s,'identity',None)is not identity):
    raise ValueError('Ordinary page current actor/phase')
   if str(uuid.UUID(token))!=token or uuid.UUID(token).version!=4:raise ValueError('Ordinary page session')
   if type(root)is RosterAccount:
    if Path(root.path).resolve()!=path:raise ValueError('Ordinary page roster path')
   elif root.store is None or Path(root.store.path).resolve()!=path:raise ValueError('Ordinary page root path')
   if app is not None:
    if (not current_lease(s)or not app.registry.enabled(account_id)
        or Path(app.config.state_file).resolve()!=path):raise ValueError('Ordinary page current lease')
  validate()
  from els_server.storage.ordinary_skill_pages import action
  operation=token+':ordinary-page-v1:'+str(owner)+':'+str(sequence)
  return action(path,owner,account_id,kind,event.payload,operation,validate=validate)
 except (ValueError,AttributeError,TypeError,sqlite3.Error):return refusal()
