# Hermes Agent Project Status (참고용)

> **주의:** 이 파일은 Hermes Agent가 세션 컨텍스트를 재구성할 때 참고하는 목적의
> **참고 문건**입니다. 소스 코드의 실제 작성/수정/커밋은 이 Hermes Agent가 아닌
> **다른 호스트(사용자 또는 공동 작업자)**에서 Git 작업합니다.
> 이 파일은 진행 상황을 기록한 **참고용**일 뿐, 실제 소스 코드를 대체하지 않습니다.

---

## 프로젝트 개요

**저장소:** `https://github.com/Jeongjuwon-259/hermes-order-k8s-flowise`
**브랜치:** `main` (최신 커밋 `4e81737` 기준)
**환경:** Mac mini M4 (64GB RAM), Tart VM 2노드, 로컬 Kubernetes

### 폴더 구조

```
0-infra/          # Tart VM 관리 (Makefile: up, down, configure-network, bootstrap)
1-cluster/        # Kubeadm + Calico + MetalLB + ArgoCD + Istio + Sealed Secrets
2-services/       # (아직 미작성 - 서비스定义)
3-workloads/      # (아직 미작성 - 워크로드 정의)
4-tools/          # (아직 미작성 - 도구 정의)
5-gitops/         # ArgoCD ApplicationSet + Git file generator
```

---

## 현재 진행 단계 (최신: 2026-09-16)

### 0-infra — 완료

- `make bootstrap` 하나完整地로 VM clone → machine-id 재생성 → netplan 정적 IP
  적용 → bridged 네트워크 구성 → verify (ping/ssh)까지 완료
- **node-1:** `192.168.0.201` (정적 IP, 정상 동작)
- **node-2:** `192.168.0.202` (정적 IP, 정상 동작 — 이전 "no IP" 문제 해결됨)
- **근본 원인:** `tart clone` 후 `/etc/machine-id`가 동일해서 DHCP DUID 충돌
  발생 → `cloud-init clean --machine-id`로 해결 확인

### 1-cluster/ansible — 완료 (미검증)

- Kubeadm 클러스터 초기화, Calico CNI, MetalLB (`.206-.239`)
- ArgoCD, Istio 1.31.0 (Gateway API CRDs v1.6.2), Sealed Secrets
- **참고:** Ansible 역할들은 테스트되지 않은 상태 (출력 참조)

### 5-gitops/ — 완료 (미검증)

- ApplicationSet + Git file generator로 Application 자동 생성
- Helm chart: deployment, service, hpa, httproute, destination-rule, sealed-secret
- **참고:** Ansible 역할들은 테스트되지 않은 상태

---

## 관련 파일

- `0-infra/Makefile`: VM 자동화 (up, down, configure-network, bootstrap, clean)
- `0-infra/TROUBLESHOOTING_NOTES.md`: 노드2 정적IP 무응답 문제 등 참고 → 상세 서사는 `HISTORY.md` §2
- `1-cluster/ansible/playbook.yml`: 전체 Ansible 플레이북 (common → kubeadm → calico → metallb → argocd → gateway-api → istio → sealed-secrets)
- `1-cluster/ansible/inventory/hosts.ini`: node-1 (201), node-2 (202)
- `HISTORY.md`: 프로젝트 전체의 결정 로그 / 트러블슈팅 기록

---

## 다음 단계 (작업 순서)

1. `1-cluster/` Ansible 플레이북을 실제 VM에 적용 (테스트 및 검증)
2. Kubeadm 클러스터 가동 상태 확인 (kubectl get nodes, pods)
3. Calico CNI 상태 확인 (pod 변환, NetworkPolicy)
4. MetalLB 할당 IP 확인
5. ArgoCD 설치 및 Dashboard 확인
6. Istio Gateway API 동작 확인
7. 2-services/ 폴더 설계 및 작성 (서비스 정의)
8. 3-workloads/ 폴더 설계 및 작성 (워크로드 정의)
9. 4-tools/ 폴더 설계 및 작성 (도구 정의)

---

## 중요 참고 사항

- **Hermes Agent는 이 파일의 내용을 참고로 하여 컨텍스트를 재구성하지만, 소스 코드의 실제 변경/수정/커밋은하지 않습니다.**
- **Git 작업은 다른 호스트에서 직접 진행**하며, 이 Hermes Agent는 `git pull`로 최신 상태를 받아서 분석합니다.
- `TART_HOME=/Users/blue/iac-project` — Tart VM 이미지 경로
- Bridge 인터페이스: `en8` (USB AX88179B 이더넷)
