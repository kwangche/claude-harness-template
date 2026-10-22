"""Supplemental hook guard. Native permissions/sandbox remain the security boundary."""
from __future__ import annotations

import re
import shlex
from pathlib import Path

from core import HarnessError, contained


def sensitive(path):
    parts = [p.casefold() for p in re.split(r"[\\/]", str(path))]
    for part in parts:
        if part == ".git":
            return True
        if part in (".env.example", ".env.sample", ".env.template"):
            continue
        if part == ".env" or part.startswith(".env."):
            return True
        if re.fullmatch(r"(?:id_rsa|id_ed25519)(?:\..*)?|secrets?\.(?:json|ya?ml|toml)", part):
            return True
        if part.endswith((".pem", ".key", ".p12", ".pfx")):
            return True
    return False


def path_check(root, cwd, value, write=False):
    if not isinstance(value, str) or not value:
        raise HarnessError("An explicit file path is required")
    if sensitive(value):
        raise HarnessError("Sensitive file access is blocked")
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = cwd / candidate
    if sensitive(candidate) or sensitive(candidate.resolve()):
        raise HarnessError("Sensitive file access is blocked")
    if write and not contained(root, candidate):
        raise HarnessError("Writes must stay inside the project, including symlink targets")
    if write and contained(root / ".harness/local", candidate):
        raise HarnessError("Use the harness CLI to update runtime evidence")


def command_check(root, cwd, command):
    if not isinstance(command, str) or not command.strip():
        raise HarnessError("An explicit command is required")
    # Parsing shell programs is outside this guard's remit. Reject obvious indirection;
    # run project scripts under native permissions/sandbox rather than promising isolation.
    if re.search(r"`|\$\(|\$\{|%[A-Za-z_][A-Za-z0-9_]*%", command):
        raise HarnessError("Dynamic shell expansion requires a reviewed project script")
    lexer = shlex.shlex(command, posix=True, punctuation_chars=";&|<>()")
    lexer.whitespace_split = True
    lexer.escape = ""  # preserve Windows path separators
    lexer.commenters = ""
    try:
        tokens = list(lexer)
    except ValueError as exc:
        raise HarnessError("Cannot safely parse this command") from exc
    lowered = [t.casefold() for t in tokens]
    # A token may itself contain a quoted inline program: inspect path-like fragments too.
    for token in tokens:
        if sensitive(token) or any(sensitive(part) for part in re.split(r"[\s\"'=,:;()]+", token) if part):
            raise HarnessError("Command references a sensitive file")
    for i, token in enumerate(lowered):
        name = re.split(r"[\\/]", token)[-1].removesuffix(".exe")
        tail = lowered[i + 1:]
        if name in ("rm", "rmdir", "rd", "del", "remove-item", "ri"):
            if any(x in ("--recursive", "-recurse", "/s", "/q") or
                   (x.startswith("-") and not x.startswith("--") and "r" in x[1:]) for x in tail):
                raise HarnessError("Recursive deletion is blocked")
        if name == "git":
            if "push" in tail and any(x == "-f" or x.startswith("--force") for x in tail):
                raise HarnessError("Forced pushes are blocked")
            if "reset" in tail and "--hard" in tail:
                raise HarnessError("Hard resets are blocked")
            if "clean" in tail and any(x.startswith("-") and "f" in x for x in tail):
                raise HarnessError("Forced git clean is blocked")
            if "checkout" in tail and "--" in tail and "." in tail:
                raise HarnessError("Discarding all changes is blocked")
            if "restore" in tail and "." in tail:
                raise HarnessError("Discarding all changes is blocked")
        if name == "format" and any(re.fullmatch(r"[a-z]:", x) for x in tail):
            raise HarnessError("Disk formatting is blocked")
        if name == "chmod" and "777" in tail and "-r" in tail:
            raise HarnessError("Recursive world-writable permissions are blocked")
        if name in ("curl", "wget", "invoke-webrequest", "iwr") and any("|" in x for x in tail):
            if any(re.split(r"[\\/]", x)[-1] in ("sh", "bash", "python", "python3", "pwsh", "powershell", "iex") for x in tail):
                raise HarnessError("Piping remote content into an interpreter is blocked")
        if token in (">", ">>") and i + 1 < len(tokens):
            path_check(root, cwd, tokens[i + 1], write=True)


def inspect(root, payload):
    if not isinstance(payload, dict) or not isinstance(payload.get("tool_input"), dict):
        raise HarnessError("Malformed tool input")
    tool = payload.get("tool_name")
    data = payload["tool_input"]
    cwd = Path(payload.get("cwd") or root).resolve()
    if not contained(root, cwd):
        raise HarnessError("Tool cwd is outside this project")
    if tool in ("Bash", "PowerShell"):
        if payload.get("agent_type") == "reviewer":
            raise HarnessError("Reviewer shell access is disabled; return findings only")
        command_check(root, cwd, data.get("command", ""))
    elif tool in ("Read", "Write", "Edit", "MultiEdit", "Glob", "Grep"):
        value = data.get("file_path") or data.get("path")
        if tool in ("Glob", "Grep"):
            if value:
                path_check(root, cwd, value)
            if sensitive(data.get("glob", "")) or sensitive(data.get("pattern", "")):
                raise HarnessError("Sensitive search scope is blocked")
        else:
            path_check(root, cwd, value, write=tool != "Read")
        if payload.get("agent_type") == "reviewer" and tool in ("Write", "Edit", "MultiEdit"):
            raise HarnessError("Reviewer cannot modify files")
