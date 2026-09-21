# ArgoCD Defaults — 운용 가이드 (초안)

> **상태:** 설계 메모 단계. 이 문서는 방향성 정리용 가이드이며, 실제 구현 파일(Ansible
> role, ArgoCD manifest 등)은 별도 작업으로 만들어야 한다. 아래 각 항목은 원래
> 메모를 근거/방법/미결정 사항 형태로 재구성한 것.

## 목표

ArgoCD를 편하게 운용·관리하기 위해 아래 두 가지 자동화가 필요하다.

1. 각 노드에 컨테이너 이미지를 배포하는 방법
2. ArgoCD의 Git 저장소 연결(Settings → Repositories) 자동화

---

## 1. 이미지 빌드 및 노드 배포

- **방침:** 이미지 빌드는 호스트(Mac mini)가 아니라 게스트(마스터 클러스터 노드)에서
  수행한다. 호스트 빌드는 권장하지 않는다.
- **흐름(안):** 마스터 노드에서 이미지 빌드 → 워커 노드로 이미지 복사/이동.
- **자동화 도구:** Ansible로 처리하는 방향을 검토 중 (`1-cluster/ansible`과
  동일한 체계 재사용 가능). 구체적인 role 설계는 미정 — 아래 해결 필요:
  - 빌드 결과 이미지를 워커 노드에 전달하는 방식 (예: `ctr image export/import`,
    사설 레지스트리 없이 tar 전달 등)
  - 빌드 트리거 시점 (Git push 감지 vs 수동 실행)

## 2. ArgoCD Repository 연결 자동화

- ArgoCD `Settings → Repositories → Connect Repo (github)` 를 수동이 아닌
  자동화로 처리하고 싶다.
- **방안(안):** GitHub PAT(Personal Access Token)을 시크릿으로 제공하고,
  `argocd-repo-creds`/`Repository` CR 또는 `argocd repo add` CLI를 Ansible/부트스트랩
  단계에 포함시키는 방식. PAT는 Sealed Secrets로 암호화해 저장.
- **미결정:** PAT 발급/회전 주기, Sealed Secrets 반영 파이프라인.

## 3. 이미지 관리 — Nexus 생략, Git 소스 기반 빌드

- 넥서스(사설 이미지 레지스트리)는 당분간 도입하지 않는다.
- 필요 시 별도 Git 저장소의 소스를 내려받고, 해당 프로젝트 안에 있는
  `Dockerfile`을 기준으로 이미지를 빌드하는 체계를 만든다.
- Jenkins 등 별도 CI/빌드 도구도 당분간 생략 — 위 1번 항목(Ansible 기반 빌드)으로
  대체.

## 4. 우선 배포 대상 — MCP Python 서버

- 현재 GitOps 구조(ApplicationSet + Helm chart, `5-gitops/argocd-templates`,
  `5-gitops/argocd-values`)를 그대로 활용하면 임의의 MCP Python 서버도
  ArgoCD 배포까지 완성할 수 있을 것으로 판단.
- **1차 대상 소스:** https://github.com/Jeongjuwon-259/hermes-gamin-connect-mcp.git
- **인증(gamin auth) 관련 처리는 이번 단계에서 제외** — 추후 해당 소스 자체에서
  해결. 이번 단계는 빌드/배포 파이프라인 검증에 집중한다.

---

## 다음 단계 (제안)

1. `hermes-gamin-connect-mcp` 저장소의 Dockerfile 유무 확인
2. 마스터 노드에서 이미지 빌드 → 워커 노드 배포하는 Ansible role 설계
   (`1-cluster/ansible` 체계 참고)
3. ArgoCD repo 연결 자동화 (PAT + Sealed Secrets) 절차 확정
4. `5-gitops/argocd-values/app/`에 MCP 서버용 values 파일 추가 →
   ApplicationSet(`5-gitops/applicationset.yaml`)이 자동으로 Application 생성하는지 검증
5. 검증 완료 후 gamin auth 인증 통합 검토