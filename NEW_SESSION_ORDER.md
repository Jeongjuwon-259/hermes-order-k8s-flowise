# 신규 세션 시작 시 오더 (Git repo URL 포함)

새 세션이 열리면 다음 순서대로 작업을 진행합니다.

---

## 0. Git 저장소 정보

- **저장소 URL:** `https://github.com/Jeongjuwon-259/hermes-order-k8s-flowise.git`
- **브랜치:** `main` (최신 커밋 `7995ffe` 기준)
- **작업 디렉토리:** `/tmp/hermes-order-k8s-flowise`

## 1. 컨텍스트 로드

- `PROJECT_STATUS.md`를 먼저 읽어 프로젝트 진행 상황을 파악하세요.
- `0-infra/TROUBLESHOOTING_NOTES.md`를 읽어서 과거 트러블슈팅 내용을 확인하세요.

## 2. 최신 소스 반영

```bash
git fetch origin && git reset --hard origin/main && git pull origin main
git log --oneline -3
```

## 3. 인프라 상태 확인 (자동화 스크립트 권장)

스크립트 경로: `/Users/blue/bootstrap-and-deploy.sh`

```bash
# 또는 수동으로 다음을 단계별 실행:
export TART_HOME=/Users/blue/iac-project
cd 0-infra
make clean    # VM 완전 삭제 (선택 사항, clean 상태라면 생략 가능)
make bootstrap # up → fix-identity → configure-network → bridged-up → verify
```

**예상 결과:**
- node-1: `192.168.0.201` (정적 IP, 정상 동작)
- node-2: `192.168.0.202` (정적 IP, 정상 동작)

**⚠ 중요:** make bootstrap 후 `ansible-playbook` 실행 전에 반드시 60초 정도 대기하세요. VM이 bridged 모드로 기동된 후 네트워크가 완전히 붙을 때까지 시간이 필요합니다.

**권장 스크립트** (`/Users/blue/bootstrap-and-deploy.sh`):

```bash
chmod +x /Users/blue/bootstrap-and-deploy.sh
/Users/blue/bootstrap-and-deploy.sh
```

스크립트는 다음을 자동 실행합니다:
1. `git pull` — 최신 코드 반영
2. `make clean` — VM 완전 삭제
3. `make bootstrap` — node-1 (201) + node-2 (202) 정적 IP로 기동
4. **retry ping 로직** — 최대 60초까지 node-1/2가 응답할 때까지 대기
5. `ansible-playbook site.yml` — Kubeadm, Calico, MetalLB, ArgoCD, Istio, Sealed Secrets 적용

## 4. 1-cluster/ 작업 (수동 실행 시)

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
- **`make bootstrap` 후 `ansible-playbook` 실행 전에 60초 대기 필수 (네트워크가 완전히 붙을 때까지)**
- 작업 전/중에 `git pull`로 최신 상태 확인
