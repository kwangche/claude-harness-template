# 공통 실행 워크플로

명령은 저장소 루트 기준입니다. `--root`와 `--session`은 하위 명령 **앞**에 넣습니다.
서브디렉터리에서는 CLI의 절대 경로와 `--root`를 사용하세요. 프로젝트 설정과 실행
증거는 `.harness/`가 관리하며, 문서나 모델 응답을 파싱해 PASS를 만들지 않습니다.

## 1. 모델과 기준점

편집 전에 `start`로 고유한 작업 ID를 만듭니다. 이미 존재하는 ID는 기준점을 초기화하지
않고 재개합니다. 새 요청은 새 ID를 사용하세요. CLI가 만든 STATUS에 세션 ID가 있습니다.
공통 모델 정책으로 검증된 구독 모델을 선택하고 실제 실행 모델과 일치하는지 확인합니다.

`light`는 작은 버그 수정·문서/설정 변경처럼 범위가 좁고 영향이 분명한 작업입니다.
`full`은 여러 영역·보안·아키텍처 변경에 사용합니다. 지휘자 모델은 두 모드 모두 최상위
가용 모델입니다. 경량화는 검증 결과 재사용과 불필요한 위임 축소로 달성합니다.

시작할 때 존재하던 미커밋 변경도 기준점에 포함합니다. 기존 변경까지 검증하려면
`check --all`을 사용하세요. DONE은 항상 `--all`과 같은 조건으로 검사합니다.

## 2. 계획과 상태 전이

PLAN에 목표, 수락 조건, 가정, 위험, 제외 범위, 태스크 ID·의존성·파일 소유권을 적습니다.
계획만 요청받았으면 구현을 시작하지 않습니다. full 모드는 계획 리뷰 PASS가 필요합니다.
리뷰를 최대 횟수까지 고쳐도 PASS가 아니면 자동 STUCK이며 실행 단계로 넘어가지 않습니다.

```text
full:  PLANNING → PLANNED → EXECUTING → TESTING → REVIEWING → DONE
light: PLANNING → EXECUTING → TESTING → REVIEWING → DONE
실패:  TESTING/REVIEWING → REFINING → EXECUTING
중단:  모든 단계 → BLOCKED 또는 STUCK (구체적 이유 필수)
```

`PARTIAL`은 작업자 보고 상태입니다. 남은 파일·수락 조건을 기록해 재위임하고, 체크박스를
완료로 바꾸지 않습니다. `BLOCKED`는 필요한 정보·권한·외부 조건을 적습니다. `STUCK`은
재시도 예산 소진이나 접근 변경이 필요한 상태입니다. 실패를 솔직히 보고하는 종료는
허용되지만 DONE으로 기록되지 않습니다. 해결되면 BLOCKED에서 PLANNING/EXECUTING으로,
STUCK에서 PLANNING으로 재개할 수 있으며 예산은 자동 초기화되지 않습니다. 예산을
늘려야 하면 사용자의 추가 범위를 확인하고 새 작업 ID로 남은 작업을 계획합니다.

## 3. 역할과 병렬 실행

지휘자가 통합·상태·최종 보고를 소유합니다. builder는 구현, tester는 행동 기반 테스트와
실행, reviewer는 실제 변경의 독립 검토를 맡습니다. 지휘자가 지정한 파일과 필요한
의존성을 읽되 요약만 믿고 검증하지 않습니다. 작업자는 shared STATUS/PLAN을 수정하지
않습니다. 작업자 보고는 결과, 변경 파일, 실행 증거 경로, 남은 문제를 포함합니다.

기본 동시 작업자는 2명입니다. 같은 파일·생성물·의존성 잠금 파일을 쓰는 태스크는
직렬로 처리하거나 별도 worktree에 격리합니다. worktree별 별도 세션과 증거를 쓰고,
합친 작업 공간에서 다시 검증합니다. 범용 설정의 병렬 한도는 지휘자가 준수하는 계약이며,
도구 자체 한도도 설정하세요. Claude의 maxTurns는 에이전트 파일에, Codex의 한도는
프로젝트 설정에 있습니다. 모든 호스트의 도구 호출을 공통 CLI가 가로채지는 않습니다.

서브에이전트 기능이 없으면 역할을 순차 수행하고 `review --mode sequential`로 기록합니다.
독립 리뷰가 필수인 프로젝트는 `review.require_independent`를 true로 바꿉니다. 이 경우
독립 리뷰어를 확보하기 전에는 DONE이 될 수 없습니다. 리뷰어의 실제 존재 여부는
운영자가 확인하며, CLI의 actor 문자열만으로 독립성을 인증하는 것은 아닙니다.

## 4. 실행 예제 (light)

모델 inventory를 실제 확인 정보로 준비하고 `route`를 마친 뒤 구현합니다.

```sh
python .harness/cli.py --session task-001 start --profile light
python .harness/cli.py --session task-001 route --inventory .harness/local/models.json
python .harness/cli.py --session task-001 transition EXECUTING
# builder가 구현; PARTIAL이면 남은 일을 완료
python .harness/cli.py --session task-001 transition TESTING
python .harness/cli.py --session task-001 run test
python .harness/cli.py --session task-001 run smoke
python .harness/cli.py --session task-001 transition REVIEWING
# 실제 리뷰 결과를 받은 뒤 그 내용을 요약해 기록
python .harness/cli.py --session task-001 review --verdict PASS --actor reviewer-1 --summary "수락 조건과 회귀 사례 검토 완료"
python .harness/cli.py --session task-001 check --all
python .harness/cli.py --session task-001 transition DONE
```

full 모드는 `review --kind plan --verdict PASS --actor ... --summary ...` 후
`transition PLANNED`를 추가합니다. 전체 변경의 리뷰 전에는 항상 검증을 완료하세요.
리뷰·테스트 후 수정하면 파일 해시가 달라지므로 필요한 검증과 리뷰를 다시 수행합니다.
구성한 build 명령이 있으면 build도 필수입니다. 비어 있는 선택 검사만 생략됩니다.
지원하지 않는 검사를 PASS로 꾸미지 마세요. NO_TESTS는 테스트 기반부터 마련해야 합니다.

실패한 테스트는 `transition REFINING --reason "실패 내용"`으로 보완합니다. 코드 리뷰의
FIX/REJECT는 자동 REFINING 또는 한도 도달 시 STUCK이 됩니다. 코드 리뷰가 REJECT라면
PLAN/접근을 수정한 뒤 다시 검토합니다. 보완은 기본 3회, 계획 리뷰 2회, 명령당 600초,
세션 2시간, 공통 CLI 작업 100회로 제한합니다. 직접 실행한 네이티브 호출은 operation
카운터에 포함되지 않으므로 호스트 예산도 사용하세요. 토큰 비용을 측정 없이 추정하지
않고 실제 사용량 화면을 참고해 기록합니다. 구독 한도 소진 시 중단하고 보고합니다.

## 5. 재개와 복구

- 세션이 바뀌어도 같은 ID를 지정하면 기준점·결과를 이어갑니다. 새 SessionStart로 기존
  검증 기록을 지우지 않습니다. HARNESS_SESSION_ID를 작업자에게 명시적으로 전달하세요.
- STATUS는 마지막으로 상태를 쓴 지휘자의 요약입니다. 실제 세션별 근거는 무시되는
  `.harness/local/<session hash>.json`에 있습니다. 서로 다른 지휘자는 같은 checkout에서
  동시에 진행하지 말고 worktree로 분리하세요.
- `.lock`이 남아 있으면 실행 중인 harness 프로세스가 없는지 먼저 확인하고 해당 세션의
  잠금 파일만 제거합니다. 실행 중인 작업을 잠금 삭제로 우회하지 마세요. 상태 JSON이
  손상되면 자동 통과시키지 않습니다. 보존한 뒤 새 세션에서 전체 검증을 다시 수행합니다.
- Git/Python/설정 오류는 검사 불가입니다. 환경을 복구하거나 BLOCKED로 보고합니다.
  Stop 훅은 `stop_hook_active`만으로 통과시키지 않습니다. 플랫폼 자체 반복 한도가
  종료시킬 수 있으므로 최종 강제 장치는 PR 필수 CI입니다.
- 최종 보고에는 변경, 실제 선택 모델, 검사 결과, 리뷰 모드, 제한·미완료 사항을 적습니다.
