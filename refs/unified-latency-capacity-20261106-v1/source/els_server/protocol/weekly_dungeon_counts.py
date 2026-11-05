"""861 facade: one SQL view for normal daily and Silver weekly counts."""
import time
def notification(db,owner):
    from els_server.storage.bank_state import account_for
    from els_server.storage.ariel_attendance import clock
    from els_server.storage.ariel_daily_special import notification as complete
    if not db.in_transaction:raise ValueError('Complete weekly map requires one SQL view')
    return complete(db,account_for(db,owner),owner,clock(time.time))
