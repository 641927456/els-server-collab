"""Close original Cartridge waits without inventing unverified transactions."""
from els_server.protocol.equipment_cartridge_messages import REQUEST_ACKS, unavailable


def handle(session, event):
    if (event.event_id != 0x202 or event.kind not in REQUEST_ACKS
            or session.client_build != 'dx11_260923'
            or session.role != 'game'):
        return None
    # No database access, collection reset, debit, receipt, or success response.
    # Invalid envelopes/phases/payloads receive the same information-free failure.
    return [unavailable(event.kind)]
