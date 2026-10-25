"""Finite original Mu FD and current owner guard for35630 EE/F4."""
from els_server.domain.guild_task35630 import source
from els_server.domain.guild_license_flow import reply_capture, guarded_reply
from els_server.protocol import tutorial_dialogue_messages as wire
from els_server.protocol.quest_messages import QUEST_REQUIREMENTS_NOT_MET
from els_server.storage.seal_quests import QuestState


def guarded_store(s):
    captured=source(s)
    def guard(db):
        if source(s)!=captured:raise ValueError('Guild task current actor/source changed')
    return QuestState(s.account.store.path,s.account.uid,account_id=s.account.account_id,
                      account_source_guard=guard)


def dialogue(s,event,sequence):
    try:npc=wire.request(event.payload)
    except ValueError:return None
    if npc!=10045:return None
    reply_guard=reply_capture(s)
    if reply_guard is None:return []
    try:
        if (type(sequence) is not int or not 1<=sequence<2**32 or event.performers!=(0,)
                or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):
            raise ValueError('Guild FD native envelope')
        store=guarded_store(s)
        from els_server.storage.guild_task_dialogue import interact
        operation=s.shop_session_id+':guild-mu:'+str(s.account.uid)+':'+str(sequence)
        result=interact(store,operation,lambda:store.account_source_guard(None))
        return result or guarded_reply(reply_guard,lambda:[wire.acknowledgement()])
    except ValueError:
        return guarded_reply(reply_guard,lambda:[wire.acknowledgement(result=QUEST_REQUIREMENTS_NOT_MET)])
