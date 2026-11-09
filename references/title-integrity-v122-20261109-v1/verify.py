"""Portable title-integrity source and inert behavior regression; no game assets."""
from pathlib import Path
import copy
import hashlib
import importlib.util
import json
import re
import subprocess
import sys

sys.dont_write_bytecode = True
AREA = Path(__file__).resolve().parent
FIXTURES = AREA / "tests/fixtures"
FILES = {
    "native_title_options.js": (
        "c0fbf0e13d04087ec61bc3cc3627bcb3d667132253de65dc48ec746049086b15",
        "51a443c0eca849569c557fce6737105495e4f8cd941c47a6eebe60875eb1a827"),
    "native_title_options.py": (
        "0db4738688e29a97e07f937dac7800924ad1a7214662a880b1ac4e39eecd05f1",
        "ec7b9c7a82fb9ba2c40f2f1721e2e39906a3993db21cf0f4ff8de6db054def58"),
    "client_compatibility_profiles.json": (
        "7dea9d098dbb7682d932a7b1a0032b4328499cbcfe6a03ffe76f230897f26dc8",
        "521eb77c2b9f9fca0c126c3aa92da88ce5a6d79ef35e7e7282b14bed7a1f98e3"),
}
OLD_PIN_SITES = (0xFE7560, 0x216FE40, 0x2181ED0, 0xB11A90)
NEW_PIN_SITES = OLD_PIN_SITES + (0x36D720, 0x373950, 0x2184560)


def require(condition, message):
    if not condition:
        raise AssertionError(message)


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def baseline(name):
    path = Path(name)
    return FIXTURES / (path.stem + ".v121" + path.suffix)


def verify_sources_and_profile():
    for name, (old, new) in FILES.items():
        require(sha(baseline(name)) == old, "V121 fixture identity: " + name)
        require(sha(AREA / "tools" / name) == new, "V122 source identity: " + name)
    old = json.loads(baseline("client_compatibility_profiles.json").read_bytes())
    new = json.loads((AREA / "tools/client_compatibility_profiles.json").read_bytes())
    require(old["schema_version"] == new["schema_version"] == 1, "Profile schema changed")
    require(len(old["profiles"]) == len(new["profiles"]) == 1, "Expected the single approved profile")
    before, after = old["profiles"][0], new["profiles"][0]
    require(before["id"] == after["id"] == "cn-dx11-6c6b5180", "Profile identity changed")
    require(before["executable_sha256"] == after["executable_sha256"] ==
            "6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709",
            "Executable identity changed")
    require(len(before["artifacts"]) == len(after["artifacts"]) == 60, "Expected 60 bindings")
    expected = copy.deepcopy(old)
    for name in ("native_title_options.js", "native_title_options.py"):
        key = "tools/" + name
        require(before["artifacts"][key] == FILES[name][0], "Unexpected parent title binding")
        expected["profiles"][0]["artifacts"][key] = FILES[name][1]
    require(new == expected, "Profile must change only the two title artifact hashes")
    return {"source_identities": 6, "compatibility_artifacts": 60, "changed_artifact_bindings": 2}


class SyntheticSnapshot:
    """Only supplied contract sites exist; no client image is read or embedded."""
    def __init__(self, sites):
        self.values = {rva: bytes((index * 29 + i * 11 + 3) & 255 for i in range(16))
                       for index, rva in enumerate(sites)}
        self.reads = []

    def __getitem__(self, span):
        require(isinstance(span, slice) and span.step is None, "Expected an ordinary snapshot slice")
        require(span.start in self.values and span.stop == span.start + 16,
                "Composer read outside a declared 16-byte pin")
        self.reads.append(span.start)
        return self.values[span.start]


def load_composer(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def verify_composition():
    candidate = load_composer(AREA / "tools/native_title_options.py", "title_integrity_candidate")
    previous = load_composer(baseline("native_title_options.py"), "title_integrity_baseline")
    template = "function initialize(){\n beforeTitle();\n installElsGuildNativePower();\n afterTitle();\n}\n"
    checks = []
    for label, module, sites in (("baseline", previous, OLD_PIN_SITES),
                                 ("candidate", candidate, NEW_PIN_SITES)):
        snapshot = SyntheticSnapshot(sites)
        result = module.compose(snapshot, template)
        require(snapshot.reads == list(sites), label + " must read each contract site once")
        match = re.search(r"pins=(\{[^\n]+\});", result)
        require(match is not None, label + " did not inject the pin object")
        require(json.loads(match.group(1)) == {str(rva): data.hex() for rva, data in snapshot.values.items()},
                label + " pin content differs from supplied snapshot")
        require("__TITLE_OPTION_PINS__" not in result, label + " left a placeholder")
        require(result.count(" installElsTitleOptionData();") == 1, label + " duplicated initialization")
        require(result.count(" installElsGuildNativePower();") == 1, label + " changed the existing initializer")
        expected_template = template.replace(" installElsGuildNativePower();",
                                             " installElsTitleOptionData();\n installElsGuildNativePower();")
        require(result.endswith("\n" + expected_template), label + " altered surrounding initialization")
        require(result.startswith("function installElsTitleOptionData(){"), label + " omitted the actual JS body")
        checks.append(label + "_pin_injection_and_order")
    for label, malformed in (("missing", "function initialize(){}"),
                              ("duplicate", template + template)):
        snapshot = SyntheticSnapshot(NEW_PIN_SITES)
        try:
            candidate.compose(snapshot, malformed)
        except ValueError as exc:
            require(str(exc) == "Title option initialization anchor", "Unexpected rejection reason")
        else:
            raise AssertionError(label + " anchor was accepted")
        require(not snapshot.reads, label + " anchor rejection must precede snapshot access")
        checks.append(label + "_anchor_rejected")
    return {"checks": checks, "candidate_pin_count": 7, "baseline_pin_count": 4,
            "snapshot": "synthetic contract bytes only"}


def main():
    sources = verify_sources_and_profile()
    composition = verify_composition()
    node = subprocess.run(["node", str(AREA / "tests/test_title_integrity.js")],
                          cwd=AREA, check=True, capture_output=True, text=True, encoding="utf8", timeout=60)
    behavior = json.loads(node.stdout)
    require(behavior["passed"] is True and behavior["case_count"] == 26 and
            behavior["baseline_expected_failure"] is True, "Complete JS behavior regression did not pass")
    require(behavior["candidate"]["sha256"] == FILES["native_title_options.js"][1] and
            behavior["baseline"]["sha256"] == FILES["native_title_options.js"][0],
            "JS regression read a different source")
    print(json.dumps({"passed": True, "sources": sources, "composition": composition,
                      "js_behavior_cases": behavior["case_count"], "baseline_expected_failure": True,
                      "limits": ["Synthetic checksum oracle and mocked native refresh contract.",
                                 "No client image, native execution, game run or stability acceptance.",
                                 "This isolated source package does not replace the repository's legacy root profile."]},
                     ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
