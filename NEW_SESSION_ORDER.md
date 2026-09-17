# 신규 세션 시작 시 오더 (HIPAA 준수 버전)

새 세션이 열리면 다음 순서대로 작업을 진행합니다. 문서에 기술적 디테일이 많으므로 순서를 따라가세요.

---

## 1. 컨텍스트 로드

- `PROJECT_STATUS.md`를 먼저 읽어 프로젝트 진행 상황을 파악하세요.
- `0-infra/TROUBLESHOOTING_NOTES.md`를 읽어서 과거 트러블슈팅 내용을 확인하세요.
- `0-infra/Makefile`을 읽어 VM 자동화 구성을 이해하세요.

## 2. 최신 소스 반영

- `git fetch origin && git reset --hard origin/main && git pull origin main` — 다른 호스트에서 진행한 변경사항을 받아오세요.
- `git log --oneline -3`으로 최신 커밋을 확인하세요.

## 3. 인프라 상태 확인

- `export TART_HOME=/Users/blue/iac-project` —tart 이미지 경로를 설정하세요.
- `tart list`로 현재 VM 상태를 확인하세요.
- VM이 없거나 clean 상태면 `cd 0-infra && make bootstrap` — node-1 (192.168.0.201), node-2 (192.168.0.202)이 모두 정적 IP로 정상 동작하는지 확인하세요.

## 4. 1-cluster/ 작업

- `1-cluster/ansible/playbook.yml`을 읽어서 전체 Ansible 순서를 파악하세요.
- `make bootstrap`으로 VM이 정상 가동된 후, 실제 VM에 Ansible playbook을 적용하세요:
  ```
  cd 1-cluster/ansible
  ansible-playbook playbook.yml -i inventory/hosts.ini --ask-become-pass
  ```
- Kubeadm 클러스터 상태 확인 (`kubectl get nodes, pods`)
- Calico, MetalLB, ArgoCD, Istio 상태 확인

## 5. 5-gitops/ 작업

- `5-gitops/applicationset.yaml`을 읽어 Application 자동 생성 구조를 파악하세요.
- ArgoCD Dashboard에서 Application이 정상적으로 생성된지 확인하세요.

## 6. 2-services/, 3-workloads/, 4-tools/ 폴더 설계 및 작성

- 현재 폴더 구조를 파악하고, 각 폴더의 purpose에 맞게 정의하세요.

---

## 주의사항

- **Hermes Agent는 컨텍스트를 재구성하고 분석만 합니다. Git 작업은 다른 호스트에서 진행합니다.**
- `TART_HOME=/Users/blue/iac-project` — 명시적으로 설정하세요.
- Bridge 인터페이스: `en8` (USB AX88179B 이더넷, mac mini)
- `make bootstrap` 실행 전 반드시 `make clean`으로 VM을 깨끗이 시작하세요.
- `0-infra/TROUBLESHOOTING_NOTES.md`에 8가지 netplan/SSH 관련 주의사항이 있으니 반드시 확인하세요.
- 다른 호스트에서 변경사항이 들어올 수 있으므로, 작업 시작 전과 중간에 `git pull`로 최신 상태를 확인하세요.
