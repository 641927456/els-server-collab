"""Draw-once server issues and atomic finite pickup/clear transactions."""
import hashlib
import json
import secrets
import sqlite3
import uuid
from contextlib import closing,contextmanager
from pathlib import Path
from els_server.domain.dungeon_equipment_loot_rules import POLICY,context,plans,inventory_plan,policy_for
from els_server.storage.inventory_state import load_items,grant_items
from els_server.domain.inventory_items import TEMPLATE_MAX_STACKS
from els_server.storage.inventory_actions import _identity,_previous,_commit


class LootActorRejected(ValueError):
    """The newly admitted material requires a current saved player actor."""


def source_actor(db,identity,rows,account_id):
    # Only the new130047 producer is extended here. Existing twelve item
    # outcomes and all lottery mass remain unchanged.
    if not any(row['template']==130047 for row in rows):return
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.bank_state import account_for
    try:
        require_active_character(db,identity['owner'])
        owner_account=account_for(db,identity['owner'])
        if account_id is not None and owner_account!=account_id:
            raise ValueError('Loot actor account changed')
    except ValueError as error:
        raise LootActorRejected(str(error)) from error


def connect(path):
    db=sqlite3.connect(Path(path).resolve().as_uri()+'?mode=rw',uri=True,timeout=10)
    db.execute('PRAGMA foreign_keys=ON')
    return db

def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS dungeon_equipment_loot_issues (
        owner INTEGER NOT NULL REFERENCES characters(uid) ON DELETE CASCADE,
        run_id TEXT NOT NULL,dungeon INTEGER NOT NULL,stage INTEGER NOT NULL,
        part INTEGER NOT NULL,visits INTEGER NOT NULL,npc_key INTEGER NOT NULL,
        proof_sha256 TEXT NOT NULL,policy_id TEXT NOT NULL,issues_json TEXT NOT NULL,
        PRIMARY KEY(owner,run_id,stage,part,visits,npc_key))''')

def key(c):return tuple(c[k] for k in ('owner','run_id','stage','part','visits','npc_key'))

def lookup(db,c):
    return db.execute('SELECT dungeon,proof_sha256,policy_id,issues_json FROM dungeon_equipment_loot_issues WHERE owner=? AND run_id=? AND stage=? AND part=? AND visits=? AND npc_key=?',key(c)).fetchone()

def digest(c,proof):
    if not isinstance(proof,bytes) or not proof or len(proof)>8192:raise ValueError('Loot death evidence')
    return hashlib.sha256(json.dumps(c,sort_keys=True,separators=(',',':')).encode()+proof).hexdigest()

def issue(path,identity,proof,boss,start_id,xyz,legacy,prepare,*,randbelow=secrets.randbelow,rules=None,accepted_effect=None,account_id=None,transaction=None,bait=None):
    c=(rules.context if rules is not None else context)(identity)
    proof_sha=digest(c,proof);policy=(rules.policy_for if rules is not None else policy_for)(c)
    if type(start_id) is not int or not 1<=start_id<2**31:raise ValueError('Loot sequence bound')
    with _issue_connection(path,transaction,identity=c,policy=policy,boss=boss,rules=rules,account_id=account_id) as db:
        if bait is not None:bait.validate(db)
        ensure(db)
        if not db.execute('SELECT 1 FROM characters WHERE uid=?',(c['owner'],)).fetchone():raise ValueError('Loot owner missing')
        old=lookup(db,c)
        if old is not None:
            if old[:3]!=(c['dungeon'],proof_sha,policy):raise ValueError('Conflicting accepted loot death')
            saved_rows=json.loads(old[3]);source_actor(db,c,saved_rows,account_id)
            if accepted_effect is not None:accepted_effect(db,True)
            result=prepare(saved_rows,True)
            if bait is not None:bait.validate(db)
            return result
        if accepted_effect is not None:accepted_effect(db,False)
        drawn=(rules.plans if rules is not None else plans)(c,boss,randbelow)
        source_actor(db,c,drawn,account_id)
        rows=[]
        for index,entry in enumerate([*legacy,*drawn]):
            is_new=index>=len(legacy);drop_id=start_id+index
            if drop_id>=2**31:raise ValueError('Loot sequence exhausted')
            rows.append({**c,**entry,'drop_id':drop_id,'xyz':list(xyz),'ed':entry.get('ed',0),
                         'source':policy if is_new else 'legacy-coin','pickup_committed':False,'claimed_uids':None,
                         'death_proof_sha256':hashlib.sha256(proof).hexdigest()})
        if bait is not None:rows.extend(bait.issue(db,c,proof,start_id+len(rows),xyz,randbelow))
        result=prepare(rows,False)
        if bait is not None:bait.validate(db)
        # All affected old/new death, CF and gate payloads have encoded before
        # the issue record commits. Session memory is applied by the caller.
        db.execute('INSERT INTO dungeon_equipment_loot_issues VALUES (?,?,?,?,?,?,?,?,?,?)',
                   (c['owner'],c['run_id'],c['dungeon'],c['stage'],c['part'],c['visits'],c['npc_key'],proof_sha,policy,json.dumps(rows,sort_keys=True)))
        if bait is not None:bait.validate(db)
        return result


def claim(path,identity,drop_id,template,prepare,*,rules=None,account_id=None,validate=None):
    c=(rules.context if rules is not None else context)(identity)
    policy=(rules.policy_for if rules is not None else policy_for)(c)
    if type(drop_id) is not int or type(template) is not int:raise ValueError('Loot claim identity')
    with closing(connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        _validate_claim(db,c,policy,rules,validate)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='dungeon_equipment_loot_issues'").fetchone():raise ValueError('Loot was not issued')
        old=lookup(db,c)
        if old is None or old[0]!=c['dungeon'] or old[2]!=policy:raise ValueError('Loot was not issued to this run')
        rows=json.loads(old[3]);row=next((r for r in rows if r['drop_id']==drop_id and r['source']==policy),None)
        if row is None or row['template']!=template or any(row[k]!=c[k] for k in c):raise ValueError('Loot claim context mismatch')
        source_actor(db,c,(row,),account_id)
        from els_server.domain.dungeon_material_loot_catalog import POLICY as MATERIAL_POLICY,validate_issued as validate_material_issue
        if rules is None and policy==MATERIAL_POLICY:validate_material_issue(row,c)
        operation='equipment-pickup:'+str(uuid.uuid5(uuid.UUID(c['run_id']),':'.join(map(str,(*key(c),drop_id)))))
        canonical=json.dumps(dict(context=c,drop_id=drop_id,proof_sha256=old[1],policy=policy),sort_keys=True).encode()
        owner,request_hash=_identity(c['owner'],0xd0,canonical,operation)
        prior=_previous(db,operation,request_hash);before=load_items(db,owner)
        if prior is not None:
            if row['claimed_uids'] is None:raise ValueError('Loot receipt/issue mismatch')
            ids=set(row['claimed_uids']);current=[i for i in before if i['uid'] in ids]
            result=prepare(current,True)
            _validate_claim(db,c,policy,rules,validate)
            return result
        if row['claimed_uids'] is not None:raise ValueError('Claimed loot has no receipt')
        options=row['option_groups']
        if rules is not None:
            awarded=rules.grant(db,row,c)
        elif policy==MATERIAL_POLICY:
            awarded=grant_items(db,[inventory_plan(template,row['quantity'])],owner)
            expected=row['instance_descriptor']['state']
            if (len(awarded)!=1 or awarded[0]['template']!=template or type(awarded[0]['count']) is not int
                or not 1<=awarded[0]['count']<=TEMPLATE_MAX_STACKS[template]
                or (awarded[0]['metadata'],awarded[0]['group'])!=(expected['metadata'],expected['group'])
                or awarded[0].get('option_groups',{})!=expected['option_groups']):
                raise ValueError('Material loot registered factory changed')
        elif policy!=POLICY:
            from els_server.domain.dungeon_loot_catalog import validate_issued
            validate_issued(row,c)
            awarded=grant_items(db,[inventory_plan(template,row['quantity'])],owner)
            expected=row['instance_descriptor']['state']
            if (len(awarded)!=1 or awarded[0]['count']!=1 or awarded[0].get('durability')!=expected['durability']
                or awarded[0].get('enhancement',0)!=expected['enhancement'] or awarded[0].get('option_groups',{})!=expected['option_groups']):
                raise ValueError('Normal loot default factory changed')
        elif template==118638:
            from els_server.domain.equipment_chip_rules import source_options
            if set(options)!={'1'}:raise ValueError('Chip issue options required')
            source_options(options['1'])
            awarded=grant_items(db,[inventory_plan(template,row['quantity'])],owner,chip_options=options)
        else:awarded=grant_items(db,[inventory_plan(template,row['quantity'])],owner)
        if policy==POLICY and options and template!=118638:
            from els_server.domain.equipment_circuit_rules import validate_material
            from els_server.storage.equipment_options import replace
            validate_material(template,options.get('1',[]))
            if len(awarded)!=1 or awarded[0]['count']!=1:raise ValueError('Circuit issue must grant one complete instance')
            replace(db,owner,awarded[0]['uid'],{},options)
        after=load_items(db,owner);ids={i['uid'] for i in awarded};current=[i for i in after if i['uid'] in ids]
        result=prepare(current,False)
        positions=[(i['group'],i['slot']) for i in current]
        _commit(db,operation,request_hash,owner,0xd0,positions,before,after)
        row['claimed_uids']=sorted(ids);row['pickup_committed']=True
        db.execute('UPDATE dungeon_equipment_loot_issues SET issues_json=? WHERE owner=? AND run_id=? AND stage=? AND part=? AND visits=? AND npc_key=?',
                   (json.dumps(rows,sort_keys=True),*key(c)))
        _validate_claim(db,c,policy,rules,validate)
        return result


def clear_reward(path,owner,reward_store,arguments,prepare):
    if reward_store.uid!=owner or Path(reward_store.path).resolve()!=Path(path).resolve():raise ValueError('Clear reward owner/store mismatch')
    with closing(connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE')
        receipt=reward_store.grant(**arguments,transaction=db)
        # Use current UIDs even when the original clear receipt is replayed.
        ids={i['uid'] for i in receipt.get('items',[])}
        current=[i for i in load_items(db,owner) if i['uid'] in ids]
        result=prepare(receipt,current)
        return receipt,result

@contextmanager
def _issue_connection(path,transaction,*,identity,policy,boss,rules,account_id):
    """A shared34320 caller owns its active writer and all-member rollback."""
    if transaction is None:
        with closing(connect(path)) as db,db:
            db.execute('BEGIN IMMEDIATE')
            yield db
        return
    if type(transaction) is not sqlite3.Connection or not transaction.in_transaction:
        raise ValueError('Shared material issue requires an active SQLite transaction')
    from els_server.domain.dungeon_material_loot_catalog import POLICY as MATERIAL_POLICY
    if (rules is not None or policy!=MATERIAL_POLICY or boss is not True
            or identity['dungeon']!=34320 or (identity['stage'],identity['part']) not in ((2,1),(3,0))):
        raise ValueError('Shared material issue is outside the admitted34320 Boss scope')
    attached=transaction.execute('PRAGMA database_list').fetchall()
    main=[row[2] for row in attached if row[1]=='main']
    if (len(main)!=1 or not main[0] or Path(main[0]).resolve()!=Path(path).resolve()
            or any(row[1] not in ('main','temp') for row in attached)
            or transaction.execute('PRAGMA foreign_keys').fetchone()!=(1,)):
        raise ValueError('Shared material issue database or foreign-key mismatch')
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.bank_state import account_for
    try:
        require_active_character(transaction,identity['owner'])
        if type(account_id) is not int or account_id<=0 or account_for(transaction,identity['owner'])!=account_id:
            raise ValueError('Shared material issue owner account changed')
    except ValueError as error:
        raise LootActorRejected(str(error)) from error
    yield transaction
    if not transaction.in_transaction:
        raise ValueError('Shared material issue transaction ended before caller commit')


def _validate_claim(db,identity,policy,rules,validate):
    """Only the admitted shared34320 caller supplies transactional D0 guards."""
    if validate is None:return
    from els_server.domain.dungeon_material_loot_catalog import POLICY as MATERIAL_POLICY
    if (rules is not None or policy!=MATERIAL_POLICY or identity['dungeon']!=34320
            or (identity['stage'],identity['part']) not in ((2,1),(3,0)) or not callable(validate)):
        raise ValueError('Shared material claim validator scope')
    validate(db)
    if not db.in_transaction:
        raise ValueError('Shared material claim validation ended transaction')

