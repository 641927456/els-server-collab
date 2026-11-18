"""Use the existing owned TLS driver for the new disconnect-only scenario."""
import asyncio
import verify_combined_private as driver
from combined_lifecycle_client import scenario

async def run(identities, snapshot, report, leave):
    await scenario(identities, snapshot, report)

driver.scenario = run
if __name__ == '__main__':
    raise SystemExit(not asyncio.run(driver.main()))
