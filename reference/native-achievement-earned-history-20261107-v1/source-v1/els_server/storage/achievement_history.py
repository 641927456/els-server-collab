"""Counts come from committed business receipts, including their retained history."""

TABLES=('native_player_trades','player_mail_receipts','fishing_attempts','pet_expedition_receipts','native_guild_actions','native_guild_operations_v2','native_guild_quest_facts_v2','inventory_action_receipts','resonance2026_reset_receipts')


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


def counts(db,account,condition_types):
    if not condition_types&{16,23,24,25,27,28,43,44,56,61,62,63}:return {}
    tables=present(db);result={}
    if 16 in condition_types and 'inventory_action_receipts'in tables:
        # Original16 currently names only189800. Its718 transaction journals
        # the actual owned stack debit, including a removed final unit.
        # A different blessing template, move or failed use cannot contribute.
        result[(16,189800)]=db.execute("SELECT COALESCE(SUM(json_extract(b.value,'$.count')-COALESCE("
            "(SELECT json_extract(c.value,'$.count')FROM json_each(a.after_json)c "
            "WHERE json_extract(c.value,'$.uid')=json_extract(b.value,'$.uid')),0)),0) "
            "FROM inventory_action_receipts a JOIN character_owners o ON o.uid=a.owner "
            "JOIN json_each(a.before_json)b WHERE o.account_id=?AND a.kind=?AND json_extract(b.value,'$.template')=?",
            (account,0x718,189800)).fetchone()[0]
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
