# Decisions

- Provider-neutral core: AGENTS.md와 Python CLI를 공통 계약으로 사용하고 도구별 이벤트는
  어댑터로 분리한다. 지원하지 않는 훅을 작동한다고 가장하지 않는다.
- Commander selection: 사용자의 실제 구독 관측 목록과 역량 순위 근거로 선택한다.
  공급자별 인증/과금 탐색을 구현하거나 공개 모델 목록으로 계정 접근을 추측하지 않는다.
- Verification: 현재 파일 내용과 실제 종료코드를 연결한다. 대화 로그 검색이나 HEAD diff만으로
  완료를 판단하지 않는다. 로컬 기록은 운영 증거이고 강제 병합 검사는 독립 CI가 담당한다.
- Lightweight/full: 작은 작업의 중복 호출은 줄이되 두 모드 모두 현재 검증과 리뷰를 요구한다.
- Recovery: 실패를 구체적 이유와 함께 BLOCKED/STUCK으로 종료할 수 있다. 이를 DONE과 구분하고
  재시도 예산을 조용히 초기화하지 않는다.
