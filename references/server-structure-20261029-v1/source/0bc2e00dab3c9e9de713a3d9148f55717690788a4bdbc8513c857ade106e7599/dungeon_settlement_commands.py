"""Existing native AD/BB consumers, callable inside the caller's reward writer.

No outer LocalSession observers, unrelated feature dispatch or new connection
is entered here. Static dungeon gates remain in the existing dungeon handler;
the legacy El Tree body below is moved verbatim from its original position.
"""
import hashlib
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.local_messages import i32,client_economy_fields


def legacy_dungeon_event(self,event):
    from els_server.domain.local_session import SessionOrderError
    kind=event.kind
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

                stage=population(self.gate_stage,hp_context=getattr(self,'_c1_hp_context',None));allowed_ids=tuple(n['key'] for n in stage['npcs'])

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

                    supply=getattr(self,'_pve_clear_supply',None)
                    if supply is not None and(supply['owner']is not self or supply['transaction']is not getattr(self,'reward_transaction',None)or not supply['transaction'].in_transaction or not getattr(self,'_pve_internal',False)):raise ValueError('Ordinary El Tree original clear writer')
                    gm_experience=supply['experience']if supply is not None else clear_experience(self,LOCAL_CLEAR_EXPERIENCE)

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

                    item_plan=(supply['plan']or None)if supply is not None else ((dungeon_rewards(30000)['clear_items'] or None) if self.item_test else None)

                    receipt=self.account.reward_store.grant(self.reward_run_id,proof,LOCAL_CLEAR_ED,gm_experience,encode_grant,item_plan=item_plan,dungeon_clear=(30000,elapsed),title_economy='clear',attendance_clear=self.activity2026_awards.prepare_clear(supply['original_session']if supply is not None else self) if self.activity2026_awards is not None else None,transaction=getattr(self,'reward_transaction',None),experience_limit=__import__('els_server.domain.legacy_pve_exp',fromlist=['experience_limit']).experience_limit()if supply is not None else None,resonance_source='clear'if supply is not None else None,raid_reward_source=supply['source']if supply is not None else None)

                    self.reward_receipt={'run_id':self.reward_run_id,**receipt}

                    if self.item_test and receipt.get('items') and not self.clear_items_synced:

                        # D3 records real acquisitions in Game+16D8. Send

                        # before C1 constructs the result UI, not on exit.

                        # Refresh counts from storage if recovering a receipt.

                        from els_server.domain.dungeon_drops import pickup_inventory_notice

                        ids={i['uid'] for i in receipt['items']}

                        updates=receipt['items']if supply is not None else [i for i in self.account.get_inventory_snapshot()['items'] if i['uid'] in ids]

                        reply.append(pickup_inventory_notice(updates))

                        self.clear_items_synced=True

                    reply.append(Event(0x201,kind=0xc1,payload=clear_identity_payload(receipt['response'],30000)))

                else:

                    from els_server.domain.dungeon_clear import prototype_clear_notice

                    reply.append(prototype_clear_notice(self.reward_probe,map_id=30000))

                self.clear_notified=True

            if self.population_test and self.gate_stage<2:

                from els_server.domain.dungeon_population import substage

                next_stage=substage(self.gate_stage+1,boss_gauge=self.boss_gauge_test,hp_context=getattr(self,'_c1_hp_context',None))

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
    return None


def _prepared_event(session,event,kind):
    if event.event_id!=0x202 or event.kind!=kind:
        raise ValueError('Prepared dungeon command event')
    if session.dungeon_run is not None:
        from els_server.domain.dungeon_flow import handle
        result=handle(session,event)
    else:
        result=legacy_dungeon_event(session,event)
    return [] if result is None else result


def settle_death(session,event):
    """Use only after the caller's death source and writer admission checks."""
    return _prepared_event(session,event,0xad)


def settle_clear(session,event):
    """Keep original part/final-source gates and reward encoding before commit."""
    return _prepared_event(session,event,0xbb)
