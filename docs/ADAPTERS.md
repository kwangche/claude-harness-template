# 런타임 어댑터

| 환경 | 자동 읽기 진입점 | 검증 실행 | 자동 종료 훅 |
|---|---|---|---|
| Claude Code | CLAUDE.md → AGENTS.md | 공통 Python CLI | SessionStart/PreToolUse/Stop 구성 |
| Codex | AGENTS.md, .codex/agents/*.toml | 공통 Python CLI | 설치하지 않음; CLI 및 필수 CI 사용 |
| Gemini CLI | GEMINI.md → AGENTS.md | 공통 Python CLI | 설치하지 않음; CLI 및 필수 CI 사용 |
| 그 외 에이전트 | AGENTS.md를 명시적으로 읽도록 요청 | 공통 Python CLI | 호스트별로 직접 연결 필요 |

도구 간 이벤트 이름·payload·권한 모델은 다릅니다. Claude용 JSON을 다른 도구에
그대로 설치하지 않습니다. 공통 규칙과 CLI는 재사용되지만 네이티브 훅 지원이
동일하다고 주장하지 않습니다. 지원하지 않는 이벤트는 조용히 검증 성공으로 바꾸지 않습니다.

## Claude

Python 3.11 이상과 Git을 PATH에 둡니다. Windows의 `python`이 Store 실행 별칭으로
동작하지 않으면 실제 Python 설치 경로 또는 `py -3.11`로 `.claude/settings.json`의
세 command 실행기를 변경합니다. 경로에 공백이 있으면 인용부호를 유지하세요.
프로젝트 hooks가 신뢰·등록됐는지 `/hooks`에서 확인하고 실제 session_id를 STATUS에서
확인하세요. 자동 SessionStart가 없던 기존 세션은 편집 전에 CLI start를 실행합니다.

검증은 대화 로그가 아니라 공통 영수증을 사용합니다. tester의 다른 transcript에 있어도
같은 `--session`으로 실행하면 공유됩니다. 부모의 HARNESS_SESSION_ID가 비어 있다면
지휘자가 STATUS의 ID를 위임 프롬프트에 명시해야 합니다. hooks timeout은 Git 검사에
충분한 30초이며, 테스트 자체는 훅 안에서 실행하지 않습니다.

## Codex

프로젝트 커스텀 역할은 현재 공식 standalone TOML 형식입니다. 모델 설정을 생략해
선택된 지휘자 모델을 상속합니다. 프로젝트의 max_concurrent_threads_per_session은 2입니다.
오래된 호스트가 이 구성을 지원하지 않으면 해당 설정을 지원 버전으로 갱신하거나
AGENTS.md와 CLI만으로 순차 역할을 수행하세요. 알 수 없는 설정을 작동한다고 가정하지
말고 호스트 진단을 확인합니다. 프로젝트는 호스트의 sandbox/approval 정책을 덮어쓰지 않습니다.

## Gemini 및 다른 도구

Gemini는 GEMINI.md 문맥과 명시적 CLI 호출로 연동합니다. Gemini hooks나 원격
subagent 인증을 자동 구성하지 않습니다. 다른 에이전트는 AGENTS.md 및 WORKFLOW를
읽고 같은 CLI 계약을 따르면 됩니다. 네이티브 위임·모델 변경·GUI 자동화 여부는
실제 도구에서 확인하고 지원되지 않으면 순차 모드/명시적 새 세션을 사용하세요.

## 호환성 검증 범위

CI는 Windows/Linux 및 Python 3.11/3.13에서 상태·모델 선택·검증·경로 가드·JSON hook
entry point를 검증합니다. 각 유료 에이전트에 실제 로그인해 모델을 호출하는 E2E는
포함하지 않습니다. 런타임을 업데이트한 뒤 모델 picker, 커스텀 역할 로딩, `/hooks`와
작은 실제 작업으로 호환성을 확인하세요. 유료 호출 없이도 핵심 회귀 검증은 가능합니다.
