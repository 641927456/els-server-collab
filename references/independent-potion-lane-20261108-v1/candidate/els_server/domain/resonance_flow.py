"""Native shared ERP sync without duplicate full-unit projections."""
def synchronize(s,messages):
 if s.role!='game' or s.phase not in ('town_ready','dungeon_active') or s.client_build!='dx11_260923' or s.account.store is None or s.account.characters is None:return messages
 from els_server.storage.resonance_state import state
 current=state(s.account.store.path,s.account.uid,s.account.account_id)
 if not current['enabled']:return messages
 from els_server.domain.resonance_allocation_flow import synchronize as allocation_sync
 key=(current['account_id'],current['revision'],s.account.uid)
 answer=allocation_sync(s,messages,current)
 # Native D38470 copies the complete610 scalars to actor+2861..2871,
 # then restores allocations/pages and refreshes the actor. A second full
 # D9 repeats that update and rebuilds unrelated equipment/skills per kill.
 if any(e.event_id==0x201 and e.kind==0x610 for e in answer[len(messages):]):
  s.resonance_sync_key=key
  return answer
 if getattr(s,'resonance_sync_key',None)==key:return answer
 # Existing opaque profiles can reject610 projection. Keep their original
 # absolute scalar sync without provisioning or replacing saved page data.
 notice=s.saved_user_sync(resonance_snapshot=current)
 from els_server.protocol.protocol_codec import encode_event
 encode_event(notice);s.resonance_sync_key=key
 return [*answer,notice]
