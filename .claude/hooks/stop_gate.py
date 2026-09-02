#!/usr/bin/env python3
"""
Stop 훅 — 턴 종료 게이트
소스 파일이 변경되었으면:
  (1) 이번 세션에서 테스트 명령이 실행된 기록이 있어야 하고
  (2) docs/STATUS.md 도 함께 갱신되어 있어야 한다.
둘 중 하나라도 아니면 턴 종료를 막고 이유를 모델에게 돌려준다.
"""
import json
import os
import re
import subprocess
import sys

# ---- 설정 --------------------------------------------------------------
# 테스트로 인정할 명령 패턴. CLAUDE.md 의 "테스트 명령:" 줄이 채워져 있으면 그것도 자동 추가.
TEST_COMMAND_PATTERNS = [
    r"\bpytest\b", r"python\s+-m\s+pytest", r"python\s+-m\s+unittest",
    r"\bnpm\s+(run\s+)?test\b", r"\bpnpm\s+(run\s+)?test\b", r"\byarn\s+test\b",
    r"\bnpx\s+(jest|vitest|mocha)\b", r"\b(jest|vitest|mocha)\b",
    r"\bgo\s+test\b", r"\bcargo\s+test\b", r"\bdotnet\s+test\b",
    r"\bmvn\s+test\b", r"\bgradle\w*\s+test\b", r"\bphpunit\b", r"\brspec\b",
]
# 소스로 간주하지 않는 경로 (여기만 바뀐 경우 게이트를 걸지 않음)
NON_SOURCE_PREFIXES = ("docs/", ".claude/", ".github/")
NON_SOURCE_SUFFIXES = (".md", ".txt", ".rst", ".gitignore", ".json", ".yaml", ".yml", ".toml", ".lock")
STATUS_FILE = "docs/STATUS.md"
# -----------------------------------------------------------------------


def git(*args):
    try:
        out = subprocess.run(["git", *args], capture_output=True, text=True, timeout=10)
        if out.returncode != 0:
            return None
        return out.stdout
    except Exception:
        return None


def changed_files():
    """작업 트리에서 변경/추가된 파일 목록 (HEAD 대비 + untracked)."""
    if git("rev-parse", "--is-inside-work-tree") is None:
        return None  # git 저장소 아님 → 게이트 스킵
    files = set()
    has_head = git("rev-parse", "--verify", "HEAD") is not None
    diff = git("diff", "--name-only", "HEAD") if has_head else git("diff", "--name-only")
    if diff:
        files.update(l.strip() for l in diff.splitlines() if l.strip())
    staged = git("diff", "--name-only", "--cached")
    if staged:
        files.update(l.strip() for l in staged.splitlines() if l.strip())
    untracked = git("ls-files", "--others", "--exclude-standard")
    if untracked:
        files.update(l.strip() for l in untracked.splitlines() if l.strip())
    return {f.replace("\\", "/") for f in files}


def is_source(path: str) -> bool:
    if path.startswith(NON_SOURCE_PREFIXES):
        return False
    if path.endswith(NON_SOURCE_SUFFIXES):
        return False
    return True


def load_extra_test_patterns():
    pats = []
    try:
        with open("CLAUDE.md", encoding="utf-8") as f:
            for line in f:
                m = re.match(r"\s*-\s*테스트 명령\s*:\s*(.+)", line)
                if m and m.group(1).strip():
                    pats.append(re.escape(m.group(1).strip().split()[0]))
    except Exception:
        pass
    return pats


def tests_ran_in_transcript(transcript_path: str) -> bool:
    if not transcript_path or not os.path.exists(transcript_path):
        return False
    patterns = [re.compile(p, re.IGNORECASE) for p in TEST_COMMAND_PATTERNS + load_extra_test_patterns()]
    try:
        with open(transcript_path, encoding="utf-8", errors="ignore") as f:
            for line in f:
                if '"Bash"' not in line and "'Bash'" not in line:
                    continue
                try:
                    rec = json.loads(line)
                except Exception:
                    continue
                for c in _iter_content(rec):
                    if c.get("type") == "tool_use" and c.get("name") == "Bash":
                        cmd = (c.get("input") or {}).get("command", "") or ""
                        if any(p.search(cmd) for p in patterns):
                            return True
    except Exception:
        return False
    return False


def _iter_content(rec):
    msg = rec.get("message") if isinstance(rec, dict) else None
    content = (msg or {}).get("content") if isinstance(msg, dict) else None
    if isinstance(content, list):
        for c in content:
            if isinstance(c, dict):
                yield c


def block(reasons):
    msg = "[hook:stop_gate] 턴을 끝낼 수 없다.\n" + "\n".join(f"- {r}" for r in reasons) + \
          "\n위 항목을 처리한 뒤 다시 완료를 시도하라."
    print(json.dumps({"decision": "block", "reason": msg}, ensure_ascii=False))
    sys.exit(0)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    # 무한 루프 방지: 훅이 이미 한 번 막은 뒤 재시도 중이면 두 번째는 통과시킨다.
    if data.get("stop_hook_active"):
        sys.exit(0)

    files = changed_files()
    if files is None:
        sys.exit(0)
    src = sorted(f for f in files if is_source(f))
    if not src:
        sys.exit(0)  # 소스 변경 없음 → 게이트 불필요

    reasons = []
    if not tests_ran_in_transcript(data.get("transcript_path", "")):
        reasons.append(
            f"소스 파일이 변경되었지만({', '.join(src[:5])}{' ...' if len(src) > 5 else ''}) "
            "이번 세션에서 테스트 실행 기록이 없다. tester 에게 전체 테스트 실행을 위임하라. "
            "테스트 프레임워크가 없으면 먼저 세팅하고 CLAUDE.md 의 '테스트 명령:' 을 채워라."
        )
    if STATUS_FILE not in files:
        reasons.append(f"{STATUS_FILE} 가 갱신되지 않았다. 현재 단계와 이력을 기록하라.")

    if reasons:
        block(reasons)
    sys.exit(0)


if __name__ == "__main__":
    main()
