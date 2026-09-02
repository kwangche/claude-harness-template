# claude-harness-template

프롬프트 한 줄로 **계획 → 실행 → 테스트 → 보완** 루프를 자동으로 돌리는 Claude Code 프로젝트 템플릿.

메인 세션(Fable 등 상위 모델)은 계획·위임·판정만 하고, 실제 코드 작성·테스트·리뷰는 저렴한 서브에이전트가 담당하도록 모델을 고정해 두었습니다.

## 구조

```
.
├── CLAUDE.md                 # 오케스트레이터 규칙, 역할/모델 라우팅
├── .claude/
│   ├── settings.json         # 권한 + 훅 등록
│   ├── hooks/
│   │   ├── pre_bash_guard.py # PreToolUse: 위험 명령·민감 파일·프로젝트 밖 쓰기 차단
│   │   └── stop_gate.py      # Stop: 소스 변경 시 테스트 실행 + STATUS.md 갱신 강제
│   ├── agents/
│   │   ├── builder.md        # 구현   (sonnet)
│   │   ├── tester.md         # 테스트 (sonnet)
│   │   └── reviewer.md       # 리뷰/게이트 (opus)
│   └── skills/
│       ├── run/SKILL.md      # 메인 루프: 계획→실행→테스트→리뷰→보완→완료
│       ├── plan/SKILL.md     # docs/PLAN.md 작성 절차
│       └── verify/SKILL.md   # 최종 점검 체크리스트
└── docs/
    ├── PLAN.md               # 요구사항·아키텍처·태스크 (오케스트레이터가 채움)
    ├── STATUS.md             # 현재 단계·이력 (세션 재개용)
    └── DECISIONS.md          # 설계 결정 기록
```

## 시작하기

1. 이 저장소를 새 프로젝트 폴더로 복사 (또는 GitHub 템플릿으로 사용)
   ```
   git clone <this-repo> my-project
   cd my-project
   ```
2. Claude Code 실행 — 메인 세션 모델은 계획을 맡길 상위 모델로
   ```
   claude --model claude-fable-5-1
   ```
3. 그냥 원하는 걸 말한다
   ```
   > FastAPI로 할 일 관리 REST API 만들어줘. SQLite 쓰고 CRUD + 테스트까지.
   ```
   `/run` 스킬이 자동으로 잡혀서 계획 → 리뷰 → 구현 → 테스트 → 보완 루프가 돕니다.

4. 중간에 끊겼거나 다음 날 이어서 하려면
   ```
   > 이어서 해줘
   ```
   `docs/STATUS.md` 를 읽고 그 지점부터 재개합니다.

## 모델 라우팅 바꾸기

`.claude/agents/*.md` 의 frontmatter `model:` 값을 수정하면 됩니다.

| 에이전트 | 기본값 | 더 싸게 | 더 정확하게 |
|---|---|---|---|
| builder | claude-sonnet-5 | claude-haiku-4-5 (단순 작업) | claude-opus-5 |
| tester | claude-sonnet-5 | claude-haiku-4-5 | claude-opus-5 |
| reviewer | claude-opus-5 | claude-sonnet-5 | (메인 세션 모델) |

`sonnet` / `opus` / `haiku` 같은 별칭도 동작합니다.

## 튜닝 포인트

- **보완 루프 횟수**: `.claude/skills/run/SKILL.md` 의 "최대 3회"
- **태스크 크기**: `.claude/skills/plan/SKILL.md` 의 "1~3 파일, 200줄 이하"
- **허용 명령**: `.claude/settings.json` — 프로젝트 언어에 맞는 테스트 명령을 추가하면 매번 승인 안 해도 됨
- **역할 추가**: 예를 들어 `docs-writer.md`, `security.md` 를 `.claude/agents/` 에 추가하고 CLAUDE.md 표에 등록

## 훅 (강제 규칙)

CLAUDE.md 는 권고이고 훅은 강제입니다. 모델이 자주 빼먹는데 빼먹으면 비싼 것만 훅으로 막았습니다.

| 훅 | 시점 | 하는 일 |
|---|---|---|
| `pre_bash_guard.py` | 도구 실행 전 | `rm -rf`, `git push --force`, `git reset --hard`, `rmdir /s`, 원격 스크립트 파이프 실행 등 차단. `.env`, 키 파일, `.git/` 접근 차단. 프로젝트 밖 경로 쓰기 차단 |
| `stop_gate.py` | 턴 종료 시 | 소스 파일이 바뀌었는데 (1) 이번 세션에서 테스트 명령 실행 기록이 없거나 (2) `docs/STATUS.md` 가 안 바뀌었으면 턴 종료를 막고 이유를 모델에게 돌려줌 |

요구사항: `python` 이 PATH 에 있어야 합니다 (Windows 에서 `py` 만 있으면 settings.json 의 `python` 을 `py` 로 바꾸세요).

**튜닝**
- 차단 패턴 추가/삭제: `pre_bash_guard.py` 상단 `DANGEROUS_PATTERNS`, `SENSITIVE_FILE_PATTERNS`
- 테스트로 인정할 명령: `stop_gate.py` 상단 `TEST_COMMAND_PATTERNS`. CLAUDE.md 의 `- 테스트 명령:` 줄을 채우면 자동으로 인식됩니다
- 소스로 보지 않을 경로: `stop_gate.py` 의 `NON_SOURCE_PREFIXES` / `NON_SOURCE_SUFFIXES` (여기만 바뀌면 게이트 안 걸림)
- 훅이 너무 자주 막아서 루프가 헛도는 느낌이면 `stop_gate.py` 의 STATUS 검사부터 빼보세요

**동작 조건**: git 저장소여야 합니다 (변경 감지를 git diff 로 함). git 이 아니면 stop_gate 는 조용히 통과합니다.

## 왜 이렇게 나눴나

- 상위 모델은 별도 사용량 풀에 과금되고 실행 작업에 쓰면 빨리 소진됨 → 계획·판정만
- 서브에이전트는 각자 격리된 컨텍스트에서 돌아서 메인 세션 컨텍스트가 안 부풀음
- 보고 형식을 강제해서 오케스트레이터가 받는 토큰을 최소화
- 상태를 파일(`docs/`)에 두어 세션이 끊겨도 이어감

## 라이선스

MIT
