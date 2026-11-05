"""Current Artifact material refresh; old action positions stay JSON arrays."""
import json

def positions(value,consumed):
 if not isinstance(value,list) or len(value)!=(1 if consumed else 0):raise ValueError('Artifact receipt material positions')
 result=[]
 for p in value:
  if (not isinstance(p,(list,tuple)) or len(p)!=2 or type(p[0]) is not int or p[0]!=4
      or type(p[1]) is not int or not 0<=p[1]<=32767):raise ValueError('Artifact receipt material position')
  result.append(tuple(p))
 return result

def store_material_uid(db,operation,owner,digest,changes,before):
 if not db.in_transaction:raise ValueError('Artifact material receipt transaction')
 points=positions([p for p,_ in changes],True)
 chosen=[i['uid'] for i in before if (i['group'],i['slot']) in points]
 if len(chosen)!=1 or type(chosen[0]) is not int or not 0<chosen[0]<2**63:raise ValueError('Artifact original reset material identity')
 db.execute('''CREATE TABLE IF NOT EXISTS artifact_action_material_uids (
  operation_id TEXT PRIMARY KEY REFERENCES artifact_actions(operation_id),
  owner INTEGER NOT NULL,request_hash TEXT NOT NULL,material_uid INTEGER NOT NULL)''')
 db.execute('INSERT INTO artifact_action_material_uids VALUES (?,?,?,?)',(operation,owner,digest,chosen[0]))

def replay_changes(db,operation,owner,digest,raw,items,*,consumed,request_uid=None):
 try:data=json.loads(raw)
 except (TypeError,json.JSONDecodeError) as error:raise ValueError('Artifact receipt JSON') from error
 points=positions(data,consumed)
 exists=db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='artifact_action_material_uids'").fetchone()
 row=db.execute('SELECT owner,request_hash,material_uid FROM artifact_action_material_uids WHERE operation_id=?',(operation,)).fetchone() if exists else None
 if row is not None:
  if (row[:2]!=(owner,digest) or not consumed or request_uid is not None
      or type(row[2]) is not int or not 0<row[2]<2**63):raise ValueError('Artifact material receipt owner/hash/identity')
  uids={row[2]}
 else:uids={request_uid} if request_uid is not None else None
 current={(i['group'],i['slot']):i for i in items}
 changes=[(p,current.get(p)) for p in points]
 # Growth requests already identify their exact material UID. Legacy reset
 # receipts have no UID witness: refresh current owned group4 state only;
 # validate_item permits these materials solely in that bag. Never rewrite
 # old receipts or guess the originally selected material by template.
 refresh=[((i['group'],i['slot']),i) for i in items if consumed and (i['group'],i['slot']) not in points
          and (i['uid'] in uids if uids is not None else i['group']==4)]
 return changes,refresh
