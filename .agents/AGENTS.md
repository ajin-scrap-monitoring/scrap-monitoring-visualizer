# 프로젝트 작업 지침

## 적용 범위

이 파일은 이 저장소의 프로젝트 지침 단일 소스다. 전역 행동 지침을 함께 적용하며,
프로젝트 컨텍스트는 이 파일과 Git으로 관리하는 프로젝트 문서에 기록한다.

에이전트 진입점 3개는 `AGENTS.md`, `GEMINI.md`, `.claude/CLAUDE.md`이며 모두 이 파일의
심링크다. 진입점에 별도 지침을 작성하지 않는다.

Antigravity는 `.agents/rules/project.md`의 Always On 규칙에서 이 파일을 참조한다.
도구별 규칙 파일에는 프로젝트 지침을 복제하지 않는다.

## 문서 정본

프로젝트 입력, 사용법, 설계와 검증의 정본은 다음 8개다.

| 문서 | 책임 |
| --- | --- |
| [README](../README.md) | 제품 개요, 환경 변수와 사용자 실행 및 배포 절차 |
| [프로젝트 명세](../docs/project-spec.md) | 제품 범위, 외부 계약과 최종 완료 조건 |
| [합성 카메라 Live 계약](../SYNTHETIC_CAMERA_VIDEO.md) | 합성 frame, 보간, WebSocket과 V4L2 외부 계약 |
| [아키텍처](../docs/architecture.md) | 채택한 설계, 모듈 경계와 내부 처리 정책 |
| [개발 계획](../docs/development-plan.md) | 현재 구현 상태, 작업 순서와 단계별 검증 |
| [계약 출처](../contracts/observation/v1/provenance.json) | 고정 계약 사본의 원본, commit과 파일 해시 |
| [검증 환경](../docs/dependencies.md) | 현재 검증 도구의 의존성과 실행 방법 |
| [실행 환경](../docs/deployment.md) | Container 제약, 릴리스 검증과 자원 기준 |

작업을 시작할 때 명세와 개발 계획을 읽고 해당 작업의 아키텍처 경계를 확인한다.
`docs/project-spec.md`는 고정 입력이므로 구현 과정에서 수정하지 않는다. 설계와 구현 상태가
달라지면 해당 정본만 갱신하며 같은 사실을 다른 문서에 복제하지 않는다.

## 조직 운영 규칙

조직 공통 절차의 원문은 다음 5개다.

| 원문 | 적용 대상 |
| --- | --- |
| [개발 운영 규칙](https://github.com/ajin-scrap-monitoring/.github/blob/main/GOVERNANCE.md) | 공개 범위, 이슈, 브랜치, commit, 병합과 릴리스 |
| [기여 절차](https://github.com/ajin-scrap-monitoring/.github/blob/main/CONTRIBUTING.md) | 변경 작업의 진행 순서 |
| [보안 정책](https://github.com/ajin-scrap-monitoring/.github/blob/main/SECURITY.md) | 취약점과 자격 증명 노출 보고 |
| [PR 템플릿](https://github.com/ajin-scrap-monitoring/.github/blob/main/PULL_REQUEST_TEMPLATE.md) | PR(Pull Request) 본문과 이슈 연결 |
| [ruleset 적용 절차](https://github.com/ajin-scrap-monitoring/.github/blob/main/rulesets/README.md) | 저장소 보호 규칙과 검사 구성의 선행 관계 |

GitHub 작업 전에 관련 원문의 최신 내용을 확인한다. 이슈는 조직의
[공통 양식](https://github.com/ajin-scrap-monitoring/.github/tree/main/.github/ISSUE_TEMPLATE)을
사용한다. 공통 운영 문서와 템플릿은 이 저장소에 복제하지 않는다.

저장소 설정과 ruleset은 조직의 적용 순서를 따른다. 사용자가 승인한 변경과 병합 범위 안에서
작업하며 검증을 우회하거나 원격 `main`에 직접 Push하지 않는다.

## 코드와 입력 경계

프로그램 구현 경로는 `src/scrap_monitoring_visualizer/`이고 자동 검증 경로는
`tests/`다. 코드와 테스트 디렉토리는 해당 구현 단계에서 생성한다.

`contracts/observation/v1/`의 계약 사본은 원본 byte를 보존한다. 형식 정리나 로컬 요구사항을
위한 schema 수정을 하지 않는다. 추가 검증 사례는 `tests/`에서 공개 합성 fixture를
기반으로 구성한다. 계약 검사는 저장소에 고정한 사본을 사용한다.

`~/scrap-monitoring-lidar-simulator`는 계약과 publisher 동작을 확인하는 읽기 전용 참고
프로젝트다. 생성기 구현을 실행 의존성으로 추가하지 않는다. 참고 범위는 공개 계약,
`docs/visualizer-requirements.md`, `docs/observation.md`와 관련 공개 소스 및 테스트다.

운영 관찰 기록과 영상의 데이터 분류는 프로젝트 명세를 따르고, 제외 패턴은 `.gitignore`에서
관리한다. 생성기의 `docs/internal/`과 운영 산출물에서 공개 문서나 테스트 값을 만들지 않는다.

## 작업 검증

변경 범위에 해당하는 개발 계획의 완료 조건을 검증한다. 실행하지 않은 검사나 준비만 된
구현을 완료로 표시하지 않는다. 작업 결과에는 검증 결과와 남은 선행 조건을 포함한다.

에이전트 구조와 계약을 변경하면 저장소 루트에서 다음 명령을 실행한다.

```bash
uv run --frozen python tools/check_repository.py
```
