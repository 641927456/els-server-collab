"""Finite current Helen exchange; existing1500 authority, native UI retained."""
import sqlite3,struct
from contextlib import closing
from pathlib import Path
from els_server.protocol import fish_exchange_messages as wire
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.storage.fish_exchange import exchange
from els_server.storage.reward_state import validate_balances
from els_server.domain.fishing_village1500 import _identity,_ordinary_binding,_facts

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x223 or len(event.payload)<4 or struct.unpack_from('>i',event.payload)[0]!=40256:return None
    from els_server.domain.town_travel_flow import _ordinary_actor
    if not _ordinary_actor(s) or s.account.characters is None or 0x28 not in s.completed:return []
    from els_server.domain.account_fishing_tasks import actor_binding,current_actor
    try:finite_binding=actor_binding(s)
    except(ValueError,AttributeError,KeyError,TypeError):return []
    actor=s.account;store=actor.store;characters=actor.characters
    root=getattr(actor,'root',None);application=getattr(s,'application',None)
    binding=_ordinary_binding(s);facts=_facts(s)
    def current():
        return bool(current_actor(s,finite_binding) and _ordinary_actor(s) and s.account is actor and actor.store is store
            and actor.characters is characters and getattr(actor,'root',None) is root
            and getattr(s,'application',None) is application and _ordinary_binding(s)==binding
            and _facts(s)==facts)
    def failed():
        # An exception after late encoding may belong to an expired actor or
        # scene. Never read a replacement actor or clear its native UI wait.
        if not current():return []
        with closing(sqlite3.connect(Path(store.path).resolve().as_uri()+'?mode=ro',uri=True))as db:
            row=db.execute('SELECT b.ed,b.experience,b.revision FROM reward_balances b JOIN character_owners o ON o.uid=b.uid WHERE b.uid=? AND o.account_id=?',(binding[2],binding[3])).fetchone()
        answer=[Event(0x201,kind=0x224,payload=wire.acknowledgement(validate_balances(row)['ed'],result=-1))]
        for reply in answer:encode_event(reply)
        return answer if current() else []
    try:
        if not _identity(s,event,sequence)or s.phase!='town_ready'or s.active_map!=1500 or s.account.get_location()['map']!=1500:raise ValueError('Fish exchange current scene/phase')
        def guard(db):
            if not current() or not _identity(s,event,sequence):raise ValueError('Fish exchange actor/source changed')
        return exchange(s.account.store.path,s.account.uid,event.payload,
            s.shop_session_id+':fish-exchange:'+str(s.account.uid)+':'+str(sequence),account_id=s.account.account_id,guard=guard)
    except (ValueError,sqlite3.Error,OverflowError):return failed()
