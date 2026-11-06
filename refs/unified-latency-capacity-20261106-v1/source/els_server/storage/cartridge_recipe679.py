"""One owned20debit and one original BOXUID; no fragment/BOX general producer."""
from contextlib import closing
from pathlib import Path
import json
import sqlite3
import struct
import time
from els_server.domain.cartridge_recipe679_rules import request, plain_source, SOURCE, BOX, _RecipeAuthority, _RecipeSource
from els_server.domain.manufacture_requirements import inventory_candidates
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.protocol.cartridge_recipe679_messages import acknowledgement
from els_server.storage.cartridge_exchange import _context as original_context
from els_server.storage.inventory_actions import _identity, _previous, _commit
from els_server.storage.inventory_state import load_items, grant_items
from els_server.storage.item_instances import remove
from els_server.storage.equipment_receipt_state import current_changes
from els_server.storage.reward_state import validate_balances
from els_server.storage.item_actor import require_active_character

WRITER_ENABLED = True


def _context(db,owner,account_id,authorize):
    if (not WRITER_ENABLED or type(authorize) is not _RecipeAuthority
            or authorize.owner!=owner or authorize.account_id!=account_id
            or not db.in_transaction):raise ValueError('Recipe679 exact authority')
    main=[r[2] for r in db.execute('PRAGMA database_list') if r[1]=='main']
    if len(main)!=1 or Path(main[0]).resolve()!=authorize.path:
        raise ValueError('Recipe679 exact original store')
    original_context(db,owner,account_id,authorize)
    require_active_character(db,owner)


def _history(db,owner,operation,positions):
    row=db.execute('SELECT owner,kind,before_json,after_json FROM inventory_action_receipts WHERE operation_id=?',
                   (operation,)).fetchone()
    if row is None or row[:2]!=(owner,0x223):raise ValueError('Recipe679 receipt owner/kind')
    try:
        before,after=(json.loads(r) for r in row[2:])
        if type(before) is not list or type(after) is not list:raise ValueError('Recipe679 history arrays')
        from els_server.domain.cartridge_selection_box import read_existing_box
        from els_server.domain.inventory_items import inventory_payload
        for rows in (before,after):
            inventory_payload([read_existing_box(r) if type(r)is dict and r.get('template')==BOX else r for r in rows])
        b,a={r['uid']:r for r in before},{r['uid']:r for r in after}
        if len(b)!=len(before) or len(a)!=len(after):raise ValueError('Recipe679 history UID duplicate')
        added=[r for uid,r in a.items() if uid not in b]
        if (len(added)!=1 or set(added[0])!={'uid','template','metadata','count','group','slot'}
                or (added[0]['template'],added[0]['metadata'],added[0]['count'],added[0]['group'])!=(BOX,0,1,4)):
            raise ValueError('Recipe679 historical one BOX')
        debit,total=[],0
        for uid,old in b.items():
            new=a.get(uid)
            if new==old:continue
            if not plain_source(old):raise ValueError('Recipe679 historical foreign change')
            if new is None:take=old['count']
            else:
                if ({k:v for k,v in old.items()if k!='count'}!={k:v for k,v in new.items()if k!='count'}
                        or type(new['count'])is not int or not 0<new['count']<old['count']):
                    raise ValueError('Recipe679 historical material shape')
                take=old['count']-new['count']
            total+=take;debit.append(old)
        if total!=20 or not debit:raise ValueError('Recipe679 historical20debit')
        debit.sort(key=lambda r:(r['group'],r['slot']))
        expected=list(dict.fromkeys([(r['group'],r['slot'])for r in debit]+[(added[0]['group'],added[0]['slot'])]))
        if positions!=expected:raise ValueError('Recipe679 receipt positions')
    except (KeyError,TypeError,json.JSONDecodeError)as exc:
        raise ValueError('Recipe679 history structure')from exc


def exchange(path,owner,payload,operation,*,account_id,authorize,now=None):
    if not WRITER_ENABLED:raise ValueError('Recipe679 writer closed')
    request(payload)
    if type(account_id)is not int or not 1<=account_id<2**63:raise ValueError('Recipe679 account')
    if type(authorize)is not _RecipeAuthority or authorize.operation!=operation or authorize.payload!=payload:
        raise ValueError('Recipe679 request authority')
    now=int(time.time())if now is None else now
    if type(now)is not int or not 0<=now<2**40:raise ValueError('Recipe679 clock')
    owner,digest=_identity(owner,0x223,struct.pack('>iQ',1012,account_id)+payload,operation)
    uri=Path(path).resolve().as_uri()+'?mode=rw'
    with closing(sqlite3.connect(uri,uri=True,timeout=10))as db,db:
        db.execute('PRAGMA foreign_keys=ON');db.execute('BEGIN IMMEDIATE')
        _context(db,owner,account_id,authorize)
        balance=validate_balances(db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone())
        previous=_previous(db,operation,digest);before=load_items(db,owner)
        if previous is not None:
            _history(db,owner,operation,previous)
            answer=[Event(0x201,kind=0x224,payload=acknowledgement(balance['ed'],
                    current_changes(db,operation,owner,0x223,previous,before),[(BOX,1)]))]
            for e in answer:encode_event(e)
            _context(db,owner,account_id,authorize)
            return answer
        by_uid={i['uid']:i for i in before}
        candidates=[(uid,count)for uid,count in inventory_candidates(before,now=now).get(SOURCE,())if plain_source(by_uid[uid])]
        if sum(count for _,count in candidates)<20:raise ValueError('Recipe679 needs20current plain fragments')
        source=_RecipeSource(db,owner,account_id,payload,operation,authorize)
        try:
            remaining,positions,debits=20,[],[]
            for uid,count in sorted(candidates,key=lambda p:(by_uid[p[0]]['group'],by_uid[p[0]]['slot'])):
                if not remaining:break
                item=by_uid[uid];take=min(count,remaining);remaining-=take
                debits.append((uid,take));positions.append((item['group'],item['slot']))
                if take==count:remove(db,owner,item)
                elif db.execute('UPDATE inventory_items SET count=count-? WHERE uid=? AND owner=? AND count=?',
                                (take,uid,owner,count)).rowcount!=1:raise ValueError('Recipe679 materialCAS')
            source.debit_complete(debits)
            grants=grant_items(db,[dict(template=BOX,metadata=0,group=4,quantity=1)],owner,cartridge_recipe679_source=source)
        finally:source.close()
        if (len(grants)!=1 or set(grants[0])!={'uid','template','metadata','group','slot','count'}
                or (grants[0]['template'],grants[0]['metadata'],grants[0]['group'],grants[0]['count'])!=(BOX,0,4,1)
                or grants[0]['uid']in by_uid):raise ValueError('Recipe679 one original factory BOX')
        after=load_items(db,owner)
        positions=list(dict.fromkeys(positions+[(grants[0]['group'],grants[0]['slot'])]))
        current={(i['group'],i['slot']):i for i in after}
        answer=[Event(0x201,kind=0x224,payload=acknowledgement(balance['ed'],[(p,current.get(p))for p in positions],[(BOX,1)]))]
        for e in answer:encode_event(e)
        if db.execute('SELECT ed,experience,revision FROM reward_balances WHERE uid=?',(owner,)).fetchone()!=tuple(balance[k]for k in ('ed','experience','revision')):
            raise ValueError('Recipe679 wallet changed')
        _context(db,owner,account_id,authorize)
        _commit(db,operation,digest,owner,0x223,positions,before,after)
        _history(db,owner,operation,positions)
        _context(db,owner,account_id,authorize)
        return answer
