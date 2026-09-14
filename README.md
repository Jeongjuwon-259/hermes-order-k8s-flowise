# hermes-order-k8s-flowise

Mac mini M4 64GB 기반 2노드 kubeadm 클러스터 + Qwen3.6-35B-A3B 4bit 상시 구동 환경

---

## 아키텍처 요약

```
┌─────────────────────────────────────────────────────────────────┐
│  Mac mini M4 64GB (macOS Host)                                  │
│                                                                 │
│  ┌──────────────┐   ┌───────────────┐   ┌──────────────────┐  │
│  │  호스트 OS    │   │  Qwen3.6      │   │  Docker          │  │
│  │  (8GB)       │   │  35B-A3B      │   │  (4GB)         │  │
│  │              │   │  4bit (22GB)  │   │                  │  │
│  │  Kubeadm     │   │  MLX/Qwen3.6  │   │  Hermes Agent  │  │
│  │  Control     │   │  컨텍스트 8K   │   │  Gateway       │  │
│  │  Plane Node1 │   │               │   │                  │  │
│  └──────┬───────┘   └───────────────┘   └──────────────────┘  │
│         │                                                     │
│  ┌──────▼──────────┐   ┌──────────────────────────────────┐  │
│  │  VM Node1        │   │  VM Node2 (Windows WSL2 준비)    │  │
│  │  (15GB)          │   │  (15GB, 조인 대기)               │  │
│  │                  │   │                                  │  │
│  │  - containerd   │   │  - containerd                    │  │
│  │  - kubeadm      │   │  - kubeadm                       │  │
│  │  - Calico CNI   │   │  - kubeadm join                  │  │
│  │  - MetalLB      │   │                                  │  │
│  │  - CoreDNS      │   │  워크로드 통합 노드                │  │
│  └──────┬──────────┘   └──────────────────────────────────┘  │
│         │                                                     │
│  ┌──────▼──────────────────────────────────────────────────┐ │
│  │  Kubernetes Services (Cluster Internal)                 │ │
│  │                                                         │ │
│  │  Postgres (CloudNativePG)  Redis (Queue Mode)          │ │
│  │  Qdrant (Vector DB)       MinIO (Object Store)        │ │
│  │  Flowise (Web UI + Worker) Ingress-nginx              │ │
│  │  Cert-Manager            Prometheus/Grafana          │ │
│  └─────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────┘
```

---

## 리소스 배분 (Host Memory Budget)

| 영역 | 메모리 | 비중 |
|------|--------|------|
| macOS 호스트 OS | 8 GB | 12.5% |
| Qwen3.6-35B-A3B 4bit (MLX) | 20~22 GB | 34% |
| VM Node 1 (Control+Work) | 15 GB | 23% |
| VM Node 2 (Work) | 15 GB | 23% |
| Docker + Hermes Gateway | 4 GB | 6% |
| **총계** | **64 GB** | **100%** |

---

## 스택 구성

| 계층 | 구성요소 | 비고 |
|------|----------|------|
| **VM 프로비저닝** | Tart + Terraform + Ansible | Parallels 불필요 (Tart 무료) |
| **컨테이너 런타임** | containerd | kubeadm 표준 |
| **CNI** | Calico (Flannel 교체 검토) | 네트워크 플러그인 |
| **LoadBalancer** | MetalLB (L2 모드) | iptime 네트워크 연동 |
| **DNS** | CoreDNS | 클러스터 내부 네임서버 |
| **상태 저장** | Postgres (CloudNativePG) + Redis | Queue Mode용 Redis 별도 |
| **벡터 DB** | Qdrant | Heremnes Agent RAG용 |
| **LLM** | Qwen3.6-35B-A3B 4bit | MLX 구동, 8K 컨텍스트 고정 |
| **오케스트레이션** | Helm/Kustomize | Chart 의존성 최소화 |

---

## 디렉토리 구조

```
kubeadm-cluster/
├── 0-infra/          # VM 프로비저닝 (Tart + Terraform + Ansible)
├── 1-cluster/        # kubeadm 클러스터 + CNI + MetalLB
├── 2-services/       # cluster-internal 서비스 (Helm/Kustomize)
├── 3-workloads/      # Application-specific 배포
├── 4-tools/          # 관측성 (Prometheus/Grafana/Jaeger)
├── scripts/          # 운영 자동화
└── .github/workflows/ # CI/CD (kubeval, helm-lint)
```

---

## 운영 원칙

1. **Windows 노트북 3번째 노드 조인**을 최우선 순위로 추진 (HA를 위한 최후의 수단)
2. **Longhorn 미적용** — 2노드에서 분산 블록 스토리지 이점 없음, LocalPV + Velero 백업으로 대체
3. **Qwen3 4bit 기준 20~22GB 고정** — 8bit 테스트는 별도 세션에서 검증 후 반영
4. **Flowise Helm 부재** — 직접 매니페스트(Kustomize)로 Chart 의존성 제거
5. **Istio/Cilium 단계적 추가** — 클러스터 안정화 후(1~2개월) 검토

---

##NEXT STEEP

- [ ] Tart VM 이미지 빌드/테스트 (Ubuntu 24.04 + containerd + kubeadm)
- [ ] Ansible role 검증 (apt/systemd 변환 + molecule 테스트)
- [ ] MetalLB IP 풀 예약 (iptime DHCP `.100~.199` / MetalLB `.200~.210`)
- [ ] Windows WSL2 노드 조인 준비
- [ ] Qwen3 4bit 메모리 실측 (MLX 로드 후 `memory_pressure` 모니터링)

---
