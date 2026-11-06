"""Native dungeon requests, using the existing authoritative consumers.

Town/shop/housing projections do not run on this path. Scene, owner, item,
death, receipt and transaction checks remain in their original consumers.
"""
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32

KINDS=frozenset((0x113,0x65e,0x219,0xd0,0xad,0xb3,0xb8,0xbb,0x471,
                 0x2ce,0x67,0x38e,0x4e2,0xff20,0xff21,0x640,0x3e6))


def accepts(s,event):
    return (event.event_id==0x202 and event.kind in KINDS
            and s.client_build=='dx11_260923' and s.role=='game'
            and s.enter_dungeon and s.item_test
            and s.phase in ('dungeon_loading','dungeon_active')
            and (s.dungeon_run is not None or s.dungeon_id==30000))


def priority_call(function,args):
    from els_server.domain.local_session import LocalSession
    s=getattr(function,'__self__',None)
    return (isinstance(s,LocalSession) and function.__name__=='handle'
            and len(args)==1 and type(args[0])is Event and accepts(s,args[0]))


def identity_before(s,event):
    if accepts(s,event) and event.kind in (0xad,0xbb,0x219):
        return s.account.character_identity()
    return None


def activity_changed(s,event,replies,before):
    if any(e.event_id==0x201 and e.kind in (0xc1,0xf5,0x2b,0x29f)for e in replies):return True
    if before is None:return False
    after=s.account.character_identity()
    return any(before[k]!=after[k]for k in ('uid','unit_type','unit_class','level','transcendence','master'))


def item_use(s,event,sequence):
    # Preserve the original item-family ordering; these are item consumers,
    # not unrelated feature routes. Their existing catalogs resolve overlaps.
    from els_server.domain.reselection_flow import handle as reselection
    from els_server.domain.artifact_flow import handle_consumable as artifact
    from els_server.domain.character_custom import handle as custom
    from els_server.domain.el_search_collection_flow import handle as collection
    from els_server.domain.rosso_reset import handle as rosso
    from els_server.domain.housing_access_flow import handle as housing_ticket
    from els_server.domain.fishing_vip_flow import handle as fishing_ticket
    from els_server.domain.life_potions_existing import handle as life_potion
    from els_server.domain.challenge_scroll import handle as challenge
    from els_server.domain.wisdom_potions import handle as wisdom
    from els_server.domain.feta_gauge_flow import handle as feta
    from els_server.domain.erp_potion_flow import handle as erp
    from els_server.domain.known_resurrection_flow import handle as resurrection
    from els_server.domain.coupon_flow import handle as coupon
    from els_server.domain.resonance_page_expansion_flow import handle as expansion
    from els_server.domain.elixir_flow import handle as elixir
    from els_server.domain.silver_mirror_flow import invitation as mirror
    from els_server.domain.pet_support_flow import handle as pet
    for handle in (reselection,artifact,custom,collection,rosso,housing_ticket,fishing_ticket,
                   life_potion,challenge,wisdom,feta,erp,resurrection,coupon,expansion,elixir,mirror,pet):
        reply=handle(s,event,sequence)
        if reply is not None:return reply
    # The remaining original219 body only allows town career/expansion items.
    from els_server.domain.title_flow import observe_kills
    observe_kills(s)
    from els_server.protocol.career_messages import use_ack
    return [use_ack(result=-1)]


def dispatch(s,event,sequence):
    kind=event.kind
    if kind in (0x640,0x3e6,0xff20,0xff21,0x113,0x65e,0xd0,0x2ce):
        from els_server.domain.title_flow import observe_kills
        observe_kills(s)
    if kind in (0x640,0x3e6):return []
    if kind in (0xff20,0xff21):
        from els_server.domain.group_wear import capability
        capability(s,event);return []
    if kind==0x38e:
        from els_server.domain.luciel_native_status import handle
        return handle(s,event,sequence)
    if kind==0x4e2:
        from els_server.domain.luciel_state import handle_active
        return handle_active(s,event,sequence)
    if kind in (0x113,0x65e):
        from els_server.domain.consumable_flow import handle
        return handle(s,event,sequence)
    if kind==0x219:return item_use(s,event,sequence)
    if kind==0xd0:
        return s.pickup_world_drop(event)if s.drop_test and s.phase=='dungeon_active'and s.dungeon_substage_synced else []
    if kind==0x2ce:
        from els_server.domain.dungeon_native_actions import spawn
        return spawn(s,event,sequence)
    if kind==0x67:
        from els_server.domain.luciel_native_end import handle
        answer=handle(s,event,sequence)
        if answer is not None:return answer
        from els_server.domain.title_flow import observe_kills
        observe_kills(s)
        from els_server.domain.dungeon_native_actions import end
        return end(s,event,sequence)
    from els_server.domain.pve_economy_flow import solo
    result=solo(s,event)
    if result is not None:return result
    from els_server.domain.title_flow import observe_kills
    observe_kills(s)
    from els_server.domain.first_story_entry import handle as first_story
    result=first_story(s,event)
    if result is not None:return result
    if s.dungeon_run is not None:
        from els_server.domain.dungeon_flow import handle
        result=handle(s,event)
        if result is not None:return result
    from els_server.domain.dungeon_settlement_commands import legacy_dungeon_event
    result=legacy_dungeon_event(s,event)
    if result is not None:return result
    if kind==0xb3:
        from els_server.domain.dungeon_native_actions import loaded
        result=loaded(s,event,sequence)
        return []if result is None else result
    return []


def process(s,event,sequence):
    from els_server.domain.quest_flow import observe
    from els_server.domain.session_auxiliary import maintenance_request,maintenance_reply
    from els_server.domain.environment_buff_flow import bind,synchronize as environment_sync
    from els_server.domain.pending_part_end import remember,finish
    notices=s.expiration_notifications()
    before=[]if not notices and event.kind!=0xd0 and maintenance_request(s,event)else observe(s,notices)
    identity=identity_before(s,event);previous=s.dungeon_run
    remember(s,event,sequence);reply=dispatch(s,event,sequence);bind(s,previous)
    from els_server.domain.fishing_attempt import invalidate
    from els_server.domain.tenebros_storage_flow import abandon
    invalidate(s);abandon(s)
    if not notices and not before and maintenance_reply(s,event,reply):return reply
    if s.account.characters is not None and any(e.kind in (0xd9,0x29f,0xf5)for e in reply):
        from els_server.domain.title_flow import enabled as titles_enabled
        if titles_enabled(s):
            from els_server.storage.titles import state
            from els_server.protocol.title_messages import equipment
            active=state(s.account.store.path,s.account.uid)['title']
            if active:reply.append(equipment(active))
    # These observers consume accepted gameplay/receipt changes. Static town,
    # shop, housing and calendar-window projections stay on their own paths.
    from els_server.domain.pet_progression_flow import observe as pet
    from els_server.domain.mount_flow import observe as mount
    from els_server.domain.artifact_flow import observe as artifact
    answer=notices+before+reply+observe(s,reply)+pet(s,reply)+mount(s)+artifact(s,reply)
    from els_server.domain.resonance_flow import synchronize as resonance
    from els_server.domain.raid_reward_flow import synchronize as raid
    from els_server.domain.feta_limit_flow import synchronize as feta
    answer=feta(s,raid(s,resonance(s,answer)))
    if activity_changed(s,event,answer,identity)and s.activity2026_awards is not None:
        answer=s.activity2026_awards.finalize(s,answer)
    from els_server.domain.growth_guide_flow import synchronize as guide
    answer=guide(s,answer)
    if event.kind in (0xb3,0xbb,0x219)or any(e.kind==0xc1 for e in answer):
        from els_server.domain.normal_fatigue_flow import synchronization as fatigue
        answer=environment_sync(s,fatigue(s,answer))
    from els_server.domain.elixir_flow import remember as remember_elixirs
    return finish(s,remember_elixirs(s,answer))
