"""Qualification for the fresh owned native client, never player inventories."""
from pathlib import Path
import json,hashlib,collections
T=Path(__file__).resolve().parent
RVAS=(0x197f500,0x197f660,0x197f740,0x2269180,0x226b400,0x22634a0,0x2269a5c,0x226b65e,0x234b280,0x88bc50,0x861940,0x2269960,0x226b560,0x2265cf0,0x30d0680)
def source(fixture,phase):
 b=Path('G:/els/analysis/client-6c6b5180/x2-runtime.bin').read_bytes()
 assert hashlib.sha256(b).hexdigest()=='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
 return (T/('native_gear_flow.template.js'if phase=='primary'else'native_gear_cold.template.js')).read_text('utf8').replace('__FIXTURE__',json.dumps(fixture)).replace('__PREFIXES__',json.dumps({r:b[r:r+8].hex()for r in RVAS}))
def primary(fixture,event,snapshot):
 fixture=json.loads(json.dumps(fixture));snapshot=json.loads(json.dumps(snapshot))
 assert event['event']=='native_gear_flow_complete'and not event['error']
 actions=event['completed'];assert len(actions)==16 and collections.Counter(a['kind']for a in actions)=={'identify':4,'shadow':4,'wear':4,'unequip':4}
 assert all(a['result']==0 for a in actions)
 before={i['uid']:i for i in fixture['items']};after={i['uid']:i for i in snapshot['items']};native={i['uid']:i for i in event['items']}
 scrolls=[i for i in before.values()if i['template']==118259];assert len(scrolls)==1 and scrolls[0]['count']==4
 assert set(before)-set(after)=={scrolls[0]['uid']}and not set(after)-set(before)
 assert snapshot['balances']==fixture['balances']
 positions={uid:(i['group'],i['slot'])for uid,i in before.items()}
 for a in actions:
  assert a['before']['uid']==a['uid']
  if a['kind']in('wear','unequip'):
   assert a['refresh']>=1
   dst=a['destination'];previous=positions[a['uid']]
   if dst['uid']:positions[dst['uid']]=previous
   positions[a['uid']]=(dst['group'],dst['slot'])
 gears={r['item']['uid']for r in fixture['gears']}
 for uid,item in after.items():
  assert (item['group'],item['slot'])==positions[uid]
  old=before[uid]
  if uid in gears:
   assert item['identified']and item['group']==1 and item['enhancement']==11 and item['reforge']==[21,100,0]
   for kind,g in [('identify','1'),('shadow','25')]:
    a=next(a for a in actions if a['kind']==kind and a['uid']==uid);row=next(r for r in a['decoded']if r['uid']==uid)
    assert len(row['groups'][g])==3 and row['groups'][g]==item['option_groups'][g]
   assert item['option_groups']['13']==old['option_groups']['13']
   stable=lambda x:{k:v for k,v in x.items()if k not in('group','slot','identified','option_groups')}
   assert stable(old)==stable(item)
  else:assert {**old,'group':item['group'],'slot':item['slot']}==item
  n=native[uid];assert not n.get('absent')and all(n[k]==item[k]for k in('template','count','group','slot'))
 assert native[scrolls[0]['uid']]['absent']
 kinds=collections.Counter(k for _,k in snapshot['action_receipts']);assert kinds[0x196]==1 and kinds[0x438]==4 and kinds[0x9ef]==4
 assert len(snapshot['wear_receipts'])==8 and event['statVectors']
 return dict(passed=True,native_ordinary_initial=4,native_shadow_initial=4,native_wear=4,native_unequip=4,ED_debit=0,scroll118259_debit=4,UID_enhancement_reforge_and_existing_options_preserved=True,original_ACK_consumers_and_attribute_refresh=True,physical_input_actions=0,native_inventory_writes=0)
def cold(primary_snapshot,event,snapshot,dtos):
 primary_snapshot=json.loads(json.dumps(primary_snapshot));snapshot=json.loads(json.dumps(snapshot))
 assert event['event']=='native_gear_cold_complete'
 for k in ('items','balances','action_receipts','wear_receipts'):assert snapshot[k]==primary_snapshot[k],k
 expected={i['uid']:i for i in snapshot['items']};actual={i['uid']:i for i in event['items']};assert set(actual)==set(expected)
 for uid,i in expected.items():assert all(actual[uid][k]==i[k]for k in('template','count','group','slot'))
 for i in expected.values():
  if not 721881<=i['template']<=721940:continue
  assert actual[i['uid']]['identified']==1
  assert len(i['option_groups']['1'])==3 and len(i['option_groups']['25'])==3
 return dict(passed=True,new_client_process=True,native_cold_identified_flags_and_inventory_verified=4,persisted_items_options_balances_receipts_unchanged=True,physical_input_actions=0)

def window_safety(pid):
 import ctypes
 from ctypes import wintypes as W
 u=ctypes.WinDLL('user32',use_last_error=True);u.GetForegroundWindow.restype=W.HWND
 u.GetWindowThreadProcessId.argtypes=[W.HWND,ctypes.POINTER(W.DWORD)];u.GetWindowRect.argtypes=[W.HWND,ctypes.POINTER(W.RECT)]
 u.GetWindowLongPtrW.restype=ctypes.c_longlong;u.GetWindowLongPtrW.argtypes=[W.HWND,ctypes.c_int];u.IsWindowVisible.argtypes=[W.HWND]
 rows=[];CALL=ctypes.WINFUNCTYPE(W.BOOL,W.HWND,W.LPARAM)
 @CALL
 def enum(h,param):
  p=W.DWORD();u.GetWindowThreadProcessId(h,ctypes.byref(p))
  if p.value==pid:
   r=W.RECT();assert u.GetWindowRect(h,ctypes.byref(r));rows.append(dict(hwnd=int(h),rect=[r.left,r.top,r.right,r.bottom],visible=bool(u.IsWindowVisible(h)),noactivate=bool(u.GetWindowLongPtrW(h,-20)&0x08000000)))
  return True
 assert u.EnumWindows(enum,0)
 p=W.DWORD();u.GetWindowThreadProcessId(u.GetForegroundWindow(),ctypes.byref(p));assert p.value!=pid
 assert rows and all(not r['visible']or(r['noactivate']and r['rect'][2]<0 and r['rect'][3]<0)for r in rows)
 return dict(passed=True,owned_pid=pid,foreground_is_owned=False,windows=rows,read_only=True,physical_input_actions=0)
