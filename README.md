# hermes-order-k8s-flowise — 아키텍처 문서

Mac mini M4(64GB) 로컬 LLM 환경 위에 얹는 개인용 kubeadm 클러스터. Qdrant(벡터 DB) + Flowise(에이전트 워크플로우 빌더)를 상시 운영하며, Hermes Agent 자동화의 인프라 기반이 된다.

---

## 0. 전체 흐름

```
Tart 설치 (brew, 1회성 수동)
      ↓
0-infra/   : Terraform(cirruslabs/tart provider)로 VM 생성 → Ansible로 접속/기본 설정
      ↓
1-cluster/ : kubeadm 클러스터 구성 (Ansible playbook 내 포함) + Calico + MetalLB
      ↓
2-services/: cluster-internal 상태 저장 서비스 (Postgres, Redis, Qdrant, MinIO)
      ↓
3-workloads/: Flowise 등 애플리케이션 배포
      ↓
4-tools/   : 관측성(모니터링) — 추후 도입
```

**역할 분리 원칙**: VM 프로비저닝은 Terraform, 노드 접속 후 모든 설정(패키지 설치·kubeadm·CNI 적용)은 Ansible이 담당한다. 이 경계를 섞지 않는다.

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

- **도구**: Tart(설치만 수동) + Terraform(`cirruslabs/tart` provider) + Ansible
- **VM 사양**: node-1(control-plane) 14GB/4vCPU, node-2(worker) 14GB/4vCPU
- **OS**: Ubuntu Server 24.04 LTS — Tart 공식 레지스트리에 Rocky Linux 사전 빌드 이미지가 없어 채택 (Rocky 선호는 유지되나 인프라 제약상 Ubuntu로 결정)
- **네트워크(iptime 게이트웨이 기준)**:
  - VM은 브리지 모드로 iptime 서브넷에서 직접 IP 수령
  - 각 노드 고정 IP 예약(MAC 기준) — kubeadm 인증서 SAN/etcd 피어링 안정성 확보
  - 외부 접근은 포트포워딩 대신 Tailscale/WireGuard VPN 권장
- **파일**: `providers.tf`, `main.tf`(`resource "tart_vm"` x2), `outputs.tf`(노드 IP), Ansible `inventory.yml`(Terraform output 연동), `playbook.yml`

---

## 3. `1-cluster/` — kubeadm 클러스터 + CNI + LB

| 구성요소 | 선택 | 비고 |
|---|---|---|
| 컨테이너 런타임 | containerd | kubeadm 표준 |
| 클러스터 구성 | kubeadm 2노드 (control-plane + worker) | control-plane taint 제거하여 워크로드 동시 수용 |
| CNI | Calico | Cilium은 리소스 여유 확인 후 추후 학습용 검토 |
| LoadBalancer | MetalLB (L2 모드) | IP 풀은 iptime DHCP 대역과 반드시 분리 (예: DHCP `.100~.199` / MetalLB `.200~.210`) |
| DNS | CoreDNS (기본 내장) | |
| Ingress | nginx-ingress 또는 Traefik | Istio는 sidecar 오버헤드로 1단계에서 제외, 추후 학습용으로 별도 도입 |
| 영속 스토리지 | **LocalPV + Velero 백업** | 2노드 환경에서 Longhorn(분산 블록 스토리지)의 이점이 낮다고 판단, 미적용으로 확정 |

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
- ArgoCD(GitOps)도 이 단계에서 함께 검토

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
- Postgres는 Helm 차트로 배포 (CloudNativePG 오퍼레이터 미사용).
- [ ] Windows 노드 조인 시점 (선행 작업 vs 2노드 안정화 이후)
