"""Ordered optional domain handlers, preserving the original first-match chain.

None declines a request; an empty list consumes it. Keep the explicit call
order, including shared packet kinds and the original guarded callbacks.
"""


def priority_handlers(self,event,request_sequence=None):
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
    from els_server.domain.coupon_failure_flow import handle as coupon_failure_handle
    coupon_failure_reply=coupon_failure_handle(self,event,request_sequence)
    if coupon_failure_reply is not None:return coupon_failure_reply
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
