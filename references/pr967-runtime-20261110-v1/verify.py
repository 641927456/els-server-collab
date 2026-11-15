"""Verify the archived source and the isolated quest catalog recovery."""
import hashlib
import json
from pathlib import Path

ARCHIVE = Path(__file__).resolve().parent
ROOT = ARCHIVE.parents[1]


def checked_files(entries, directory):
    expected = set()
    for entry in entries:
        path = ROOT / entry["path"]
        assert path.resolve().is_relative_to(directory), path
        data = path.read_bytes()
        assert len(data) == entry["size"], path
        assert hashlib.sha256(data).hexdigest() == entry["sha256"], path
        expected.add(path)
    assert len(expected) == len(entries)
    assert {path for path in directory.rglob("*") if path.is_file()} == expected


def load_catalog(directory):
    path = directory / "els_server/data/story_quests.json"
    raw = path.read_bytes()
    catalog = json.loads(raw)
    manifest = json.loads(path.with_suffix(".manifest.json").read_bytes())
    assert manifest["payload_sha256"] == hashlib.sha256(raw).hexdigest()
    assert manifest["quests"] == len(catalog["quests"])
    assert manifest["subquests"] == len(catalog["subquests"])
    return catalog


def main():
    manifest = json.loads((ARCHIVE / "archive-files.json").read_bytes())
    files = manifest["files"]
    recovery = manifest["quest_32080_recovery"]["files"]
    checked_files(files, ARCHIVE / "source")
    checked_files(recovery, ARCHIVE / "recovery")

    original = load_catalog(ARCHIVE / "source")
    restored = load_catalog(ARCHIVE / "recovery")
    quest = restored["quests"].pop("32080")
    step = restored["subquests"].pop("32080")
    assert quest["m_iID"] == step["m_iID"] == 32080
    assert quest["m_vecSubQuest"]["1"] == 32080
    reward = quest["Reward"]["m_vecItem"]["1"]
    assert (reward["m_iItemID"], reward["m_iQuantity"]) == (481315, 1)
    rewards = restored["reward_definitions"]
    definition, = (row for row in rewards if row["template"] == 481315)
    rewards.remove(definition)
    assert restored == original

    print(json.dumps({"ok": True, "archived_files": len(files), "restored_quest": 32080}))


if __name__ == "__main__":
    main()
