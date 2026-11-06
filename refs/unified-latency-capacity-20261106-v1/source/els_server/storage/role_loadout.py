"""Idempotent role starter grants in the caller's SQL transaction."""
from els_server.domain.role_progression import catalog


def grant_loadout(db,character):
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS,FASHION_EQUIP_SLOTS,validate_item,inventory_payload
    from els_server.domain.equipment_requirements import catalog as requirements
    from els_server.domain.equipment_instance import require_wearable
    from els_server.storage.inventory_state import grant_items,load_items
    from els_server.game_data import client_data
    from els_server.domain.character_rules import CLASSES
    uid=character['uid'];row=catalog()['roles'][str(character['unit_type'])]
    if CLASSES[character['unit_class']]['base_class']!=row['base_class']:raise ValueError('Starter identity mismatch')
    original=load_items(db,uid);owned={i['template'] for i in original};occupied={i['slot'] for i in original if i['group']==9}
    plan=[dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=1)
          for t in row['costumes']+row['alternate_costumes']+row['equipment'] if t not in owned]
    items=grant_items(db,plan,uid) if plan else []
    for item in items:
        t=item['template']
        if t in row['costumes']+row['alternate_costumes']:slot=FASHION_EQUIP_SLOTS[t]
        else:
            slot=requirements()[1][client_data().item(t)['equip_position']]
            require_wearable(dict(item,group=9,slot=slot),character)
        if slot in occupied:continue
        validate_item(dict(item,group=9,slot=slot));occupied.add(slot)
        db.execute('UPDATE inventory_items SET bag_group=9,slot=? WHERE uid=? AND owner=?',(slot,item['uid'],uid))
    saved=load_items(db,uid);inventory_payload(saved)
    db.execute('CREATE TABLE IF NOT EXISTS character_loadout_receipts (owner INTEGER PRIMARY KEY, policy TEXT NOT NULL, items_json TEXT NOT NULL)')
    import json
    db.execute('INSERT INTO character_loadout_receipts VALUES (?,?,?)',(uid,catalog()['policy'],json.dumps(saved,sort_keys=True)))
    return saved


def repair_created_loadouts(path):
    """Backfill old creation receipts once, retaining every owned item and slot.

    Only proven created characters are eligible; the original imported UID 1001
    save is untouched. A full bag defers the entire kit without partial grants.
    """
    import sqlite3
    from contextlib import closing
    from els_server.storage.inventory_state import InventoryFull
    from els_server.storage.characters import Characters
    repaired=[];deferred=[]
    with closing(sqlite3.connect(path,timeout=10)) as db,db:
        db.execute('CREATE TABLE IF NOT EXISTS character_loadout_receipts (owner INTEGER PRIMARY KEY, policy TEXT NOT NULL, items_json TEXT NOT NULL)')
        owners=[r[0] for r in db.execute('SELECT DISTINCT uid FROM character_creation_receipts WHERE uid>1001 AND uid NOT IN (SELECT owner FROM character_loadout_receipts)')]
    for uid in owners:
        try:
            with closing(sqlite3.connect(path,timeout=10)) as db,db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute('SELECT 1 FROM character_loadout_receipts WHERE owner=?',(uid,)).fetchone():continue
                row=db.execute('SELECT uid,name,unit_type,unit_class,level,transcendence,master,revision FROM characters WHERE uid=?',(uid,)).fetchone()
                if row is None:raise ValueError('Missing created role identity')
                grant_loadout(db,Characters._row(row));repaired.append(uid)
        except InventoryFull:deferred.append(uid)
    return dict(repaired=repaired,deferred=deferred)
