# hermes-order-k8s-flowise — 아키텍처 문서

Mac mini M4(64GB) 로컬 LLM 환경 위에 얹는 개인용 kubeadm 클러스터. Qdrant(벡터 DB) + Flowise(에이전트 워크플로우 빌더)를 상시 운영하며, Hermes Agent 자동화의 인프라 기반이 된다.

> 같은 `node-1`/`node-2` 클러스터를 **Sub-3 러닝 데이터 인프라 프로젝트**(SQLite + AWS S3 + Garmin MCP)와 공유한다. 해당 프로젝트의 설계/작업 로그는 Obsidian `AI러닝` 볼트에서 관리하며, 이 저장소에는 공유 인프라(0-infra/1-cluster) 소스만 함께 반영한다.

---

## 0. 전체 흐름

```
Tart 설치 (brew, 1회성 수동)
      ↓
0-infra/   : Makefile(tart CLI 래핑)로 VM 생성 → Ansible로 접속/기본 설정
      ↓
1-cluster/ : kubeadm 클러스터 구성 (Ansible playbook 내 포함) + Calico + MetalLB
      ↓
2-services/: cluster-internal 상태 저장 서비스 (Postgres, Redis, Qdrant, MinIO)
      ↓
3-workloads/: Flowise 등 애플리케이션 배포
      ↓
4-tools/   : 관측성(모니터링) — 추후 도입
```

**역할 분리 원칙**: VM 프로비저닝은 Makefile(`tart` CLI 직접 래핑), 노드 접속 후 모든 설정(패키지 설치·kubeadm·CNI 적용)은 Ansible이 담당한다. 이 경계를 섞지 않는다.

---

## 1. 리소스 예산 (Mac mini M4, 64GB)

### 로컬 LLM 구성 (2개, MLX, 동시 상주)

| 모델 | 역할 | 스펙 |
|---|---|---|
| **Qwen3.6-35B-A3B-4bit** | 주력 — 코딩 / 추론 / OpenClaw / Agent / 복잡한 작업 | 전체 35B · 활성 3B · MoE · 4-bit · 이미지+텍스트 입력 |
| **Gemma-3n-E4B-it-4bit** | 경량 보조 — 빠른 질의 / 이미지 / 멀티모달 / 간단한 대화 | E4B · Instruction Tuned · 4-bit · 멀티모달 |

### 메모리 배분

| 용도 | 메모리 |
|---|---|
| macOS 호스트 | ~6~8GB |
| 로컬 LLM — Qwen3.6-35B-A3B-4bit | ~20~22GB |
| 로컬 LLM — Gemma-3n-E4B-it-4bit | ~3~4GB |
| Hermes Agent + 자동화 프로세스 | ~3~4GB |
| **VM(K8s)에 배분 가능한 예산** | **~26~30GB** |

---

## 2. `0-infra/` — VM 프로비저닝

- **도구**: Tart(설치만 수동) + Makefile(`tart` CLI 래핑) + Ansible
- **VM 사양**: node-1(control-plane) 14GB/4vCPU, node-2(worker) 14GB/4vCPU, 디스크 170GB
- **OS**: Ubuntu Server 24.04 LTS — Tart 공식 레지스트리에 Rocky Linux 사전 빌드 이미지가 없어 채택 (Rocky 선호는 유지되나 인프라 제약상 Ubuntu로 결정)
- **VM 이미지/디스크 저장 위치**: `TART_HOME=/Users/blue/iac-project` (기본 `~/.tart` 대신 지정)
- **네트워크(iptime BE3600QCA 게이트웨이 기준, `192.168.0.0/24`)**:
  - VM은 브리지 모드(`--net-bridged`)로 iptime 서브넷에서 직접 IP 수령
  - **`tart ip`/ARP 리졸버는 bridged+Ubuntu Server 게스트 조합에서 공식적으로 미해결 버그**([cirruslabs/tart#460](https://github.com/cirruslabs/tart/issues/460), "not possible at the moment") — IP 자동조회에 의존하지 않고 **게스트 OS(netplan) 안에 정적 IP를 직접 박는 방식**으로 확정
  - 부트스트랩 3단계, **전부 0-infra/Makefile에서 처리** (Ansible 불필요): ① `make up` — NAT 모드로 최초 기동, `tart ip` 정상 동작 ② `make configure-network` — NAT IP로 SSH 접속해 게스트에 netplan 정적 IP 주입(cloud-init의 network 관리는 비활성화) ③ `make down` 후 `make bridged-up` — `--net-bridged`로 재기동, 이후 IP는 항상 고정값
  - 노드 정적 IP: `node-1 = 192.168.0.201`, `node-2 = 192.168.0.202` (VM 예약 구간 `.200~.205` 안에서 배정, Windows 3번째 노드 등 향후 확장 여유분 `.203~.205` 포함)
  - 라우터 DHCP 대여 범위를 `192.168.0.2~199`로 축소 완료(실기), `.200~.254`는 고정 IP 전용 구간으로 확보 — `.200~.205`는 VM 전용, `.206~.239`는 MetalLB IP 풀, `.240~.254`는 향후용 여유
  - 외부 접근은 포트포워딩 대신 Tailscale/WireGuard VPN 권장
- **파일**: `Makefile`(`pull`/`up`/`fix-identity`/`configure-network`/`bridged-up`/`down`/`status`/`ip`/`verify`/`inventory`/`clean`/`bootstrap`(전체 자동화) 타깃, 게스트 인터페이스명·netplan 내용은 SSH로 부팅 후 자동 감지해 인라인 생성), `TROUBLESHOOTING_NOTES.md`(해결된 이슈 + 재발 방지 힌트), Ansible `inventory/hosts.ini`(`make inventory`가 고정 IP 기준으로 생성), `playbook.yml`

---

## 3. `1-cluster/` — kubeadm 클러스터 + CNI + LB

| 구성요소 | 선택 | 비고 |
|---|---|---|
| 컨테이너 런타임 | containerd | kubeadm 표준 |
| 클러스터 구성 | kubeadm 2노드 (control-plane + worker) | control-plane taint 제거하여 워크로드 동시 수용 |
| Pod Network CIDR | `10.244.0.0/16` | 기존 검토안(`192.168.0.0/16`)이 실제 물리 LAN 대역(`192.168.0.0/24`, 노드/MetalLB 풀 포함)과 정확히 겹쳐서 변경. kubeadm 기본 Service CIDR(`10.96.0.0/12`)과도 안 겹침 |
| CNI | Calico | Cilium은 리소스 여유 확인 후 추후 학습용 검토 |
| LoadBalancer | MetalLB (L2 모드) | IP 풀 `192.168.0.206~239` — DHCP(`.2~.199`)·VM 예약 구간(`.200~205`)과 모두 분리, `.240~254`는 향후용 여유 |
| DNS | CoreDNS (기본 내장) | |
| Ingress | nginx-ingress 또는 Traefik | Istio는 sidecar 오버헤드로 1단계에서 제외, 추후 학습용으로 별도 도입 — ⚠️ 단, 같은 클러스터를 쓰는 Sub-3 러닝 프로젝트 쪽에서 외부 노출용 Gateway로 Istio를 채택(구현은 후순위)하기로 해서, 두 결정이 어긋남. 실제 Ingress 구현 시점에 재확인 필요 |
| 영속 스토리지 | **LocalPV + Velero 백업** | 2노드 환경에서 Longhorn(분산 블록 스토리지)의 이점이 낮다고 판단, 미적용으로 확정 |
| GitOps | **ArgoCD** | 기본 셋업에 포함(1-cluster 단계에서 함께 설치) — 기존엔 `4-tools`(클러스터 안정화 이후)로 미뤄뒀으나 앞당김. 웹 UI는 내부(LAN) 전용 HTTP + NodePort(`30080`)로 접근, 외부 노출 없음 |

- kubeadm init/join, Calico/MetalLB 적용까지 전부 Ansible playbook 내에 포함 (수동 bash 명령 지양)

---

## 4. `2-services/` — 상태 저장 서비스

| 서비스 | 역할 | 배치 노드 |
|---|---|---|
| PostgreSQL (Helm 차트) | Flowise 메타데이터, 채팅 히스토리 | node-1 (control-plane과 동거, 경량 상태 서비스) |
| PgBouncer | Postgres 앞단 커넥션 풀링 (transaction 모드) | node-1 (Postgres와 동거) |
| Redis (Queue Mode) | Flowise BullMQ 잡 큐, 스트리밍 이벤트 | node-1 |
| Qdrant | 벡터 유사도 검색 전용 DB (디스크 영속) | node-2 (워커, 메모리 변동폭 큰 워크로드 격리) |
| MinIO | S3 호환 오브젝트 스토리지 (파일 업로드) | node-2 |

- Qdrant 컬렉션은 도메인별로 분리 예정(`obsidian_notes`, `running_logs`, `career_docs` 등) — 추후 멀티에이전트 스코핑의 기반
- Flowise 내부 Vector Store 노드는 Qdrant로 직접 연결 (별도 pgvector 불필요)

### PostgreSQL 경량 운영 방안

> ⚠️ Bitnami 차트는 2025-08-28부로 무료 티어 비-hardened 이미지가 `bitnamilegacy`로 이관되어 업데이트/보안 패치가 끊김 — 사용하지 않는다.

- **차트**: [`groundhog2k/postgres`](https://github.com/groundhog2k/helm-charts/tree/master/charts/postgres) — 공식 `postgres` 이미지 기반, exporter/init container 등 불필요한 기본 구성 없음. 기본 `resources: {}`라 직접 request/limit을 지정해야 함
- **k8s 리소스**:
  ```yaml
  resources:
    requests: { cpu: 100m, memory: 256Mi }
    limits:   { cpu: 500m, memory: 512Mi }
  ```
- **postgresql.conf 튜닝** (저동시성 워크로드 기준):
  ```conf
  max_connections = 30          # PgBouncer가 앞단에서 풀링하므로 낮게 유지
  shared_buffers = 128MB
  work_mem = 4MB
  maintenance_work_mem = 64MB
  effective_cache_size = 256MB
  wal_buffers = 4MB
  autovacuum_max_workers = 1    # 단일 소형 DB
  ```
- **PgBouncer**: transaction pooling 모드로 Postgres 앞단에 배치. Flowise Queue Mode(BullMQ) 워커가 늘어나도(특히 node-2 확장 시) 실제 Postgres 백엔드 연결 수는 `max_connections=30` 이내로 억제하는 역할.
  ```yaml
  # pgbouncer.ini 핵심 값
  pool_mode = transaction
  max_client_conn = 200         # Flowise/워커 측 연결 상한
  default_pool_size = 20        # Postgres로 실제 나가는 연결 상한
  ```
  리소스: requests `{cpu: 50m, memory: 16Mi}` / limits `{cpu: 200m, memory: 64Mi}` 수준으로 충분 (경량 프록시)
- **스토리지**: LocalPV, PVC는 2~4Gi로 시작 후 필요 시 확장

---

## 5. `3-workloads/` — 애플리케이션

### Flowise (Web UI + Queue Mode)

> 공식 Helm 차트 부재 확인됨 — 직접 매니페스트(Kustomize)로 구성, Chart 의존성 제거

- `flowise-main` Deployment (Web UI + API)
- `flowise-worker` Deployment (`QUEUE_WORKER=true`, 큐 처리 전담)
- `flowise-service` (type: LoadBalancer, MetalLB가 External-IP 할당)

---

## 6. `4-tools/` — 관측성 (추후 도입)

- Prometheus/Grafana, Jaeger 등은 클러스터 안정화 이후 단계적으로 추가
- ArgoCD(GitOps)는 `1-cluster` 기본 셋업으로 앞당겨져 여기서 제외됨 (§3 참고)

---

## 7. `.github/workflows/` — CI/CD

- kubeval / helm-lint 등으로 매니페스트 검증

---

## 8. 확장 계획

1. **Windows 노트북(Core Ultra 7 255H, 32GB) 3번째 노드 조인**
   - **Hyper-V + External Switch**로 구성 (WSL2 방식은 NAT 네트워킹 한계로 제외)
   - VM 스펙: 16GB RAM / 6vCPU 권장 (Windows 자체 오버헤드 4~6GB 제외)
   - 주의: Hyper-V 활성화 시 하이퍼바이저 계층 변경으로 기존 VPN/보안 소프트웨어와 충돌 가능성 있음 — 활성화 직후 VPN 연결 검증 필요
2. **Istio + Kiali + Cilium** — 클러스터 안정화 후(1~2개월) 학습 목적으로 단계적 추가
3. **과거 Rocky 기반 노트 자산 재이식** — kubeadm init 옵션, containerd CRI 플러그인 이슈 해결 절차, Calico CIDR 매칭, Fluentd→OpenSearch→Kibana 로깅 파이프라인 등 기존 문서화된 노하우를 Ansible role 단위로 번역

---

## 9. 결정 로그

- VM 노드 스펙 15GB×2(총 30GB) → **14GB×2(총 28GB)로 하향 조정** (2026-09-15). 새 예산(~26~30GB) 안에 더 여유 있게 들어옴.
- 디스크 100GB → **170GB로 상향 조정** (2026-09-15).
- Tart VM 이미지/디스크 저장 위치를 `TART_HOME=/Users/blue/iac-project`로 지정 (2026-09-15). 기본값 `~/.tart` 대신 사용.
- Postgres는 Helm 차트로 배포 (CloudNativePG 오퍼레이터 미사용).
- **VM 네트워킹: bridged + 게스트 정적 IP로 확정** (2026-09-16). `tart ip`가 bridged+Ubuntu Server 조합에서 공식 미해결 버그([tart#460](https://github.com/cirruslabs/tart/issues/460))라 자동 IP조회 대신 netplan 정적 IP 채택. node-1=`192.168.0.201`, node-2=`192.168.0.202`.
- 라우터(ipTIME BE3600QCA) DHCP 범위를 `.2~.199`로 축소 완료(실기), `.200~.254`는 고정 IP 전용 확보 (2026-09-16).
- MetalLB IP 풀을 `.200~210` → `.210~220` → `.206~254` → **`.206~239`로 조정** (2026-09-16, 34개). `.200~205`는 VM 전용, `.240~254`는 향후용 여유로 남김 — 처음(11개)엔 너무 작았고 전체(49개)는 과했다고 판단해 중간으로 확정.
- **NAT→static→bridged 전환을 0-infra/Makefile에서 직접 구현** (2026-09-16). Ansible에 위임하지 않고 `configure-network`/`bridged-up` 타깃으로 0-infra 단계에서 완결 — kubeadm이 시작되기 전에 노드 IP가 이미 고정이어야 하므로. Tart 공식 이미지 기본 계정(`admin`/`admin`)으로 SSH 자동화, `sshpass` 필요.
- **clone된 VM의 machine-id 중복이 node-2 bridged 무응답의 근본 원인으로 확정, 수정 완료** (2026-09-16). `fix-identity` 타깃(`cloud-init clean --machine-id` + reboot)을 `up`과 `configure-network` 사이에 추가. Mac mini에서 `make clean && make bootstrap`으로 재검증 완료 — **0-infra는 이제 end-to-end로 완전히 검증됨**. 상세는 `0-infra/TROUBLESHOOTING_NOTES.md`.
- **Pod Network CIDR을 `192.168.0.0/16` → `10.244.0.0/16`으로 변경** (2026-09-16, 1-cluster 계획 단계에서 발견). 기존 검토안이 실제 물리 LAN 대역과 겹치는 문제를 실행 전에 미리 수정.
- **ArgoCD를 `4-tools`(추후)에서 `1-cluster` 기본 셋업으로 앞당김** (2026-09-16).
- **ArgoCD 웹 UI: 내부 전용 HTTP + NodePort(`30080`)로 확정** (2026-09-16). TLS/외부 노출 없음 — `server.insecure: "true"`로 평문 HTTP 서빙.
- [ ] Windows 노드 조인 시점 (선행 작업 vs 2노드 안정화 이후)
- [ ] Ingress: nginx-ingress/Traefik(hermes 결정) vs Istio Gateway(Sub-3 결정) — 실제 구현 시점에 재확인
