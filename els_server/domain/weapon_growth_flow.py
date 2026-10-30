"""Native weapon quests: live counters, persistent claim and original UI refresh."""
from els_server.domain.equipment_engrave_flow import current_lease
from els_server.protocol import weapon_growth_messages as wire


def equipped(items):
    from els_server.domain.weapon_growth import templates
    from els_server.domain.equipment_requirements import catalog
    from els_server.game_data import client_data
    slots = catalog()[1]
    for item in items:
        if item['group'] == 9 and item['template'] in templates():
            position = client_data().item(item['template'])['equip_position']
            if item['slot'] == slots.get(position):
                return item['uid']
    return None


def _unit(s, result=None):
    from els_server.protocol.local_messages import character_unit
    from els_server.domain.fashion_state import record
    import struct
    if result is None:
        saved = s.account.get_inventory_snapshot()
        result = dict(character=s.account.character(), slots=s.account.get_skills(),
                      balances=saved['balances'], items=saved['items'])
    unit = character_unit(s.account.get_location(), True, result['slots'],
                          result['balances'], result['items'], result['character'])
    changed = [result['updated']] if result.get('updated') is not None else []
    return unit + struct.pack('>I', len(changed)) + b''.join(record(i) for i in changed) + bytes(5)


def handle(s, event, sequence):
    if event.event_id != 0x202 or event.kind != 0x96c or not s.item_test or s.client_build != 'dx11_260923':
        return None
    quest_id = item_uid = 0
    try:
        quest_id, item_uid, _ = wire.request(event.payload)
        if (not current_lease(s) or s.role != 'game' or s.phase != 'town_ready'
                or s.account.characters is None or s.account.store is None
                or s.account.store.uid != s.account.uid or type(sequence) is not int
                or not 1 <= sequence < 2**32 or event.performers not in ((), (0,))
                or event.uid != 0xffffffffffffffff or event.target_uid != 0xffffffffffffffff
                or event.payload_mode != 0):
            raise ValueError('Weapon growth session envelope')
        actor = (s.account, s.account.store, s.account.uid, s.account.account_id, s.shop_session_id)

        def guard(db):
            current = (s.account, s.account.store, s.account.uid, s.account.account_id, s.shop_session_id)
            if not current_lease(s) or s.phase != 'town_ready' or current != actor:
                raise ValueError('Weapon growth actor changed')

        def encode(result):
            from els_server.protocol.protocol_codec import encode_event
            events = [wire.acknowledge(quest_id, item_uid, _unit(s, result))]
            # The original ACK records completion. The original live update
            # then replaces the active task with the next stage, if any.
            rows = result['state']['item_active']
            if rows:
                events.append(wire.progress(rows))
            for reply in events:
                encode_event(reply)
            return events

        from els_server.storage.weapon_growth import claim
        operation = s.shop_session_id + ':weapon-growth:' + str(s.account.uid) + ':' + str(sequence)
        return claim(s.account.store.path, s.account.uid, s.account.account_id, item_uid,
                     quest_id, operation, encode, guard)['events']
    except ValueError:
        return [wire.acknowledge(quest_id, item_uid, _unit(s), result=2005)]


def observe(s, run, replies):
    if (not current_lease(s) or s.role != 'game' or s.account.store is None
            or s.account.characters is None):
        return []
    if run is None:
        s._weapon_growth_run = None
        return []
    # Capture before the first loaded battle update; once the weapon changes
    # during a run, changing it back cannot restore this run's eligibility.
    identity = (str(s.account.store.path), s.account.uid, run.run_id)
    tracked = getattr(s, '_weapon_growth_run', None)
    inventory_changed = any(reply.kind == 0x105 for reply in replies)
    if tracked is None or tracked['identity'] != identity or inventory_changed:
        selected = equipped(s.account.get_inventory_snapshot()['items'])
        if tracked is None or tracked['identity'] != identity:
            tracked = dict(identity=identity, item_uid=selected, eligible=selected is not None, recorded=False)
            s._weapon_growth_run = tracked
        elif selected != tracked['item_uid']:
            tracked['eligible'] = False
    if (tracked['recorded'] or not tracked['eligible'] or not s.clear_notified
            or not s.reward_test or s.reward_receipt is None):
        return []
    proof = (run.run_id + ':' + run.graph['source_sha256']).encode()
    actor = (s.account, s.account.store, s.account.uid, s.account.account_id, s.shop_session_id)

    def guard(db):
        current = (s.account, s.account.store, s.account.uid, s.account.account_id, s.shop_session_id)
        if (not current_lease(s) or current != actor
                or s._weapon_growth_run is not tracked or not tracked['eligible']):
            raise ValueError('Weapon growth clear actor changed')

    from els_server.storage.weapon_growth import record_clear
    result = record_clear(s.account.store.path, s.account.uid, s.account.account_id,
                          tracked['item_uid'], run.run_id, run.identity, proof, guard)
    tracked['recorded'] = True
    return [wire.progress(result['state']['item_active'])] if result['changed'] else []
