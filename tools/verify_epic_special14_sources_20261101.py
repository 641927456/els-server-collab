"""Verify the frozen fourteen-quest source archive without activating it."""

import hashlib
import json
from pathlib import Path

from repository_guard import violations


ROOT = Path(__file__).resolve().parents[1]
ARCHIVE = ROOT / "references/epic-special14-20261031-v1"
FINAL_SHA = "68b174207c48a292bff5acb664696641fe3e892e508d62893fb074984182cd9a"


def digest(data):
    return hashlib.sha256(data).hexdigest()


def archive_file(name):
    path = (ROOT / name).resolve()
    if not path.is_relative_to(ARCHIVE.resolve()):
        raise ValueError(f"Archive path escapes its directory: {name}")
    return path


def main():
    final = ARCHIVE / "candidate-v5.json"
    assert digest(final.read_bytes()) == FINAL_SHA, "Final frozen manifest changed"
    checked = set()
    versions = {}
    for version in ("v3", "v4", "v5"):
        contract = json.loads((ARCHIVE / f"candidate-{version}.json").read_bytes())
        rows = contract["runtime_files"]
        assert len({row["path"] for row in rows}) == len(rows)
        source_set = digest(json.dumps(
            [(row["path"], row["sha256"]) for row in rows],
            separators=(",", ":"),
        ).encode())
        assert source_set == contract["source_set_sha256"], version
        for row in rows:
            path = archive_file(row["source"])
            data = path.read_bytes()
            assert digest(data) == row["sha256"], row["source"]
            assert len(data) == row["size"], row["source"]
            assert path.parent.name == row["sha256"], row["source"]
            if path.suffix == ".py" and path not in checked:
                compile(data, str(path), "exec")
            checked.add(path)
        for row in contract["evidence"]:
            path = archive_file(row["path"])
            assert digest(path.read_bytes()) == row["sha256"], row["path"]
        versions[version] = len(rows)
    assert contract["ready"] and not contract["automatic_deployment"]
    assert not contract["original_EXE_KOM_changed"]
    assert contract["saved_reader_only"] == [22164]
    assert contract["native_exp"] == {"legacy_22164": 399650, "other_thirteen": 0}
    assert len(contract["task_ids"]) == 14 and len(rows) == 66
    privacy = []
    for path in sorted(ARCHIVE.rglob("*")):
        if path.is_file():
            name = path.relative_to(ROOT).as_posix()
            issues = violations(name, path.read_bytes())
            if issues:
                privacy.append({"path": name, "reasons": issues})
    assert not privacy, privacy
    print(json.dumps({"ok": True, "versions": versions,
                      "source_set_sha256": contract["source_set_sha256"],
                      "unique_source_files": len(checked),
                      "privacy_violations": [], "automatic_deployment": False}))


if __name__ == "__main__":
    main()
