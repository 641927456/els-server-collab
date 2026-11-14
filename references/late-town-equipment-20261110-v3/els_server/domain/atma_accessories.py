"""Verified Atma breath, accessory synthesis and box definitions."""
from functools import lru_cache
from hashlib import sha256
import json
from pathlib import Path

from els_server.game_data import CLIENT_SHA, client_data


@lru_cache(maxsize=1)
def catalog():
    raw = (Path(__file__).resolve().parents[1]/"data/atma_accessories.json").read_bytes()
    if sha256(raw).hexdigest() != "4f40c138f6482224a7f4998a7ad096d12f36f02363e1e0823e1e265fbe4572d2":
        raise ValueError("Atma accessory policy identity")
    data = json.loads(raw)
    if data["client_sha256"] != CLIENT_SHA:
        raise ValueError("Atma accessory client identity")
    client = client_data()
    for row in data["readers"]:
        item = client.item(row["template"])
        if sha256(item["record"]).hexdigest() != row["record_sha256"]:
            raise ValueError("Atma accessory material or box record")
    return data


def input_grade(template):
    return (template-30846)//2 if 30846<=template<=30855 else None
