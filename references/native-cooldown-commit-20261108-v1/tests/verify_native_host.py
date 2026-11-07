"""Run actual product JS and original join instructions in an owned helper only."""
import hashlib
import json
import subprocess
import sys
import time
from pathlib import Path

W = Path(__file__).resolve().parent
R = Path(json.loads((W / "parent-bindings.json").read_text("utf8"))["runtime"])
sys.path.insert(0, str(R / "tools/pylibs"))
import frida

snapshot = (R / "analysis/client-6c6b5180/x2-runtime.bin").read_bytes()
windows = {r: snapshot[r:r+n].hex() for r, n in ((0x8f4b63, 6), (0x8f4b88, 6), (0x8f4bca, 2), (0x8f4c19, 0x25))}
template = (W / "native_cooldown_host.js").read_text("utf8")
results = {}
for label, product in (("parent", R / "tools/dungeon_result_stats.js"), ("fixed", W / "candidate/tools/dungeon_result_stats.js")):
    raw = product.read_text("utf8")
    # The synthetic module has a harness parent, so identity is checked separately
    # against the real snapshot by verify_source.py, not spoofed in this host.
    source = template.replace("__ORIGINAL_WINDOWS__", json.dumps(windows)).replace("__PRODUCT_SOURCE__", raw.replace("__DUNGEON_RESULT_PINS__", "{}"))
    child = subprocess.Popen([sys.executable, "-I", "-S", "-u", "-c", "import sys;print('owned-cooldown-host-ready',flush=True);sys.stdin.read()"],
                             stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, creationflags=subprocess.CREATE_NO_WINDOW)
    session = script = None
    errors = []
    try:
        assert child.stdout.readline().strip() == "owned-cooldown-host-ready"
        session = frida.attach(child.pid)
        script = session.create_script(source)
        script.on("message", lambda m, d: errors.append(m) if m.get("type") == "error" else None)
        script.load()
        if errors:
            raise RuntimeError(json.dumps(errors))
        result = script.exports_sync.run()
        time.sleep(.1)
        result.update(errors=[m.get("description") for m in errors], product_sha256=hashlib.sha256(product.read_bytes()).hexdigest())
        results[label] = result
        assert result["insertedValue"] == 1.5 and result["existingValue"] == 100.25, result
        if label == "parent":
            assert len(errors) == 4 and all("0xffffffffffffffff" in m.get("description", "") for m in errors), result
        else:
            assert not errors, result
            assert result["skipped"] == {} and result["afterInsert"] == {"2002": 1.5}, result
            assert result["afterSkippedIteration"] == {"2002": 1.5} and result["afterExisting"] == {"2002": 1.75}, result
    finally:
        if script:
            try:
                script.exports_sync.cleanup()
            except frida.RPCException:
                pass
            finally:
                script.unload()
        if session:
            session.detach()
        child.stdin.close()
        try:
            child.wait(timeout=8)
        except subprocess.TimeoutExpired:
            child.terminate()
            child.wait(timeout=8)
        if label in results:
            results[label]["owned_helper_exited"] = child.poll() is not None
record = {"passed": True, "frida_version": frida.__version__, "results": results,
          "scope": "Actual Gum hooks plus original x64 skip/join instructions in isolated synthetic memory; lookup, parent prologue and report writer are explicit fixture shims.",
          "game_process": False, "player_process_attached": False, "physical_input": False,
          "original_instruction_windows": windows, "natural_gameplay_verified": False}
(W / "native-host-verification.json").write_text(json.dumps(record, indent=2) + "\n", "utf8")
print(json.dumps({"passed": True, "parent_errors": len(results["parent"]["errors"]), "fixed_errors": len(results["fixed"]["errors"]), "frida": frida.__version__, "helpers_cleaned": all(r["owned_helper_exited"] for r in results.values())}))
