"""Require a true first native Show and preserve the client's exception path."""
import copy,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from verify_inventory_manager_first_show import evaluate
p=ROOT/'analysis/client-6c6b5180/20261014-015631/potion-bag-correction-snapshot.json';s=json.loads(p.read_text(encoding='utf8'));assert evaluate(s,p.parent)['original_inventory_first_show_verified']
def reject(change):
 v=copy.deepcopy(s);change(v);assert not evaluate(v,p.parent)['original_inventory_first_show_verified']
def calls(v):return [r['payload'] for r in v['rows'] if r.get('payload',{}).get('event')=='original_inventory_manager_called']
reject(lambda v:calls(v)[0].__setitem__('before',1))
reject(lambda v:calls(v)[1].__setitem__('native_exception_behavior','steal'))
reject(lambda v:calls(v)[1].__setitem__('after',0))
reject(lambda v:calls(v)[1].__setitem__('selected_category',2))
reject(lambda v:v['rows'].append({'type':'send','payload':calls(v)[1]}))
reject(lambda v:v['rows'].append({'type':'send','payload':{'event':'inventory_open_error','error':'interrupted'}}))
reject(lambda v:next(r['payload'] for r in v['rows'] if r.get('payload',{}).get('event')=='inventory_manager_native_exception').__setitem__('type','access-violation'))
reject(lambda v:v.__setitem__('rows',[r for r in v['rows'] if r.get('payload',{}).get('event')!='inventory_manager_native_exception']))
reject(lambda v:v['database']['inventory_items'][0].__setitem__(5,2))
reject(lambda v:v['identity'].__setitem__('pid',55968))
print('PASS: first native Show acceptance rejects reopen/retry, stolen/invalid exceptions, missing UI and incorrect saved bag.')
