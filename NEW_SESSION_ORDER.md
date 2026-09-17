# 신규 세션 시작 시 오더 (Git repo URL 포함)

새 세션이 열리면 다음 순서대로 작업을 진행합니다.

---

## 0. Git 저장소 정보

- **저장소 URL:** `https://github.com/Jeongjuwon-259/hermes-order-k8s-flowise.git`
- **브랜치:** `main` (최신 커밋 `4f3d594` 기준)
- **작업 디렉토리:** `/tmp/hermes-order-k8s-flowise`

## 1. 컨텍스트 로드

- `PROJECT_STATUS.md`를 먼저 읽어 프로젝트 진행 상황을 파악하세요.
- `0-infra/TROUBLESHOOTING_NOTES.md`를 읽어서 과거 트러블슈팅 내용을 확인하세요.

## 2. 최신 소스 반영

```bash
git fetch origin && git reset --hard origin/main && git pull origin main
git log --oneline -3
```

## 3. 인프라 상태 확인

```bash
export TART_HOME=/Users/blue/iac-project
cd 0-infra
make clean    # VM 완전 삭제 (선택 사항, clean 상태라면 생략 가능)
make bootstrap # up → fix-identity → configure-network → bridged-up → verify
```

**예상 결과:**
- node-1: `192.168.0.201` (정적 IP, 정상 동작)
- node-2: `192.168.0.202` (정적 IP, 정상 동작)

## 4. 1-cluster/ 작업

```bash
cd 1-cluster/ansible
ansible-playbook playbook.yml -i inventory/hosts.ini --ask-become-pass
```

Kubeadm 클러스터, Calico, MetalLB, ArgoCD, Istio, Sealed Secrets 적용.

## 5. 5-gitops/ 작업

- `5-gitops/applicationset.yaml` 확인
- ArgoCD Dashboard에서 Application 상태 확인

---

## 중요

- **Hermes Agent는 컨텍스트 재구성만 합니다. Git 커밋/푸시는 다른 호스트에서 진행합니다.**
- `TART_HOME=/Users/blue/iac-project` — 명시 설정
- Bridge 인터페이스: `en8` (USB AX88179B)
- 작업 전/중에 `git pull`로 최신 상태 확인
