"""Trusted progress facts from existing authorities and committed history."""
import json

TABLES=('native_player_trades','player_mail_receipts','fishing_attempts','pet_expedition_receipts','native_guild_actions','native_guild_operations_v2','native_guild_quest_facts_v2','inventory_action_receipts','resonance2026_reset_receipts','profession_anvil_receipts','consumable_uses','known_resurrection_spends','native_couple_pairs_v1','native_wedding_bookings','native_wedding_ceremonies','dungeon_records','official_pvp_profiles')


def present(db):
    return {r[0]for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'AND name IN("
        +','.join('?'for _ in TABLES)+')',TABLES)}


def ensure_indexes(db):
    # Called from achievement persistence, not its read-only source projector.
    tables=present(db)
    if 'native_player_trades'in tables:
        db.execute("CREATE INDEX IF NOT EXISTS native_achievement_trade_account_a ON native_player_trades(json_extract(ledger_json,'$[0].account'))")
        db.execute("CREATE INDEX IF NOT EXISTS native_achievement_trade_account_b ON native_player_trades(json_extract(ledger_json,'$[1].account'))")
    if 'player_mail_receipts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_post_sender ON player_mail_receipts(account_id)')
    if 'fishing_attempts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_fishing_account ON fishing_attempts(account,caught,fish)')
    if 'pet_expedition_receipts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_expedition_account ON pet_expedition_receipts(account,action)')
    if 'native_guild_actions'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_guild_owner_kind ON native_guild_actions(owner,kind)')
    if 'native_guild_operations_v2'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_guild_operation_owner_kind ON native_guild_operations_v2(owner,kind)')
    if 'native_guild_quest_facts_v2'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_guild_fact_owner ON native_guild_quest_facts_v2(owner)')
    if 'resonance2026_reset_receipts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_reset_account ON resonance2026_reset_receipts(account)')
    if 'profession_anvil_receipts'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_anvil_account ON profession_anvil_receipts(account_id)')
    if 'consumable_uses'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_consumable_owner_template ON consumable_uses(owner,template)')
    if 'official_pvp_profiles'in tables:
        db.execute('CREATE INDEX IF NOT EXISTS native_achievement_pvp_profile_account ON official_pvp_profiles(account_id,policy)')


def _inventory_units(db,account,kind,*,template=None):
    # Compare the same instance in the committed before/after snapshots. A
    # removed final unit contributes its entire prior count. Quantity is
    # significant: a batch can consume several stones in a single request.
    total=0
    rows=db.execute('SELECT a.before_json,a.after_json FROM inventory_action_receipts a '
        'JOIN character_owners o ON o.uid=a.owner WHERE o.account_id=?AND a.kind=?',(account,kind))
    for before,after in rows:
        # Parse each snapshot once. A correlated JSON scan for every item
        # makes ordinary full bags quadratic in the retained history query.
        remaining={item['uid']:item['count']for item in json.loads(after)}
        total+=sum(max(0,item['count']-remaining.get(item['uid'],0))for item in json.loads(before)
            if template is None or item['template']==template)
    return total


def counts(db,account,condition_types):
    if not condition_types&{2,4,5,16,18,19,23,24,25,26,27,28,32,35,36,43,44,45,51,52,53,56,60,61,62,63}:return {}
    tables=present(db);result={}
    if 2 in condition_types and 'dungeon_records'in tables:
        # The reward writer keeps only positive server-measured best times.
        # Loading, failed runs and old unmeasured zero-time receipts do not
        # create these rows. One account may attain its best on another role.
        for dungeon,seconds in db.execute('SELECT d.map_id,MIN(d.seconds)FROM dungeon_records d '
                'JOIN character_owners o ON o.uid=d.uid WHERE o.account_id=?GROUP BY d.map_id',(account,)):
            result[(2,dungeon)]=seconds
    if condition_types&{4,5}and 'official_pvp_profiles'in tables:
        from els_server.domain.pvp_official_1v1_policy import POLICY,CHANNEL_CLASS
        # These cumulative counters are changed by the sealed official
        # settlement writer. AP spending/registration preserve them; draws
        # and the leaver's penalty do not become defeats. Unknown historical
        # profiles and practice/duel records are not adopted into this policy.
        wins,losses=db.execute("SELECT COALESCE(SUM(json_extract(profile_json,'$.wins')),0),"
            "COALESCE(SUM(json_extract(profile_json,'$.losses')),0)FROM official_pvp_profiles "
            "WHERE account_id=?AND policy=?",(account,POLICY)).fetchone()
        if 4 in condition_types:result[(4,CHANNEL_CLASS)]=wins
        if 5 in condition_types:result[(5,CHANNEL_CLASS)]=losses
    if 'native_couple_pairs_v1'in tables:
        # One immutable generation is created only after mutual acceptance.
        # It belongs to both accounts and survives farewell or remarriage.
        if 18 in condition_types:
            result[(18,0)]=db.execute('SELECT COUNT(*)FROM native_couple_pairs_v1 '
                'WHERE a_account=?OR b_account=?',(account,account)).fetchone()[0]
        if 19 in condition_types and {'native_wedding_bookings','native_wedding_ceremonies'}<=tables:
            # The revamp requires an actual ceremony, including a reminder
            # ceremony. A reservation or deadline marriage is not a wedding;
            # guest attendance is not either spouse holding that ceremony.
            result[(19,0)]=db.execute("SELECT COUNT(*)FROM native_wedding_ceremonies c "
                "JOIN native_wedding_bookings b ON b.id=c.reservation AND b.pair_id=c.pair_id "
                "JOIN native_couple_pairs_v1 p ON p.id=c.pair_id "
                "WHERE c.mode='ceremony'AND b.finished_at=c.at AND b.canceled_at IS NULL "
                "AND(p.a_account=?OR p.b_account=?)",(account,account)).fetchone()[0]
    if 16 in condition_types and 'inventory_action_receipts'in tables:
        # Original16 currently names only189800. Its718 transaction journals
        # the actual owned stack debit, including a removed final unit.
        # A different blessing template, move or failed use cannot contribute.
        result[(16,189800)]=_inventory_units(db,account,0x718,template=189800)
    if 'inventory_action_receipts'in tables:
        if 32 in condition_types:
            # Both ordinary and blacksmith attempts commit5FF. Credit only
            # a successful increase to this exact level, including a smith
            # jump. Amulets use219, so cannot masquerade as paid enhancement.
            rows=db.execute('SELECT a.before_json,a.after_json FROM inventory_action_receipts a '
                'JOIN character_owners o ON o.uid=a.owner WHERE o.account_id=?AND a.kind=?',(account,0x5ff))
            for before,after in rows:
                previous={item['uid']:item.get('enhancement',0)for item in json.loads(before)}
                for item in json.loads(after):
                    level=item.get('enhancement',0);uid=item['uid']
                    if level in(10,11,12,13)and uid in previous and level>previous[uid]:
                        result[(32,level)]=result.get((32,level),0)+1
        # The1C4 writer debits only socket stones. The6E7 writer also journals
        # applying its pending result, which debits zero stones; counting RPCs
        # would award that same paid magic-stone use twice.
        for condition,kind in((45,0x1c4),(60,0x6e7)):
            if condition in condition_types:result[(condition,0)]=_inventory_units(db,account,kind)
        # These are the actual special profession tools. Ordinary crafting
        # and the flask9AE gauge-reward claim are separate operations.
        for condition,kind in((51,0x705),(52,0x707)):
            if condition in condition_types:
                result[(condition,0)]=db.execute('SELECT COUNT(*)FROM inventory_action_receipts a '
                    'JOIN character_owners o ON o.uid=a.owner WHERE o.account_id=?AND a.kind=?',
                    (account,kind)).fetchone()[0]
    if 53 in condition_types and 'profession_anvil_receipts'in tables:
        result[(53,0)]=db.execute('SELECT COUNT(*)FROM profession_anvil_receipts WHERE account_id=?',(account,)).fetchone()[0]
    if 35 in condition_types and 'consumable_uses'in tables:
        from els_server.domain.consumables import catalog
        # Native35's group IDs are COOLTIME_ITEM_GROUP, not the shortcut
        # binding IDs. Each committed use emits its effect once, including
        # an admitted infinite item; retry ACKs do not add another use row.
        definitions=catalog()
        rows=db.execute('SELECT a.template,COUNT(*)FROM consumable_uses a '
            'JOIN character_owners o ON o.uid=a.owner WHERE o.account_id=?GROUP BY a.template',(account,))
        for template,count in rows:
            group=definitions[template]['cooldown_group']
            result[(35,group)]=result.get((35,group),0)+count
    if 36 in condition_types and 'known_resurrection_spends'in tables:
        # The existing writer spends one owned stone per committed current
        # life. Opening a box, free revival and repeated life/operation cannot
        # contribute to this counter.
        result[(36,0)]=db.execute('SELECT COUNT(*)FROM known_resurrection_spends a '
            'JOIN character_owners o ON o.uid=a.owner WHERE o.account_id=?',(account,)).fetchone()[0]
    if 23 in condition_types and 'native_guild_operations_v2'in tables:
        # The committed291 ACK is i32(success),bool(kicked),u64(target).
        # Match an ordinary self-departure; an officer's expulsion is not
        # the officer leaving, and the expelled target did not request it.
        result[(23,0)]=db.execute("SELECT COUNT(*)FROM native_guild_operations_v2 a JOIN character_owners o ON o.uid=a.owner "
            "WHERE o.account_id=?AND a.kind=?AND json_extract(a.result,'$.events[0][0]')=? "
            "AND json_extract(a.result,'$.events[0][1]')=printf('0000000000%016llx',a.owner)",
            (account,0x290,0x291)).fetchone()[0]
    if 56 in condition_types and 'native_guild_operations_v2'in tables:
        # Each successful803 harvest consumes one owned plot, independently
        # of how many crop items its native recipe produces. Plant, remove,
        # water and failed/immature harvests are different operations.
        result[(56,0)]=db.execute("SELECT COUNT(*)FROM native_guild_operations_v2 a JOIN character_owners o ON o.uid=a.owner "
            "WHERE o.account_id=?AND a.kind=?AND json_extract(a.result,'$.events[0][0]')=? "
            "AND substr(json_extract(a.result,'$.events[0][1]'),1,8)='00000000'",
            (account,0x803,0x804)).fetchone()[0]
    if 24 in condition_types and 'native_guild_actions'in tables:
        result[(24,0)]=db.execute('SELECT COUNT(*)FROM native_guild_actions a JOIN character_owners o ON o.uid=a.owner '
            'WHERE o.account_id=?AND a.kind=?',(account,0x6c8)).fetchone()[0]
    if 25 in condition_types and 'native_guild_quest_facts_v2'in tables:
        # Activity100 is the producer's actually credited honor after caps;
        # history survives guild departure and weekly task rollover.
        result[(25,0)]=db.execute("SELECT COALESCE(SUM(json_extract(f.value,'$[1]')),0) "
            "FROM native_guild_quest_facts_v2 a JOIN character_owners o ON o.uid=a.owner "
            "JOIN json_each(a.facts_json,'$.activities')f WHERE o.account_id=?AND json_extract(f.value,'$[0]')=100",
            (account,)).fetchone()[0]
    if 26 in condition_types and 'native_guild_operations_v2'in tables:
        # Board posts have their own successful27D/27E receipt. Editing the
        # announcement/greeting, deleting posts and failed daily-limit calls
        # do not count; the retained receipt survives later post deletion.
        result[(26,0)]=db.execute("SELECT COUNT(*)FROM native_guild_operations_v2 a JOIN character_owners o ON o.uid=a.owner "
            "WHERE o.account_id=?AND a.kind=?AND json_extract(a.result,'$.events[0][0]')=? "
            "AND substr(json_extract(a.result,'$.events[0][1]'),1,8)='00000000'",
            (account,0x27d,0x27e)).fetchone()[0]
    if 27 in condition_types and 'native_player_trades'in tables:
        # perform() seals exactly two different accounts. One trade counts
        # once for each participant, independent of its two inventory receipts.
        result[(27,0)]=db.execute("SELECT COUNT(*)FROM native_player_trades WHERE "
            "json_extract(ledger_json,'$[0].account')=?OR json_extract(ledger_json,'$[1].account')=?",(account,account)).fetchone()[0]
    if 28 in condition_types and 'player_mail_receipts'in tables:
        result[(28,0)]=db.execute('SELECT COUNT(*)FROM player_mail_receipts WHERE account_id=?',(account,)).fetchone()[0]
    if condition_types&{43,44}and 'resonance2026_reset_receipts'in tables:
        from els_server.domain.resonance_2026_reset_items import reset_items
        from els_server.domain.resonance_category_scroll import scroll_items
        # One coin per refunded point, one scroll per category reset. Reuse
        # the owned-item families accepted by the existing debit operations.
        for kind,load_items,item_kind in((43,reset_items,'coin'),(44,scroll_items,'scroll')):
            if kind not in condition_types:continue
            templates=load_items().allowed[item_kind]
            result[(kind,0)]=db.execute("SELECT COALESCE(SUM(json_extract(c.value,'$.quantity')),0) "
                "FROM resonance2026_reset_receipts a JOIN json_each(a.consumed_json)c "
                "WHERE a.account=?AND json_extract(c.value,'$.template')IN("+','.join('?'for _ in templates)+')',
                (account,*templates)).fetchone()[0]
    if condition_types&{61,62}and 'fishing_attempts'in tables:
        # Each settled attempt, including a miss, is one61. Only the actual
        # committed caught item contributes to62, never a bait debit or retry.
        groups=list(db.execute('SELECT caught,fish,COUNT(*)FROM fishing_attempts WHERE account=?GROUP BY caught,fish',(account,)))
        if 61 in condition_types:result[(61,0)]=sum(n for _,_,n in groups)
        if 62 in condition_types:
            result.update({(62,fish):n for caught,fish,n in groups if caught and fish is not None})
    if 63 in condition_types and 'pet_expedition_receipts'in tables:
        result[(63,0)]=db.execute("SELECT COUNT(*)FROM pet_expedition_receipts WHERE account=?AND action='complete'",(account,)).fetchone()[0]
    return result
