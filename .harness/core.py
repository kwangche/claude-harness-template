"""Provider-neutral validation evidence and workflow state. Python 3.11+, stdlib only."""
from __future__ import annotations

import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import signal
import stat
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone


class HarnessError(Exception):
    pass


def now():
    return datetime.now(timezone.utc).isoformat()


def digest(data):
    return hashlib.sha256(data).hexdigest()


def git(root, *args):
    try:
        env = {key: value for key, value in os.environ.items()
               if key not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_COMMON_DIR")}
        result = subprocess.run(
            ["git", "-C", str(root), *args], capture_output=True, timeout=15, env=env
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise HarnessError("Git could not run; validation is unavailable") from exc
    if result.returncode:
        raise HarnessError("Git inspection failed; initialize or repair the repository")
    return result.stdout


def project_root(path):
    return Path(os.fsdecode(git(Path(path).resolve(), "rev-parse", "--show-toplevel")).strip()).resolve()


def contained(root, target):
    try:
        return os.path.commonpath([os.path.normcase(str(root.resolve())),
                                   os.path.normcase(str(target.resolve()))]) == os.path.normcase(str(root.resolve()))
    except (ValueError, OSError):
        return False


def validation_file(name):
    path = name.replace("\\", "/")
    if path.startswith(".harness/local/") or path == "docs/STATUS.md":
        return False
    if path.startswith((".harness/", ".claude/", ".codex/", ".github/")):
        return True
    if path in ("AGENTS.md", "CLAUDE.md", "GEMINI.md"):
        return True
    return Path(path).suffix.lower() not in (".md", ".txt", ".rst")


def snapshot(root):
    """Hash current content, including ignored tracked files, deletions, modes and symlinks.

    Deliberately independent of HEAD: committing cannot erase pending validation.
    NUL-delimited Git output preserves Unicode, spaces and unusual filenames.
    """
    names = set(os.fsdecode(name) for name in git(
        root, "ls-files", "--cached", "--others", "--exclude-standard", "-z"
    ).split(b"\0") if name)
    files = {}
    for name in sorted(names):
        if not validation_file(name):
            continue
        path = root / name
        try:
            info = path.lstat()
            if path.is_symlink():
                content = b"symlink\0" + os.fsencode(os.readlink(path))
            elif stat.S_ISREG(info.st_mode):
                if not contained(root, path):
                    raise HarnessError("A tracked file resolves outside the project")
                content = str(stat.S_IMODE(info.st_mode)).encode() + b"\0" + path.read_bytes()
            else:
                raise HarnessError("Unsupported file type or submodule; validate it separately")
        except FileNotFoundError:
            content = b"deleted\0"
        files[name] = digest(content)
    return digest(json.dumps(files, sort_keys=True, ensure_ascii=True).encode())


def load_config(root):
    try:
        config = json.loads((root / ".harness/config.json").read_text(encoding="utf-8"))
        if config["version"] != 1:
            raise ValueError("unsupported version")
        if not isinstance(config["runtimes"], dict) or not config["runtimes"]:
            raise ValueError("at least one runtime adapter is required")
        for runtime, adapter in config["runtimes"].items():
            if not re.fullmatch(r"[a-z][a-z0-9_-]*", runtime):
                raise ValueError("invalid runtime adapter name")
            argv = adapter["launch_argv"]
            if not isinstance(argv, list) or any(not isinstance(x, str) or not x for x in argv):
                raise ValueError("launch_argv must be an argv array; empty means native UI only")
            if argv and "{model}" not in argv:
                raise ValueError("a launch adapter must pass the selected model explicitly")
        for field in ("command_timeout_seconds", "session_timeout_seconds", "max_operations",
                      "max_plan_reviews", "max_refinements", "max_parallel_workers"):
            value = config["budgets"][field]
            if type(value) is not int or value < 1:
                raise ValueError("budgets must be positive integers")
        for kind in ("test", "build", "smoke"):
            argv = config["commands"][kind]
            if not isinstance(argv, list) or any(not isinstance(x, str) or not x for x in argv):
                raise ValueError("commands must be argv arrays")
        if not config["commands"]["test"]:
            raise ValueError("a test command is required")
        if config["models"]["policy"] != "best_available_subscription":
            raise ValueError("unsupported model policy")
        if type(config["models"]["inventory_max_age_hours"]) is not int or config["models"]["inventory_max_age_hours"] < 1:
            raise ValueError("inventory expiry must be positive")
        if config["models"]["allow_api_billing"] is not False:
            raise ValueError("this template only launches subscription sessions")
        if type(config["review"]["required"]) is not bool or type(config["review"]["require_independent"]) is not bool:
            raise ValueError("review switches must be booleans")
        return config
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HarnessError("Invalid .harness/config.json: " + str(exc)) from exc


def local_dir(root):
    path = root / ".harness/local"
    if not contained(root, path):
        raise HarnessError("Runtime directory must stay inside this repository")
    path.mkdir(parents=True, exist_ok=True)
    return path


def session_path(root, session):
    if not isinstance(session, str) or not session.strip():
        raise HarnessError("A nonempty session ID is required")
    return local_dir(root) / (digest(session.encode()) + ".json")


def read_state(root, session):
    path = session_path(root, session)
    try:
        if path.is_symlink() or not contained(root, path):
            raise ValueError("runtime record escapes the project")
        data = json.loads(path.read_text(encoding="utf-8"))
        if data["version"] != 1 or data["session"] != session or data["root"] != str(root):
            raise ValueError("session identity mismatch")
        if data["phase"] not in TRANSITIONS or not isinstance(data["evidence"], dict):
            raise ValueError("invalid session state")
        return data
    except (OSError, ValueError, KeyError, TypeError) as exc:
        raise HarnessError("Session unavailable; run start before editing, or resume the original session ID") from exc


def atomic_json(path, data):
    if path.is_symlink():
        raise HarnessError("Refusing a symlinked runtime record")
    fd, name = tempfile.mkstemp(dir=path.parent, prefix=".write-")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as handle:
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        # Windows scanners can briefly hold the previous record without delete-sharing.
        deadline = time.monotonic() + 2
        while True:
            try:
                os.replace(name, path)
                break
            except PermissionError:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)
    finally:
        if os.path.exists(name):
            os.unlink(name)


@contextlib.contextmanager
def session_lock(root, session):
    path = session_path(root, session).with_suffix(".lock")
    deadline = time.monotonic() + 5
    while True:
        try:
            fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
            break
        except FileExistsError:
            if time.monotonic() > deadline:
                raise HarnessError("Session busy; wait for the active worker. See recovery docs for stale locks")
            time.sleep(0.05)
    try:
        os.close(fd)
        yield
    finally:
        path.unlink()


def write_state(root, state):
    """The commander owns STATUS; workers only return reports."""
    status = root / "docs/STATUS.md"
    if not contained(root, status) or status.is_symlink():
        raise HarnessError("STATUS must be a regular file inside the project")
    status.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = now()
    route = state.get("routing")
    selected = (route["runtime"] + "/" + route["model"]) if route else "NOT_SELECTED (run route)"
    lines = ["# STATUS", "", "Generated by .harness/cli.py; do not edit by hand.", "",
             "## Current session", state["session"], "", "## Phase", state["phase"], "",
             "## Commander", selected, "", "## Updated (UTC)", state["updated_at"], "",
             "## Next action", state.get("reason") or "Follow docs/WORKFLOW.md", "",
             "## Verification", json.dumps(state.get("evidence", {}), ensure_ascii=False, sort_keys=True), "",
             "## Review", json.dumps(state.get("review"), ensure_ascii=False), "",
             "## History"]
    lines += ["- " + entry for entry in state.get("history", [])[-30:]]
    status.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    state["status_hash"] = digest(status.read_bytes())
    atomic_json(session_path(root, state["session"]), state)


def start(root, session, profile="full"):
    if profile not in ("light", "full"):
        raise HarnessError("Profile must be light or full")
    load_config(root)
    with session_lock(root, session):
        if session_path(root, session).exists():
            return read_state(root, session)  # resume never resets the baseline
        state = {"version": 1, "session": session, "root": str(root), "profile": profile,
                 "phase": "PLANNING", "baseline": snapshot(root), "started_at": now(),
                 "operations": 0, "plan_reviews": 0, "refinements": 0,
                 "evidence": {}, "review": None, "routing": None, "history": [now() + " PLANNING"]}
        write_state(root, state)
        return state


def budget(state, config):
    elapsed = (datetime.now(timezone.utc) - datetime.fromisoformat(state["started_at"])).total_seconds()
    if elapsed > config["budgets"]["session_timeout_seconds"]:
        raise HarnessError("Session time budget reached; record STUCK with a reason before stopping")
    if state["operations"] >= config["budgets"]["max_operations"]:
        raise HarnessError("Operation budget reached; record STUCK with a reason before stopping")
    state["operations"] += 1


def selection(config, inventory, runtime=None):
    """Select only observed subscription entitlements, never a guessed model ID."""
    try:
        observed = datetime.fromisoformat(inventory["observed_at"].replace("Z", "+00:00"))
        if observed.tzinfo is None:
            raise ValueError("observation requires a timezone")
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age < -300 or age > config["models"]["inventory_max_age_hours"] * 3600:
            raise ValueError("model inventory is stale or future-dated")
        if inventory["version"] != 1 or not inventory["source"].strip():
            raise ValueError("inventory requires version and observation source")
        candidates = []
        seen = set()
        for item in inventory["models"]:
            key = (item["runtime"], item["id"])
            if key in seen:
                raise ValueError("duplicate model identity")
            seen.add(key)
            if item["runtime"] not in config["runtimes"] or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+\-]{0,255}", item["id"]):
                raise ValueError("invalid runtime or model ID")
            if type(item["capability_rank"]) is not int or item["capability_rank"] < 0:
                raise ValueError("rank must be a nonnegative integer based on observed capabilities")
            if not isinstance(item["rank_reason"], str) or not item["rank_reason"].strip():
                raise ValueError("each capability rank requires a rationale")
            if item["available"] is True and item["billing"] == "subscription" and item["supports_tools"] is True:
                if runtime is None or item["runtime"] == runtime:
                    candidates.append(item)
        pin = config["models"].get("commander_pin")
        if pin:
            candidates = [m for m in candidates if m["runtime"] + "/" + m["id"] == pin]
        if not candidates:
            raise ValueError("no verified subscription model is available; refresh inventory, do not downgrade silently")
        chosen = sorted(candidates, key=lambda m: (-m["capability_rank"], m["runtime"], m["id"]))[0]
        return {"runtime": chosen["runtime"], "model": chosen["id"], "selected_at": now(),
                "observed_at": inventory["observed_at"], "source": inventory["source"],
                "rank_reason": chosen["rank_reason"], "billing": "subscription",
                "policy": "explicit_pin" if pin else "best_available_subscription",
                "launch_argv": [chosen["id"] if arg == "{model}" else arg
                                for arg in config["runtimes"][chosen["runtime"]]["launch_argv"]]}
    except (KeyError, TypeError, ValueError, AttributeError) as exc:
        raise HarnessError("Invalid model inventory: " + str(exc)) from exc


def route(root, session, inventory, runtime=None):
    with session_lock(root, session):
        config = load_config(root)
        state = read_state(root, session)
        budget(state, config)
        state["routing"] = selection(config, inventory, runtime)
        state["history"].append(now() + " commander selected")
        write_state(root, state)
        return state["routing"]


def execute(argv, root, log, timeout):
    """No shell. Capture output in an ignored log and stop descendants on timeout."""
    if log.is_symlink() or not contained(root, log):
        raise HarnessError("Log file must stay inside the project")
    with log.open("wb") as output:
        kwargs = {"cwd": root, "stdout": output, "stderr": subprocess.STDOUT, "stdin": subprocess.DEVNULL}
        if os.name == "nt":
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP
        else:
            kwargs["start_new_session"] = True
        try:
            process = subprocess.Popen(argv, **kwargs)
        except OSError as exc:
            output.write(str(exc).encode())
            return 127
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            if os.name == "nt":
                try:
                    subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
                except (OSError, subprocess.TimeoutExpired):
                    pass
                # Sandboxed hosts may deny taskkill while allowing termination via
                # the original child process handle. Always reap our direct child.
                if process.poll() is None:
                    process.kill()
            else:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
            process.wait(timeout=15)
            return 124


def run_check(root, session, kind):
    if kind not in ("test", "build", "smoke"):
        raise HarnessError("Unknown check")
    with session_lock(root, session):
        config = load_config(root)
        state = read_state(root, session)
        budget(state, config)
        argv = [sys.executable if x == "{python}" else x for x in config["commands"][kind]]
        if not argv:
            raise HarnessError("No command configured for " + kind)
        before = snapshot(root)
        # Persist invalidation before launching: a crash cannot retain an old PASS.
        state["evidence"].pop(kind, None)
        write_state(root, state)
        log = local_dir(root) / (digest(session.encode()) + "-" + kind + ".log")
        code = execute(argv, root, log, config["budgets"]["command_timeout_seconds"])
        after = snapshot(root)
        record = {"fingerprint": after, "command": argv, "exit_code": code,
                  "passed": code == 0 and before == after, "completed_at": now(),
                  "log": str(log.relative_to(root))}
        state["evidence"][kind] = record
        state["history"].append(now() + " " + kind + " " + ("PASS" if record["passed"] else "FAIL"))
        write_state(root, state)
        return record


def review(root, session, verdict, summary, actor, kind="code", mode="independent"):
    if verdict not in ("PASS", "FIX", "REJECT") or kind not in ("plan", "code") or mode not in ("independent", "sequential"):
        raise HarnessError("Invalid review result")
    if not summary.strip() or not actor.strip():
        raise HarnessError("Review requires a named actor and substantive summary")
    with session_lock(root, session):
        config = load_config(root)
        state = read_state(root, session)
        budget(state, config)
        if kind == "plan":
            if state["phase"] != "PLANNING":
                raise HarnessError("Plan reviews are only accepted during PLANNING")
            if state["plan_reviews"] >= config["budgets"]["max_plan_reviews"]:
                raise HarnessError("Plan review budget reached; record STUCK and revise the task scope")
            state["plan_reviews"] += 1
            plan = root / "docs/PLAN.md"
            if not plan.is_file() or not contained(root, plan):
                raise HarnessError("Write docs/PLAN.md before requesting a plan review")
            state["plan_review"] = {"verdict": verdict, "summary": summary, "actor": actor,
                                    "plan_hash": digest(plan.read_bytes())}
            if verdict != "PASS" and state["plan_reviews"] >= config["budgets"]["max_plan_reviews"]:
                state["phase"], state["reason"] = "STUCK", "Plan review limit: " + summary
        else:
            if state["phase"] != "REVIEWING":
                raise HarnessError("Code reviews are only accepted during REVIEWING")
            state["review"] = {"verdict": verdict, "summary": summary, "actor": actor,
                               "mode": mode, "fingerprint": snapshot(root), "completed_at": now()}
            if verdict != "PASS":
                if state["refinements"] >= config["budgets"]["max_refinements"]:
                    state["phase"], state["reason"] = "STUCK", "Refinement limit: " + summary
                else:
                    state["refinements"] += 1
                    state["phase"] = "REFINING"
        state["history"].append(now() + " " + kind + " review " + verdict)
        write_state(root, state)
        return state


def routing_reasons(state, config):
    route = state.get("routing")
    if not route:
        return ["Commander not selected: run route with a verified model inventory"]
    try:
        observed = datetime.fromisoformat(route["observed_at"].replace("Z", "+00:00"))
        age = (datetime.now(timezone.utc) - observed).total_seconds()
        if age < -300 or age > config["models"]["inventory_max_age_hours"] * 3600:
            return ["Commander inventory expired; refresh observed entitlements and run route again"]
    except (ValueError, KeyError, TypeError):
        return ["Commander observation is invalid; refresh inventory"]
    return []


def gate_reasons(root, state, require_all=False):
    config = load_config(root)
    reasons = []
    status = root / "docs/STATUS.md"
    if not status.is_file() or digest(status.read_bytes()) != state.get("status_hash"):
        reasons.append("STATUS does not match this session; use transition to refresh it")
    if state["phase"] in ("STUCK", "BLOCKED"):
        if not state.get("reason", "").strip():
            reasons.append("A stopped task requires an explicit reason")
        if require_all:
            reasons.append("Task is incomplete: " + state["phase"])
        return reasons  # honest failure reports may stop; this is never DONE
    fingerprint = snapshot(root)
    if not require_all and fingerprint == state["baseline"]:
        return reasons
    reasons.extend(routing_reasons(state, config))
    for kind in ("test", "build", "smoke"):
        if not config["commands"][kind]:
            continue
        evidence = state["evidence"].get(kind, {})
        expected = [sys.executable if x == "{python}" else x for x in config["commands"][kind]]
        if not (evidence.get("passed") is True and evidence.get("exit_code") == 0
                and evidence.get("fingerprint") == fingerprint and evidence.get("command") == expected):
            reasons.append("Run configured " + kind + " successfully on the current files")
    if config["review"]["required"]:
        result = state.get("review") or {}
        if result.get("verdict") != "PASS" or result.get("fingerprint") != fingerprint:
            reasons.append("Current changes require a recorded PASS review")
        elif config["review"]["require_independent"] and result.get("mode") != "independent":
            reasons.append("This project requires an independent reviewer")
    return reasons


TRANSITIONS = {
    "PLANNING": {"PLANNED"}, "PLANNED": {"EXECUTING", "PLANNING"},
    "EXECUTING": {"TESTING"}, "TESTING": {"REVIEWING", "REFINING"},
    "REVIEWING": {"DONE", "REFINING"}, "REFINING": {"EXECUTING", "PLANNING"},
    "BLOCKED": {"PLANNING", "EXECUTING"}, "STUCK": {"PLANNING"}, "DONE": set(),
}


def transition(root, session, phase, reason=""):
    with session_lock(root, session):
        config = load_config(root)
        state = read_state(root, session)
        if phase not in TRANSITIONS:
            raise HarnessError("Unknown workflow phase")
        if phase in ("STUCK", "BLOCKED"):
            if not reason.strip():
                raise HarnessError("Stopping requires a concrete reason")
        else:
            budget(state, config)
            allowed = TRANSITIONS[state["phase"]].copy()
            if state["phase"] == "PLANNING" and state["profile"] == "light":
                allowed.add("EXECUTING")
            if phase not in allowed:
                raise HarnessError("Invalid phase transition: " + state["phase"] + " -> " + phase)
            if phase == "PLANNED" and (state.get("plan_review") or {}).get("verdict") != "PASS":
                raise HarnessError("A full plan needs a PASS review before execution")
            if phase == "PLANNED" or (phase == "EXECUTING" and state["profile"] == "full"):
                plan = root / "docs/PLAN.md"
                result = state.get("plan_review") or {}
                if not plan.is_file() or result.get("verdict") != "PASS" or result.get("plan_hash") != digest(plan.read_bytes()):
                    raise HarnessError("Plan changed or was not approved; review the current plan")
            if phase == "EXECUTING":
                reasons = routing_reasons(state, config)
                if reasons:
                    raise HarnessError("; ".join(reasons))
            if phase == "REFINING":
                if state["refinements"] >= config["budgets"]["max_refinements"]:
                    raise HarnessError("Refinement budget reached; record STUCK")
                state["refinements"] += 1
            if phase == "DONE":
                reasons = gate_reasons(root, state, require_all=True)
                if reasons:
                    raise HarnessError("; ".join(reasons))
        state["phase"], state["reason"] = phase, reason
        state["history"].append(now() + " " + phase + (": " + reason if reason else ""))
        write_state(root, state)
        return state
