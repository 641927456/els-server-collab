"""Exact current House40256 fifteen recipe rows; no catch-rate policy."""
import functools,hashlib,json,struct
from pathlib import Path
from els_server.game_data import client_data,CLIENT_SHA
@functools.lru_cache(maxsize=1)
def catalog():
 raw=(Path(__file__).resolve().parents[1]/'data/fish_exchange.json').read_bytes()
 if hashlib.sha256(raw).hexdigest()!='8ac05048148acf5414dd2588a2b50879aebafc8fbae102e4b35b4a4269aa4a5c':raise ValueError('Original fish exchange data')
 c=json.loads(raw)
 if c['client_sha256']!=CLIENT_SHA or c['catalog_sha256']!=client_data().manifest['catalog_sha256']:raise ValueError('Original fish exchange build')
 if len(c['recipes'])!=15:raise ValueError('Original fish exchange row count')
 for r in c['recipes']:
  a=r['original_call']['arguments']
  if r['original_call']['function']!='g_pItemManager.AddItemExchangeData' or a[1:7]!=[40256,r['type'],r['source'],r['destination'],r['quantity'],r['rate']]or a[7]!={'m_iServerGroupID':-1,'m_iSourceQuantity':r['source_quantity']}:raise ValueError('Original fish exchange row')
 for r in c['definitions']:
  d=client_data().item(r['template'])
  if hashlib.sha256(d['record']).hexdigest()!=r['record_sha256']or tuple(d[k]for k in('metadata','item_type','flags4','flags8'))!=tuple(r[k]for k in('metadata','item_type','flags4','flags8'))or struct.unpack_from('<H',d['record'],16)[0]!=r['max_stack']:raise ValueError('Original fish instance')
 return c
def inventory_definitions():return catalog()['definitions']
def recipe(request):
 rows=[r for r in catalog()['recipes']if(r['source'],r['type'],r['source_quantity'])==(request.source,request.exchange_type,request.source_quantity)]
 if request.exchange_type==3:rows=[r for r in rows if r['destination']==request.destination]
 elif request.destination!=0:raise ValueError('Nonselect fish destination must be original zero')
 if not rows or request.exchange_type in(1,3)and len(rows)!=1 or request.exchange_type==2 and sum(r['rate']for r in rows)!=100:raise ValueError('Original fish recipe selection')
 return rows
