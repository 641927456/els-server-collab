"""Exact existing expiry economic/rollback cases; no private trace dependency."""
import unittest
import test_item_expiration as fixture


def load_tests(loader,tests,pattern):
    return unittest.TestSuite([
        fixture.ExpirationTests('test_grant_reopen_stacks_and_expiration_atomicity'),
        fixture.ExpirationTests('test_offline_expired_equipment_cleans_dependent_rows_without_duplicate_receipts')])
