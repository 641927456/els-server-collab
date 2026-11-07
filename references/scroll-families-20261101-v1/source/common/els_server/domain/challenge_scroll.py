"""Owned native219 scrolls; both challenge categories are approved always open."""
from pathlib import Path
from els_server.protocol.career_messages import use_ack

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x219:return None
    actor=getattr(s,'account',None);store=getattr(actor,'store',None)
    if store is None:return None
    from els_server.storage.challenge_scroll import recognizes,perform
    op=s.shop_session_id+':challenge-scroll:'+str(actor.uid)+':'+str(sequence)
    if not recognizes(store.path,actor.uid,event.payload,op):return None
    from els_server.domain.raid_reward_flow import town
    from els_server.domain.equipment_chip_flow import reset_authority
    try:
        bound=town(s,sequence);path=Path(store.path).resolve()
        def prepare(db):
            reset_authority(s)
            if (town(s,sequence)!=bound or s.account is not actor or actor.store is not store
                or Path(db.execute('PRAGMA database_list').fetchone()[2]).resolve()!=path
                or not db.in_transaction or not {0x28,0x225,0x227}<=s.completed
                or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0
                or getattr(s,'active_challenge',None)is not None or getattr(s,'challenge_deadline',None)is not None):raise ValueError('Challenge reset current town actor')
        return perform(path,actor.uid,actor.account_id,event.payload,op,prepare=prepare)
    except ValueError:return[use_ack(result=2005)]
