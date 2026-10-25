"""Finite extra Boss draw, persisted in the original death writer; no new DDL at install."""
import hashlib,json,sqlite3,uuid
from contextlib import closing
from els_server.storage import dungeon_equipment_loot as base
from els_server.storage.inventory_state import load_items,grant_items
from els_server.storage.inventory_actions import _identity,_previous,_commit


def canonical(v):return json.dumps(v,sort_keys=True,separators=(',',':'))


def ensure(db):
    db.execute('''CREATE TABLE IF NOT EXISTS fishing_bait_boss_draws (
      owner INTEGER NOT NULL REFERENCES characters(uid),run_id TEXT NOT NULL,
      stage INTEGER NOT NULL,part INTEGER NOT NULL,visits INTEGER NOT NULL,npc_key INTEGER NOT NULL,
      context_json TEXT NOT NULL,proof_sha256 TEXT NOT NULL CHECK(length(proof_sha256)=64),
      hit INTEGER NOT NULL CHECK(hit IN(0,1)),drop_id INTEGER,claimed_json TEXT,
      PRIMARY KEY(owner,run_id,stage,part,visits,npc_key))''')


def issue(db,c,proof,drop_id,xyz,origin,account,randbelow):
    from els_server.domain.fishing_bait_loot import POLICY,WRITER_ENABLED
    if not db.in_transaction or not WRITER_ENABLED:raise ValueError('Bait authorized original death writer')
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    require_active_character(db,c['owner']);require_owner(db,c['owner'],account)
    if type(drop_id)is not int or not 1<=drop_id<2**31:raise ValueError('Bait ground UID bound')
    ensure(db);key=base.key(c)
    if db.execute('SELECT 1 FROM fishing_bait_boss_draws WHERE owner=? AND run_id=? AND stage=? AND part=? AND visits=? AND npc_key=?',key).fetchone():
        raise ValueError('Bait draw already has a committed source')
    from els_server.storage.elixir_economy import bonus as elixir_bonus
    from els_server.domain.elixir_economy import hit as probability_hit
    operation='elixir-bait:'+str(uuid.uuid5(uuid.UUID(c['run_id']),canonical(c)))
    drop_bp=elixir_bonus(db,c['owner'],c['dungeon'],'drop',operation,dict(c,origin=origin,proof_sha256=hashlib.sha256(proof).hexdigest()))
    hit=probability_hit(75,1000,randbelow,drop_bp);digest=hashlib.sha256(proof).hexdigest()
    db.execute('INSERT INTO fishing_bait_boss_draws VALUES (?,?,?,?,?,?,?,?,?,?,NULL)',(*key,canonical(origin),digest,int(hit),drop_id if hit else None))
    if not hit:return []
    return [{**c,'template':99809,'quantity':1,'option_groups':{},'drop_id':drop_id,
             'xyz':list(xyz),'ed':0,'source':POLICY,'pickup_committed':False,'claimed_uids':None,
             'death_proof_sha256':digest,'bait_origin':origin}]


def claim(path,c,request,drop,origin,account,prepare,validate):
    from els_server.domain import fishing_bait_loot as rules
    if request['drop_id']!=drop['drop_id'] or request['template']!=99809:raise ValueError('Bait issued pickup identity')
    with closing(base.connect(path)) as db,db:
        db.execute('BEGIN IMMEDIATE');validate(db)
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='fishing_bait_boss_draws'").fetchone():raise ValueError('Bait never issued')
        saved=db.execute('SELECT context_json,proof_sha256,hit,drop_id,claimed_json FROM fishing_bait_boss_draws WHERE owner=? AND run_id=? AND stage=? AND part=? AND visits=? AND npc_key=?',base.key(c)).fetchone()
        if saved is None or saved[:4]!=(canonical(origin),drop['death_proof_sha256'],1,drop['drop_id']):raise ValueError('Bait original committed draw')
        issued=base.lookup(db,c)
        if issued is None or issued[0]!=c['dungeon']:raise ValueError('Bait original death ledger')
        rows=json.loads(issued[3]);entries=[r for r in rows if r.get('source')==rules.POLICY and r.get('drop_id')==drop['drop_id']]
        if (len(entries)!=1 or entries[0].get('bait_origin')!=origin or entries[0].get('template')!=99809
                or entries[0].get('quantity')!=1 or entries[0].get('option_groups')!={}
                or entries[0].get('death_proof_sha256')!=saved[1]
                or any(entries[0].get(k)!=v for k,v in c.items())):raise ValueError('Bait original issue row')
        op='fishing-bait:'+str(uuid.uuid5(uuid.UUID(c['run_id']),canonical(dict(context=c,drop_id=drop['drop_id']))))
        owner,digest=_identity(c['owner'],0xd0,canonical(dict(context=c,drop_id=drop['drop_id'],source=rules.POLICY,proof=saved[1])).encode(),op)
        prior=_previous(db,op,digest);before=load_items(db,owner)
        if prior is not None:
            if saved[4]is None:raise ValueError('Bait receipt/source mismatch')
            ids=set(json.loads(saved[4]));reply=prepare([i for i in before if i['uid']in ids],True)
            validate(db);return dict(reply=reply,replayed=True)
        if not rules.WRITER_ENABLED or saved[4]is not None:raise ValueError('Bait uncompleted pickup held')
        from els_server.domain.reward_rules import item_plan
        awarded=grant_items(db,[item_plan(99809,1)],owner)
        if len(awarded)!=1 or (awarded[0]['template'],awarded[0]['metadata'],awarded[0]['group'])!=(99809,2,3):raise ValueError('Bait current registered factory')
        after=load_items(db,owner);ids={i['uid']for i in awarded};current=[i for i in after if i['uid']in ids]
        reply=prepare(current,False);validate(db)
        if not rules.WRITER_ENABLED:raise ValueError('Bait writer held after response encoding')
        _commit(db,op,digest,owner,0xd0,[(i['group'],i['slot'])for i in current],before,after)
        db.execute('UPDATE fishing_bait_boss_draws SET claimed_json=? WHERE owner=? AND run_id=? AND stage=? AND part=? AND visits=? AND npc_key=?',(canonical(sorted(ids)),*base.key(c)))
        validate(db)
        if not rules.WRITER_ENABLED:raise ValueError('Bait writer held before final commit')
        return dict(reply=reply,replayed=False)
