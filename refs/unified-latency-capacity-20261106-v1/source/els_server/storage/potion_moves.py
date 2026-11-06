"""Compatibility entry for group-6 moves; shared implementation is bag_moves."""
from els_server.storage.bag_moves import move_bag_items, positions as bag_positions


def positions(payload):
    source, destination = bag_positions(payload)
    if source[0] != 6:
        raise ValueError("Unsupported potion move")
    return source, destination


def move_potions(path, payload, uid=1001):
    positions(payload)
    return move_bag_items(path, payload, uid)
