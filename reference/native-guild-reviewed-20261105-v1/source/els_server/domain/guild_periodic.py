"""Use the existing session clock to expire guild Gnosis and weekly fountain effects."""
from contextlib import closing
import sqlite3,time
from els_server.domain.equipment_chip_flow import current_lease
from els_server.domain import guild_rules
from els_server.storage.guild_membership_state import snapshot
from els_server.domain.guild_initial_profile import profile
from els_server.protocol.guild_membership_profile import full_notification
from els_server.protocol.protocol_codec import encode_event

def periodic(s):
    if(s.client_build!='dx11_260923'or not s.item_test or s.role!='game'or s.phase not in('town_ready','guild_agit_ready','dungeon_active')or not current_lease(s)):return []
    from els_server.domain.guild_services import synchronize
    service_events=synchronize(s)
    if s.phase=='guild_agit_ready':
        from els_server.domain.guild_appearance import observe
        observe(s)
    from els_server.domain.guild_expedition import periodic as expedition_clock
    service_events+=expedition_clock(s)
    account=s.account;binding=(account,account.uid,account.account_id,s.shop_session_id);now=int(time.time());old=getattr(s,'_guild_timing',None)
    quest_clock=getattr(s,'_guild_quest_timing',None)
    if old is not None and old[0]==binding and now<old[1]:return service_events
    with closing(sqlite3.connect(account.store.path))as db:
        db.execute('BEGIN');saved=snapshot(db,account.uid,account.account_id)
        due=guild_rules.next_week(now)
        if saved is not None:
            expires=[p['cash_expires']for p in saved['system']['pages'].values()if p['cash_expires']>now]
            if expires:due=min(due,*expires)
        answer=[full_notification(profile(saved,db=db,now=now))]if saved is not None and old is not None and old[0]==binding else []
        if quest_clock is not None and quest_clock[0]==binding and quest_clock[1]!=guild_rules.week(now):
            from els_server.storage.seal_quests import _state
            from els_server.storage.inventory_state import load_items
            from els_server.protocol.quest_messages import initialization
            if all(db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name=?",(t,)).fetchone()for t in('character_quests','completed_quests')):
                answer.append(initialization(_state(db,account.uid,load_items(db,account.uid),now=now)))
        for event in answer:encode_event(event)
        if not current_lease(s)or s.account is not account or(account.uid,account.account_id,s.shop_session_id)!=binding[1:]:return []
    s._guild_timing=(binding,due)
    s._guild_quest_timing=(binding,guild_rules.week(now))
    return service_events+answer
