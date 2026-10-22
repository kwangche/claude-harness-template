# Universal Agent Harness

Claude Code, Codex, Gemini CLI 등에서 **계획 → 구현 → 검증 → 리뷰 → 보완**을
이어가는 프로젝트 템플릿입니다. 저장소 이름은 호환성을 위해 유지합니다.

지휘자는 특정 회사·모델 버전에 고정하지 않습니다. **현재 구독으로 실제 사용할 수
있다고 확인된 모델 중, 추론·코딩·도구 사용 역량 순위가 가장 높은 모델**을 선택합니다.
선택 근거를 남기며, 계정 권한을 추측하거나 유료 API로 자동 전환하지 않습니다.

## 시작

Python 3.11 이상과 Git이 필요합니다. GitHub의 **Use this template**으로 프로젝트를
만들거나 기존 Git 작업 공간에 템플릿을 적용하세요. 저장소를 원격에서만 수정할 때는
아래 CI가 GitHub 실행 환경에서 검증하므로 개인 컴퓨터의 clone은 필요하지 않습니다.
대화형 에이전트를 실행하려면 해당 에이전트가 접근할 Git 작업 공간은 필요합니다.

```sh
python .harness/cli.py doctor
python .harness/cli.py --session task-001 start --profile light
```

사용 중인 도구의 모델 선택 화면 또는 지원되는 계정별 카탈로그에서 사용 가능 모델을
확인하세요. `.harness/models.example.json`을 참고해 `.harness/local/models.json`에
현재 시각, 확인 출처, 구독 사용 가능 여부, 모델별 역량 순위와 근거를 기록합니다.
이 확인·기록은 에이전트가 지원되는 모델 목록 기능으로 수행할 수 있으며, 목록을 볼 수
없는 환경에서만 사용자의 확인이 필요합니다. Cursor/Copilot 등 GUI 모델 선택과
사용자 정의 런타임도 `runtimes` 설정으로 등록할 수 있습니다.
예제는 의도적으로 비활성·미완성이라 그대로는 실행할 수 없습니다.

```sh
python .harness/cli.py --session task-001 route --inventory .harness/local/models.json
# 선택된 도구의 구독 세션을 실제로 실행하려면 대화형 터미널에서:
python .harness/cli.py --session task-001 route --inventory .harness/local/models.json --launch
```

`--runtime codex`처럼 특정 도구 안에서만 선택할 수도 있습니다. 옵션이 없으면 등록된
도구 전체를 비교합니다. 실행 중인 세션의 모델은 설정 파일만으로 바뀌지 않습니다.
출력된 명령으로 시작하거나 도구의 모델 선택 기능으로 실제 전환을 확인하세요.

새 에이전트에게 `AGENTS.md와 docs/WORKFLOW.md를 읽고 task-001을 진행해줘`라고
요청합니다. CLI의 `--session` 또는 `HARNESS_SESSION_ID`를 모든 작업자가 공유해야
합니다. 공통 규칙은 `AGENTS.md`, 도구별 진입점은 `CLAUDE.md`, `.codex/`, `GEMINI.md`입니다.

## 검증

프로젝트에 맞게 `.harness/config.json`의 `commands`를 **argv 배열**로 바꿉니다.
셸 파이프 문자열이 아니라 실행 파일과 인자 각각을 넣으세요. `{python}`은 현재 Python입니다.

```sh
python .harness/cli.py --session task-001 run test
python .harness/cli.py --session task-001 run smoke
python .harness/cli.py --session task-001 check --all
```

마지막 명령은 모델 선택과 리뷰까지 있어야 통과합니다. 전체 단계 예제는
[WORKFLOW](docs/WORKFLOW.md)에 있습니다. 실패한 실행, `echo pytest`, 부모 대화에
없는 서브에이전트 로그는 완료 근거가 되지 않습니다. 공통 실행기가 실제 프로세스의
종료코드와 검증 전후 파일 해시를 기록합니다. 커밋해도 검증 요구는 유지되고,
검증 후 코드·의존성·훅·설정이 바뀌면 기존 기록은 무효입니다.

## 구성

| 위치 | 역할 |
|---|---|
| `AGENTS.md` | 도구에 독립적인 공통 규칙 |
| `.harness/` | 설정, 모델 선택, 실행 증거, 상태 전이, 보조 가드 |
| `.claude/` | Claude 훅·역할·스킬 어댑터 |
| `.codex/` | Codex 역할 정의와 동시 실행 한도 |
| `GEMINI.md` | Gemini CLI 문맥 어댑터 |
| `docs/` | 워크플로, 모델 정책, 보안, 재개·복구 안내 |
| `tests/` | 실제 Git·프로세스·훅 경로를 검증하는 회귀 테스트 |
| `.github/workflows/ci.yml` | Windows/Linux × Python 3.11/3.13, 필수 `harness-ci` |

## 운영

- [모델 선택과 구독 정책](docs/MODEL_POLICY.md): 도구별 사용 가능 모델, 순위, 갱신, 고정 선택.
- [어댑터와 지원 범위](docs/ADAPTERS.md): 자동 훅과 CLI 검증의 차이, 도구 업데이트 대응.
- [보안과 브랜치 보호](docs/SECURITY.md): 가드의 범위, CI 필수 검사 설정, 원격 PR 흐름.
- [워크플로와 복구](docs/WORKFLOW.md): PARTIAL/BLOCKED/STUCK, 예산, 병렬 작업, 재개.

로컬 증거 파일은 같은 사용자 권한으로 수정할 수 있는 운영 기록이며 보안 증명서가
아닙니다. 실제 실행 권한은 도구의 sandbox/permissions, 병합 강제는 GitHub의 필수 CI가
담당합니다. 이 템플릿은 에이전트 로그인·구독 결제·API 키를 관리하지 않습니다.

라이선스: [MIT](LICENSE).
