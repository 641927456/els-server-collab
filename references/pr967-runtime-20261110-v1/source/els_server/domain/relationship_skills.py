"""Independent current couple900 source for native22-slot equipment only.

No ordinary learned/Force grant, effect, HP, cooldown or skill-use simulation.
Requires the strict C9 mutual source snapshot and caller's SQL snapshot.
"""
PERSISTED_IDS=frozenset((900,))


def equipment(character):
    if character is None or character.get('relationship') is None:return ()
    source=character['relationship'];owner=character.get('uid')
    if (type(source)is not dict or set(source)!=set(('pair_id','kind','peer_uid','peer_name','created_at'))
        or type(owner)is not int or not 1001<=owner<2**63
        or type(source['kind'])is not int or source['kind']!=1
        or type(source['peer_uid'])is not int or not 1001<=source['peer_uid']<2**63 or source['peer_uid']==owner
        or type(source['pair_id'])is not str or not 1<=len(source['pair_id'])<=160
        or type(source['peer_name'])is not str or not 1<=len(source['peer_name'])<=24
        or type(source['created_at'])is not int or not 0<source['created_at']<2**63):
        raise ValueError('Independent current couple skill source')
    from els_server.game_data import client_data
    skill=client_data().skill(900)
    if skill['m_eType']!=12 or skill['m_SkillCoolTime'].get('1')!=300:
        raise ValueError('Pinned native couple skill definition')
    return (900,)


def saved(db,owner):
    """Read-only, same SQL snapshot as the owner/slots write or projection.

    Existing strict relationships.snapshot validates reciprocal membership,
    current active actors and immutable original mutual/ring debit producer.
    A legacy character DB without an owner mapping has no relation source.
    """
    if not db.in_transaction:raise ValueError('Couple skill needs caller SQL snapshot')
    if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='character_owners'").fetchone():return None
    row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if row is None:return None
    from els_server.storage.relationships import snapshot
    return snapshot(db,owner,row[0])


def persisted_slots(previous, visible, character, *, touched=()):
    """Retain only an existing, currently dormant900 at an untouched slot.

    The caller first validates/encodes the visible layout against its current
    source. This separate copy is storage-only; it must never become an ACK,
    hot Unit projection or learned/Force source. A122 target is explicit even
    when its incoming value is0. A full filtered layout cannot express that
    intent: its zero leaves the already hidden value unchanged.
    """
    from els_server.domain.role_progression import slot_accepts
    from els_server.domain.skill_expansion import unlocked_indices
    previous=tuple(previous);result=list(visible);touched=tuple(touched)
    if (len(previous)!=22 or len(result)!=22
        or any(type(v)is not int for v in previous)
        or any(type(i)is not int or not 0<=i<22 for i in touched)
        or len(set(touched))!=len(touched)):
        raise ValueError('Dormant relation persistence shape')
    locations=[i for i,s in enumerate(previous)if s in PERSISTED_IDS]
    if len(locations)>1 or any(i not in unlocked_indices(character)or not slot_accepts(i,previous[i])for i in locations):
        raise ValueError('Invalid persisted relation slot')
    if not equipment(character):
        for i in locations:
            if i not in touched and not result[i]:result[i]=previous[i]
    return tuple(result)
