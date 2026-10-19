"""Seed pre-policy inventory for compatibility tests only.

These tests exercise moving/repairing/enchanting items already owned before
legacy acquisition was disabled. New-acquisition tests must use grant_items.
"""
from unittest.mock import patch
from els_server.storage.inventory_state import grant_items


def seed_existing_items(db, plan, owner=1001):
    with patch('els_server.domain.acquisition_policy.require_acquirable'):
        return grant_items(db, plan, owner)
