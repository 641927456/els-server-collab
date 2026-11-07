"""Verify composed pins, error routing and actual UTF-8 child output."""
import ast
import contextlib
import hashlib
import importlib.util
import io
import json
import subprocess
import sys
from pathlib import Path

sys.dont_write_bytecode = True
W = Path(__file__).resolve().parent
R = Path(json.loads((W / "parent-bindings.json").read_text("utf8"))["runtime"])
C = W / "candidate"
snapshot = (R / "analysis/client-6c6b5180/x2-runtime.bin").read_bytes()
checks = []
for path in (C / "tools").glob("*.py"):
    ast.parse(path.read_text("utf8"), filename=str(path))
checks.append("All changed Python sources parse")

sys.path[:0] = [str(R / "tools"), str(R)]
spec = importlib.util.spec_from_file_location("dungeon_result_stats", C / "tools/dungeon_result_stats.py")
module = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = module
spec.loader.exec_module(module)
from native_cache_sync import compose
composed = compose(snapshot, "6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709",
                   (R / "tools/trace_dx11_login.js").read_text("utf8"))
pins = None
for line in composed.splitlines():
    if "pins=" in line and "__DUNGEON_RESULT_PINS__" not in line and "prepareElsDungeonResultStats" not in line:
        try:
            value = json.loads(line.split("pins=", 1)[1].rstrip(";"))
        except (ValueError, IndexError):
            continue
        if str(0x8f4c19) in value:
            pins = value
            break
assert pins and pins[str(0x8f4c19)] == snapshot[0x8f4c19:0x8f4c29].hex()
assert composed.count("module.base.add(0x8f4c19)") == 1
assert composed.count("installElsDungeonResultStats(()=>mainThread") == 1
(W / "hook-pins.json").write_text(json.dumps(pins, indent=2) + "\n", "utf8")
checks.append("Full actual V108 composition succeeds with the new verified native pin")

tree = ast.parse((C / "tools/probe_updated_client.py").read_text("utf8"))
receive = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "receive")
login_receive = next(n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef) and n.name == "receive_native_login")
env = {"json": json, "log": io.StringIO(), "remote_stop_file": None,
       "native_cache_failure": None, "native_script_failure": None}
exec(compile(ast.Module(body=[receive, login_receive], type_ignores=[]), "actual-receivers", "exec"), env)
failure = {"type": "error", "description": "Error: access violation accessing 0xffffffffffffffff"}
env["receive_native_login"](failure, None)
assert env["native_script_failure"] == failure["description"]
assert env["native_cache_failure"] is None
guard = next(n for n in ast.walk(tree) if isinstance(n, ast.If) and isinstance(n.test, ast.Name) and n.test.id == "native_script_failure")
with contextlib.redirect_stdout(io.StringIO()) as output:
    try:
        exec(compile(ast.Module(body=[guard], type_ignores=[]), "actual-script-error-guard", "exec"), env)
    except RuntimeError as error:
        assert str(error) == "Native gameplay support script failed: " + failure["description"]
    else:
        raise AssertionError("A script error must remain an explicit failure")
assert "\u6218\u529b" not in output.getvalue()
assert "ELS_LAUNCH_ERROR: " in output.getvalue()
env["native_script_failure"] = None
env["receive_native_login"]({"type": "send", "payload": {"event": "native_cache_sync_disabled", "reason": "verified-cache-error"}}, None)
assert env["native_cache_failure"] == "verified-cache-error" and env["native_script_failure"] is None
checks.append("Recorded script exception is accurately reported; genuine cache failure stays separate")

launch_tree = ast.parse((C / "tools/launch_client.py").read_text("utf8"))
make = next(n for n in ast.walk(launch_tree) if isinstance(n, ast.FunctionDef) and n.name == "make_command")
flags = next(ast.literal_eval(n.value) for n in launch_tree.body if isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == "COMMON_FLAGS" for t in n.targets))
scope = {"sys": sys, "ROOT": R, "Path": Path, "COMMON_FLAGS": flags}
exec(compile(ast.Module(body=[make], type_ignores=[]), "actual-native-command", "exec"), scope)
command = scope["make_command"](Path("G:/owned-fixture/x2_dx11.exe"))
assert command[1:3] == ["-X", "utf8"]
message = "\u5ba2\u6237\u7aef\u8fd0\u884c\u7ec4\u4ef6\u53d1\u751f\u9519\u8bef"
child = subprocess.run(command[:3] + ["-c", "print(" + repr(message) + ")"], capture_output=True, check=True, creationflags=subprocess.CREATE_NO_WINDOW)
assert child.stdout.decode("utf8").strip() == message
checks.append("The actual nested Python command emits Chinese as valid UTF-8")

bindings = json.loads((W / "parent-bindings.json").read_text("utf8"))
for name, entry in bindings["files"].items():
    assert hashlib.sha256((R / name).read_bytes()).hexdigest() == entry["parent_sha256"]
checks.append("Actually installed runtime is unchanged")
result = {"passed": True, "checks": checks, "game_launched_or_attached": False,
          "composed_source_sha256": hashlib.sha256(composed.encode()).hexdigest()}
(W / "source-verification.json").write_text(json.dumps(result, indent=2) + "\n", "utf8")
print(json.dumps(result))
