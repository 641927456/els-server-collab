"""Ordered optional domain handlers, preserving the original first-match chain.

None declines a request; an empty list consumes it. Keep the explicit call
order, including shared packet kinds and the original guarded callbacks.
"""

# TEMPORARY diagnostics for the wardrobe exchange; state/ is gitignored.
_NOISY=frozenset((0x7d0,0x38e,0xff20,0x0))

# The pet-information window's native nutrient/investment/digestive requests.
# Their storage module owns a new column set, so the dependencies are refreshed
# before the handler runs; all of them are imported lazily elsewhere.
_PET_NUTRITION_MODULES=('els_server.protocol.companion_messages',
    'els_server.storage.pet_progression',
    'els_server.protocol.pet_progression_messages',
    'els_server.domain.pet_digestion',
    'els_server.storage.pet_nutrition',
    'els_server.domain.companion_peer_sync',
    'els_server.domain.pet_nutrition_flow')
_PET_NUTRITION_KINDS=frozenset((0x8ad,0x8af,0x8b9,0x2ea))

# Cube preview/use. Their storage module is imported inside the session method,
# so refreshing it by mtime here lands an admission fix without a restart.
_CUBE_KINDS=frozenset((0x196,0x559))

# Quest accept/abandon/claim. The pinned quest table is lru_cached, so a newly
# registered definition only reaches the next click after those caches drop.
_QUEST_KINDS=frozenset((0xee,0xfa,0xf4))


def _refresh_quest_data():
    import os
    from els_server.paths import PROJECT_ROOT
    path=PROJECT_ROOT/'els_server/data/seal_quests.json'
    try:stamp=(os.path.getmtime(path),os.path.getsize(path))
    except OSError:return
    if _refresh_quest_data.stamp==stamp:return
    try:
        from els_server.domain import seal_quests as quest_table
        quest_table.seal_catalog.cache_clear();quest_table.quest_catalog.cache_clear()
    except Exception:return
    _refresh_quest_data.stamp=stamp


_refresh_quest_data.stamp=None

def _refresh(names):
    import importlib
    modules=[]
    for name in names:modules.append(_live(importlib.import_module(name)))
    return modules


def _live(module):
    """Follow source edits for a handler module outside the hot-reload list.

    Session_dispatch itself is hot-reloaded, so re-checking the dependency's
    mtime here lets a fix to pet auto admission land without stopping the
    server or dropping the client connection.
    """
    import importlib,os
    path=getattr(module,'__file__',None)
    try:stamp=(os.path.getmtime(path),os.path.getsize(path))
    except (OSError,TypeError):return module
    if getattr(module,'SOURCE_STAMP',None)==stamp:return module
    try:module=importlib.reload(module)
    except Exception:return module
    module.SOURCE_STAMP=stamp
    return module

def _wire_debug(event,sequence):
    import os,time
    try:
        path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'state','wire-debug.log')
        payload=event.payload.hex() if isinstance(event.payload,bytes) else str(event.payload)
        with open(path,'a',encoding='utf-8') as handle:
            handle.write('%s kind=%#x event=%#x seq=%r len=%d performers=%r uid=%#x target=%#x mode=%r payload=%s\n'
                %(time.strftime('%H:%M:%S'),event.kind,event.event_id,sequence,
                  len(event.payload)if isinstance(event.payload,bytes)else -1,tuple(event.performers or ()),
                  event.uid,event.target_uid,event.payload_mode,payload))
    except Exception:pass


def _wear_dbg(text):
    import os,time
    try:
        path=os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),'state','wear-debug.log')
        with open(path,'a',encoding='utf-8') as handle:handle.write(time.strftime('%H:%M:%S ')+text+'\n')
    except Exception:pass


# Native104 bag-only rearrangement is not avatar wearing and keeps its own
# storage module; 24 is the artifact path with its own result codes.
_WEAR_BAG_ONLY=frozenset((2,3,4,5,6,21))
# Every phase the original client lets the avatar panel be used in.
_WEAR_PHASES=frozenset(('town_ready','field_active','dungeon_active'))


def _inventory_notice(notice):
    """Absolute inventory rows for cells a wear move rewrote.

    The105 vector is matched against the request, so a cell that changed without
    being asked about (the outgoing piece relocating to its own avatar page)
    leaves the client holding a phantom there and the next click on it resolves
    to nothing. 0xD3 is the plain inventory updater the pickup path already
    uses: same DD46E0 rows, applied by position, no request matching.
    """
    import struct
    from els_server.protocol.protocol_codec import Event
    from els_server.domain.inventory_items import inventory_payload
    from els_server.domain.fashion_state import empty_record
    items=[item for item,_ in notice if item is not None]
    removed=[position for item,position in notice if item is None]
    if not items and not removed:return None
    base=inventory_payload(items) if items else struct.pack('>I',0)
    count=struct.unpack_from('>I',base)[0]+len(removed)
    return Event(0x201,kind=0xd3,
        payload=struct.pack('>I',count)+base[4:]+b''.join(empty_record(*p) for p in removed))


def _wear_options():
    """Runtime A/B switches for the104 reply, no restart needed.

    state/wear-options.json may hold {"notice":false,"snapshot":false} while a
    reply shape is being compared against the real client; missing or malformed
    keeps both on.
    """
    from els_server.paths import PROJECT_ROOT
    import json
    try:
        path=PROJECT_ROOT/'state'/'wear-options.json'
        data=json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(data,dict):return {}
        return {key:bool(data[key]) for key in ('notice','snapshot') if key in data}
    except Exception:
        return {}


def _equipment_snapshot(self):
    """Absolute worn-item vector, byte-identical in shape to the227 refresh.

    Reads the committed rows with its own connection: the operation-scoped
    inventory projection may still hold the pre-move read of this same request.
    """
    from els_server.protocol.protocol_codec import Event
    from els_server.domain.fashion_state import move_ack
    from els_server.storage.read_scope import snapshot_connection
    from els_server.storage.inventory_state import load_items
    with snapshot_connection(self.account.store.path) as db:
        db.execute('BEGIN')
        items=[item for item in load_items(db,self.account.uid) if item['group']==9]
        db.commit()
    if not items:return None
    return Event(0x201,kind=0x105,payload=move_ack([((9,item['slot']),item) for item in items]))


def _native_wear(self,event,request_sequence):
    """Native104 for the phases where local_session's shared branch refuses.

    local_session's 104 branch accepts town_ready only, so an avatar change in
    a field or a dungeon came back as the blank native error. That branch lives
    in a module holding live sessions and cannot be re-executed in place, so the
    plain wear case is answered here - session_dispatch is hot reloaded and runs
    before local_session._handle. Bag-only rearrangement, the artifact path and
    the fishing-equipment path still decline here and keep their own branches.
    """
    if (getattr(self,'phase',None) not in _WEAR_PHASES or getattr(self,'role',None)!='game'
        or not getattr(self,'item_test',False) or getattr(self,'client_build',None)!='dx11_260923'):return None
    payload=event.payload
    if (not isinstance(payload,bytes) or len(payload)!=11 or event.performers!=(0,)
        or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):return None
    if payload[0]==payload[5] and payload[0] in _WEAR_BAG_ONLY:return None
    if 24 in (payload[0],payload[5]):return None
    if not getattr(self,'normal_equipment_moves_enabled',False):
        # Same gate local_session applies: ordinary equipment and non-avatar
        # equipment slots stay closed on this profile.
        from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
        import struct as _struct
        pairs=((payload[0],_struct.unpack_from('>i',payload,1)[0]),(payload[5],_struct.unpack_from('>i',payload,6)[0]))
        if any(g in (1,2) or g==9 and slot not in FASHION_EQUIP_SLOTS.values() for g,slot in pairs):return None
    from els_server.protocol.protocol_codec import Event
    from els_server.domain import tutorial_accessory as accessory_gate
    from els_server.storage import wear_moves as wear_store
    from els_server.domain.fashion_state import move_ack
    _wear_dbg('104 take phase=%s payload=%s'%(self.phase,payload.hex()))
    notice=[]
    try:
        captured=accessory_gate.wear_context(self)
        ack=wear_store.move(self.account.store.path,payload,self.account.uid,
            account_id=self.account.account_id,session_id=self.shop_session_id,
            sequence=request_sequence,validate=lambda:accessory_gate.validate_wear_context(self,captured),
            notice=notice)
    except ValueError as error:
        _wear_dbg('104 reject phase=%s %s payload=%s'%(self.phase,error,payload.hex()))
        ack=move_ack(result=1)
    reply=[Event(0x201,kind=0x105,payload=ack)]
    options=_wear_options()
    try:
        extra=_inventory_notice(notice) if options.get('notice',True) else None
    except Exception:
        import traceback;traceback.print_exc()
        extra=None
    if extra is not None:reply.append(extra)
    if ack[-4:]==bytes(4) and options.get('snapshot',True):
        # The request-matched105 vector only repaints the two cells the client
        # named - the worn model itself is refreshed from the absolute equipment
        # snapshot the scene-ready (227) path pushes. A swap therefore landed in
        # SQL while the character kept its old shoes on screen. Re-send the same
        # snapshot shape 227 uses, from the state the move just committed.
        try:
            snapshot=_equipment_snapshot(self)
        except Exception:
            import traceback;traceback.print_exc()
            snapshot=None
        if snapshot is not None:reply.append(snapshot)
    _wear_dbg('104 reply phase=%s kinds=%r ack=%dB notice=%d'%(self.phase,
        [hex(e.kind) for e in reply],len(ack),len(notice)))
    return reply


def priority_handlers(self,event,request_sequence=None):
    if event.event_id==0x202 and event.kind==0x104:
        # Native104 wear/swap is also imported lazily, so an edit to the move
        # rules has to reach the live session without dropping the client.
        try:
            from els_server.storage import wear_moves as wear_store
            from els_server.domain import fashion_state as fashion_domain
            from els_server.domain import tutorial_accessory as accessory_gate
            from els_server.domain import inventory_items as inventory_rules
            # inventory_items first: the other three import validate_item by
            # value, so they have to be re-executed after it.
            _live(inventory_rules);_live(fashion_domain);_live(wear_store);_live(accessory_gate)
        except Exception:
            import traceback;traceback.print_exc()
        try:
            away_reply=_native_wear(self,event,request_sequence)
        except Exception:
            import traceback;traceback.print_exc()
            away_reply=None
        if away_reply is not None:return away_reply
    if event.event_id==0x202 and event.kind==0x219:
        # A permanent custom book is used straight from the inventory tab, so
        # the 219 chain must follow catalog edits too. Domain first: the store
        # re-imports its functions when it reloads.
        try:
            from els_server.domain import character_custom as custom_domain
            from els_server.storage import character_custom as custom_store
            _live(custom_domain);_live(custom_store)
        except Exception:
            import traceback;traceback.print_exc()
    # Artifact level-up items and EXP potions are kind219 too, and their own
    # admission must run before every other 219 family.
    try:
        from els_server.domain import artifact_flow
        artifact_consumable_reply=_live(artifact_flow).handle_consumable(self,event,request_sequence)
    except Exception:
        import traceback;traceback.print_exc()
        artifact_consumable_reply=None
    if artifact_consumable_reply is not None:return artifact_consumable_reply
    # Native synergy tickets share kind219 with every other usable item, so the
    # exact owned-template admission has to run before the generic families.
    try:
        from els_server.domain.el_search_collection_flow import handle as collection_ticket_handle
        collection_ticket_reply=collection_ticket_handle(self,event,request_sequence)
    except Exception:
        import traceback;traceback.print_exc()
        collection_ticket_reply=None
    if collection_ticket_reply is not None:return collection_ticket_reply
    # A failed hot edit must never take the whole request chain down with it.
    try:
        from els_server.domain import pet_auto_flow
        pet_auto_reply=_live(pet_auto_flow).handle(self,event,request_sequence)
    except Exception:
        import traceback;traceback.print_exc()
        pet_auto_reply=None
    if pet_auto_reply is not None:return pet_auto_reply
    if event.event_id==0x202 and event.kind in _PET_NUTRITION_KINDS:
        try:
            pet_nutrition_reply=_refresh(_PET_NUTRITION_MODULES)[-1].handle(self,event,request_sequence)
        except Exception:
            import traceback;traceback.print_exc()
            pet_nutrition_reply=None
        if pet_nutrition_reply is not None:return pet_nutrition_reply
    if event.event_id==0x202 and event.kind in _QUEST_KINDS:_refresh_quest_data()
    if event.event_id==0x202 and event.kind in _CUBE_KINDS:
        # Storage-level cube admission: a Count0/Count1 fix must apply to the
        # next click instead of waiting for the player to relog.
        try:
            import importlib
            _live(importlib.import_module('els_server.storage.fixed_cubes'))
        except Exception:pass
    if event.kind not in _NOISY:_wire_debug(event,request_sequence)
    try:
        from els_server.domain import wardrobe_open_flow
        wardrobe_open_reply=_live(wardrobe_open_flow).handle(self,event,request_sequence)
    except Exception:
        import traceback;traceback.print_exc()
        wardrobe_open_reply=None
    if wardrobe_open_reply is not None:return wardrobe_open_reply
    from els_server.domain.bag_expansion_flow import handle as bag_expansion_handle
    bag_expansion_reply=bag_expansion_handle(self,event,request_sequence)
    if bag_expansion_reply is not None:return bag_expansion_reply
    from els_server.domain.black_market_flow import handle as black_market_handle
    black_market_reply=black_market_handle(self,event,request_sequence)
    if black_market_reply is not None:return black_market_reply
    from els_server.domain.black_market_box_flow import handle as market_box_handle
    market_box_reply=market_box_handle(self,event,request_sequence)
    if market_box_reply is not None:return market_box_reply
    from els_server.domain.pve_economy_flow import solo as ordinary_economy
    ordinary_reply=ordinary_economy(self,event)
    if ordinary_reply is not None:return ordinary_reply
    from els_server.domain.rosso_reset import handle as rosso_reset_handle
    rosso_reset_reply=rosso_reset_handle(self,event,request_sequence)
    if rosso_reset_reply is not None:return rosso_reset_reply
    from els_server.domain.raid_reward_flow import handle as raid_reward_handle
    raid_reward_reply=raid_reward_handle(self,event,request_sequence)
    if raid_reward_reply is not None:return raid_reward_reply
    from els_server.domain.ariel_attendance_flow import handle as ariel_attendance_handle
    ariel_attendance_reply=ariel_attendance_handle(self,event,request_sequence)
    if ariel_attendance_reply is not None:return ariel_attendance_reply
    from els_server.domain.housing_layout_flow import handle as housing_layout_handle
    housing_layout_reply=housing_layout_handle(self,event,request_sequence)
    if housing_layout_reply is not None:return housing_layout_reply
    from els_server.domain.relationship_flow import handle as relationship_handle
    relationship_reply=relationship_handle(self,event,request_sequence)
    if relationship_reply is not None:return relationship_reply
    from els_server.domain.guild_agit_flow import handle as guild_agit_handle
    guild_agit_reply=guild_agit_handle(self,event,request_sequence)
    if guild_agit_reply is not None:return guild_agit_reply
    from els_server.domain.housing_room_flow import handle as housing_room_handle
    housing_room_reply=housing_room_handle(self,event,request_sequence)
    if housing_room_reply is not None:return housing_room_reply
    from els_server.domain.housing_access_flow import handle as housing_access_handle
    housing_access_reply=housing_access_handle(self,event,request_sequence)
    if housing_access_reply is not None:return housing_access_reply
    from els_server.domain.fishing_vip_flow import handle as fishing_vip_handle
    fishing_vip_reply=fishing_vip_handle(self,event,request_sequence)
    if fishing_vip_reply is not None:return fishing_vip_reply
    from els_server.domain.fishing_attempt import handle as fishing_handle
    fishing_reply=fishing_handle(self,event,request_sequence)
    if fishing_reply is not None:return fishing_reply
    from els_server.domain.skill_page_shop_flow import handle as skill_page_shop_handle
    skill_page_shop_reply=skill_page_shop_handle(self,event,request_sequence)
    if skill_page_shop_reply is not None:return skill_page_shop_reply
    from els_server.domain.potion_choice_box import handle as potion_choice_handle
    potion_choice_reply=potion_choice_handle(self,event,request_sequence)
    if potion_choice_reply is not None:return potion_choice_reply
    from els_server.domain.teacher_elixir_boxes import handle as teacher_elixir_handle
    teacher_elixir_reply=teacher_elixir_handle(self,event,request_sequence)
    if teacher_elixir_reply is not None:return teacher_elixir_reply
    from els_server.domain.life_potions_existing import handle as life_potion_handle
    life_potion_reply=life_potion_handle(self,event,request_sequence)
    if life_potion_reply is not None:return life_potion_reply
    from els_server.domain.normal_fatigue_flow import potion as normal_fatigue_potion
    normal_fatigue_reply=normal_fatigue_potion(self,event,request_sequence)
    if normal_fatigue_reply is not None:return normal_fatigue_reply
    from els_server.domain.skill_trait_reset_flow import handle as trait_reset_handle
    trait_reset_reply=trait_reset_handle(self,event,request_sequence)
    if trait_reset_reply is not None:return trait_reset_reply
    from els_server.domain.challenge_scroll import handle as challenge_scroll_handle
    challenge_scroll_reply=challenge_scroll_handle(self,event,request_sequence)
    if challenge_scroll_reply is not None:return challenge_scroll_reply
    from els_server.domain.wisdom_potions import handle as wisdom_potion_handle
    wisdom_potion_reply=wisdom_potion_handle(self,event,request_sequence)
    if wisdom_potion_reply is not None:return wisdom_potion_reply
    from els_server.domain.feta_gauge_flow import handle as feta_gauge_handle
    feta_gauge_result=feta_gauge_handle(self,event,request_sequence)
    if feta_gauge_result is not None:return feta_gauge_result
    from els_server.domain.erp_potion_flow import handle as erp_potion_handle
    erp_potion_reply=erp_potion_handle(self,event,request_sequence)
    if erp_potion_reply is not None:return erp_potion_reply
    from els_server.domain.known_resurrection_flow import handle as known_resurrection_handle
    known_resurrection_reply=known_resurrection_handle(self,event,request_sequence)
    if known_resurrection_reply is not None:return known_resurrection_reply
    from els_server.domain.coupon_flow import handle as coupon_handle
    coupon_reply=coupon_handle(self,event,request_sequence)
    if coupon_reply is not None:return coupon_reply
    # Native customization opener/Apply. Follow source edits so a fix lands on
    # the running session; the 0x4CB kind is shared, so this stays in its
    # original first-match position behind the Ariel mark handler above.
    if event.event_id==0x202 and event.kind in (0x634,0x4cb):
        try:
            from els_server.domain import character_custom
            _live(character_custom)
            from els_server.storage import character_custom as custom_store
            custom_reply=_live(custom_store).handle(self,event,request_sequence)
        except Exception:
            import traceback;traceback.print_exc()
            custom_reply=None
    else:
        from els_server.domain.character_custom import handle as custom_handle
        custom_reply=custom_handle(self,event,request_sequence)
    if custom_reply is not None:return custom_reply
    from els_server.domain.resonance_page_expansion_flow import handle as page_expansion_handle
    page_expansion_reply=page_expansion_handle(self,event,request_sequence)
    if page_expansion_reply is not None:return page_expansion_reply

    from els_server.domain.resonance_period_flow import handle as resonance_period_handle
    resonance_period_reply=resonance_period_handle(self,event,request_sequence)
    if resonance_period_reply is not None:return resonance_period_reply
    from els_server.domain.resonance_allocation_flow import handle as resonance_allocation_handle
    resonance_allocation_reply=resonance_allocation_handle(self,event,request_sequence)
    if resonance_allocation_reply is not None:return resonance_allocation_reply
    return None


def feature_handlers(self,event,request_sequence=None):
    from els_server.domain.assembly_flow import handle as assembly_handle
    assembly_reply=assembly_handle(self,event,request_sequence)
    if assembly_reply is not None:return assembly_reply
    from els_server.domain.random_mission_flow import handle as mission_handle
    mission_reply=mission_handle(self,event)
    if mission_reply is not None:return mission_reply
    from els_server.domain.elixir_flow import handle as world_elixir_handle
    world_elixir_reply=world_elixir_handle(self,event,request_sequence)
    if world_elixir_reply is not None:return world_elixir_reply
    from els_server.domain.avatar_set_flow import handle as avatar_set_handle
    avatar_set_reply=avatar_set_handle(self,event,request_sequence)
    if avatar_set_reply is not None:return avatar_set_reply
    from els_server.domain.fishing_village1500 import handle as fishing1500_handle
    fishing1500_reply=fishing1500_handle(self,event,request_sequence)
    if fishing1500_reply is not None:return fishing1500_reply
    from els_server.domain.town_travel_flow import handle as town_travel_handle

    town_travel_reply=town_travel_handle(self,event,request_sequence)

    if town_travel_reply is not None:return town_travel_reply

    if self.activity2026_awards is not None:
        from els_server.domain.local_bootstrap_clock import handle as bootstrap_clock_handle
        bootstrap_reply=bootstrap_clock_handle(self,event)
        if bootstrap_reply is not None:return bootstrap_reply
    from els_server.domain.character_lifecycle_flow import handle as lifecycle_handle

    lifecycle_reply=lifecycle_handle(self,event)

    if lifecycle_reply is not None:return lifecycle_reply

    from els_server.domain.character_selection_flow import handle as selection_handle

    selection_reply=selection_handle(self,event)

    if selection_reply is not None:return selection_reply

    from els_server.domain.ordinary_skill_pages import handle as ordinary_pages_handle
    ordinary_pages_reply=ordinary_pages_handle(self,event,request_sequence)
    if ordinary_pages_reply is not None:return ordinary_pages_reply
    from els_server.domain.luciel_native_end import handle as luciel_end_handle

    luciel_end_reply=luciel_end_handle(self,event,request_sequence)

    if luciel_end_reply is not None:return luciel_end_reply

    from els_server.domain.luciel_native_status import handle as luciel_status_handle

    luciel_status_reply=luciel_status_handle(self,event,request_sequence)

    if luciel_status_reply is not None:return luciel_status_reply

    from els_server.domain.luciel_state import handle_active as luciel_active_handle

    luciel_active_reply=luciel_active_handle(self,event,request_sequence)

    if luciel_active_reply is not None:return luciel_active_reply

    from els_server.domain.luciel_state import handle as luciel_handle

    luciel_reply=luciel_handle(self,event,request_sequence)

    if luciel_reply is not None:return luciel_reply

    from els_server.domain.player_mail_flow import handle as player_mail_handle

    player_mail_reply=player_mail_handle(self,event,request_sequence)

    if player_mail_reply is not None:return player_mail_reply

    from els_server.domain.mailbox_extras import handle as mailbox_handle

    mailbox_reply=mailbox_handle(self,event,request_sequence)

    if mailbox_reply is not None:return mailbox_reply

    from els_server.domain.mail_flow import handle as mail_handle

    mail_reply=mail_handle(self,event)

    if mail_reply is not None:return mail_reply

    from els_server.domain.anvil_flow import handle as anvil_handle
    anvil_reply=anvil_handle(self,event,request_sequence)
    if anvil_reply is not None:return anvil_reply
    from els_server.domain.manufacture_flow import handle as manufacture_handle

    manufacture_reply=manufacture_handle(self,event,request_sequence)

    if manufacture_reply is not None:return manufacture_reply

    from els_server.domain.title_flow import handle as title_handle

    title_reply=title_handle(self,event)

    if title_reply is not None:return title_reply

    from els_server.domain.challenge_flow import handle as challenge_handle

    challenge_reply=challenge_handle(self,event)

    if challenge_reply is not None:return challenge_reply

    if self.account.characters is not None:

        from els_server.domain.dungeon_rotation import handle as rotation_handle

        rotation_reply=rotation_handle(self,event)

        if rotation_reply is not None:return rotation_reply

    from els_server.domain.silver_mirror_flow import invitation as mirror_invitation
    invitation_reply=mirror_invitation(self,event,request_sequence)
    if invitation_reply is not None:return invitation_reply

    from els_server.domain.companion_flow import handle as companion_handle

    companion_reply=companion_handle(self,event,request_sequence)

    if companion_reply is not None:return companion_reply

    from els_server.domain.pet_support_flow import handle as pet_support_handle

    pet_support_reply=pet_support_handle(self,event,request_sequence)

    if pet_support_reply is not None:return pet_support_reply

    from els_server.domain.equipment_reforge_transfer_flow import handle as transfer_handle
    transfer_reply=transfer_handle(self,event,request_sequence)
    if transfer_reply is not None:return transfer_reply
    from els_server.domain.equipment_reforge_flow import handle as reforge_handle

    reforge_reply=reforge_handle(self,event,request_sequence)

    if reforge_reply is not None:return reforge_reply

    from els_server.domain.equipment_engrave_flow import handle as engrave_handle

    engrave_reply=engrave_handle(self,event,request_sequence)

    if engrave_reply is not None:return engrave_reply

    from els_server.domain.modern_synthesis_flow import handle as modern_synthesis
    synthesis_reply=modern_synthesis(self,event,request_sequence)
    if synthesis_reply is not None:return synthesis_reply
    from els_server.domain.chip_circuit_transfer_flow import handle as chip_circuit_transfer_handle
    chip_circuit_transfer_reply=chip_circuit_transfer_handle(self,event,request_sequence)
    if chip_circuit_transfer_reply is not None:return chip_circuit_transfer_reply
    from els_server.domain.neblon_role_change_flow import handle as neblon_role_handle
    neblon_role_reply=neblon_role_handle(self,event,request_sequence)
    if neblon_role_reply is not None:return neblon_role_reply
    from els_server.domain.equipment_cartridge_flow import handle as cartridge_handle
    cartridge_reply=cartridge_handle(self,event,request_sequence)
    if cartridge_reply is not None:return cartridge_reply
    from els_server.domain.tenebros_identification_flow import handle as tenebros_identification_handle
    tenebros_identification_reply=tenebros_identification_handle(self,event,request_sequence)
    if tenebros_identification_reply is not None:return tenebros_identification_reply
    from els_server.domain.tenebros_conversion_flow import handle as tenebros_conversion_handle
    tenebros_conversion_reply=tenebros_conversion_handle(self,event,request_sequence)
    if tenebros_conversion_reply is not None:return tenebros_conversion_reply
    from els_server.domain.tenebros_storage_flow import handle as tenebros_storage_handle
    tenebros_storage_reply=tenebros_storage_handle(self,event,request_sequence)
    if tenebros_storage_reply is not None:return tenebros_storage_reply
    from els_server.domain.tenebros_capacity_flow import handle as tenebros_capacity_handle
    tenebros_capacity_reply=tenebros_capacity_handle(self,event,request_sequence)
    if tenebros_capacity_reply is not None:return tenebros_capacity_reply
    from els_server.domain.equipment_chip_flow import handle as chip_handle

    chip_reply=chip_handle(self,event,request_sequence)

    if chip_reply is not None:return chip_reply

    from els_server.domain.exascale_color_flow import handle as color_handle

    color_reply=color_handle(self,event,request_sequence)

    if color_reply is not None:return color_reply

    from els_server.domain.spell_socket_flow import handle as spell_fill_handle
    spell_fill_reply=spell_fill_handle(self,event,request_sequence)
    if spell_fill_reply is not None:return spell_fill_reply
    from els_server.domain.equipment_spell_exchange_flow import handle as spell_exchange_handle
    spell_exchange_reply=spell_exchange_handle(self,event,request_sequence)
    if spell_exchange_reply is not None:return spell_exchange_reply
    from els_server.domain.equipment_circuit_flow import handle as circuit_handle

    circuit_reply=circuit_handle(self,event,request_sequence)

    if circuit_reply is not None:return circuit_reply

    from els_server.domain.market_conversion_flow import handle as market_conversion_handle
    market_conversion_reply=market_conversion_handle(self,event,request_sequence)
    if market_conversion_reply is not None:return market_conversion_reply
    from els_server.domain.option_conversion_existing_flow import handle as existing_conversion_handle
    existing_conversion_reply=existing_conversion_handle(self,event,request_sequence)
    if existing_conversion_reply is not None:return existing_conversion_reply
    from els_server.domain.artifact_flow import handle as artifact_handle

    artifact_reply=artifact_handle(self,event,request_sequence)

    if artifact_reply is not None:return artifact_reply

    from els_server.domain.trade_board_flow import handle as trade_board_handle
    trade_board_result=trade_board_handle(self,event,request_sequence)
    if trade_board_result is not None:return trade_board_result
    from els_server.domain.board_ranking_flow import handle as board_ranking_handle
    board_ranking_result=board_ranking_handle(self,event,request_sequence)
    if board_ranking_result is not None:return board_ranking_result
    from els_server.domain.quest_flow import handle as quest_handle

    if self.activity2026_awards is not None:
        answer=self.activity2026_awards.handle(self,event,request_sequence)
        if answer is not None:return answer
    quest_reply=quest_handle(self,event,request_sequence)

    if quest_reply is not None:return quest_reply

    from els_server.domain.first_story_entry import handle as first_story_handle

    first_story_reply=first_story_handle(self,event)

    if first_story_reply is not None:return first_story_reply
    return None
