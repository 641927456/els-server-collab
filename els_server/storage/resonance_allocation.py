"""Read-only ERP point allocation for a character's selected page.

The 2026 page store keeps every opened page in
``resonance2026_characters.state_json`` as
``[revision, enabled, selected_page, [[page_id, available_points, [[stat_id, points], ...]], ...]]``.

Combat needs only the *selected* page's non-zero entries. This exposes that
projection without opening a write transaction, re-running the allocation
rules, or importing the page codec (which would pull the catalog in). Missing
tables, disabled profiles and malformed rows all read as "no allocation" so a
partially migrated save can still log in.
"""
import json


def points(db, character, account=None):
    """Return ``{stat_id: points}`` for the character's selected page."""
    try:
        row = db.execute(
            'SELECT account,state_json FROM resonance2026_characters WHERE character=?',
            (character,)).fetchone()
    except Exception:
        return {}
    if row is None:
        return {}
    if account is not None and row[0] != account:
        return {}
    try:
        _, enabled, selected, pages = json.loads(row[1])
    except (TypeError, ValueError):
        return {}
    if enabled is not True:
        return {}
    for page in pages:
        if page[0] == selected:
            return {int(key): int(value) for key, value in page[2] if int(value)}
    return {}
