#!/usr/bin/env python3
"""
PreToolUse 훅 (Bash / Read / Write / Edit)
위험한 명령과 민감 파일 접근을 차단한다. exit 2 = 차단, stderr 가 모델에게 전달됨.
"""
import json
import os
import re
import sys

# ---- 설정 --------------------------------------------------------------
DANGEROUS_PATTERNS = [
    (r"\brm\s+(-[a-zA-Z]*r[a-zA-Z]*f|-[a-zA-Z]*f[a-zA-Z]*r)\b", "rm -rf 계열 명령"),
    (r"\brm\s+-r\b.*\s/(\s|$)", "루트 경로 삭제"),
    (r"\bgit\s+push\b.*(--force|-f)\b", "git push --force"),
    (r"\bgit\s+reset\s+--hard\b", "git reset --hard"),
    (r"\bgit\s+clean\s+-[a-zA-Z]*f", "git clean -f"),
    (r"\bgit\s+checkout\s+--\s+\.", "git checkout -- . (전체 되돌리기)"),
    (r"(^|[\s;&|])(del|rmdir|rd)\s+/[sq]", "Windows 재귀 삭제 (del /s, rmdir /s)"),
    (r"Remove-Item\b.*-Recurse", "PowerShell Remove-Item -Recurse"),
    (r"\bformat\s+[a-zA-Z]:", "디스크 포맷"),
    (r"\b(curl|wget)\b.*\|\s*(sh|bash|python)", "원격 스크립트 파이프 실행"),
    (r"\bchmod\s+-R\s+777\b", "chmod -R 777"),
]

SENSITIVE_FILE_PATTERNS = [
    r"(^|[\\/])\.env($|\.)",
    r"(^|[\\/])\.git[\\/]",
    r"(^|[\\/])(id_rsa|id_ed25519)($|\.)",
    r"\.(pem|key|p12|pfx)$",
    r"(^|[\\/])secrets?\.(json|ya?ml|toml)$",
]
# 프로젝트 밖 경로 쓰기 차단 (Write/Edit 만)
BLOCK_WRITE_OUTSIDE_PROJECT = True
# -----------------------------------------------------------------------


def block(msg: str):
    sys.stderr.write(f"[hook:guard] 차단됨 — {msg}\n"
                     "이 작업은 정책상 금지되어 있다. 다른 방법을 쓰거나 사용자에게 확인을 요청하라.\n")
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    tool = data.get("tool_name", "")
    inp = data.get("tool_input", {}) or {}

    if tool == "Bash":
        cmd = inp.get("command", "") or ""
        for pat, label in DANGEROUS_PATTERNS:
            if re.search(pat, cmd, flags=re.IGNORECASE):
                block(f"{label}: `{cmd.strip()[:120]}`")
        # 민감 파일을 cat/type/echo > 로 건드리는 경우
        for pat in SENSITIVE_FILE_PATTERNS:
            if re.search(pat, cmd):
                block(f"민감 파일 접근 시도: `{cmd.strip()[:120]}`")
        sys.exit(0)

    if tool in ("Read", "Write", "Edit", "MultiEdit"):
        path = inp.get("file_path", "") or inp.get("path", "") or ""
        if not path:
            sys.exit(0)
        for pat in SENSITIVE_FILE_PATTERNS:
            if re.search(pat, path):
                block(f"민감 파일 {tool}: {path}")
        if tool != "Read" and BLOCK_WRITE_OUTSIDE_PROJECT:
            project = os.path.abspath(os.environ.get("CLAUDE_PROJECT_DIR", os.getcwd()))
            target = os.path.abspath(path)
            if not target.startswith(project):
                block(f"프로젝트 밖 경로 쓰기: {path}")
        sys.exit(0)

    sys.exit(0)


if __name__ == "__main__":
    main()
