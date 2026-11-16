"""Move complete owned instances between persistent containers, in one SQL tx."""
from functools import lru_cache
from els_server.domain.inventory_items import validate_item


def remove(db, owner, item):
    if not db.in_transaction:
        raise ValueError('Instance removal requires transaction')
    from els_server.domain.cartridge_registration_rules import require_unbound
    require_unbound(db,item['uid'])
    for table in ('equipment_attributes', 'equipment_durability', 'equipment_enhancement', 'item_expiration', 'item_activation_periods', 'item_locks', 'equipment_options', 'equipment_identification', 'equipment_enhancement_progress', 'item_seals','artifact_equipment_state','equipment_chip_tuning','equipment_reforge_states','equipment_engrave_previews','wardrobe_item_state','wardrobe_dyes'):
        if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)).fetchone():
            db.execute(f'DELETE FROM {table} WHERE item_uid=?', (item['uid'],))
    if db.execute('DELETE FROM inventory_items WHERE uid=? AND owner=?', (item['uid'], owner)).rowcount != 1:
        raise ValueError('Instance removal owner mismatch')


def insert(db, owner, item):
    if not db.in_transaction:
        raise ValueError('Instance insertion requires transaction')
    from els_server.domain.cartridge_registration_rules import non_authority,require_unbound
    non_authority(dict(item));require_unbound(db,item['uid'])
    item = validate_item(item)
    from els_server.storage.equipment_chip_reset_history import hydrate
    item = hydrate(db,item)
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
        replace_chip(db,owner,item['uid'],[0,0,0,item['chip_tuning'][3]],item['chip_tuning'])
    if 'reforge' in item:
        from els_server.storage.equipment_reforge import replace as replace_reforge
        replace_reforge(db,owner,item['uid'],[0,100,0],item['reforge'])
    if 'identified' in item:
        from els_server.storage.equipment_identification import replace as replace_identification
        from els_server.domain.identification_ui import initial_pending
        initial={k:v for k,v in item.items()if k!='identified'}
        replace_identification(db, owner, item['uid'], not initial_pending(initial), item['identified'])
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
    if 'activation_seconds'in item:
        from els_server.storage.item_expiration import assign_activation
        assign_activation(db,owner,item['uid'],item['activation_seconds'])
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
        for table in ('private_bank_items','shared_bank_items','native_guild_bank_items_v1','pet_bag_items'))


def uid_reserved(db,uid):
    """Allocation/buyback cannot reuse a UID held in a live or escrow container.

    Transfer consumers use uid_in_use while their qualified source still owns
    the escrow row. History and retired escrow rows do not reserve an instance.
    """
    if uid_in_use(db,uid):return True
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='player_mail_items'").fetchone():
        if db.execute('''SELECT 1 FROM player_mail_items WHERE item_uid=?
            AND claimed_at IS NULL AND moved_to IS NULL AND expired_at IS NULL LIMIT 1''',(uid,)).fetchone():return True
    if db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='trade_board_listings'").fetchone():
        if db.execute('SELECT 1 FROM trade_board_listings WHERE item_uid=? AND remaining>0 LIMIT 1',(uid,)).fetchone():return True
    return False


@lru_cache(maxsize=1)
def _existing_readers():
    """Current owned-read contracts; this registry grants no acquisition."""
    from els_server.domain import cartridge_selection_box as cartridge,wardrobe_ticket_box as wardrobe
    from els_server.domain import erp_potions_existing as erp,teacher_elixir_boxes as teacher
    from els_server.domain import life_potions_existing as life,wisdom_potions as wisdom
    from els_server.domain import normal_fatigue_rules as fatigue,retained_native_consumables as native,potion_choice_box as choice
    from els_server.domain.inventory_items import existing_normal_fatigue_potions
    families=(
        ((cartridge.BOX,),cartridge.read_existing_box,cartridge.validate_existing_box),
        ((wardrobe.BOX,),wardrobe.read_existing_box,wardrobe.validate_existing_box),
        (erp.TEMPLATES,erp.read_existing,erp.validate_existing),
        (teacher.BOXES,teacher.read_existing,teacher.validate_existing),
        # These two independently admitted items already have ordinary moves.
        (set(life.TEMPLATES)-{135953},life.read_existing,life.validate_existing),
        (wisdom.TEMPLATES,wisdom.read_existing,wisdom.validate_existing),
        (set(existing_normal_fatigue_potions)-{710098},fatigue.read_existing,fatigue.validate_existing),
        (native.TEMPLATES,native.read_existing,native.validate_existing),
        # The inventory loader gives716611 to the retained-native reader.
        (set(choice.BOXES)-native.TEMPLATES,choice.read_existing,choice.validate_existing),
    )
    return {template:(read,validate)for templates,read,validate in families for template in templates}


def read_stored(item):
    """Rebuild a reader only for a record loaded from an owned container."""
    reader=_existing_readers().get(item['template'])
    return reader[0](item)if reader is not None else item


def bag_group(item):
    """Retained readers already validate the original bag independently."""
    if item['template']in _existing_readers():return item['group']
    from els_server.domain.inventory_items import TEMPLATE_BAG_GROUPS
    return TEMPLATE_BAG_GROUPS[item['template']]


def relocate(item,updated):
    """Preserve a trusted whole-instance reader while changing its position."""
    from els_server.domain.cartridge_selection_box import BOX,relocate_existing_box
    if item['template']==BOX:return relocate_existing_box(item,updated)
    reader=_existing_readers().get(item['template'])
    if reader is None:return updated
    read,validate=reader;validate(item)
    if(type(updated)is not dict
       or {k:v for k,v in item.items()if k not in('group','slot')}
          !={k:v for k,v in updated.items()if k not in('group','slot')}):
        raise ValueError('Owned item movement must retain whole instance')
    return read(updated)


def reduce_count(item,count):
    """Build a positive remainder after the caller authorizes destruction."""
    if type(count)is not int or not 0<count<item['count']:
        raise ValueError('Owned remainder must strictly decrease a positive count')
    updated=dict(item,count=count)
    reader=_existing_readers().get(item['template'])
    if reader is None:return validate_item(updated)
    read,validate=reader;validate(item)
    return read(updated)
