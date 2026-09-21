# HISTORY — 변경 이력 / 결정 로그 / 트러블슈팅 기록

이 파일은 저장소 전체의 **과거 의사결정 배경, 트러블슈팅 서사, 날짜가 있는 기록**을
모아두는 곳입니다. 소스 코드(Makefile, Ansible role, Helm 템플릿, 아키텍처 문서)에는
"왜 지금 이렇게 되어 있는가"만 간결하게 남기고, "언제/어떤 시행착오를 거쳐 그렇게
결정했는가"는 이 파일에서 관리합니다. 새로운 결정/트러블슈팅이 생기면 소스에는 한 줄
요약 + 이 파일 링크만 남기고, 상세 서사는 아래에 이어서 추가하세요.

---

## 1. 아키텍처 결정 로그 (README.md 관련)

- VM 노드 스펙 15GB×2(총 30GB) → 14GB×2(총 28GB)로 하향 조정 (2026-09-15). 리소스 예산(~26~30GB) 안에 더 여유 있게 들어옴.
- 디스크 100GB → 170GB로 상향 조정 (2026-09-15).
- Tart VM 이미지/디스크 저장 위치를 `TART_HOME=/Users/blue/tart-home`로 지정 (2026-09-15). 기본값 `~/.tart` 대신 사용.
- Postgres는 Helm 차트로 배포하기로 결정 (CloudNativePG 오퍼레이터 미사용).
- **VM 네트워킹: bridged + 게스트 정적 IP로 확정** (2026-09-16). `tart ip`가 bridged+Ubuntu Server 조합에서 공식 미해결 버그([tart#460](https://github.com/cirruslabs/tart/issues/460))라 자동 IP조회 대신 netplan 정적 IP 채택. node-1=`192.168.0.201`, node-2=`192.168.0.202`.
- 라우터(ipTIME BE3600QCA) DHCP 범위를 `.2~.199`로 축소 완료(실기), `.200~.254`는 고정 IP 전용 확보 (2026-09-16).
- MetalLB IP 풀을 `.200~210` → `.210~220` → `.206~254` → `.206~239`로 조정 (2026-09-16, 34개). `.200~205`는 VM 전용, `.240~254`는 향후용 여유로 남김.
- **NAT→static→bridged 전환을 0-infra/Makefile에서 직접 구현하기로 결정** (2026-09-16). Ansible에 위임하지 않고 `configure-network`/`bridged-up` 타깃으로 0-infra 단계에서 완결 — kubeadm이 시작되기 전에 노드 IP가 이미 고정이어야 하므로.
- **clone된 VM의 machine-id 중복이 node-2 bridged 무응답의 근본 원인으로 확정, 수정 완료** (2026-09-16). 상세는 §2 참고.
- **Pod Network CIDR을 `192.168.0.0/16` → `10.244.0.0/16`으로 변경** (2026-09-16). 기존 검토안이 실제 물리 LAN 대역과 겹치는 문제를 실행 전에 미리 발견/수정.
- ArgoCD를 `4-tools`(추후 도입 예정)에서 `1-cluster` 기본 셋업으로 앞당김 (2026-09-16).
- ArgoCD 웹 UI: 내부 전용 HTTP + NodePort(`30080`)로 확정 (2026-09-16). TLS/외부 노출 없음.
- ArgoCD 매니페스트 리포 분리 여부: 지금은 같은 리포, 나중에 분리하기로 결정 (2026-09-16). 솔로 프로젝트 규모에서 리포 분리 관리 비용이 아직 정당화 안 됨. 재사용성이 필요해지거나 커밋 이력이 섞여 불편해지면 `git subtree split`으로 분리.
- Ingress/Gateway: Istio로 통일 확정 (2026-09-16). nginx-ingress/Traefik 검토안 폐기, Sub-3 프로젝트 결정과 통일.
- `5-gitops/` 구조를 `argocd-templates`(공유 차트) + `argocd-values`(앱별 값) 2단 구조로 확정 (2026-09-16). 과거 프로젝트 패턴 재사용.
- 최신 K8s/GitOps 트렌드 검토 후 3가지 반영 (2026-09-16):
  1. Istio VirtualService → 표준 Gateway API(HTTPRoute), Istio 공식 권장 전환
  2. 수동 ArgoCD Application → ApplicationSet(Git file generator)
  3. 평문 secret 커밋 → Sealed Secrets (ESO/SOPS 대비 외부 의존성 없음)

  반영 결과: `1-cluster/ansible`에 `roles/gateway-api`(CRD v1.6.2), `roles/istio`(Helm, 1.31.0),
  `roles/sealed-secrets` 추가, `5-gitops/argocd-templates/chart/app/stable` 차트 작성
  (로컬 `helm lint`/`helm template` 통과), `5-gitops/applicationset.yaml`(초안, 미검증).

### 미검증/미결 항목
- [ ] Windows 노드 조인 시점 (선행 작업 vs 2노드 안정화 이후)
- [ ] Istio/Gateway API/Sealed Secrets/ApplicationSet — 소스만 작성됨, Mac mini에서 `ansible-playbook` 실행 검증 아직 안 함
- [ ] `applicationset.yaml`은 실제 앱 값 파일 추가 후 sync 확인 전까지 미신뢰 상태로 취급
- [ ] `5-gitops/argocd-templates`의 `func/` — 용도 불명확해서 생성 안 함, 필요해지면 내용과 함께 추가

---

## 2. 0-infra 트러블슈팅 기록

### [해결됨] node-2 bridged 모드 무응답 — clone된 VM의 machine-id 충돌

**증상**: `tart clone`으로 만든 node-1/node-2가 완전히 같은 절차(netplan 정적 IP 주입 →
bridged 전환)를 거치는데도 node-2만 정적 IP(`192.168.0.202`)에 ping/ssh 응답이 없었음.

**근본 원인**: `tart clone`은 `/etc/machine-id`도 그대로 복사한다. systemd-networkd의
DHCPv4 ClientIdentifier(DUID)는 이 machine-id를 해시해서 만들기 때문에, NAT 부트스트랩
단계에서 macOS(host) DHCP 서버가 node-1과 node-2를 같은 클라이언트로 착각 → node-2의
DHCP lease가 오염되고, 이후 정적 IP 전환도 꼬임.

**해결**: `up` 직후, `configure-network` 이전에 `fix-identity` 단계를 추가해
`cloud-init clean --machine-id` + reboot로 clone된 VM마다 새 machine-id를 발급받게 함.
`bootstrap` 타깃에 이미 연결되어 있어 별도 조치 불필요.

**앞으로 비슷한 문제를 만나면**: "두 VM 중 하나만 네트워크가 이상하다" 증상이 다시
보이면, 가장 먼저 `ssh <VM> "cat /etc/machine-id"`로 두 VM의 machine-id가 서로 다른지
확인. tart/cloud-init 이미지를 clone해서 여러 대 굴릴 때는 항상 identity(machine-id,
SSH host key 등)를 clone 직후 재발급하는 습관을 들일 것.

### [해결됨] 2026-09-18 재발 — bridged 전환 후 ping/ssh 전부 무응답 (복합 원인)

`make clean && make bootstrap`을 재실행했을 때 `verify` 단계에서 두 노드 모두 100%
패킷 손실, SSH 타임아웃이 재발함. 원인을 하나씩 분리한 결과:

1. **`tart stop` 이후에도 이전 프로세스가 좀비로 남음** — `nohup tart run $n ... & disown`
   으로 띄운 프로세스가 `tart stop $n` 실행 후에도 남아있어, bridged 모드로 새 `tart run`을
   또 띄우면 같은 VM에 대해 프로세스가 중복 실행되어 네트워크가 꼬임.
   → `down` 타깃에 `pgrep -f "tart run <node> "` + `kill -9`로 강제 정리 로직 추가.
2. **macOS ARP 캐시 stale REJECT 엔트리** — `route get <ip>`에 `REJECT` 플래그가 남아
   ping/ssh가 즉시 차단됨. `sudo arp -d <ip>`로 캐시 삭제(사용자가 직접 실행) 또는 자연 만료 대기.
3. **(오판, 정정)** netplan apply 후 NAT IP로 재검증하려던 시도 — 정적 IP 적용 순간
   NAT 주소가 사라지는 것이 정상 동작인데 이를 실패로 오판, 재시도 루프를 넣었다가 오히려
   정상 케이스를 실패 처리하는 사고가 있었음. **검증은 반드시 bridged-up 이후 `verify`
   단계(TARGET_IP)에서만 할 것.**
4. **두 노드 순차 configure 시 마지막 노드의 apply 반영 시간 부족** — node-1은 안정화
   시간이 충분했지만 node-2는 apply 직후 곧바로 stop되어 netplan 설정이 완전히 반영되기
   전에 종료됨 (`/etc/netplan/99-static.yaml`이 0바이트). `bootstrap`의 `configure-network`
   완료 후 `down` 진입 전 대기를 10초 → 30초로 늘려서 완화.

부수 발견: **make 3.81(macOS 기본 CommandLineTools make)** 은 이 Makefile 조합에서
암묵적 패턴 규칙(`configure-network-node-%:`)의 레시피를 실행하지 않고 "Nothing to be
done for ..."을 내며 조용히 no-op 처리하는 버그가 있음 확인. 개별 구체 타깃 +
`define/call` 재사용 방식으로 되돌림 — 패턴 규칙(%)으로 다시 리팩터링하지 말 것.

검증: 위 항목을 모두 반영한 뒤 `make bootstrap` 재실행 → node-1(192.168.0.201),
node-2(192.168.0.202) ping 0% loss, SSH hostname 정상 확인 (2026-09-18).

### [2026-09-21] Bootstrap 실행 중 NAT DHCP 실패 / Bridged DHCP 응답 지연 → 재시도 로직 추가

**증상**: `make bootstrap` 실행 시 두 가지 예외가 recurring.

1. **NAT DHCP 실패** (VM 재생성 시 간헐적): `tart ip node-X --wait 120`이 120초 후에도 IP
   반환하지 않음 → 기존 코드가 `exit 1`로 전체 bootstrap 중단. 수동 `make clean && make bootstrap`
   재실행 필요.
2. **Bridged DHCP 응답 지연** (기억: DHCPlease 재발 가능): bridged 전환 후 `ping`이 120초(24×5초)
   재시도 후 silently 실패 (`set -e` 없으므로 re-run 필요). DHCP 서버 응답까지 수 분 이상
   소요되는 환경에서 timeout이 너무 짧음.

**근본 원인**: `tart ip` (NAT)는 cirruslabs/tart#460 버그로 공식 미해결. NAT 부트스트랩 단계에서만
신뢰 가능하며, VM 생성/재부팅 시 DHCP 응답 시간 차이가 큼. Bridged 전환 후 정적 IP(netplan)가
적용되어도 macOS 물리 네트워크의 DHCP 서버 응답 시간이 느린 경우(라우터 CACHE, AP 상태) 최대 3~4분
걸릴 수 있음.

**해결**: `0-infra/Makefile`에 3개 utility 함수 추가 (2026-09-21).

- `wait-for-nat-ip`: `tart ip` 실패 시 5회 재시도 (5초 간격 = 25초), 실패 시 명확 안내 메시지
  (`make clean && make bootstrap` 권장).
- `wait-for-bridged-ip`: `ping` 실패 시 48회 재시도 (5초 간격 = 4분), 실패 시 DHCPlease 안내
  메시지 (DHCP 서버 활성화 확인, MAC whitelist 확인, clean+b 권장).
- SSH 실패 시 `ssh-keygen -R` 자동 호출 → known_hosts stale 해소.
- `NET_IFACE` 감지 실패 시 `en0/en1/en8` fallback 목록 추가.
- `up` 단계에서 이미 실행 중이지만 broken/stuck한 VM 처리 (pid kill → 재시도).

검증: 위 개선을 반영한 `make bootstrap` 재실행 → 두 노드 모두 정상 완료 (2026-09-21).

### 과거 겪었던 그 외 문제 (재발 방지용 요약)

- scp로 netplan YAML 전송 시 간헐적으로 파일이 손상됨(`Invalid YAML: aliases are not
  supported`) → SSH heredoc/`printf` 체인으로 원격에서 직접 파일 작성.
- netplan 파일 작성과 `netplan apply`를 한 세션에서 같이 하면 파일 쓰기 검증 없이
  넘어갈 수 있음 → 파일 쓰기 직후 `sudo test -s <file>`로 확인 후 별도 SSH 호출로 apply.
- 정적 IP 적용 후 재부팅하면 cloud-init이 netplan 설정을 재생성/초기화함 → 재부팅 없이
  바로 bridged로 전환.
- `en0`이 기본값처럼 보여도 실제로 unplugged(media: none)일 수 있음 → `route get default`로
  실제 게이트웨이 인터페이스 자동 감지.
- Makefile 변수에 인라인 주석(`값 # 주석`)을 달면 trailing space가 값에 포함되어 인증이 깨짐
  → 주석은 반드시 별도 줄에 작성.
- `sudo`로 쓴 파일 검증 시 `$(sudo cmd < file)` 형태는 sudo 없는 셸에서 먼저 리다이렉션이
  열려 Permission denied가 남 → `sudo test -s <file>` 사용.

---

## 3. 1-cluster / 5-gitops 관련 참고

- `1-cluster/ansible/group_vars/all.yml`의 버전 pin(k8s 1.37, Calico v3.32.2, MetalLB
  v0.16.1, Gateway API v1.6.2, Istio 1.31.0 등)은 2026-09-16 기준 확인된 최신 안정
  버전 기준. 재실행 시점에 최신 여부 재확인 권장.
- `roles/sealed-secrets`: 홈랩/솔로 규모에서 External Secrets Operator(외부 Vault
  필요)나 SOPS(KMS/PGP 키 관리 필요)보다 외부 의존성이 없어 2026-09-16에 채택.
- `roles/gateway-api`: Istio가 자체 Gateway/VirtualService API를 deprecate하고 표준
  Gateway API 전환을 공식 권장한다는 점을 2026-09-16에 확인하고 도입.
- `5-gitops/.../destination-rule.yaml`: 서킷브레이커/커넥션풀 등 세부 트래픽 정책이
  아직 Gateway API에 완전히 대응되지 않는다는 점을 2026-09-16에 확인, Istio 자체
  CRD(DestinationRule)를 선택적으로 유지하기로 결정.
