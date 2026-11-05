"""Current Flask envelopes, owner binding and native notification reuse."""
import sqlite3
from els_server.protocol.protocol_codec import Event, encode_event
from els_server.protocol.flask_messages import acknowledgement


def handle(session, event, sequence):
    if event.event_id != 0x202 or event.kind not in (0x707, 0x9ae):
        return None
    try:
        from els_server.domain.manufacture_flow import _actor, _binding, _same_binding
        def context():
            return bool(_actor(session) and type(sequence) is int and 1 <= sequence < 2**32
                        and event.performers in ((), (0,)) and event.uid == event.target_uid == 2**64-1
                        and event.payload_mode == 0)
        if not context():
            raise ValueError('Flask session envelope')
        binding = _binding(session)
        def authorize():
            return bool(context() and _same_binding(session, binding))
        def replay(events):
            return [*events, session.saved_user_sync()]
        from els_server.storage.flask import execute
        result = execute(binding[6], binding[4], binding[5], event.kind, event.payload,
                         f'{binding[7]}:{binding[4]}:flask:{event.kind}:{sequence}',
                         authorize=authorize, prepare_replay=replay)
        return result['events']
    except (ValueError, sqlite3.Error):
        return [Event(0x201, kind=0x708 if event.kind == 0x707 else 0x9af,
                      payload=acknowledgement(event.kind, result=-1))]


def periodic(session):
    """Original 9B0 when cold entering town or its projected state changes."""
    from els_server.domain.manufacture_flow import _actor, _binding, _same_binding
    if not _actor(session):
        session.flask_state_signature = None
        return []
    binding = _binding(session)
    def authorize():
        return bool(_actor(session) and _same_binding(session, binding))
    try:
        from els_server.storage.flask import observe
        wire = observe(binding[6], binding[4], binding[5], authorize=authorize)
        signature = (binding[4], binding[5], binding[6], binding[7], wire)
        if getattr(session, 'flask_state_signature', None) == signature:
            return []
        answer = Event(0x201, kind=0x9b0, payload=wire)
        encode_event(answer)
        if not authorize():
            raise ValueError('Flask notification actor changed')
        session.flask_state_signature = signature
        return [answer]
    except (ValueError, sqlite3.Error):
        return []
