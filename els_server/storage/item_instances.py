"""Move complete owned instances between persistent containers, in one SQL tx."""
from els_server.domain.inventory_items import validate_item


def remove(db, owner, item):
    if not db.in_transaction:
        raise ValueError('Instance removal requires transaction')
    for table in ('equipment_attributes', 'equipment_durability', 'equipment_enhancement', 'item_expiration', 'item_locks', 'equipment_options', 'equipment_identification', 'equipment_enhancement_progress', 'item_seals','artifact_equipment_state','equipment_chip_tuning','equipment_reforge_states','equipment_engrave_previews','wardrobe_item_state','wardrobe_dyes'):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            db.execute(f'DELETE FROM {table} WHERE item_uid=?', (item['uid'],))
    if db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?', (item['uid'], owner)).rowcount != 1:
        raise ValueError('Instance removal owner mismatch')


def insert(db, owner, item):
    if not db.in_transaction:
        raise ValueError('Instance insertion requires transaction')
    item = validate_item(item)
    db.execute('INSERT INTO inventory_items VALUES (?,?,?,?,?,?,?)',
        (item['uid'], owner, item['template'], item['metadata'], item['count'], item['group'], item['slot']))
    if 'attributes' in item:
        from els_server.storage.equipment_attributes import replace_attributes
        replace_attributes(db, owner, item['uid'], [0]*4, item['attributes'])
    if 'option_groups' in item:
        from els_server.storage.equipment_options import replace as replace_options
        replace_options(db, owner, item['uid'], {}, item['option_groups'])
    if 'chip_tuning' in item:
        from els_server.storage.equipment_chip import replace as replace_chip
        replace_chip(db,owner,item['uid'],[0,0,0,0],item['chip_tuning'])
    if 'reforge' in item:
        from els_server.storage.equipment_reforge import replace as replace_reforge
        replace_reforge(db,owner,item['uid'],[0,100,0],item['reforge'])
    if 'identified' in item:
        from els_server.storage.equipment_identification import replace as replace_identification
        replace_identification(db, owner, item['uid'], True, item['identified'])
    if 'artifact_socket_open' in item:
        from els_server.storage.artifact_equipment_state import replace as replace_artifact_slot
        replace_artifact_slot(db, owner, item['uid'], False, item['artifact_socket_open'])
    if 'durability' in item:
        from els_server.storage.equipment_durability import replace_durability
        replace_durability(db, owner, item['uid'], 0, item['durability'])
    if item.get('enhancement'):
        from els_server.storage.equipment_enhancement import replace
        replace(db, owner, item['uid'], 0, item['enhancement'])
    if item.get('enhancement_gauge') or item.get('enhancement_guarantee'):
        from els_server.storage.enhancement_progress import replace as replace_progress
        replace_progress(db,owner,item,item.get('enhancement_gauge',0),item.get('enhancement_guarantee',0))
    if 'expires_at' in item:
        from els_server.storage.item_expiration import assign
        assign(db, owner, item['uid'], item['expires_at'])
    if 'lock_until' in item:
        from els_server.storage.item_locks import assign
        assign(db, owner, item['uid'], item['lock_until'])
    if 'sealed' in item or 'seal_used' in item:
        from els_server.storage.item_seals import assign
        assign(db,owner,item['uid'],item.get('sealed',False),item.get('seal_used',0))
    if 'appearance_template' in item or 'wardrobe_hanger' in item:
        from els_server.storage.wardrobe import assign as assign_wardrobe
        assign_wardrobe(db,owner,item)
    elif 'dye_colors'in item or 'appearance_colors'in item:
        from els_server.storage.wardrobe import assign_colors
        assign_colors(db,owner,item)
    return item


def next_uid(db):
    uid = db.execute('SELECT next_uid FROM inventory_sequence WHERE id=1').fetchone()[0]
    if type(uid) is not int or not 0 < uid < 2**63-1:
        raise ValueError('Instance UID sequence bound')
    db.execute('UPDATE inventory_sequence SET next_uid=? WHERE id=1', (uid+1,))
    return uid


def uid_in_use(db,uid):
    if db.execute('SELECT 1 FROM inventory_items WHERE uid=?',(uid,)).fetchone():return True
    return any(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone()
        and db.execute(f'SELECT 1 FROM {table} WHERE uid=?',(uid,)).fetchone()
        for table in ('private_bank_items','shared_bank_items'))
