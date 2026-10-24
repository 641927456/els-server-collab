"""Minimal connection-local business phases for the single-player experiment."""
from els_server.protocol.local_messages import responses,character_list,client_economy_fields,character_gate_notice,player_initialization,inventory_initialization,optional_player_initializations,skill_slots_initialization,i32,u32,wstring,LOCAL_TOWN_MAP
from els_server.protocol.protocol_codec import Event
import struct
import math
import threading
import uuid
import hashlib
from els_server.domain.dungeon_clock import DungeonClock
from els_server.storage.local_state import DEFAULT_LOCATION,TOWN_SCENES,scene_ready_location,movement_location,validate_location
from els_server.domain.ui_layout import DEFAULT_LAYOUT,encode_layout,decode_layout
from els_server.protocol.local_messages import key_bindings_initialization
from els_server.domain.key_bindings import DEFAULT_BINDINGS,validate_bindings
from els_server.domain.skill_state import DEFAULT_SLOTS,validate_slots,equip_request
from els_server.domain.skill_rules import equippable_skills,upgraded_slots
import els_server.protocol.dungeon_messages as dungeon_messages  # Pin experimental builders at startup with local_messages.

class SessionOrderError(ValueError):pass

class LocalAccount:
    def __init__(self,store=None,account_id=1,account_name='local'):
        self.account_id=account_id;self.account_name=account_name
        self.terms_accepted=False;self.lock=threading.Lock();self.store=store
        self.uid=store.uid if store else 1001
        self.characters=None;self.character_accounts={};self.root=self
        self.location=store.load() if store else dict(DEFAULT_LOCATION)
        self.layout=store.load_layout() if store else DEFAULT_LAYOUT
        self.bindings=store.load_bindings() if store else DEFAULT_BINDINGS
        self.skills=store.load_skills() if store else DEFAULT_SLOTS
        self.reward_store=None;self.inventory_store=None
    def enable_characters(self):
        self.enable_inventory()
        from els_server.storage.characters import Characters
        self.characters=Characters(self.store.path,self.account_id)
        from els_server.storage.role_loadout import repair_created_loadouts
        self.initial_loadout_repair=repair_created_loadouts(self.store.path)
        from els_server.storage.master_presets import repair as repair_master_presets
        self.master_preset_repair=repair_master_presets(self.store.path)
        self.character_accounts[self.uid]=self
    def character_identity(self):
        from els_server.storage.read_scope import role_projection
        return role_projection(self,self._character_identity_projection,projection='identity')

    def _character_identity_projection(self):
        return self.characters.identity(self.uid) if self.characters else None

    def character(self):
        from els_server.storage.read_scope import role_projection
        return role_projection(self,self._character_projection)

    def _character_projection(self):
        character=self.characters.get(self.uid) if self.characters else None
        if character is not None and self.store is not None:
            from els_server.storage.bank_state import snapshot as bank_snapshot
            character.update(bank_snapshot(self.store.path,self.uid))
            from els_server.storage.boosting_2026_force_inventory import snapshot as force_snapshot
            from els_server.storage.boosting_2026_force_equipment import snapshot as force_slot_snapshot
            character['force_inventory']=force_snapshot(self.store.path,self.uid)
            character['force_slots']=force_slot_snapshot(self.store.path,self.uid)
            from els_server.storage.wardrobe import snapshot as wardrobe_snapshot
            character['wardrobe']=wardrobe_snapshot(self.store.path,self.uid,self.account_id)
            from els_server.storage.wardrobe import favorite_snapshot
            character['wardrobe_favorites']=favorite_snapshot(self.store.path,self.uid,self.account_id)
            from els_server.storage.resurrection_counter import snapshot as known_resurrection_count
            character['known_resurrection_count']=known_resurrection_count(self.store.path,self.uid)
            from els_server.storage.guild_membership_state import cold as guild_membership_cold
            character['guild_membership']=guild_membership_cold(self.store.path,self.uid,self.account_id)
        return character
    def for_character(self,uid):
        if self.characters is None:
            if uid!=self.uid:raise ValueError('Unknown character')
            return self
        self.characters.get(uid)
        root=self.root
        if uid not in root.character_accounts:
            from els_server.storage.local_state import LocalState
            account=LocalAccount(LocalState(self.store.path,uid),self.account_id,self.account_name)
            account.root=root;account.characters=self.characters
            account.enable_inventory();root.character_accounts[uid]=account
        return root.character_accounts[uid]
    def character_list(self):
        result=[]
        for c in self.characters.list():
            account=self.for_character(c['uid'])
            snapshot=account.get_inventory_snapshot()
            result.append(dict(c,economy=snapshot['balances'],items=snapshot['items'],location=account.get_location()))
        return result
    def enable_rewards(self):
        if self.store is None:raise ValueError('Persistent rewards require a save file')
        with self.lock:
            if self.reward_store is None:
                from els_server.storage.reward_state import RewardState
                self.reward_store=RewardState(self.store.path,self.uid,account_id=self.account_id)
        return self.reward_store
    def get_reward_balances(self):
        return self.enable_rewards().balances()
    def enable_inventory(self):
        from els_server.domain.owned_growth_items import install as install_owned_growth
        install_owned_growth()
        self.enable_rewards()
        with self.lock:
            if self.inventory_store is None:
                from els_server.storage.inventory_state import InventoryState
                self.inventory_store=InventoryState(self.store.path,self.uid)
        return self.inventory_store
    def get_inventory_snapshot(self):
        inventory=self.enable_inventory()
        if self.store:
            from els_server.storage.equipment_circuits import repair_missing
            repair_missing(self.store.path,self.uid)
        return inventory.snapshot()
    def get_skills(self):
        with self.lock:
            self.skills=self.store.load_skills() if self.store else upgraded_slots(self.skills,self.character())
            return self.skills
    def save_skills(self,slots):
        slots=validate_slots(slots,equippable_skills(self.character()),self.character())
        with self.lock:self.skills=self.store.save_skills(slots,account_id=self.account_id if self.characters is not None else None) if self.store else slots
    def equip_skill(self,payload):
        with self.lock:
            if self.store:
                slots,ack=self.store.equip_skill(payload,account_id=self.account_id if self.characters is not None else None)
            else:
                character=self.character()
                slots,ack=equip_request(payload,upgraded_slots(self.skills,character),equippable_skills(character),character)
            self.skills=slots
            return ack
    def get_bindings(self):
        # Keyboard mappings belong to the authenticated account, including
        # its still-empty roster. Preserve the established 28/399 send timing.
        from els_server.storage.account_key_bindings import load,account_identity
        account_identity(self.account_id)
        path=getattr(self.root,'path',None) or (self.store.path if self.store else None)
        if path is not None and self.characters is not None:
            with self.root.lock:return load(path,self.account_id)
        with self.lock:return self.bindings
    def save_bindings(self,payload):
        from els_server.storage.account_key_bindings import save,account_identity
        account_identity(self.account_id)
        payload=validate_bindings(payload)
        path=getattr(self.root,'path',None) or (self.store.path if self.store else None)
        if path is not None and self.characters is not None:
            with self.root.lock:self.bindings=save(path,self.account_id,payload)
        else:
            with self.lock:self.bindings=self.store.save_bindings(payload) if self.store else payload
    def get_layout(self):
        with self.lock:return self.layout
    def save_layout(self,payload):
        values=decode_layout(payload)
        with self.lock:self.layout=self.store.save_layout(values) if self.store else values
    def get_location(self):
        with self.lock:return dict(self.location)
    def save_location(self,map_id,board,progress,xyz):
        validate_location(map_id,board,progress,xyz)
        with self.lock:
            if self.store:self.location=self.store.save(map_id,board,progress,xyz)
            else:self.location={**self.location,'map':map_id,'board':board,'progress':progress,'xyz':xyz}
    def accept_terms(self):
        with self.root.lock:self.root.terms_accepted=True
    def has_terms(self):
        with self.root.lock:return self.root.terms_accepted

class LocalSession:
    def __init__(self,account=None,enter_town=False,enter_dungeon=False,client_build='legacy',npc_slot_test=False,gate_test=False,population_test=False,clear_test=False,reward_probe=False,reward_test=False,item_test=False,drop_probe=False,drop_test=False,boss_gauge_test=False,shop_test=False,ice_test=False,port_probe_port=1,attribute_enchant_enabled=False,normal_equipment_moves_enabled=False,equipment_repair_enabled=False,activity2026_awards=None):
        if client_build not in ('legacy','dx11_260923'):raise ValueError('Unknown client schema')
        self.client_build=client_build
        self.port_probe_port=port_probe_port
        self.account=account if account is not None else LocalAccount()
        self.role=None
        self.phase='new'
        self.completed=set()
        self.enter_town=enter_town
        self.active_map=None;self.pending_map=None
        self.enter_dungeon=enter_dungeon;self.dungeon_requested=False
        self.dungeon_id=30000;self.requested_dungeon_id=None;self.requested_dungeon_mode=None;self.dungeon_run=None
        self.dungeon_substage_synced=False
        self.dungeon_clock=DungeonClock()
        self.summon_next_key=16;self.summon_requests={}
        self.summon_keys=set();self.summon_deaths={}
        self.dungeon_end_payload=None
        if npc_slot_test and (client_build!='dx11_260923' or not enter_dungeon):raise ValueError('NPC slot experiment requires DX11 dungeon')
        self.npc_slot_test=npc_slot_test;self.defeated_npcs={};self.part_end_notified=False
        if gate_test and not npc_slot_test:raise ValueError('Gate test requires isolated NPC slot experiment')
        self.gate_test=gate_test
        if population_test and not gate_test:raise ValueError('Population test requires isolated gate profile')
        self.population_test=population_test
        if boss_gauge_test and not population_test:raise ValueError('Boss gauge test requires isolated original population')
        self.boss_gauge_test=boss_gauge_test
        if clear_test and not population_test:raise ValueError('Clear test requires isolated population profile')
        self.clear_test=clear_test;self.clear_notified=False
        if reward_probe and not clear_test:raise ValueError('Reward probe requires isolated clear profile')
        self.reward_probe=reward_probe
        if reward_test and (not clear_test or reward_probe):raise ValueError('Persistent reward test requires clear profile without diagnostic markers')
        self.reward_test=reward_test;self.reward_run_id=None;self.reward_receipt=None;self.clear_items_synced=False
        if reward_test:self.account.enable_rewards()
        if item_test and not reward_test:raise ValueError('Item test requires isolated persistent reward profile')
        self.item_test=item_test;self.inventory_town_sync_sent=False
        if type(attribute_enchant_enabled) is not bool or attribute_enchant_enabled and (not item_test or client_build!='dx11_260923'):raise ValueError('Attribute enchant requires verified DX11 inventory')
        self.attribute_enchant_enabled=attribute_enchant_enabled
        if type(normal_equipment_moves_enabled) is not bool or normal_equipment_moves_enabled and (not item_test or client_build!='dx11_260923'):raise ValueError('Equipment moves require verified DX11 inventory')
        self.normal_equipment_moves_enabled=normal_equipment_moves_enabled
        if type(equipment_repair_enabled) is not bool or equipment_repair_enabled and (not item_test or client_build!='dx11_260923'):raise ValueError('Repair requires verified DX11 inventory')
        self.equipment_repair_enabled=equipment_repair_enabled
        self.dungeon_return_pending=False
        if item_test:self.account.enable_inventory()
        if shop_test and (not item_test or not enter_town or client_build!='dx11_260923'):
            raise ValueError('Shop test requires isolated DX11 saved inventory and Town')
        self.shop_test=shop_test;self.shop_available_pending=False
        self.shop_session_id=str(uuid.uuid4());self.ed_catalog_loaded=False
        self.npc_history_id=self.shop_session_id
        self.fixed_cube_preview_template=None
        self.fixed_cube_operations={}
        if ice_test and (not item_test or not enter_town or client_build!='dx11_260923'):raise ValueError('Ice test requires isolated DX11 Town inventory')
        self.ice_test=ice_test;self.ice_preview_ready=False
        if drop_probe and not item_test:raise ValueError('World drop probe requires isolated inventory profile')
        self.drop_probe=drop_probe;self.world_drop_sequence=910001;self.world_drop_issued=None;self.world_drops={}
        if drop_test and not drop_probe:raise ValueError('Persistent pickup test requires isolated ground-spawn profile')
        self.drop_test=drop_test;self.pickup_receipt=None
        self.gate_stage=0;self.gate_stage_loading=False
        self.expiration_checked=None
        self.luciel_dungeon_hp_source=None;self.luciel_dungeon_hp_max=None
        self.activity2026_awards=activity2026_awards

    def saved_user_sync(self,*,clear_reward_only=False,resonance_snapshot=None):
        snapshot=self.account.get_inventory_snapshot() if self.item_test else {'balances':self.account.get_reward_balances() if self.reward_test else None,'items':None}
        # Existing inventory is restored by the native login map (2A).
        # D9 is an acquisition delta: unchanged rows become NEW and, in a
        # dungeon, zero-count result entries. Never use it as a full bag sync.
        updates=[]
        if clear_reward_only and not self.clear_items_synced:
            # D9 -> 1AB0A20 -> 197DAD0 is a delta updater with result
            # counting enabled. Re-sending an unchanged stackable coupon
            # adds a zero-count coupon to Game+16D8 and the result UI.
            # Keep full items for unit/equipment serialization, but only
            # update the bag slots awarded by this run, at CURRENT counts.
            awarded={i['uid'] for i in (self.reward_receipt or {}).get('items',[])}
            updates=[i for i in snapshot['items'] or [] if i['uid'] in awarded]
        character=self.account.character()
        if resonance_snapshot is not None:
            if character is None:raise ValueError('ERP sync requires owned character')
            character=dict(character,resonance=resonance_snapshot)
        return dungeon_messages.return_user_sync(self.account.get_location(),self.account.get_skills(),snapshot['balances'],snapshot['items'],character,inventory_updates=updates)

    def periodic_notifications(self):
        from els_server.domain.fishing_attempt import periodic as fishing_periodic
        fishing_notices=fishing_periodic(self)
        from els_server.domain.dungeon_flow import periodic
        from els_server.domain.quest_flow import observe
        from els_server.domain.mount_flow import periodic as mount_periodic
        from els_server.domain.title_flow import periodic as title_periodic
        messages=fishing_notices+self.expiration_notifications()+self._periodic_notifications()+periodic(self)+mount_periodic(self)+title_periodic(self)
        answer=messages+observe(self,messages)
        from els_server.domain.resonance_flow import synchronize as resonance_sync
        answer=resonance_sync(self,answer)
        from els_server.domain.flask_flow import periodic as flask_periodic
        answer+=flask_periodic(self)
        from els_server.domain.equipment_cartridge_flow import synchronize as cartridge_sync
        answer=cartridge_sync(self,answer)
        from els_server.domain.tenebros_capacity_flow import synchronize as tenebros_capacity_sync
        answer=tenebros_capacity_sync(self,answer)
        return self.activity2026_awards.finalize(self,answer) if self.activity2026_awards is not None else answer

    def _capture_luciel_dungeon_hp(self,payload,spans):
        self.luciel_dungeon_hp_source=None;self.luciel_dungeon_hp_max=None
        character=self.account.character()
        if character['unit_type']!=10:return
        import struct
        if set(spans)!=set(('0x198','0x1b4','0x1d1')):raise ValueError('LuCiel admitted member spans')
        self.luciel_dungeon_hp_source=(self.account.uid,payload,dict(spans))
        self.luciel_dungeon_hp_max=struct.unpack_from('>f',payload,spans['0x198'][0])[0]

    def expiration_notifications(self):
        if not (self.item_test and self.client_build=='dx11_260923' and self.role=='game' and self.phase in ('town_ready','dungeon_active')):return []
        import time
        now=int(time.time());key=(self.account.uid,now)
        if key==self.expiration_checked:return []
        from els_server.storage.item_expiration import remove_due
        prepared_hp=[]
        def prepare_luciel_slots(items,remaining):
            # load_items already validates every admitted owned instance.
            # All current worn slots need removal, including both costume sides.
            worn=[i for i in items if i['group']==9]
            if not worn:return None
            character=self.account.character()
            if character['uid']!=self.account.uid:raise ValueError('Expiration actor mismatch')
            if character['unit_type']!=10:return None
            from els_server.domain.fashion_state import move_ack
            answer=[Event(0x201,kind=0x105,payload=move_ack([((i['group'],i['slot']),None) for i in worn]))]
            source=self.luciel_dungeon_hp_source
            if self.phase=='dungeon_active' and not self.dungeon_return_pending and source is not None and source[0]==self.account.uid:
                from els_server.domain.character_stats import combat_values
                maximum=combat_values(character,remaining)[0]
                if maximum!=self.luciel_dungeon_hp_max:
                    from els_server.protocol.dungeon_messages import luciel_hp_notification
                    from els_server.protocol.luciel_messages import preference
                    answer.append(luciel_hp_notification(source,maximum,preference(character)))
                    prepared_hp.append(maximum)
            return answer
        result=remove_due(self.account.store.path,self.account.uid,now=now,prepare_remaining_refresh=prepare_luciel_slots)
        if prepared_hp:self.luciel_dungeon_hp_max=prepared_hp[-1] # Only after the removal transaction committed.
        from els_server.storage.bank_state import remove_due as remove_due_bank
        result+=remove_due_bank(self.account.store.path,self.account.uid)
        from els_server.storage.boosting_2026_limited_pet import periodic as limited_pet_periodic
        result+=limited_pet_periodic(self.account.store.path,self.account.uid,at=now)
        self.expiration_checked=key
        from els_server.domain.elixir_flow import periodic as world_elixir_periodic
        return result+world_elixir_periodic(self)

    def _periodic_notifications(self):
        from els_server.domain.mailbox_extras import periodic as mail_periodic
        from els_server.domain.luciel_state import periodic as luciel_periodic
        mail_notices=mail_periodic(self)+luciel_periodic(self)
        if self.shop_test and self.role=='game' and self.phase=='town_ready' and self.shop_available_pending:
            from els_server.protocol.shop_messages import availability_notice
            self.shop_available_pending=False
            return mail_notices+[availability_notice()]
        # DX11 C25B90 kind9C consumes four bytes, dispatching float timer
        # to Game v350=1045200, which credits 450 updates to Game+a88.
        # Map30000 has no supported timed-dungeon policy: timer is float0.
        # 1AA5B80 stops physical-key conversion
        # when this credit reaches zero. Only an active loaded substage
        # receives the local keepalive; no character/save state is changed.
        if (self.client_build=='dx11_260923' and self.enter_dungeon and
                self.role=='game' and self.phase=='dungeon_active' and
                self.dungeon_substage_synced):
            return mail_notices+[Event(0x201,kind=0x9c,payload=u32(0))]
        return mail_notices

    def pickup_world_drop(self,event):
        from els_server.domain.drop_pickup import ground_pickup_request,GROUND_ED,GROUND_FOOD
        from els_server.domain.dungeon_drops import ground_pickup_notice,pickup_inventory_notice
        from els_server.storage.inventory_state import InventoryFull
        self.pickup_receipt=None
        if event.performers!=(0,) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0:return []
        try:request=ground_pickup_request(event.payload)
        except ValueError:return []
        drop=self.world_drops.get(request['drop_id'])
        if drop is None or drop['run_id']!=self.reward_run_id or drop['owner']!=self.account.uid or drop['template']!=request['template']:return []
        if drop['stage']!=self.gate_stage and not drop.get('pickup_committed'):return []
        # Experimental local distance checks, not a claim about retail radii.
        if math.dist(request['player_xyz'],request['drop_xyz'])>250 or math.dist(request['drop_xyz'],drop['xyz'])>250:
            # Original 1032A90 permits pet pickup across the loaded stage.
            # 1AB5CE0 represents it with a destination within +/-10 on each
            # axis of the player, rather than the issued ground position.
            from els_server.storage.pet_support import remote_pickup_enabled
            if (any(abs(a-b)>10.125 for a,b in zip(request['player_xyz'],request['drop_xyz']))
                    or not remote_pickup_enabled(self.account.store.path,self.account.uid)):return []

        from els_server.domain.fishing_bait_loot import claim as bait_claim
        bait_reply=bait_claim(self,request,drop)
        if bait_reply is not None:return bait_reply
        from els_server.domain.hunter_chest_flow import claim as hunter_claim
        hunter_reply=hunter_claim(self,request,drop)
        if hunter_reply is not None:return hunter_reply
        from els_server.domain.dungeon_equipment_loot_rules import TEMPLATES as EQUIPMENT_LOOT_TEMPLATES
        from els_server.domain.dungeon_source_loot import POLICY as SOURCE_LOOT_POLICY
        if request['template'] in EQUIPMENT_LOOT_TEMPLATES or drop.get('source')==SOURCE_LOOT_POLICY:
            from els_server.domain.dungeon_equipment_loot_flow import claim
            return claim(self,request,drop)
        receipt_id=str(uuid.uuid5(uuid.UUID(self.reward_run_id),f"pickup:{self.account.uid}:{drop['stage']}:{drop['drop_id']}"))
        proof=b'local-world-pickup-v1'+uuid.UUID(self.reward_run_id).bytes+struct.pack('>Qiiii',self.account.uid,drop['stage'],drop['npc_key'],drop['drop_id'],drop['template'])+bytes.fromhex(drop['death_proof_sha256'])+bytes.fromhex(drop['payload_hex'])
        # The server fixes quantity; dynamic request suffixes are not grant keys.
        try:
            from els_server.domain.reward_rules import dungeon_rewards
            immediate=drop['template'] in GROUND_ED|GROUND_FOOD
            if drop['template'] in GROUND_ED:
                def encode_coin(balances,economy):
                    from els_server.protocol.local_messages import client_economy_fields
                    client_economy_fields(balances)
                    return ground_pickup_notice(drop['drop_id'],self.account.uid,template=drop['template'],ed=drop['ed'],bonus_ed=economy['bonus_ed']).payload
                receipt=self.account.reward_store.grant(receipt_id,proof,drop['ed'],0,response_builder=encode_coin,title_economy='ground_ed',title_dungeon=self.dungeon_run.identity if self.dungeon_run is not None else 30000)
            elif immediate:
                # Persist coins atomically with the receipt; food creates only
                # a consumption receipt, never a synthetic inventory item.
                notice=ground_pickup_notice(drop['drop_id'],self.account.uid,template=drop['template'],ed=drop['ed'])
                receipt=self.account.reward_store.grant(receipt_id,proof,drop['ed'],0,response_builder=lambda balances:notice.payload)
            else:
                receipt=self.account.reward_store.grant(receipt_id,proof,0,0,item_plan=[dungeon_rewards(30000)['world_drop']],inventory_response_builder=lambda balances,items:pickup_inventory_notice(items).payload)
        except InventoryFull:return [Event(0x201,kind=0xd1,payload=i32(-1))]
        drop['pickup_committed']=True
        self.pickup_receipt={'run_id':receipt_id,'dungeon_run_id':self.reward_run_id,'drop_id':drop['drop_id'],**receipt}
        reply=[Event(0x201,kind=0xd1,payload=i32(0))]
        if immediate:
            # D2 is additive for coins and activates food effects. Replaying it
            # would duplicate local ED/healing despite an idempotent DB grant.
            if not receipt['replayed']:reply.append(Event(0x201,kind=0xd2,payload=receipt['response']))
            return reply
        if receipt['replayed']:
            # Absolute slot counts from older receipts can lag other pickups.
            awarded={i['uid'] for i in receipt.get('items',[])}
            reply.append(pickup_inventory_notice([i for i in self.account.get_inventory_snapshot()['items'] if i['uid'] in awarded]))
        else:
            reply.extend([ground_pickup_notice(drop['drop_id'],self.account.uid),Event(0x201,kind=0xd3,payload=receipt['response'])])
        return reply

    def handle(self,event,request_sequence=None):
        notices=self.expiration_notifications()
        from els_server.domain.quest_flow import observe
        before=observe(self,notices)
        village1012_origin=None
        if self.active_map==1012 and event.event_id==0x202 and event.kind in (0x37f,0x382):
            from els_server.domain.town_travel_flow import capture_village1012_origin
            village1012_origin=capture_village1012_origin(self,event)
        reply=self._handle(event,request_sequence)
        from els_server.domain.fishing_attempt import invalidate as invalidate_fishing
        invalidate_fishing(self)
        if self.phase!='town_ready' or self.active_map!=20013:
            from els_server.domain.tenebros_storage_flow import abandon as abandon_shadow
            abandon_shadow(self)
        if village1012_origin is not None:
            from els_server.domain.town_travel_flow import finish_village1012_origin
            finish_village1012_origin(self,village1012_origin)
        if self.account.characters is not None and any(e.kind==0x2a for e in reply):
            from els_server.domain.elixir_flow import cold as world_elixir_cold
            reply.extend(world_elixir_cold(self))
            from els_server.domain.guild_membership_flow import cold as guild_membership_cold
            reply.extend(guild_membership_cold(self))
            from els_server.domain.avatar_set_flow import initialization as avatar_set_initialization
            reply.extend(avatar_set_initialization(self,reply))
            from els_server.domain.dungeon_rotation import notification
            reply.append(notification())
            from els_server.domain.title_flow import enabled as titles_enabled,restore as restore_titles
            if titles_enabled(self):reply.extend(restore_titles(self))
        elif self.account.characters is not None and any(e.kind in (0xd9,0x29f,0xf5) for e in reply):
            from els_server.domain.title_flow import enabled as titles_enabled
            if titles_enabled(self):
                from els_server.storage.titles import state as title_state
                from els_server.protocol.title_messages import equipment as title_equipment
                active=title_state(self.account.store.path,self.account.uid)['title']
                if active:reply.append(title_equipment(active))
        from els_server.domain.anvil_flow import synchronize as anvil_sync
        reply=anvil_sync(self,reply)
        from els_server.domain.housing_access_flow import synchronize as housing_access_cold
        reply=housing_access_cold(self,reply)
        from els_server.domain.pet_progression_flow import observe as observe_pet_progression
        from els_server.domain.mount_flow import observe as observe_mount
        from els_server.domain.artifact_flow import observe as observe_artifact
        from els_server.domain.luciel_state import restore as restore_luciel
        answer=notices+before+reply+observe(self,reply)+observe_pet_progression(self,reply)+observe_mount(self)+observe_artifact(self,reply)+restore_luciel(self,event,reply)
        from els_server.domain.resonance_flow import synchronize as resonance_sync
        answer=resonance_sync(self,answer)
        return self.activity2026_awards.finalize(self,answer) if self.activity2026_awards is not None else answer

    def responses(self,kind):
        return responses(kind,self.client_build,account_id=self.account.account_id,
                         account_name=self.account.account_name,
                         character=self.account.character() if self.account.account_id!=1 else None)

    def _handle(self,event,request_sequence=None):
        from els_server.domain.housing_room_flow import handle as housing_room_handle
        housing_room_reply=housing_room_handle(self,event,request_sequence)
        if housing_room_reply is not None:return housing_room_reply
        from els_server.domain.housing_access_flow import handle as housing_access_handle
        housing_access_reply=housing_access_handle(self,event,request_sequence)
        if housing_access_reply is not None:return housing_access_reply
        from els_server.domain.fishing_attempt import handle as fishing_handle
        fishing_reply=fishing_handle(self,event,request_sequence)
        if fishing_reply is not None:return fishing_reply
        from els_server.domain.skill_page_shop_flow import handle as skill_page_shop_handle
        skill_page_shop_reply=skill_page_shop_handle(self,event,request_sequence)
        if skill_page_shop_reply is not None:return skill_page_shop_reply
        from els_server.domain.erp_potion_flow import handle as erp_potion_handle
        erp_potion_reply=erp_potion_handle(self,event,request_sequence)
        if erp_potion_reply is not None:return erp_potion_reply
        from els_server.domain.known_resurrection_flow import handle as known_resurrection_handle
        known_resurrection_reply=known_resurrection_handle(self,event,request_sequence)
        if known_resurrection_reply is not None:return known_resurrection_reply
        if getattr(self,'application',None) is None:
            from els_server.domain.coupon_failure_flow import handle as coupon_handle
        else:
            from els_server.domain.coupon_flow import handle as coupon_handle
        coupon_reply=coupon_handle(self,event,request_sequence)
        if coupon_reply is not None:return coupon_reply
        from els_server.domain.character_custom import handle as custom_handle
        custom_reply=custom_handle(self,event,request_sequence)
        if custom_reply is not None:return custom_reply
        from els_server.domain.resonance_allocation_flow import handle as resonance_allocation_handle
        resonance_allocation_reply=resonance_allocation_handle(self,event,request_sequence)
        if resonance_allocation_reply is not None:return resonance_allocation_reply
        kind=event.kind
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
        from els_server.domain.equipment_cartridge_flow import handle as cartridge_handle
        cartridge_reply=cartridge_handle(self,event,request_sequence)
        if cartridge_reply is not None:return cartridge_reply
        from els_server.domain.modern_synthesis_flow import handle as modern_synthesis
        synthesis_reply=modern_synthesis(self,event,request_sequence)
        if synthesis_reply is not None:return synthesis_reply
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
        from els_server.domain.equipment_spell_exchange_flow import handle as spell_exchange_handle
        spell_exchange_reply=spell_exchange_handle(self,event,request_sequence)
        if spell_exchange_reply is not None:return spell_exchange_reply
        from els_server.domain.equipment_circuit_flow import handle as circuit_handle
        circuit_reply=circuit_handle(self,event,request_sequence)
        if circuit_reply is not None:return circuit_reply
        from els_server.domain.option_conversion_existing_flow import handle as existing_conversion_handle
        existing_conversion_reply=existing_conversion_handle(self,event,request_sequence)
        if existing_conversion_reply is not None:return existing_conversion_reply
        from els_server.domain.artifact_flow import handle as artifact_handle
        artifact_reply=artifact_handle(self,event,request_sequence)
        if artifact_reply is not None:return artifact_reply
        from els_server.domain.quest_flow import handle as quest_handle
        if self.activity2026_awards is not None:
            answer=self.activity2026_awards.handle(self,event,request_sequence)
            if answer is not None:return answer
        quest_reply=quest_handle(self,event,request_sequence)
        if quest_reply is not None:return quest_reply
        from els_server.domain.first_story_entry import handle as first_story_handle
        first_story_reply=first_story_handle(self,event)
        if first_story_reply is not None:return first_story_reply
        if self.dungeon_run is not None:
            from els_server.domain.dungeon_flow import handle
            answer=handle(self,event)
            if answer is not None:return answer
        if self.enter_dungeon and event.event_id==0x202 and kind==0x2ce:
            # Local diagnostic: record every Lua-script spawn request with its
            # exact bytes so unrecognised objects can be mapped offline.
            # Behaviour is unchanged; the dump is never sent to the client.
            try:
                import json as _json, time as _time
                from els_server.paths import PROJECT_ROOT as _root
                path=_root/'state/launcher/script-spawn-dump.jsonl'
                path.parent.mkdir(parents=True,exist_ok=True)
                run=getattr(self,'dungeon_run',None)
                with path.open('a',encoding='utf8') as handle:
                    handle.write(_json.dumps(dict(
                        at=_time.strftime('%Y-%m-%dT%H:%M:%S'),
                        size=len(event.payload),payload=event.payload.hex(),
                        dungeon=getattr(run,'identity',None),stage=getattr(run,'stage',None),
                        part=getattr(run,'part',None),
                        unit_type=(self.account.character() or {}).get('unit_type'),
                        sequence=request_sequence))+'\n')
            except (OSError,TypeError,ValueError):pass
            from els_server.domain.dungeon_spawns import handle as scripted_spawn
            scripted_reply=scripted_spawn(self,event,request_sequence)
            if scripted_reply is not None:return scripted_reply
            from els_server.domain.summons import sentry_spawn,summon_ack
            character=self.account.character()
            if (self.client_build!='dx11_260923' or self.role!='game' or self.phase!='dungeon_active'
                    or not self.population_test or not self.dungeon_substage_synced or self.clear_notified
                    or self.part_end_notified or not character or character['unit_type']!=5
                    or type(request_sequence) is not int or not 1<=request_sequence<2**32):
                return [summon_ack(-1)]
            previous=self.summon_requests.get(request_sequence)
            if previous is not None:
                return [summon_ack(0 if previous==event.payload else -1)]
            from els_server.domain.dungeon_spawns import occupied_slots
            if occupied_slots(self)>=80:return [summon_ack(-1)]
            if self.dungeon_run is not None:
                while self.summon_next_key in self.dungeon_run.reserved_keys:self.summon_next_key+=1
            try:notice=sentry_spawn(event.payload,self.account.uid,self.summon_next_key)
            except ValueError:return [summon_ack(-1)]
            self.summon_keys.add(self.summon_next_key)
            self.summon_next_key+=1;self.summon_requests[request_sequence]=event.payload
            return [summon_ack(),notice]
        # The native character screen also requests its channel list before
        # creating a role. Both phases are still the authenticated roster UI.
        if (self.account.characters is not None and self.role=='game' and self.phase in ('characters_ready','channels_ready')
                and event.event_id==0x202 and kind in (0x48b,0x489)):
            from els_server.protocol.character_messages import name_request,create_request,name_ack,create_ack,creation_error,NAME_TAKEN
            from els_server.storage.characters import DEFAULT_CHARACTER
            if event.performers!=(0,) or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0:
                return [name_ack('',1) if kind==0x48b else create_ack(DEFAULT_CHARACTER,1)]
            if kind==0x48b:
                try:
                    name=name_request(event.payload)
                    return [name_ack(name,0 if self.account.characters.name_available(name) else NAME_TAKEN)]
                except (ValueError,UnicodeError) as error:return [name_ack('',creation_error(error))]
            try:
                req=create_request(event.payload)
                if type(request_sequence) is not int or not 1<=request_sequence<2**32:raise ValueError('Creation sequence')
                c=self.account.characters.create(req['name'],req['unit_type'],self.shop_session_id+':'+str(request_sequence))
                created_account=self.account.for_character(c['uid'])
                return [create_ack(c,items=created_account.get_inventory_snapshot()['items'],location=created_account.get_location())]
            except (ValueError,UnicodeError) as error:return [create_ack(DEFAULT_CHARACTER,creation_error(error))]
        if event.event_id==0 and kind==0:return []
        if event.event_id==0x402 and kind==0xd40 and self.phase=='new':return []
        if kind==0x274 and event.event_id==0x402:
            if self.role not in [None,'frontend']:raise SessionOrderError('Authentication request on game connection')
            answer=self.responses(kind);self.role='frontend';self.phase='authenticated';self.completed.add(kind);return answer
        if self.role=='frontend':
            if kind in [0xd33,0x41] and event.event_id==0x402:
                self.completed.add(kind);return self.responses(kind)
            return []
        if self.drop_test and self.role=='game' and self.phase=='dungeon_active' and self.dungeon_substage_synced and event.event_id==0x202 and kind==0xd0:
            return self.pickup_world_drop(event)
        restore_clear_economy=False
        if (self.clear_test and self.clear_notified and self.role=='game' and self.phase=='dungeon_active'
                and event.event_id==0x202 and kind==0x225):
            # Native C1 result continuation191521 returned directly through
            # the original town entry request, without training's reason72/67.
            # Accept only this character's saved town; no rewards are inferred.
            if event.payload!=i32(self.account.get_location()['map'])+b'\0':return []
            self.phase='map_loading';self.pending_map=None
            restore_clear_economy=self.reward_test
        if self.npc_slot_test and self.role=='game' and self.phase=='dungeon_active' and event.event_id==0x202:
            from els_server.domain.dungeon_lifecycle import death_report,death_ack,empty_reward_death_notice,part_end_notice
            if kind==0xad:
                try:data=death_report(event.payload)
                except ValueError:return []
                if data['index'] in self.summon_keys:
                    from els_server.domain.summons import valid_sentry_death
                    if (not self.dungeon_substage_synced or event.performers!=(0,)
                            or not valid_sentry_death(data,self.account.uid)):return []
                    previous=self.summon_deaths.get(data['index'])
                    if previous is not None:
                        return [death_ack()] if previous==event.payload else []
                    self.summon_deaths[data['index']]=bytes(event.payload)
                    # Native AF retires the actual summon. No enemy kill,
                    # drop, reward or part-end state is advanced here.
                    return [death_ack(),empty_reward_death_notice(data['index'],data['killer'])]
                # The isolated fixture is slot0 only. Actual capture: performer0,
                # index0, own participantself.account.uid. Other IDs do not grant a clear.
                expected_id=data['index'];allowed_ids=(0,1) if self.gate_test else (0,)
                if self.population_test:
                    from els_server.domain.dungeon_population import population
                    stage=population(self.gate_stage);allowed_ids=tuple(n['key'] for n in stage['npcs'])
                participants=getattr(self,'dungeon_participants',frozenset((self.account.uid,)))
                if (not self.dungeon_substage_synced or event.performers!=(0,) or data['flag'] not in (0,1) or expected_id not in allowed_ids
                        or any(data[name] not in participants for name in ('source','killer','last_uid'))
                        or any(uid not in participants for name in ('contribution','readiness','counters') for uid in data[name])):return []
                # Gate test170652 produced another AD with index/performer0
                # from a gate with native maxHP1000. Do not treat this as
                # another training death or guess a general identity mapping.
                if self.population_test:
                    npc=stage['npcs'][expected_id]
                    if data['hp_bits']!=struct.unpack('>I',struct.pack('>f',npc['hp']))[0]:return []
                    if expected_id==stage['clear_key'] and any(n['active'] and n['key']!=expected_id and n['key'] not in self.defeated_npcs for n in stage['npcs']):return []
                elif self.gate_test:
                    if data['hp_bits']!={0:0x42c80000,1:0x447a0000}[expected_id]:return []
                    if expected_id==1 and 0 not in self.defeated_npcs:return []
                if expected_id in self.defeated_npcs:return [death_ack()] if self.defeated_npcs[expected_id]==event.payload else []
                self.defeated_npcs[expected_id]=bytes(event.payload)
                drops=[]
                from els_server.domain.reward_rules import ground_loot
                loot=ground_loot(30000,npc,self.reward_run_id,self.gate_stage,stage['clear_key']) if self.drop_probe and self.population_test else []
                for plan in loot:
                    from els_server.domain.dungeon_drops import ground_drop_notice
                    # Explicit local fallback policy, separate from native
                    # spawn/no-drop flags. Inactive chests can still drop.
                    # Request/report second XYZ triplet is the NPC-side position.
                    # Final Boss follows the same drop policy. Spawn before BA;
                    # original BB/BC/C1 still determine clear timing. Gates are
                    # excluded; spawning alone does not grant a bag item.
                    drop_id=self.world_drop_sequence;self.world_drop_sequence+=1
                    xyz=data['xyz'][3:]
                    notice=ground_drop_notice(drop_id,xyz,uid=self.account.uid,template=plan['template'])
                    self.world_drop_issued={'run_id':self.reward_run_id,'stage':self.gate_stage,'npc_key':expected_id,'drop_id':drop_id,'owner':self.account.uid,**plan,'xyz':list(xyz),'payload_hex':notice.payload.hex(),'death_proof_sha256':hashlib.sha256(event.payload).hexdigest(),'pickup_committed':False}
                    self.world_drops[drop_id]=dict(self.world_drop_issued)
                    drops.append(notice)
                if self.population_test and expected_id!=stage['clear_key']:return [death_ack(),empty_reward_death_notice(expected_id,data['killer']),*drops]
                if self.gate_test and not self.population_test and expected_id==0:return [death_ack(),empty_reward_death_notice(0,self.account.uid)]
                self.part_end_notified=True
                self.dungeon_clock.pause()
                return [death_ack(),empty_reward_death_notice(expected_id,data['killer']),*drops,part_end_notice(0)]
            if kind==0xbb:
                if event.payload!=b'\0':return []
                if self.gate_test and self.gate_stage_loading:return [Event(0x201,kind=0xbc,payload=i32(0))]
                if not self.part_end_notified:return []
                # BC only acknowledges BB. BD is a start notification; replaying
                # it here restarted the dying actor in native test161653.
                reply=[Event(0x201,kind=0xbc,payload=i32(0))]
                if self.clear_test and self.gate_stage==2 and not self.clear_notified:
                    if self.reward_test:
                        if self.reward_run_id is None or 0 not in self.defeated_npcs:raise SessionOrderError('Reward clear outside an allocated and verified run')
                        from els_server.domain.dungeon_clear import reward_clear_notice,LOCAL_CLEAR_ED,LOCAL_CLEAR_EXPERIENCE,clear_identity_payload
                        from els_server.domain.gm_rates import clear_experience
                        gm_experience=clear_experience(self,LOCAL_CLEAR_EXPERIENCE)
                        proof=b'local-clear-v1'+struct.pack('>Qiii',self.account.uid,30000,2,5)+self.defeated_npcs[0]+event.payload
                        # Failures leave clear_notified false. A retry uses the
                        # same UUID and either retries or reads its saved C1.
                        elapsed=self.dungeon_clock.seconds()
                        def encode_grant(balances,best,economy):
                            # Refuse totals that cannot be restored by the verified
                            # unit scalar widths; this runs before the SQL commit.
                            client_economy_fields(balances)
                            return reward_clear_notice(economy['ed'],economy['experience'],self.account.uid,elapsed_seconds=elapsed,best_seconds=best,map_id=30000).payload
                        # Explicit local reward policy, with independently decoded
                        # potion body. World drops and C1 item-choice fields remain
                        # separate work; this grants a durable real bag item.
                        from els_server.domain.reward_rules import dungeon_rewards
                        item_plan=dungeon_rewards(30000)['clear_items'] if self.item_test else None
                        receipt=self.account.reward_store.grant(self.reward_run_id,proof,LOCAL_CLEAR_ED,gm_experience,encode_grant,item_plan=item_plan,dungeon_clear=(30000,elapsed),title_economy='clear',attendance_clear=self.activity2026_awards.prepare_clear(self) if self.activity2026_awards is not None else None)
                        self.reward_receipt={'run_id':self.reward_run_id,**receipt}
                        if self.item_test and receipt.get('items') and not self.clear_items_synced:
                            # D3 records real acquisitions in Game+16D8. Send
                            # before C1 constructs the result UI, not on exit.
                            # Refresh counts from storage if recovering a receipt.
                            from els_server.domain.dungeon_drops import pickup_inventory_notice
                            ids={i['uid'] for i in receipt['items']}
                            updates=[i for i in self.account.get_inventory_snapshot()['items'] if i['uid'] in ids]
                            reply.append(pickup_inventory_notice(updates))
                            self.clear_items_synced=True
                        reply.append(Event(0x201,kind=0xc1,payload=clear_identity_payload(receipt['response'],30000)))
                    else:
                        from els_server.domain.dungeon_clear import prototype_clear_notice
                        reply.append(prototype_clear_notice(self.reward_probe,map_id=30000))
                    self.clear_notified=True
                if self.population_test and self.gate_stage<2:
                    from els_server.domain.dungeon_population import substage
                    next_stage=substage(self.gate_stage+1,boss_gauge=self.boss_gauge_test)
                    self.gate_stage+=1;self.gate_stage_loading=True
                    self.dungeon_substage_synced=False;self.part_end_notified=False;self.defeated_npcs={}
                    reply.append(next_stage)
                elif self.gate_test and not self.population_test and self.gate_stage==0:
                    from els_server.domain.dungeon_transition import candidate_substage_one
                    next_stage=candidate_substage_one()
                    self.gate_stage=1;self.gate_stage_loading=True
                    self.dungeon_substage_synced=False;self.part_end_notified=False;self.defeated_npcs={}
                    reply.append(next_stage)
                return reply
        if self.enter_town and kind==0x397 and event.event_id==0x202 and self.role=='game':
            if self.phase not in ('game_authenticated','port_ready','session_ready','terms_ready','characters_ready','channels_ready','player_initialized','skill_ui_ready','initialization_confirmed','map_loading','square_accepted','town_ready','dungeon_loading','dungeon_active'):
                return [Event(0x201,kind=0x398,payload=i32(-1))]
            try:self.account.save_bindings(event.payload)
            except ValueError:return [Event(0x201,kind=0x398,payload=i32(-1))]
            return [Event(0x201,kind=0x398,payload=i32(0))]
        if self.item_test and self.client_build=='dx11_260923' and kind==0x55f and event.event_id==0x202:
            from els_server.domain.skill_traits import reset_acknowledgement
            from els_server.storage.skill_traits import reset,saved as saved_traits
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:return [reset_acknowledgement(result=-1)]
            from els_server.storage.career_shop import notifications as career_notifications
            character=self.account.character();updates=[]
            def prepare_reset(db):
                refreshed=dict(character,skill_traits=saved_traits(db,self.account.uid))
                updates.extend(career_notifications(db,self.account.uid,refreshed,self.account.get_location(),None,None,True))
            operation='trait-reset:'+self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:ack=reset(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation,prepare=prepare_reset)
            except ValueError:return [reset_acknowledgement(result=-1)]
            return [ack]+updates
        if self.item_test and self.client_build=='dx11_260923' and kind==0x55d and event.event_id==0x202:
            from els_server.domain.skill_traits import acknowledgement
            from els_server.storage.skill_traits import choose
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:return [acknowledgement(result=-1)]
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return [choose(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation)]
            except ValueError:return [acknowledgement(result=-1)]
        if self.item_test and self.client_build=='dx11_260923' and kind==0x460 and event.event_id==0x202:
            from els_server.domain.boosting_2026_essence import acknowledgement as essence_ack
            from els_server.storage.boosting_2026_essence import action as essence_action
            if self.role!='game' or self.phase!='dungeon_active' or type(request_sequence) is not int or not 1<=request_sequence<2**32:return [essence_ack(result=-1)]
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return essence_action(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation)['events']
            except ValueError:return [essence_ack(result=-1)]
        if self.item_test and self.client_build=='dx11_260923' and kind==0x6ce and event.event_id==0x202:
            from els_server.domain.boosting_2026_force_extraction import acknowledgement as force_extract_ack
            from els_server.storage.boosting_2026_force_extraction import action as force_extract_action
            from els_server.domain.equipment_chip_flow import current_lease
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32 or self.account.store is None or self.account.store.uid!=self.account.uid or not current_lease(self):return [force_extract_ack(result=-1)]
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:force=force_extract_action(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation)
            except ValueError:return [force_extract_ack(result=-1)]
            events=force['events']
            if force['replayed']:events.append(self.saved_user_sync())
            return events
        if self.item_test and self.client_build=='dx11_260923' and kind==0x6d0 and event.event_id==0x202:
            from els_server.domain.boosting_2026_force_equipment import acknowledgement as force_slot_ack
            from els_server.storage.boosting_2026_force_equipment import action as force_slot_action
            from els_server.domain.equipment_chip_flow import current_lease
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32 or self.account.store is None or self.account.store.uid!=self.account.uid or not current_lease(self):return [force_slot_ack(result=-1)]
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return [force_slot_action(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation)]
            except ValueError as error:return [force_slot_ack(result=getattr(error,'result',-1))]
        if self.item_test and self.account.characters is not None and kind==0x219 and event.event_id==0x202:
            from els_server.protocol.career_messages import use_ack,career_notice,stage_notice
            from els_server.storage.careers import use_career_item
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return [use_ack(result=-1)]
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            from els_server.storage.boosting_2026_nested_capacity import use_ticket as use_capacity_ticket
            try:capacity=use_capacity_ticket(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return [use_ack(result=-1)]
            if capacity is not None:return capacity['events']+([self.saved_user_sync()] if capacity['replayed'] else [])
            from els_server.storage.resonance_state import use_book as use_resonance_book
            from els_server.domain.equipment_chip_flow import current_lease
            resonance_account=self.account;resonance_store=self.account.store;resonance_root=self.account.root
            resonance_owner=self.account.uid;resonance_account_id=self.account.account_id;resonance_session_id=self.shop_session_id
            resonance_path=getattr(resonance_store,'path',None);resonance_app=getattr(self,'application',None);resonance_identity=getattr(self,'identity',None)
            def prepare_resonance_book():
                if (self.account is not resonance_account or self.account.store is not resonance_store
                    or self.account.root is not resonance_root or resonance_store is None
                    or resonance_store.path!=resonance_path or getattr(self,'application',None) is not resonance_app
                    or getattr(self,'identity',None) is not resonance_identity
                    or (self.account.uid,self.account.account_id,self.shop_session_id)!=(resonance_owner,resonance_account_id,resonance_session_id)
                    or self.role!='game' or self.phase!='town_ready' or getattr(self,'released',False)
                    or resonance_store.uid!=resonance_owner or not current_lease(self)):
                    raise ValueError('ERP book current actor or lease changed')
            try:resonance=use_resonance_book(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation,prepare=prepare_resonance_book)
            except ValueError:return [use_ack(result=-1)]
            if resonance is not None:return resonance['events']+[self.saved_user_sync()]
            from els_server.domain.character_custom import require_admitted as custom_admission,book_validator as pointmark_validator
            from els_server.storage.character_custom import use_book as use_custom_book
            try:custom=use_custom_book(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation,validate=lambda:custom_admission(self),validate_pointmark=pointmark_validator(self))
            except ValueError:return [use_ack(result=-1)]
            if custom is not None:return custom['events']
            from els_server.storage.boosting_2026_force_inventory import use_book as use_force_book
            from els_server.domain.equipment_chip_flow import current_lease
            try:force=use_force_book(self.account.store.path,self.account.uid,self.account.account_id,event.payload,operation,session_authorized=bool(self.account.store is not None and self.account.store.uid==self.account.uid and current_lease(self)))
            except ValueError as error:return [use_ack(result=getattr(error,'result',-1))]
            if force is not None:return force['events']+([self.saved_user_sync()] if force['replayed'] else [])
            from els_server.storage.artifact_progression import action as artifact_action
            try:artifact=artifact_action(self.account.store.path,self.account.uid,'potion',event.payload,operation,account_id=self.account.account_id)
            except ValueError:return [use_ack(result=2005)]
            if artifact is not None:return artifact
            from els_server.storage.titles import use_item as use_title_item
            from els_server.protocol.title_messages import initialization as title_initialization
            try:title_receipt=use_title_item(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return [use_ack(result=-1)]
            if title_receipt is not None:
                return [title_receipt['ack'],title_initialization(title_receipt['state'])]
            from els_server.storage.expansion_items import use_expansion_item
            from els_server.domain.skill_expansion import notice
            try:expansion=use_expansion_item(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return [use_ack(result=-1)]
            if expansion is not None:
                answer=[Event(0x201,kind=0x21a,payload=expansion['response'])]
                return answer+[notice(self.account.uid,self.account.character())]
            from els_server.storage.skill_unlocks import use_skill_book
            try:unlock=use_skill_book(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return [use_ack(result=-1)]
            if unlock is not None:
                answer=[Event(0x201,kind=0x21a,payload=unlock['response'])]
                if not unlock['replayed']:answer.append(unlock['notification'])
                return answer+[Event(0x201,kind=0x55b,payload=unlock['initialization'])]
            try:
                receipt=use_career_item(self.account.store.path,self.account.uid,event.payload,
                    operation)
            except ValueError:return [use_ack(result=-1)]
            if receipt['replayed']:
                # Old deltas can predate a later purchase/use. Restore current
                # absolute state without replaying an old class/Artifact spawn.
                return [use_ack(ed=self.account.get_reward_balances()['ed']),self.saved_user_sync()]
            snapshot=self.account.get_inventory_snapshot();character=self.account.character()
            answer=[Event(0x201,kind=0x21a,payload=receipt['response'])]
            if receipt['before']['unit_class']!=character['unit_class']:
                answer.append(career_notice(character,self.account.get_location(),self.account.get_skills(),snapshot['balances'],snapshot['items']))
            else:
                # Transcendence/master retain their class. First restore the
                # full Artifact data, then let 59F create the spirit once.
                answer.append(self.saved_user_sync())
            if (receipt['before']['transcendence'],receipt['before']['master'])!=(character['transcendence'],character['master']):
                answer.append(stage_notice(character))
            return answer+[skill_slots_initialization(self.account.get_skills(),self.account.uid,character)]
        if self.equipment_repair_enabled and kind==0x18c and event.event_id==0x202:
            from els_server.storage.equipment_repair import repair
            from els_server.protocol.repair_messages import acknowledgement
            from els_server.domain.equipment_chip_flow import current_lease
            if (not current_lease(self) or self.role!='game' or self.phase!='town_ready'
                    or self.account is None or self.account.characters is None or self.account.store is None
                    or self.account.store.uid!=self.account.uid
                    or type(request_sequence) is not int or not 1<=request_sequence<2**32
                    or event.performers not in ((),(0,)) or event.uid!=0xffffffffffffffff
                    or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                return [Event(0x201,kind=0x18d,payload=acknowledgement(0,result=2))]
            ed=0
            try:
                ed=self.account.get_reward_balances()['ed']
                if not current_lease(self):raise ValueError('Obsolete repair lease')
                receipt=repair(self.account.store.path,self.account.uid,event.payload,self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence),
                               account_id=self.account.account_id)
            except ValueError:
                return [Event(0x201,kind=0x18d,payload=acknowledgement(ed,result=100))]
            answer=[Event(0x201,kind=0x18d,payload=receipt['response'])]
            return answer+[self.saved_user_sync()] if receipt['requires_inventory_sync'] else answer
        if self.attribute_enchant_enabled and kind==0x204 and event.event_id==0x202:
            from els_server.storage.attribute_enchant import change_attribute
            from els_server.protocol.enchant_messages import acknowledgement,EnchantRejected,EnchantResult
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return [Event(0x201,kind=0x205,payload=acknowledgement(self.account.get_reward_balances()['ed'],result=int(EnchantResult.INVALID_STATE)))]
            try:receipt=change_attribute(self.account.store.path,self.account.uid,event.payload,self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence))
            except ValueError as error:
                result=error.result if isinstance(error,EnchantRejected) else int(EnchantResult.UNKNOWN)
                return [Event(0x201,kind=0x205,payload=acknowledgement(self.account.get_reward_balances()['ed'],result=result))]
            answer=[Event(0x201,kind=0x205,payload=receipt['response'])]
            return answer+[self.saved_user_sync()] if receipt['requires_inventory_sync'] else answer
        if self.item_test and self.client_build=='dx11_260923' and kind in (0x113,0x65e) and event.event_id==0x202:
            from els_server.domain.consumable_flow import handle as consumable_handle
            return consumable_handle(self,event,request_sequence)
        if self.item_test and self.client_build=='dx11_260923' and kind==0x8a1 and event.event_id==0x202:
            from els_server.storage.quick_slots import save_request,acknowledgement
            if self.role!='game' or self.phase not in ('town_ready','dungeon_active'):
                return [acknowledgement(result=-1)]
            try:return [save_request(self.account.store.path,event.payload,self.account.uid)]
            except ValueError:return [acknowledgement(result=-1)]
        if self.item_test and self.client_build=='dx11_260923' and kind==0xec and event.event_id==0x202:
            from els_server.protocol.npc_sale_messages import acknowledgement as sale_ack
            from els_server.storage.npc_sale import sell
            def sale_failed():
                return [Event(0x201,kind=0xed,payload=sale_ack(self.account.get_reward_balances()['ed'],result=-1))]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return sale_failed()
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return sell(self.account.store.path,self.account.uid,event.payload,operation,self.npc_history_id)
            except ValueError:return sale_failed()
        from els_server.domain.guild_membership_flow import handle as guild_membership_handle
        guild_membership_reply=guild_membership_handle(self,event,request_sequence)
        if guild_membership_reply is not None:return guild_membership_reply
        from els_server.domain.guild_license_flow import handle as guild_license_handle
        guild_license_reply=guild_license_handle(self,event,request_sequence)
        if guild_license_reply is not None:return guild_license_reply
        if self.item_test and self.client_build=='dx11_260923' and kind in (0xea,0x567) and event.event_id==0x202:
            from els_server.protocol.npc_trade_messages import purchase_ack,repurchase_ack
            from els_server.storage.npc_trade import purchase,repurchase
            def trade_failed():
                ack=purchase_ack if kind==0xea else repurchase_ack
                return [Event(0x201,kind=kind+1,payload=ack(self.account.get_reward_balances()['ed'],result=-1))]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return trade_failed()
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:
                if kind==0xea:return purchase(self.account.store.path,self.account.uid,self.account.get_location()['map'],event.payload,operation)
                return repurchase(self.account.store.path,self.account.uid,event.payload,operation,self.npc_history_id,self.account.get_location()['map'])
            except ValueError:return trade_failed()
        from els_server.domain.cartridge_recipe679_flow import handle as recipe679_handle
        recipe679_reply=recipe679_handle(self,event,request_sequence)
        if recipe679_reply is not None:return recipe679_reply
        from els_server.domain.fish_exchange_flow import handle as fish_exchange_handle
        fish_exchange_reply=fish_exchange_handle(self,event,request_sequence)
        if fish_exchange_reply is not None:return fish_exchange_reply
        from els_server.domain.cartridge_exchange_flow import handle as cartridge_exchange_handle
        cartridge_exchange_reply=cartridge_exchange_handle(self,event,request_sequence)
        if cartridge_exchange_reply is not None:return cartridge_exchange_reply
        from els_server.domain.purifier_exchange_flow import handle as purifier_exchange_handle
        purifier_exchange_reply=purifier_exchange_handle(self,event,request_sequence)
        if purifier_exchange_reply is not None:return purifier_exchange_reply
        from els_server.domain.ep_conversion_flow import handle as ep_conversion_handle
        ep_conversion_reply=ep_conversion_handle(self,event,request_sequence)
        if ep_conversion_reply is not None:return ep_conversion_reply
        from els_server.domain.equipment_ui_flow import handle as equipment_ui_handle
        equipment_ui_reply=equipment_ui_handle(self,event,request_sequence)
        if equipment_ui_reply is not None:return equipment_ui_reply
        from els_server.domain.bank_view_flow import handle as bank_view_handle
        bank_view_reply=bank_view_handle(self,event)
        if bank_view_reply is not None:return bank_view_reply
        if self.item_test and self.client_build=='dx11_260923' and kind==0x7d7 and event.event_id==0x202:
            from els_server.protocol.bank_messages import money_ack
            from els_server.storage.bank_money import transfer as transfer_bank_money
            failed=[Event(0x201,kind=0x7d8,payload=money_ack(False,result=-1))]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:return failed
            operation=self.shop_session_id+':'+str(self.account.uid)+':bank-money:'+str(request_sequence)
            try:return [Event(0x201,kind=0x7d8,payload=transfer_bank_money(self.account.store.path,self.account.uid,event.payload,operation))]
            except ValueError:return failed
        if self.item_test and self.client_build=='dx11_260923' and kind in (0x26a,0x54f,0x477,0x54b,0x475,0x54d) and event.event_id==0x202:
            from els_server.storage.bank_state import contents,quote,expand
            from els_server.protocol.bank_messages import contents_ack,quote_ack,expansion_ack
            group=8 if kind in (0x26a,0x477,0x475) else 16
            def bank_service_error():
                body=(contents_ack(ed=0,result=-1) if kind==0x54f else contents_ack() if kind==0x26a
                    else quote_ack(group,result=-1) if kind in (0x477,0x54b) else expansion_ack(group,result=-1))
                return [Event(0x201,kind=kind+1,payload=body)]
            if self.role!='game' or self.phase!='town_ready' or event.payload:return bank_service_error()
            if request_sequence is not None and (type(request_sequence) is not int or not 1<=request_sequence<2**32):return bank_service_error()
            if kind in (0x475,0x54d) and request_sequence is None:return bank_service_error()
            if not hasattr(self,'bank_quotes'):self.bank_quotes={}
            key=(self.account.uid,group)
            try:
                if kind in (0x26a,0x54f):return contents(self.account.store.path,self.account.uid,group)
                if kind in (0x477,0x54b):
                    self.bank_quotes[key]=quote(self.account.store.path,self.account.uid,group)
                    return [Event(0x201,kind=kind+1,payload=quote_ack(group,self.bank_quotes[key][1]))]
                operation=self.shop_session_id+':'+str(self.account.uid)+':bank-expand:'+str(request_sequence)
                wire=expand(self.account.store.path,self.account.uid,group,event.payload,operation,self.bank_quotes.get(key))
                self.bank_quotes.pop(key,None)
                return [Event(0x201,kind=kind+1,payload=wire)]
            except ValueError:return bank_service_error()
        if self.item_test and self.client_build=='dx11_260923' and kind in (0x551,0x372) and event.event_id==0x202:
            from els_server.protocol.bank_messages import transfer_ack,sort_ack
            from els_server.storage.bank_state import transfer,sort
            def bank_failed():
                group=16 if event.payload==struct.pack('>i',16) else 8
                return [Event(0x201,kind=kind+1,payload=transfer_ack(result=-1) if kind==0x551 else sort_ack(group,result=-1))]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return bank_failed()
            try:
                operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
                return [Event(0x201,kind=kind+1,payload=(transfer if kind==0x551 else sort)(self.account.store.path,self.account.uid,event.payload,operation))]
            except ValueError:return bank_failed()
        from els_server.domain.white_chip_decomposition_flow import handle as white_chip_decompose
        white_chip_reply=white_chip_decompose(self,event,request_sequence)
        if white_chip_reply is not None:return white_chip_reply
        if self.item_test and self.client_build=='dx11_260923' and kind==0x1c0 and event.event_id==0x202:
            from els_server.protocol.inventory_management_messages import decompose_ack
            from els_server.storage.decomposition import decompose
            failed=[Event(0x201,kind=0x1c1,payload=decompose_ack(result=-1))]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return failed
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return decompose(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return failed
        if self.item_test and self.client_build=='dx11_260923' and kind in (0x270,0x272) and event.event_id==0x202:
            from els_server.protocol.inventory_management_messages import seal_ack
            from els_server.storage.item_seals import change_seal
            failed=[Event(0x201,kind=kind+1,payload=seal_ack(result=-1))]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return failed
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:answer=change_seal(self.account.store.path,self.account.uid,event.payload,operation,sealing=kind==0x270)
            except ValueError:return failed
            return [Event(0x201,kind=kind+1,payload=answer)]
        if self.item_test and self.client_build=='dx11_260923' and kind==0x370 and event.event_id==0x202:
            from els_server.protocol.inventory_management_messages import category_sort_request,category_sort_ack
            from els_server.storage.inventory_management import sort_category_inventory
            try:category=category_sort_request(event.payload)
            except ValueError:category=0
            def category_failed():return [Event(0x201,kind=0x371,payload=category_sort_ack(category,result=-1))]
            if (self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int
                    or not 1<=request_sequence<2**32 or event.performers!=(0,)
                    or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                return category_failed()
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return sort_category_inventory(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return category_failed()
        if self.item_test and self.client_build=='dx11_260923' and kind==0x563 and event.event_id==0x202:
            from els_server.protocol.wardrobe_messages import ticket_information
            if (self.role!='game' or self.phase not in ('player_initialized','skill_ui_ready','initialization_confirmed','map_loading','square_accepted','town_ready')or event.performers!=(0,)
                    or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):return []
            try:return [ticket_information(event.payload)]
            except ValueError:return []
        if self.item_test and self.client_build=='dx11_260923' and kind in (0x4af,0x4b1,0xbee,0x4f4,0x565,0x6d7,0xad6) and event.event_id==0x202:
            from els_server.protocol.wardrobe_messages import acknowledgement
            from els_server.storage.wardrobe import change
            from els_server.domain.tutorial_accessory import wear_context,validate_wear_context
            failed=[acknowledgement(kind,result=-1)]
            if (self.role!='game' or self.phase!='town_ready' or type(request_sequence)is not int
                    or not 1<=request_sequence<2**32 or event.performers!=(0,)
                    or event.uid!=0xffffffffffffffff or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):
                return failed
            operation=self.shop_session_id+':wardrobe:'+str(self.account.uid)+':'+str(request_sequence)
            try:
                captured=wear_context(self)
                answer=change(self.account.store.path,self.account.uid,self.account.account_id,kind,event.payload,operation,
                    validate=lambda:validate_wear_context(self,captured))
                return answer if isinstance(answer,list)else[answer]
            except ValueError:return failed
        if self.item_test and self.client_build=='dx11_260923' and kind in (0xbd6,0x663) and event.event_id==0x202:
            from els_server.protocol.inventory_management_messages import sort_ack,lock_ack
            from els_server.storage.inventory_management import sort_inventory,lock_item
            response_kind=0xbd7 if kind==0xbd6 else 0x664
            def failed():
                payload=sort_ack(result=-1) if kind==0xbd6 else lock_ack(self.account.get_reward_balances()['ed'],result=-1)
                return [Event(0x201,kind=response_kind,payload=payload)]
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return failed()
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            try:return (sort_inventory if kind==0xbd6 else lock_item)(self.account.store.path,self.account.uid,event.payload,operation)
            except ValueError:return failed()
        if self.item_test and self.client_build=='dx11_260923' and kind in (0x555,0x109) and event.event_id==0x202:
            from els_server.protocol.inventory_action_messages import split_ack,discard_ack
            from els_server.storage.inventory_actions import split_stack,discard
            response_kind=0x556 if kind==0x555 else 0x10a
            failed=split_ack if kind==0x555 else discard_ack
            if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                return [Event(0x201,kind=response_kind,payload=failed(result=-1))]
            operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
            updates=[]
            try:
                if kind==0x555:answer=split_stack(self.account.store.path,self.account.uid,event.payload,operation)
                else:answer,updates=discard(self.account.store.path,self.account.uid,event.payload,operation,with_updates=True)
            except ValueError:answer=failed(result=-1)
            return [Event(0x201,kind=response_kind,payload=answer),*updates]
        if self.item_test and self.client_build=='dx11_260923' and kind==0x104 and event.event_id==0x202 and len(event.payload)==11 and any(g in (22,23) for g in (event.payload[0],event.payload[5])):
            from els_server.domain.fishing_equipment import handle as life_equipment_handle
            return life_equipment_handle(self,event,request_sequence)
        if self.item_test and self.client_build=='dx11_260923' and kind==0x104 and event.event_id==0x202:
            from els_server.domain.fashion_state import move_fashion,move_ack
            if self.role!='game' or self.phase!='town_ready':return [Event(0x201,kind=0x105,payload=move_ack(result=2005 if len(event.payload)==11 and 24 in (event.payload[0],event.payload[5]) else -1))]
            try:
                if self.client_build=='dx11_260923' and len(event.payload)==11 and event.payload[0]==event.payload[5] and event.payload[0] in (2,3,4,5,6,21):
                    from els_server.storage.bag_moves import move_bag_items
                    ack=move_bag_items(self.account.store.path,event.payload,self.account.uid)
                elif len(event.payload)==11 and 24 in (event.payload[0],event.payload[5]):
                    from els_server.domain.tutorial_accessory import wear_context,validate_wear_context
                    if (event.performers!=(0,) or event.uid!=0xffffffffffffffff
                        or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Artifact wear envelope')
                    from els_server.storage.artifact_progression import move as move_artifact
                    captured=wear_context(self)
                    ack=move_artifact(self.account.store.path,event.payload,self.account.uid,account_id=self.account.account_id,
                        session_id=self.shop_session_id,sequence=request_sequence,validate=lambda:validate_wear_context(self,captured))
                else:
                    from els_server.domain.tutorial_accessory import wear_context,validate_wear_context
                    if (event.performers!=(0,) or event.uid!=0xffffffffffffffff
                        or event.target_uid!=0xffffffffffffffff or event.payload_mode!=0):raise ValueError('Wear envelope')
                    if len(event.payload)!=11:raise ValueError('Wear request size')
                    if not self.normal_equipment_moves_enabled:
                        from els_server.domain.inventory_items import FASHION_EQUIP_SLOTS
                        if any(g in (1,2) or g==9 and slot not in FASHION_EQUIP_SLOTS.values() for g,slot in ((event.payload[0],struct.unpack_from('>i',event.payload,1)[0]),(event.payload[5],struct.unpack_from('>i',event.payload,6)[0]))):raise ValueError('Ordinary wear route disabled')
                    from els_server.storage.wear_moves import move as move_wear
                    captured=wear_context(self)
                    ack=move_wear(self.account.store.path,event.payload,self.account.uid,account_id=self.account.account_id,
                        session_id=self.shop_session_id,sequence=request_sequence,validate=lambda:validate_wear_context(self,captured))
            except ValueError:ack=move_ack(result=2005 if len(event.payload)==11 and 24 in (event.payload[0],event.payload[5]) else -1)
            return [Event(0x201,kind=0x105,payload=ack)]
        if self.shop_test and event.event_id==0x202 and kind==0xd78:
            from els_server.protocol.shop_messages import catalog_request,empty_catalog_ack
            if self.role!='game' or self.phase!='town_ready':return [empty_catalog_ack(False)]
            try:catalog_request(event.payload)
            except ValueError:return [empty_catalog_ack(False)]
            return [empty_catalog_ack()]
        if self.shop_test and event.event_id==0x202 and kind in (0x1f1,0x1f3):
            from els_server.domain.wishlist_flow import handle as wishlist_handle
            return wishlist_handle(self,event)
        if self.shop_test and event.event_id==0x202 and kind==0xd7c:
            # Real cash entitlement and claim sources are not admitted.
            # The native producer still needs its original wait-ending refusal.
            from els_server.protocol.shop_messages import purchased_cash_unavailable_ack
            return [purchased_cash_unavailable_ack()]

        if self.shop_test and event.event_id==0x202 and kind==0xd7a:
            from els_server.protocol.shop_messages import empty_deposit_ack
            if self.role!='game' or self.phase!='town_ready':return []
            if event.payload!=bytes.fromhex('0000001500000001'):
                return [empty_deposit_ack(-1)]
            return [empty_deposit_ack()]
        if self.shop_test and event.event_id==0x202 and kind==0x80d:
            from els_server.protocol.shop_messages import catalog_request,ed_catalog_ack
            from els_server.storage.shop_state import quantity_catalog as catalog
            if self.role!='game' or self.phase!='town_ready':return []
            try:catalog_request(event.payload)
            except ValueError:return []
            self.ed_catalog_loaded=True
            return [ed_catalog_ack(catalog((self.account.character() or {'unit_type':1})['unit_type']))]
        if self.shop_test and event.event_id==0x202 and kind==0x80f:
            from els_server.protocol.shop_messages import ed_purchase_ack
            from els_server.storage.shop_state import purchase
            if self.role!='game' or self.phase!='town_ready' or not self.ed_catalog_loaded:
                return [ed_purchase_ack(-1,[],0)]
            if request_sequence is not None and (type(request_sequence) is not int or not 1<=request_sequence<2**32):
                return [ed_purchase_ack(-1,[],0)]
            operation=self.shop_session_id+':'+(str(request_sequence) if request_sequence is not None else str(uuid.uuid4()))
            before=self.account.character()
            career_updates=[]
            from els_server.storage.career_shop import notifications as career_purchase_notifications
            def prepare_career(db,old,new,replayed):
                career_updates.extend(career_purchase_notifications(db,self.account.uid,before,self.account.get_location(),old,new,replayed))
            from els_server.storage.skill_unlocks import purchase_notifications as skill_book_purchase_notifications
            def prepare_skill_books(db,character,previous,replayed):
                career_updates.extend(skill_book_purchase_notifications(db,self.account.uid,character,previous,replayed))
            try:payload=purchase(self.account.store.path,event.payload,operation,self.account.uid,prepare_career=prepare_career,prepare_skill_books=prepare_skill_books)
            except ValueError:return [ed_purchase_ack(-1,[],0)]
            answer=[Event(0x201,kind=0x810,payload=payload)]
            from els_server.storage.shop_state import bank_purchase_refresh
            answer+=bank_purchase_refresh(self.account.store.path,event.payload,operation,self.account.uid,payload)
            from els_server.domain.bag_capacity import expansion_notice
            expanded=expansion_notice(before,self.account.character())
            if expanded is not None:answer.append(expanded)
            from els_server.domain.bank_memberships import notice as bank_membership_notice
            bank_expanded=bank_membership_notice(before,self.account.character())
            if bank_expanded is not None:answer.append(bank_expanded)
            from els_server.domain.skill_expansion import ORDINARY_SKU,notice
            from els_server.protocol.shop_messages import ed_purchase_request
            if any(sku==ORDINARY_SKU for sku,n in ed_purchase_request(event.payload)):
                answer.append(notice(self.account.uid,self.account.character()))
            return answer+career_updates
        if self.enter_dungeon and event.event_id==0x202 and kind==0x110:
            # C38760 sends an empty request and waits for 111. C38880 reads
            # result:i32, reserved:i32, map-count:u32, then runs native exit.
            # Keep the scene until its original 225/227 return handshake.
            if self.role!='game' or self.phase!='dungeon_active' or not self.clear_notified or event.payload:return []
            return [Event(0x201,kind=0x111,payload=bytes(12))]
        from els_server.domain.cartridge_selection_box import handle as cartridge_box_handle
        cartridge_box_reply=cartridge_box_handle(self,event,request_sequence)
        if cartridge_box_reply is not None:return cartridge_box_reply
        if self.item_test and self.client_build=='dx11_260923' and event.event_id==0x202 and kind==0x559:
            from els_server.protocol.ice_messages import preview_request,preview_ack
            from els_server.domain.cubes import catalog as fixed_cubes
            self.fixed_cube_preview_template=None
            self.ice_preview_ready=False
            try:cube_request=preview_request(event.payload)
            except ValueError:return [preview_ack(-1,0)]
            if cube_request.template in fixed_cubes():
                if self.role!='game' or self.phase!='town_ready':return [preview_ack(-1,cube_request.template)]
                try:
                    if cube_request.keys not in ((),(0,)) or cube_request.flag1 not in (0,1) or cube_request.flag2 not in (0,1):raise ValueError('Fixed cube preview mode')
                    if cube_request.template==715036:
                        from els_server.domain.wardrobe_ticket_box import require_session_context
                        require_session_context(self,event,request_sequence)

                    if cube_request.template==168889:
                        from els_server.domain.equipment_chip_flow import current_lease
                        if self.account.store is None or self.account.store.uid!=self.account.uid or not current_lease(self):raise ValueError('Growing kit preview lease')
                    from els_server.domain.item_expiration import require_current
                    item=next((i for i in self.account.get_inventory_snapshot()['items'] if i['template']==cube_request.template and i['group']==4),None)
                    if item is None:raise ValueError('Missing fixed cube')
                    require_current(item)
                except ValueError:return [preview_ack(-1,cube_request.template)]
                row=fixed_cubes()[cube_request.template];self.fixed_cube_preview_template=cube_request.template
                if row.get('growing_adventure_kit'):
                    from els_server.domain.growing_adventure_kit import outputs_for
                    try:row=dict(row,entries=outputs_for(self.account.character()['unit_class']))
                    except ValueError:
                        self.fixed_cube_preview_template=None
                        return [preview_ack(-1,cube_request.template)]
                elif row.get('participation_gear'):
                    from els_server.domain.boosting_2026_participation_gear import preview
                    row=dict(row,entries=preview(row,self.account.character()['unit_class']))
                elif row.get('role_fashion90'):
                    from els_server.domain.boosting_2026_fashion_rewards import preview
                    row=dict(row,entries=preview(cube_request.template,self.account.character(),cube_request.flag2))

                self.ice_preview_ready=False

                self.ice_preview_ready=False
                return [preview_ack(0,cube_request.template,selection_count=row['selection_count'],entries=tuple((e['template'],0,e['quantity']) for e in row['entries']))]
            if not self.ice_test:return [preview_ack(-1,cube_request.template)]
        if self.item_test and self.client_build=='dx11_260923' and event.event_id==0x202 and kind==0x196:
            from els_server.storage.fixed_cubes import open_cube
            from els_server.protocol.cube_messages import result as cube_result
            from els_server.protocol.ice_messages import use_request
            from els_server.domain.cubes import catalog as fixed_cubes
            try:cube_use=use_request(event.payload)
            except ValueError:return cube_result(self.account.get_reward_balances()['ed'],code=-1)
            cube_item=next((i for i in self.account.get_inventory_snapshot()['items'] if i['uid']==cube_use.uid),None)
            cube_template=cube_item['template'] if cube_item and cube_item['template'] in fixed_cubes() else self.fixed_cube_operations.get((self.account.uid,request_sequence),self.fixed_cube_preview_template)
            if cube_template is not None:
                if cube_template==715036:
                    from els_server.domain.wardrobe_ticket_box import require_session_context
                    try:require_session_context(self,event,request_sequence)
                    except ValueError:return cube_result(self.account.get_reward_balances()['ed'],code=-1)

                if cube_template==168889:
                    from els_server.domain.equipment_chip_flow import current_lease
                    if self.account.store is None or self.account.store.uid!=self.account.uid or not current_lease(self):return cube_result(0,code=-1)
                if self.role!='game' or self.phase!='town_ready' or type(request_sequence) is not int or not 1<=request_sequence<2**32:
                    return cube_result(self.account.get_reward_balances()['ed'],code=-1)
                operation=self.shop_session_id+':'+str(self.account.uid)+':'+str(request_sequence)
                try:
                    if cube_template==715036:
                        require_session_context(self,event,request_sequence)
                        answer=open_cube(self.account.store.path,self.account.uid,cube_template,event.payload,operation,account_id=self.account.account_id)
                    else:answer=open_cube(self.account.store.path,self.account.uid,cube_template,event.payload,operation)
                except ValueError:return cube_result(self.account.get_reward_balances()['ed'],code=-1)
                self.fixed_cube_operations[(self.account.uid,request_sequence)]=cube_template
                return answer
        if self.item_test and self.client_build=='dx11_260923' and event.event_id==0x202 and kind==0x196 and not self.ice_test:
            from els_server.protocol.cube_messages import result as cube_result
            return cube_result(self.account.get_reward_balances()['ed'],code=-1)
        if self.ice_test and event.event_id==0x202 and kind==0x559:
            from els_server.protocol.ice_messages import preview_request,preview_ack
            if self.role!='game' or self.phase!='town_ready':return []
            try:
                request=preview_request(event.payload)
                from els_server.domain.ice_rules import role_pools
                pools=role_pools((self.account.character() or {'unit_type':1})['unit_type'])
                if request.template not in pools or request.keys!=(0,):raise ValueError('Unsupported ice preview for this character')
                items=self.account.get_inventory_snapshot()['items']
                if not any(i['template']==request.template and i['group']==4 for i in items):raise ValueError('Missing ice consumable')
            except ValueError:return [preview_ack(-1,0)]
            self.ice_preview_ready=True
            # Legacy random-item UI rejects a successful but empty preview as
            # "This character cannot use this item" (2271D30 -> 227217A).
            # 22977C0 consumes template, duration and quantity per 12-byte row.
            # Display the same role-filtered pool that the transaction draws from.
            return [preview_ack(0,request.template,entries=tuple((template,0,1) for template,_ in pools[request.template]))]
        if self.ice_test and event.event_id==0x202 and kind==0x196:
            from els_server.protocol.ice_messages import result_ack,result_events
            from els_server.storage.ice_state import draw
            if self.role!='game' or self.phase!='town_ready' or not self.ice_preview_ready:return [result_ack(-1,[],0)]
            if type(request_sequence) is not int or not 1<=request_sequence<2**32:return [result_ack(-1,[],0)]
            try:payload=draw(self.account.store.path,event.payload,self.shop_session_id+':'+str(request_sequence),uid=self.account.uid)
            except ValueError:return [result_ack(-1,[],0)]
            return result_events(payload)
        if kind==0x233:
            # Observed native exit request also occurs before 0x225/0x227.
            # Completed requests cannot bypass the current-phase boundary.
            allowed=self.phase=='channels_ready' or (self.enter_town and self.phase=='map_loading') or (self.phase=='closing' and kind in self.completed)
            if event.event_id!=0x202 or event.payload or self.role!='game' or not allowed:
                raise SessionOrderError(f'Request {kind:#x} outside phase {self.phase} or invalid exit payload')
            self.pending_map=None;self.shop_available_pending=False
            self.phase='closing';self.completed.add(kind)
            return self.responses(kind)
        rules={0x1a:('new','game_connected'),0x1e:('game_connected','game_authenticated'),
               0x35:('game_authenticated','port_ready'),0x1ef:('port_ready','session_ready'),
               0x39:('session_ready','terms_ready'),0x485:('terms_ready','characters_ready'),
               0x490:('characters_ready','channels_ready')}
        if self.enter_town:
            rules.update({0x28:('characters_ready','player_initialized'),
                          0x6e9:('player_initialized','skill_ui_ready'),
                          0x5bf:('skill_ui_ready','initialization_confirmed'),
                          0x32:('initialization_confirmed','map_loading'),
                          0x225:('map_loading','square_accepted'),
                          0x227:('square_accepted','town_ready')})
        if kind in rules:
            before,after=rules[kind]
            # Client keeps the accepted terms flag across a channel reconnect.
            if kind==0x485 and self.phase=='session_ready' and self.account.has_terms():before='session_ready'
            returning_to_selection=self.enter_town and kind==0x490 and self.phase=='town_ready'
            if returning_to_selection:before='town_ready'
            if kind==0x490 and self.phase=='closing' and 0x233 in self.completed:before='closing'
            if kind==0x28 and self.phase=='channels_ready':before='channels_ready'
            if kind==0x485 and self.phase=='channels_ready':before='channels_ready'
            if event.event_id!=0x202 or (self.phase!=before and kind not in self.completed):
                raise SessionOrderError(f'Request {kind:#x} outside phase {self.phase}')
            if kind==0x225 and self.phase not in ['map_loading','town_ready','square_accepted']:
                raise SessionOrderError('Town request before initialization')
            if kind==0x227 and self.phase not in ['square_accepted','town_ready']:
                raise SessionOrderError('Scene ready outside current town phase')
            if kind==0x28:
                if (event.performers!=(0,) or event.uid!=2**64-1
                        or event.target_uid!=2**64-1 or event.payload_mode!=0):
                    raise SessionOrderError('Invalid character initialization envelope')
                if self.phase not in ('characters_ready','channels_ready'):
                    # A transport retry can repeat the original initialization
                    # while loading. It cannot switch the selected identity,
                    # reset phases, or repeat companion/receipt recovery writes.
                    if (self.phase in ('player_initialized','skill_ui_ready','initialization_confirmed','map_loading')
                            and event.payload==getattr(self,'player_initialization_request',None)
                            and getattr(self,'player_initialization_reply',None) is not None):
                        return list(self.player_initialization_reply)
                    raise SessionOrderError('Character initialization outside selection or current loading')
                if len(event.payload)<8:raise SessionOrderError('Missing character UID')
                chosen_uid=struct.unpack_from('>Q',event.payload)[0]
                if self.account.characters is not None and self.account.characters.get(chosen_uid).get('pending_delete'):
                    raise SessionOrderError('Pending deletion character cannot enter game')
                # Selection is validated before discarding the old paid candidate.
                try:next_account=self.account.for_character(chosen_uid)
                except ValueError as e:raise SessionOrderError(str(e)) from e
                from els_server.domain.tenebros_storage_flow import abandon as abandon_shadow
                abandon_shadow(self)
                try:self.account=next_account
                except ValueError as e:raise SessionOrderError(str(e)) from e
                self.first_story_entry=None
                if self.item_test and self.client_build=='dx11_260923':
                    from els_server.storage.item_expiration import remove_due
                    # A fresh character restore contains only surviving items;
                    # there is no old client inventory to notify at this point.
                    remove_due(self.account.store.path,self.account.uid)
                    self.expiration_checked=None
                    self.luciel_dungeon_hp_source=None;self.luciel_dungeon_hp_max=None
                    from els_server.storage.career_purchase_recovery import recover
                    from els_server.storage.career_shop import notifications as career_notifications
                    character=self.account.character();location=self.account.get_location()
                    self.career_purchase_recovery=recover(self.account.store.path,self.account.uid,self.account.account_id,
                        prepare=lambda db,before,after,replayed:career_notifications(db,self.account.uid,character,location,before,after,replayed))
                self.completed.difference_update((0x28,0x6e9,0x5bf,0x32,0x225,0x227))
                self.cartridge_sync_key=None
                self.tenebros_capacity_sync_key=None
                self.tenebros_storage_sync_key=None
                self.ed_catalog_loaded=False;self.ice_preview_ready=False
                self.fixed_cube_preview_template=None;self.fixed_cube_operations.clear();self.npc_history_id=str(uuid.uuid4())
                self.shop_available_pending=False
                saved=self.account.get_inventory_snapshot() if self.item_test else None
                from els_server.domain.quest_flow import initialization as quest_initialization
                from els_server.domain.first_story_entry import pending_tutorial
                initial_health_max=100
                character=self.account.character()
                if (self.enter_dungeon and character['unit_type']==10 and character['level']==1
                        and self.account.get_reward_balances()['experience']==0):
                    from els_server.domain.character_stats import combat_values
                    initial_health_max=math.ceil(combat_values(character,saved['items'] if saved else None)[0])
                if self.enter_dungeon and character['unit_type']==10 and character['level']>1:
                    # Current2F restores absolute LuCiel HP; reuse the existing
                    # HP aggregate while native equipment/passive code stays intact.
                    from els_server.domain.character_stats import combat_values
                    initial_health_max=math.ceil(combat_values(character,saved['items'] if saved else None)[0])
                answer=[player_initialization(self.account.get_location(),initialize_attributes=self.enter_dungeon,economy=saved['balances'] if saved else self.account.get_reward_balances() if self.reward_test else None,items=saved['items'] if saved else None,character=self.account.character(),restore_equipped=self.enter_dungeon),skill_slots_initialization(self.account.get_skills(),self.account.uid,self.account.character()),quest_initialization(self)]+optional_player_initializations(initialize_health=self.enter_dungeon,uid=self.account.uid,health_max=initial_health_max,luciel_active=(character.get('luciel_active_unit',0) if character['unit_type']==10 else 0),wardrobe=character.get('wardrobe',{}),wardrobe_favorites=character.get('wardrobe_favorites',()),tutorial_pending=pending_tutorial(self))+[Event(0x201,kind=0x29,payload=i32(0))]
                if self.item_test and self.client_build=='dx11_260923':
                    from els_server.storage.wardrobe import color_initializations,point_initialization
                    answer+=color_initializations(self.account.store.path,self.account.uid,self.account.account_id)
                    answer.append(point_initialization(self.account.store.path,self.account.uid,self.account.account_id))
                if self.item_test and self.client_build=='dx11_260923':
                    from els_server.storage.quick_slots import initialization
                    answer.insert(1,initialization(self.account.store.path,self.account.uid))
                    from els_server.protocol.paid_enhancement_messages import hammer_initialization
                    answer.insert(2,hammer_initialization())
                    from els_server.storage.companion_state import snapshot as companion_snapshot
                    from els_server.protocol.companion_messages import initialization as companion_initialization
                    companion_save=companion_snapshot(self.account.store.path,self.account.uid,enter_world=True)
                    answer=[companion_initialization(companion_save) if e.kind==0x2d else e for e in answer]
                    from els_server.storage.pet_support import initialization as pet_automatic_initialization
                    answer.append(pet_automatic_initialization(self.account.store.path,self.account.uid))
                # Restore the authenticated account keyboard preference after
                # selection, preserving the established native 2A/399 timing.
                answer.insert(1,key_bindings_initialization(self.account.get_bindings()))
                from els_server.domain.fishing_attempt import initialize_login as initialize_life
                answer=initialize_life(self,answer)
                self.player_initialization_request=bytes(event.payload)
                self.player_initialization_reply=tuple(answer)
            elif kind==0x6e9:answer=[Event(0x201,kind=0x6ea,payload=encode_layout(self.account.get_layout()))]
            elif kind==0x5bf:
                # DX11 13E4030 writes two i32 cursors. The current 2A restore
                # sends the complete inventory map; no split rows remain.
                # 138ECC0 consumes result/current/total, then sends 32 only
                # when current == total. Reject invented continuation cursors
                # instead of advancing initialization on malformed input.
                if self.client_build=='dx11_260923' and event.payload!=bytes(8):
                    raise SessionOrderError('Invalid inventory split cursors')
                answer=[Event(0x201,kind=0x5c0,payload=i32(0)*3)]
            # 138F0E0: local DX11 has no inventory PIN configured; the ACK
            # must mark access ready. False enters 1C7 verification forever
            # instead of continuing to the original first tutorial request.
            elif kind==0x32:answer=[Event(0x201,kind=0x33,payload=i32(0)+bytes([self.client_build=='dx11_260923']))]
            elif kind==0x225:
                if len(event.payload)!=5:raise SessionOrderError('Invalid local town entry')
                if event.payload[4]!=0:
                    # B934A0's explicit native default-position branch sends
                    # 225(town, 1). Only the witnessed Noah source-clear return
                    # may use it; ordinary entry and other callers keep flag 0.
                    story=getattr(self,'first_story_entry',None)
                    character=self.account.character()
                    native_noah_return=(
                        event.payload==i32(20012)+b'\x01'
                        and self.client_build=='dx11_260923' and self.enter_dungeon
                        and self.phase in ('map_loading','square_accepted')
                        and event.performers==(0,) and event.uid==event.target_uid==2**64-1
                        and event.payload_mode==0 and self.dungeon_return_pending and self.clear_notified
                        and story is not None and story.get('map')==34570
                        and story.get('started') is True and story.get('returned') is True
                        and story.get('run') is not None and self.dungeon_run is story['run']
                        and character is not None and character['unit_type']==14 and character['level']==1
                        and self.account.get_reward_balances()['experience']==0)
                    if not native_noah_return:raise SessionOrderError('Invalid local town entry')
                requested=struct.unpack_from('>i',event.payload)[0]
                if requested==1011 and not _mainline1011_entry(self,event,request_sequence):
                    return [Event(0x201,kind=0x226,payload=i32(-1)+i32(requested)+i32(0)*3)]
                # Source Village20010 Start608 ->1009/1602 produces225(1009,0).
                # This finite ordinary-role22375 consumer is separate from58C;
                # unknown special-role routing stays closed, with no clear waiver.
                native_varnimyr_rest=False
                if requested==1009:
                    if (event.payload==i32(1009)+b'\x00'
                        and self.client_build=='dx11_260923' and self.enter_town
                        and self.role=='game' and self.phase in ('map_loading','town_ready','square_accepted')
                        and event.performers==(0,) and event.uid==event.target_uid==2**64-1 and event.payload_mode==0
                        and type(request_sequence) is int and 1<=request_sequence<2**32
                        and self.account.characters is not None and self.account.store is not None
                        and TOWN_SCENES.get(1009)==851 and getattr(self,'town_warp_transition',None) is None):
                        from contextlib import closing
                        import sqlite3
                        from els_server.storage.seal_quests import load_character,completed_ids
                        with closing(sqlite3.connect(self.account.store.path,timeout=10)) as db:
                            db.execute('BEGIN')
                            character=load_character(db,self.account.uid,self.account.account_id)
                            if character['unit_type'] in range(1,13) and character['level']==99:
                                completed=completed_ids(db,self.account.uid)
                                records={r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(self.account.uid,))}
                                saved=db.execute('SELECT town FROM location WHERE uid=?',(self.account.uid,)).fetchone()
                                source=(saved==(20010,) and self.active_map==20010
                                    and self.phase in ('town_ready','square_accepted') and not self.dungeon_return_pending)
                                restore=(saved==(1009,) and self.active_map in (None,1009))
                                task=(22375 in completed or db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=22375',(self.account.uid,)).fetchone() is not None)
                                native_varnimyr_rest=(26640 in completed and 30092 in records and task and (source or restore))
                    if not native_varnimyr_rest:
                        return [Event(0x201,kind=0x226,payload=i32(-1)+i32(requested)+i32(0)*3)]

                warp=getattr(self,'town_warp_transition',None)
                if warp is not None and (requested!=warp['destination'] or event.payload[4]!=0):raise SessionOrderError('Town entry differs from committed warp')
                if requested==1012:
                    from els_server.domain.town_travel_flow import authorize_village1012_entry
                    if not authorize_village1012_entry(self,event,request_sequence):
                        return [Event(0x201,kind=0x226,payload=i32(-1)+i32(requested)+i32(0)*3)]
                if requested not in TOWN_SCENES:
                    return [Event(0x201,kind=0x226,payload=i32(-1)+i32(requested)+i32(0)*3)]
                # 0xb78c10 consumes five int32 fields. The requested map is
                # already selected in the native stage manager before this ACK.
                self.pending_map=requested
                if not self.dungeon_return_pending:self.inventory_town_sync_sent=False
                answer=[Event(0x201,kind=0x226,payload=i32(0)+i32(requested)+i32(0)*3)]
                if restore_clear_economy:
                    answer.insert(0,self.saved_user_sync(clear_reward_only=True));self.inventory_town_sync_sent=True
            elif kind==0x227:
                # 1bbac80 -> 1cee770 serializes xyz floats + byte + ushort.
                # 1bbb430 reads int result and clears the original 0x228 wait.
                if self.pending_map is None:raise SessionOrderError('Scene ready without a selected town')
                try:
                    board,progress,xyz=scene_ready_location(event.payload)
                    self.account.save_location(self.pending_map,board,progress,xyz)
                except ValueError as e:raise SessionOrderError(str(e)) from e
                self.active_map=self.pending_map
                answer=[Event(0x201,kind=0x228,payload=i32(0))]
                if self.item_test and not self.inventory_town_sync_sent:
                    answer.append(self.saved_user_sync());self.inventory_town_sync_sent=True
                self.dungeon_return_pending=False
                self.town_warp_transition=None
                if self.item_test and self.phase=='square_accepted':
                    # 227 proves the actor/scene is ready. Deliver the native
                    # equipment refresh immediately AFTER 228/D9, rather than
                    # waiting behind shop availability on two one-second ticks.
                    from els_server.domain.fashion_state import move_ack
                    items=[i for i in self.account.get_inventory_snapshot()['items'] if i['group']==9]
                    if items:answer.append(Event(0x201,kind=0x105,payload=move_ack([((9,i['slot']),i) for i in items])))
                if self.item_test and self.phase=='square_accepted':
                    from els_server.domain.character_custom import restored as custom_restored
                    answer.extend(custom_restored(self.account.character()))
                if self.shop_test and self.phase=='square_accepted':self.shop_available_pending=True
            elif kind==0x1a:
                from els_server.protocol.local_messages import connection_ack
                answer=[connection_ack(self.port_probe_port)]
            elif kind==0x485 and self.account.characters is not None:
                roles=self.account.character_list()
                selection=None
                if self.client_build=='dx11_260923':
                    from els_server.storage.character_selection import snapshot as selection_snapshot
                    selection=selection_snapshot(self.account.characters.path,self.account.account_id)
                answer=[character_list(self.client_build,characters=roles,selection=selection)]
            elif kind==0x485 and self.reward_test:answer=[character_list(self.client_build,self.account.get_reward_balances())]
            else:answer=self.responses(kind)
            if returning_to_selection:answer=[character_gate_notice()]+answer
            if self.enter_town and kind==0x485:
                # Restore keys after selection (0x2A), as in the accepted parent.
                # Do not arm the old pre-selection missing-key popup.
                initial=[character_gate_notice()]
                if self.account.characters is None:initial.insert(0,key_bindings_initialization(self.account.get_bindings()))
                answer=initial+answer
            self.role='game'
            if kind not in self.completed or kind in [0x485,0x490,0x225,0x227]:self.phase=after
            self.completed.add(kind)
            if kind==0x39:self.account.accept_terms()
            return answer
        if self.enter_dungeon and self.client_build=='dx11_260923' and event.event_id==0x202 and kind==0x67:
            # Authenticated loopback end request generated by Game v270.
            # Native state callers use reason 0x72. Trailing statistics remain
            # opaque and do not grant rewards or update character attributes.
            payload=event.payload
            if not 100<=len(payload)<=8192 or payload[:4]!=i32(0x72):return []
            if self.dungeon_end_payload is not None:
                return [dungeon_messages.end_ack()] if payload==self.dungeon_end_payload else []
            if self.role!='game' or self.phase!='dungeon_active':return []
            self.dungeon_end_payload=bytes(payload)
            self.phase='map_loading';self.pending_map=None
            self.dungeon_return_pending=True
            self.luciel_dungeon_hp_source=None;self.luciel_dungeon_hp_max=None
            self.inventory_town_sync_sent=True
            return [dungeon_messages.end_ack(),self.saved_user_sync(clear_reward_only=self.clear_notified)]
        if self.enter_dungeon and self.phase=='dungeon_active' and event.event_id==0x202 and kind==0xb3:
            # B57E30 -> B940C0: first substage load completion (bool,
            # int, float). B4 consumes result/removes wait; B5 consumes result/UID
            # and updates native peer loading state via 3FBB70.
            if len(event.payload)!=9 or event.payload[:5]!=bytes(5):return []
            # Original B940C0 writer's float is no longer zero with real
            # combat attributes (updated native capture: 40B66666 = 5.7).
            # Preserve the bool/error constraints and validate the scalar.
            value=struct.unpack_from('>f',event.payload,5)[0]
            if not math.isfinite(value) or not 0<=value<=1e9:return []
            reply=[Event(0x201,kind=0xb4,payload=i32(0)),
                   Event(0x201,kind=0xb5,payload=i32(0)+struct.pack('>Q',self.account.uid))]
            if not self.dungeon_substage_synced:
                # B581A0: int, inventory vector, bool vector, float.
                # Then select resource part 0 (B7) before resuming actors (BD).
                # All three notifications are once-only for this first substage.
                reply.append(Event(0x201,kind=0xb6,payload=bytes(16)))
                reply.append(dungeon_messages.initial_part())
                npc_entries=()
                if self.client_build=='dx11_260923' and self.population_test:
                    from els_server.domain.dungeon_population import population
                    npc_entries=tuple((n['key'],n['template']) for n in population(self.gate_stage)['npcs'])
                reply.append(dungeon_messages.begin_substage(npc_entries=npc_entries))
                self.dungeon_substage_synced=True
                self.dungeon_clock.resume()
                self.gate_stage_loading=False
            return reply
        if self.enter_dungeon and self.phase in ['dungeon_loading','dungeon_active'] and event.event_id==0x202 and kind==0x91:
            # B558D0: result, echoed loading progress, uint. Native removes
            # the 0x92 wait and clears the loading flag at progress >= 100.
            if len(event.payload)!=8:return []
            progress,mode=struct.unpack('>ii',event.payload)
            if not 0<=progress<=100 or mode!=0:return []
            reply=[Event(0x201,kind=0x92,payload=i32(0)+i32(progress)+u32(0)),
                   Event(0x201,kind=0x93,payload=struct.pack('>Q',self.account.uid)+i32(progress))]
            # B55B20 consumes UID/progress. B55EE0 consumes no payload and
            # starts the native scene. One local member, one start notification.
            if progress==100 and self.phase=='dungeon_loading':
                from els_server.protocol.dungeon_messages import initial_substage
                if self.activity2026_awards is not None:self.activity2026_awards.capture(self)
                self.phase='dungeon_active'
                if self.dungeon_run is not None:
                    initial=self.dungeon_run.population_event()
                elif self.population_test:
                    from els_server.domain.dungeon_population import substage
                    initial=substage(0)
                else:initial=initial_substage(self.client_build,0 if self.npc_slot_test else None,gate_test=self.gate_test)
                reply.extend([Event(0x201,kind=0x96,payload=b''),initial])
            return reply
        if self.enter_town and self.phase in ['player_initialized','skill_ui_ready','initialization_confirmed','map_loading','square_accepted','town_ready'] and event.event_id==0x202:
            if self.enter_dungeon and self.phase=='town_ready' and kind==0x7d4:
                from els_server.protocol.dungeon_messages import SUPPORTED_DUNGEON
                from els_server.domain.dungeon_routes import route_catalog
                mode,identity=struct.unpack('>ii',event.payload) if len(event.payload)==8 else (0,0)
                if self.population_test and self.client_build=='dx11_260923':identity=route_catalog().entry_identity(identity)
                # 2CC06D0/3782 -> mode 2, then 2D7DE20 selects 37F for
                # DCC_SINGLE_DUNGEON. Mode 2 on ordinary maps is matching,
                # which this single-player path must not admit.
                from els_server.game_data import client_data
                internal=str(identity) in route_catalog()._data.get('internal_routes',{})
                from els_server.domain.challenge_flow import allowed as challenge_allowed
                challenge=challenge_allowed(self,identity) if internal else None
                supported=route_catalog().supports(identity) or internal and challenge is not None
                single=supported and 1 in client_data().dungeon(identity).get('DUNGEON_CHECK_CONDITION',{}).values()
                # 7D5's second i32 chooses the original continuation mode.
                # Ordinary matching uses the existing local solo flow; native
                # single-only maps retain mode 2 and their 37F continuation.
                admitted_mode=1 if mode==2 and not single and self.population_test and self.client_build=='dx11_260923' else mode
                from els_server.protocol.dungeon_errors import DUNGEON_CLOSED,INVALID_DUNGEON_MODE,ENTRY_REQUIREMENTS_NOT_MET
                result=INVALID_DUNGEON_MODE if not (admitted_mode==1 or admitted_mode==2 and single) else DUNGEON_CLOSED
                valid=(admitted_mode==1 or admitted_mode==2 and single) and (identity==SUPPORTED_DUNGEON or
                    self.population_test and self.client_build=='dx11_260923' and supported)
                if valid:
                    from els_server.domain.region_quests import account_dungeon_allowed
                    valid=account_dungeon_allowed(self.account,identity)
                    result=ENTRY_REQUIREMENTS_NOT_MET
                from els_server.domain.event_dungeons import is_reviewed
                if valid and is_reviewed(identity):
                    from els_server.domain.event_admission import eligible
                    valid=admitted_mode==2 and eligible(self.account,identity)
                extra=[]
                if valid and not internal:
                    from els_server.domain.challenge_flow import ordinary_entry
                    valid,extra=ordinary_entry(self)
                self.dungeon_requested=valid
                self.requested_dungeon_id=identity if valid else None
                self.requested_dungeon_mode=admitted_mode if valid else None
                self.requested_challenge=challenge if valid else None
                return extra+[Event(0x201,kind=0x7d5,payload=i32(0 if valid else result)+i32(admitted_mode))]
            if self.enter_dungeon and self.phase=='town_ready' and kind in (0x37f,0x382):
                from els_server.protocol.dungeon_messages import SUPPORTED_DUNGEON,dungeon_start
                # Current 2E09A80 -> 2E0DE00 -> virtualized 2B48B60:
                # the native 18-byte record is
                # transformed, plus a variable opaque string inserted at a
                # variable field boundary. The map
                # comes from the already authenticated, clear 7d4 request.
                # Inner encoding/checksum remains experimental, not verified.
                opaque=event.payload
                # 2D62090 and 2D6D830 use the same 18-byte DTO and the
                # same 2E09A80 -> 2E0DE00 -> 2B48B60 writer.
                ack=0x380 if kind==0x37f else 0x383
                def admission_ack(result):
                    # 2D62800 reads result, u64, two wide strings (380).
                    return Event(0x201,kind=ack,payload=i32(result)+(bytes(8) if kind==0x37f else b'')+wstring('')*2)
                valid=self.dungeon_requested and self.requested_dungeon_mode==(2 if kind==0x37f else 1) and 23<=len(opaque)<=86 and any(struct.unpack_from('>I',opaque,o)[0]==len(opaque)-22 for o in range(19))
                if valid:
                    from els_server.domain.region_quests import account_dungeon_allowed
                    valid=account_dungeon_allowed(self.account,self.requested_dungeon_id)
                if not valid:return [admission_ack(-1)]
                identity=self.requested_dungeon_id
                from els_server.domain.challenge_flow import allowed as challenge_allowed
                challenge=getattr(self,'requested_challenge',None)
                if challenge is not None and challenge_allowed(self,identity)!=challenge:return [admission_ack(-1)]
                from els_server.domain.dungeon_routes import DungeonRun
                run_id=str(uuid.uuid4())
                # Compile the initial packet before changing connection state.
                run=DungeonRun(identity,run_id,internal=challenge is not None) if identity!=SUPPORTED_DUNGEON else None
                from els_server.domain.event_dungeons import is_reviewed
                if is_reviewed(identity):
                    from els_server.domain.event_admission import start as start_event
                    if kind!=0x37f:return [admission_ack(-1)]
                    return start_event(self,identity,run_id,run,opaque,admission_ack)
                self.active_challenge=challenge;self.challenge_clear_effect=None
                from els_server.domain.challenge_flow import store as challenge_store
                self.challenge_deadline=challenge_store(self).current()['deadline'] if challenge is not None else None
                self.phase='dungeon_loading';self.dungeon_requested=False
                self.dungeon_id=identity;self.dungeon_run=run;self.requested_dungeon_id=None;self.requested_dungeon_mode=None
                self.previous_dungeon_part=None
                self.dungeon_clock=DungeonClock()
                self.summon_next_key=16;self.summon_requests={}
                self.summon_keys=set();self.summon_deaths={}
                self.dungeon_substage_synced=False;self.dungeon_end_payload=None
                self.defeated_npcs={};self.part_end_notified=False
                self.gate_stage=0;self.gate_stage_loading=False
                self.clear_notified=False
                self.dungeon_failed=False
                self.dungeon_participants=frozenset((self.account.uid,))
                self.reward_run_id=run_id if self.reward_test else None;self.reward_receipt=None;self.clear_items_synced=False
                self.world_drops={};self.world_drop_issued=None;self.world_drop_sequence=910001
                self.pickup_receipt=None
                world=getattr(getattr(self,'application',None),'world',None)
                room=world.party_of.get(self,{}) if world else (getattr(self,'solo_challenge_party',None) or {})
                reply=[admission_ack(0),dungeon_start(self.account.get_skills(),self.account.character(),self.account.get_inventory_snapshot()['items'] if self.item_test else None,dungeon_id=identity,room_id=room.get('id',10001) if room.get('solo_challenge') else 10001,account_id=self.account.account_id,bootstrap_port=self.port_probe_port,member_capture=self._capture_luciel_dungeon_hp)]
                if challenge is not None:
                    from els_server.domain.challenge_flow import notification
                    reply.append(notification(self))
                return reply
            if kind==0x122:
                try:
                    from els_server.domain.equipment_chip_flow import current_lease
                    if self.role!='game' or not current_lease(self):
                        raise ValueError('Obsolete skill layout session')
                    if getattr(self,'application',None) is not None and (self.account.characters is None or self.account.store is None or self.account.store.uid!=self.account.uid):
                        raise ValueError('Skill layout character/store binding')
                    ack=self.account.equip_skill(event.payload)
                except ValueError:ack=i32(-1)+i32(-1)+i32(0)+i32(-1)+i32(0)
                return [Event(0x201,kind=0x123,payload=ack)]
            if kind==0x6eb:
                # Native 196b2b0 reads int result and removes the 6ec wait.
                try:self.account.save_layout(event.payload)
                except ValueError:return [Event(0x201,kind=0x6ec,payload=i32(-1))]
                return [Event(0x201,kind=0x6ec,payload=i32(0))]
            if kind==0x22b and self.phase=='town_ready':
                try:
                    board,progress,xyz=movement_location(event.payload,self.client_build)
                    self.account.save_location(self.active_map,board,progress,xyz)
                except ValueError as e:raise SessionOrderError(str(e)) from e
                return []  # Local movement is a notification, not an outstanding wait.
            if kind==0x1b2:
                # B8FE10 sends only an ID; B92570 reads the 29-byte cash ACK.
                # This profile has no cash/billing source; ED is independent.
                if self.client_build=='dx11_260923' and event.payload:
                    raise SessionOrderError('Cash balance query has no request body')
                # result, legacy balance, only-type flag, type index, four cash values.
                return [Event(0x201,kind=0x1b3,payload=i32(0)+u32(0)+b'\x00'+i32(-1)+u32(0)*4)]
            if kind==0xb6f:
                # Current DX11 B6F is a CustomEvent reply, not this old query.
                if self.client_build=='dx11_260923':
                    raise SessionOrderError('Legacy auxiliary request is not valid for DX11')
                return [Event(0x201,kind=0xb70,payload=i32(0)+u32(0)*3)]
            if kind==0x231:return [Event(0x201,kind=0x232,payload=i32(0))]
        if kind==0x48d:
            if self.role!='game' or self.phase in ['new','game_connected']:raise SessionOrderError('Role metadata before game login')
            return self.responses(kind)
        # Undecoded auxiliary notices are observed but do not advance the phase.
        return []
def _mainline1011_entry(s,event,sequence):
    """Finite source1011 entry: paid warp, saved reader, or real adjacency."""
    from els_server.domain.town_travel_flow import _ordinary_actor,_ordinary_binding
    from contextlib import closing
    import sqlite3
    try:
        if (not _ordinary_actor(s) or s.role!='game' or not s.enter_town or not s.item_test
            or s.client_build!='dx11_260923' or s.account.characters is None
            or event.event_id!=0x202 or event.kind!=0x225 or event.payload!=struct.pack('>iB',1011,0)
            or event.performers!=(0,) or event.uid!=event.target_uid or event.uid!=2**64-1
            or event.payload_mode!=0 or type(sequence) is not int or not 1<=sequence<2**32
            or s.phase not in ('map_loading','square_accepted','town_ready')):
            return False
        from els_server.storage.seal_quests import load_character,completed_ids
        with closing(sqlite3.connect(s.account.store.path.resolve().as_uri()+'?mode=ro',uri=True,timeout=10))as db:
            db.execute('BEGIN');character=load_character(db,s.account.uid,s.account.account_id)
            row=db.execute('SELECT town FROM location WHERE uid=?',(s.account.uid,)).fetchone()
            if row is not None and row[0]!=1011:
                # Git's independent225 path lacks the runtime's later generic
                # destination gate. Restore only1011 changed-destination admission,
                # with identity, level/quests and clear records from this snapshot.
                from els_server.domain.town_travel import require_destination
                records={r[0] for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(s.account.uid,))}
                require_destination(1011,character,completed_ids(db,s.account.uid),records)
        if row is None or s.account.get_location()['map']!=row[0]:return False
        saved=row[0];pending=getattr(s,'town_warp_transition',None)
        if pending is not None:
            # Ordinary58C commits the paid position before225/227. Reuse that
            # exact actor/session transition rather than charging a second fee.
            return bool(saved==1011 and isinstance(pending,dict)
                and pending.get('actor_binding')==_ordinary_binding(s)
                and pending.get('destination')==1011 and isinstance(pending.get('payload'),bytes)
                and pending['payload'][:4]==struct.pack('>i',1011)
                and s.phase in ('map_loading','square_accepted') and not s.dungeon_return_pending)
        if saved==1011:
            if not s.dungeon_return_pending:
                return s.active_map in (None,1011)
            # Retain only the existing same-origin solo clear return reader.
            payload=getattr(s,'dungeon_end_payload',None)
            run=getattr(s,'reward_run_id',None)
            return bool(s.active_map==1011 and s.phase=='map_loading'
                and getattr(s,'dungeon_participants',None)==frozenset((s.account.uid,))
                and isinstance(payload,bytes) and 100<=len(payload)<=8192
                and payload[:4]==struct.pack('>i',0x72)
                and isinstance(run,str) and str(uuid.UUID(run))==run and uuid.UUID(run).version==4)
        # Same-build Village edges:20013 Start804->1011/1707;
        #1011 Start1710<->1012/1712. Changed destinations were gated above.
        return bool(saved in (20013,1012) and s.active_map==saved
            and s.phase in ('town_ready','square_accepted') and not s.dungeon_return_pending
            and getattr(s,'pending_map',None) in (None,saved,1011))
    except (ValueError,TypeError,KeyError,AttributeError,OverflowError):
        return False
