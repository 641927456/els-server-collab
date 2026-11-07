"""Original account25600 only; successor and fishing production are separate."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT
QUEST=25600
@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/account_fishing25600.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='5508f11b2224c18a5f745e4a13343e2bf8f7e283ac7add6574ac80a9a07ae41d':raise ValueError('Original25600 source changed')
    return json.loads(raw)
def target(sub):
    if sub!=catalog()['subquests']['25600']:raise ValueError('Original25600 NPC subquest')
    return 1
def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0xfd:return None
    from els_server.protocol import tutorial_dialogue_messages as wire
    from els_server.protocol.quest_messages import QUEST_REQUIREMENTS_NOT_MET
    try:npc=wire.request(event.payload)
    except ValueError:return None
    if npc!=7507:return None
    from els_server.domain.quest_flow import store
    from els_server.domain.account_fishing_tasks import actor_binding,current_actor,actor_guard
    from els_server.protocol.protocol_codec import encode_event
    try:bound=actor_binding(s)
    except(ValueError,AttributeError,KeyError,TypeError):return []
    def failed():
        if not current_actor(s,bound):return []
        answer=[wire.acknowledgement(result=QUEST_REQUIREMENTS_NOT_MET)]
        for reply in answer:encode_event(reply)
        return answer if current_actor(s,bound)else[]
    if (s.phase!='town_ready' or s.active_map!=1500 or s.account.get_location()['map']!=1500
        or type(sequence)is not int or not 1<=sequence<2**32 or event.performers!=(0,)
        or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode!=0):return failed()
    from els_server.storage.account_fishing25600_scope import interact
    actor=store(s);actor.account_source_guard=actor_guard(s,bound)
    try:
        answer=interact(actor,s.shop_session_id+':fishing25600-FD:'+str(s.account.uid)+':'+str(sequence))
        return answer if current_actor(s,bound)else[]
    except ValueError:return failed()
