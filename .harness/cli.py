#!/usr/bin/env python3
"""Portable CLI and Claude hook adapter; never calls a model API or reads credentials."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

from core import (HarnessError, gate_reasons, load_config, project_root, read_state,
                  review, route, run_check, selection, snapshot, start, transition)
from guard import inspect


def emit(data):
    print(json.dumps(data, ensure_ascii=False, indent=2))


def hook(event):
    try:
        payload = json.load(sys.stdin)
        if not isinstance(payload, dict):
            raise HarnessError("Hook input must be an object")
        # Wrapper location is stable even when the agent cd's into a subdirectory.
        root = project_root(Path(__file__).resolve().parent.parent)
        session = os.environ.get("HARNESS_SESSION_ID") or payload.get("session_id")
        if event == "guard":
            inspect(root, payload)
        elif event == "start":
            start(root, session, os.environ.get("HARNESS_PROFILE", "full"))
        else:
            reasons = gate_reasons(root, read_state(root, session))
            if reasons:
                emit({"decision": "block", "reason": "; ".join(reasons) +
                      ". Fix the checks, or record BLOCKED/STUCK with a concrete reason and report incomplete work."})
        return 0
    except (HarnessError, OSError, ValueError, TypeError, KeyError) as exc:
        # Invalid payloads and Git failures must never silently approve an action.
        if event == "stop":
            emit({"decision": "block", "reason": "Harness validation unavailable: " + str(exc)})
            return 0
        print("[harness] " + str(exc), file=sys.stderr)
        return 2


def parser():
    result = argparse.ArgumentParser(description=__doc__)
    result.add_argument("--root", default=str(Path(__file__).resolve().parent.parent))
    result.add_argument("--session", default=os.environ.get("HARNESS_SESSION_ID", "manual"))
    sub = result.add_subparsers(dest="action", required=True)
    sub.add_parser("doctor")
    init = sub.add_parser("start")
    init.add_argument("--profile", choices=("light", "full"), default="full")
    routes = sub.add_parser("route")
    routes.add_argument("--inventory", required=True)
    routes.add_argument("--runtime", help="A runtime registered in .harness/config.json")
    routes.add_argument("--launch", action="store_true")
    run = sub.add_parser("run")
    run.add_argument("kind", choices=("test", "build", "smoke"))
    change = sub.add_parser("transition")
    change.add_argument("phase")
    change.add_argument("--reason", default="")
    report = sub.add_parser("review")
    report.add_argument("--kind", choices=("plan", "code"), default="code")
    report.add_argument("--verdict", choices=("PASS", "FIX", "REJECT"), required=True)
    report.add_argument("--summary", required=True)
    report.add_argument("--actor", required=True)
    report.add_argument("--mode", choices=("independent", "sequential"), default="independent")
    check = sub.add_parser("check")
    check.add_argument("--all", action="store_true", help="Require verification even when baseline has no changes")
    sub.add_parser("status")
    hooks = sub.add_parser("hook")
    hooks.add_argument("event", choices=("start", "guard", "stop"))
    return result


def main(argv=None):
    args = parser().parse_args(argv)
    if args.action == "hook":
        return hook(args.event)
    try:
        if sys.version_info < (3, 11):
            raise HarnessError("Python 3.11 or later is required")
        root = project_root(args.root)
        config = load_config(root)
        if args.action == "doctor":
            fingerprint = snapshot(root)
            emit({"ok": True, "root": str(root), "python": sys.version.split()[0],
                  "fingerprint": fingerprint, "commands": config["commands"],
                  "model_policy": config["models"]["policy"]})
        elif args.action == "start":
            emit(start(root, args.session, args.profile))
        elif args.action == "route":
            inventory = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
            selected = route(root, args.session, inventory, args.runtime)
            emit(selected)
            if args.launch:
                if not selected["launch_argv"]:
                    raise HarnessError("This runtime uses native model selection; apply the selected model in its UI")
                api_env = {"claude": ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"),
                           "codex": ("OPENAI_API_KEY", "CODEX_API_KEY"),
                           "gemini": ("GEMINI_API_KEY", "GOOGLE_API_KEY", "GOOGLE_GENAI_USE_VERTEXAI")}
                if any(os.environ.get(name) for name in api_env.get(selected["runtime"], ())):
                    raise HarnessError("API billing environment detected; verify subscription authentication before launching")
                env = dict(os.environ, HARNESS_SESSION_ID=args.session)
                return subprocess.run(selected["launch_argv"], cwd=root, env=env, check=False).returncode
        elif args.action == "run":
            evidence = run_check(root, args.session, args.kind)
            emit(evidence)
            return 0 if evidence["passed"] else 1
        elif args.action == "transition":
            emit(transition(root, args.session, args.phase, args.reason))
        elif args.action == "review":
            emit(review(root, args.session, args.verdict, args.summary, args.actor, args.kind, args.mode))
        elif args.action == "check":
            reasons = gate_reasons(root, read_state(root, args.session), args.all)
            emit({"ok": not reasons, "reasons": reasons})
            return 1 if reasons else 0
        else:
            emit(read_state(root, args.session))
        return 0
    except (HarnessError, OSError, ValueError) as exc:
        print("[harness] " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
