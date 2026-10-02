# hermes-order-k8s-flowise — 전체 소스 코드 분석 보고서

> 분석일: 2026-10-02 (KST)  
> 분석 범위: 전체 리포지토리 (77개 파일)  
> 기준 커밋: `main` 브랜치 최신

---

## 1. 프로젝트 개요

**목적:** Mac mini M4 (64GB RAM)에서 Tart VM 2노드를 활용해 로컬 Kubernetes 클러스터를 구성하고, ArgoCD GitOps로 Garmin Connect MCP 서버를 배포하는 자동화 인프라 프로젝트.

**환경:**
- 호스트: Mac mini M4 (64GB RAM)
- 가상화: Tart VM (2노드, 각 15GB RAM)
- 네트워크: Bridged (en8 인터페이스, USB AX88179B)
- IP: node-1=192.168.0.201 (control-plane), node-2=192.168.0.202 (worker)
- K8s 버전: 1.31 (kubeadm)

---

## 2. 폴더 구조 및 구성 요소

```
hermes-order-k8s-flowise/
├── PROJECT_STATUS.md        # 진행 상태 (완료/미검증)
├── HISTORY.md               # 개발 역사 및 결정 로그
├── README.md               # 아키텍처 및 설정 가이드
├── NEW_SESSION_ORDER.md    # 세션 시작 체크리스트
│
├── 0-infra/               # Tart VM 관리 (Makefile)
│   ├── Makefile            # up, down, bootstrap, clean 등
│   └── TROUBLESHOOTING_NOTES.md
│
├── 1-cluster/             # Kubernetes 클러스터 프로비저닝 (Ansible)
│   └── ansible/
│       ├── playbook.yml        # 전역 플레이북 (8단계)
│       ├── inventory/hosts.ini  # node-1 (201), node-2 (202)
│       ├── group_vars/all.yml
│       │
│       ├── roles/common/        # 제1단계: 사용자, apt, swap, 정체성 정리
│       │   └── tasks/main.yml
│       ├── roles/kubeadm/       # 제2단계: kubeadm init/join
│       │   └── tasks/main.yml
│       ├── roles/cni-calico/    # 제3단계: Calico CNI
│       │   └── tasks/main.yml
│       ├── roles/metallb/       # 제4단계: MetalLB (LoadBalancer)
│       │   └── tasks/main.yml
│       ├── roles/gateway-api/   # 제5단계: Gateway API CRDs
│       │   └── tasks/main.yml
│       ├── roles/istio/         # 제6단계: Istio 1.31.0 (Gateway API 모드)
│       │   └── tasks/main.yml
│       ├── roles/sealed-secrets/# 제7단계: Sealed Secrets 컨트롤러
│       │   └── tasks/main.yml
│       └── roles/argocd/        # 제8단계: ArgoCD 설치
│           └── tasks/main.yml
│
├── 5-gitops/              # GitOps: ArgoCD + ApplicationSet + Helm + MCP
│   ├── applicationset.yaml      # ApplicationSet (Git file generator)
│   │
│   ├── argocd-defaults/         # Garmin MCP 애플리케이션 (소스 코드)
│   │   ├── src/garmin_mcp/      # 핵심 Python 패키지
│   │   │   ├── __init__.py
│   │   │   ├── client.py        # Garmin Connect API 클라이언트 (unofficial-garmin-api)
│   │   │   ├── auth.py          # Garmin Connect OAuth 인증
│   │   │   ├── sanitize.py      # PII 데이터 필터링
│   │   │   └── tools/           # MCP Tool 모듈 (12개)
│   │   │       ├── activities.py   # 러닝 활동 (5 tools)
│   │   │       ├── training.py     # 훈련 지표 (6 tools)
│   │   │       ├── wellness.py     # 웰빙/회복 (3 tools)
│   │   │       ├── records.py      # 개인 기록 (2 tools)
│   │   │       ├── condition.py    # 컨디션 추적 (총 8 tools)
│   │   │       ├── gear.py         # 장비 관리 (총 3 tools)
│   │   │       ├── heart_rate.py   # 심박대 연동 (총 5 tools)
│   │   │       ├── summary.py      # 주간/월간 요약 (총 5 tools)
│   │   │       ├── tcx.py          # TCX 파일 처리 (총 7 tools)
│   │   │       ├── workout.py      # 운동处方 (총 8 tools)
│   │   │       └── __init__.py
│   │   ├── Dockerfile_garmin_mcp      # K8s용 (http_main.py, streamable-http)
│   │   ├── Dockerfile_garmin_mcp_build  # 로컬용 (stdio)
│   │   ├── pyproject.toml           # hatchling 빌드, MCP Tool 등록
│   │   ├── scripts/auth.py          # 인증 토큰 갱신 스크립트
│   │   └── README.md
│   │
│   ├── argocd-garmin-templates/     # Garmin MCP용 Helm chart (기본)
│   │   └── chart/app/stable/
│   │       ├── templates/
│   │       │   ├── deployment.yaml  # K8s Deployment (garmin-mcp-http)
│   │       │   ├── httproute.yaml   # Gateway API HTTPRoute
│   │       │   └── service.yaml     # ClusterIP Service (8000/tcp)
│   │       └── Chart.yaml
│   │
│   ├── argocd-hello-world-templates/  # nginx 테스트용 Helm chart
│   │   └── chart/app/stable/
│   │       ├── templates/
│   │       │   ├── deployment.yaml  # nginx Deployment
│   │       │   └── service.yaml     # NodePort Service (80/tcp)
│   │       └── Chart.yaml
│   │
│   ├── argocd-project-templates/    # Garmin MCP용 Helm chart (완전판)
│   │   └── chart/app/stable/
│   │       ├── templates/
│   │       │   ├── deployment.yaml       # K8s Deployment
│   │       │   ├── service.yaml          # ClusterIP Service
│   │       │   ├── httproute.yaml        # Gateway API HTTPRoute (HTTPS 종료)
│   │       │   ├── destination-rule.yaml # Istio DestinationRule (서킷브레이커)
│   │       │   ├── hpa.yaml              # HorizontalPodAutoscaler
│   │       │   └── sealed-secret.yaml    # SealedSecret (Docker registry creds 등)
│   │       └── Chart.yaml
│   │
│   ├── argocd-values/                 # Helm values
│   │   ├── app/hello-world.yaml       # hello-world values (replicas, service, hpa)
│   │   ├── app/garmin-mcp-values.yaml # Garmin MCP values (HTTPS, resource limits)
│   │   └── example-values.yaml
│   │
│   └── ansible/               # 5-gitops 전용 Ansible (Docker 빌드, 적용)
│       ├── garmin-mcp-build.yml       # node-1에서 Docker 이미지 빌드
│       ├── garmin-mcp-transfer.yml    # node-1 → scp → node-2로 이미지 전송
│       ├── applicationset-apply-playbook.yml  # ApplicationSet 적용
│       ├── kubeconfig-setup-playbook.yml  # kubeconfig 설정
│       ├── argocd-cli-install-playbook.yml  # ArgoCD CLI 설치
│       ├── docker-install-playbook.yml  # Docker 설치 (참고용)
│       ├── inventory/hosts.ini
│       └── group_vars/all.yml
│
└── (2-services/, 3-workloads/, 4-tools/)  # 미작성 (placeholder)
```

총 77개 파일, 약 200KB의 소스 코드 (Python 55%, Helm/Ansible YAML 35%, 문서 10%).

---

## 3. 아키텍처 상세 분석

### 3.1 인프라 레이어 (0-infra)

**Makefile**은 Tart VM 관리의 전자기간을 담당합니다.

| 명령어 | 역할 |
|--------|------|
| `make up` | VM 클론 (node-1, node-2) |
| `make configure-network` | cloud-init clean + machine-id 재생성 + netplan 정적 IP |
| `make bridged-up` | Bridged 네트워크 기동 (en8 인터페이스) |
| `make bootstrap` | 위 3단계 + verify (ping/ssh) |
| `make clean` | VM 완전 삭제 |

**핵심 문제 해결 (HISTORY.md §2):**
`tart clone` 후 `/etc/machine-id`가 동일해 DHCP DUID 충돌이 발생했고, `cloud-init clean --machine-id`로 해결됨.

### 3.2 클러스터 레이어 (1-cluster/ansible)

`playbook.yml`은 **8단계 역할**을 순차적으로 실행합니다.

| 단계 | 역할 | 대상 | 역할 내용 |
|------|------|------|-----------|
| 1 | `common` | 모든 노드 | admin 사용자 생성, apt 업데이트, swap 해제, containerd 설치 |
| 2 | `kubeadm` | 모든 노드 | K8s 바이너리 설치 (1.31), etcd, kube-apiserver, kube-controller-manager, kube-scheduler, kube-proxy, kubelet kubeadm init, worker join |
| 3 | `cni-calico` | control_plane | Calico CNI 설치 (pod 네트워크) |
| 4 | `metallb` | control_plane | MetalLB 설치 (IP 범위: `.206`~`.239` — 34개 IP) |
| 5 | `gateway-api` | control_plane | Gateway API CRDs (v1.6.2) 설치 |
| 6 | `istio` | control_plane | Istio 1.31.0 설치 (Gateway API 모드, istio-ingressgateway) |
| 7 | `sealed-secrets` | control_plane | Bitnami Sealed Secrets 컨트롤러 설치 |
| 8 | `argocd` | control_plane | ArgoCD 설치 (core, ui, server, redis, notifications, gitea) |

**모든 역할이 완료되었으나 미검증 상태.**

### 3.3 GitOps 레이어 (5-gitops)

#### 3.3.1 ApplicationSet (`applicationset.yaml`)

ArgoCD ApplicationSet의 Git file generator를 사용합니다. 

```yaml
apiVersion: argoproj.io/v1alpha1
kind: ApplicationSet
spec:
  generators:
    - git:
        repoURL: https://github.com/Jeongjuwon-259/hermes-order-k8s-flowise
        revision: main
        directories:
          - path: 5-gitops/argocd-values/app/*
          - path: 5-gitops/argocd-hello-world-templates/chart/app/stable
          - path: 5-gitops/argocd-garmin-templates/chart/app/stable
          - path: 5-gitops/argocd-project-templates/chart/app/stable
```

**동작 원리:** `argocd-values/app/` 폴더의 각 YAML 파일(예: `hello-world.yaml`, `garmin-mcp-values.yaml`)이 개별 Application으로 생성됨. templates 폴더는 values 파일과 매핑되어 Application을 자동 생성.

**알려진 이슈:** `.path.basenameNormalized` 렌더링 오류로 인한 중복 충돌 (kubectl에서 `duplicate name` 확인).

#### 3.3.2 Helm Charts (3종)

| 차트 | 용도 | 템플릿 구성 |
|------|------|-------------|
| `argocd-hello-world-templates` | 클러스터 검증용 nginx | deployment, service (NodePort) |
| `argocd-garmin-templates` | Garmin MCP 기본판 | deployment, service (ClusterIP), httproute |
| `argocd-project-templates` | Garmin MCP 완전판 | 위 + destination-rule (Istio), hpa, sealed-secret |

**argocd-project-templates**가 최종 프로덕션 차트입니다. 다른 템플릿 디렉토리는 레거시 또는 테스트용.

#### 3.3.3 Helm Values

**garmin-mcp-values.yaml:**
- HTTPS 종료 (Gateway API HTTPRoute)
- 리소스 제한 (requests/limits)
- HPA (min 2, max 10 pods)
- destinationRule (서킷브레이커)
- SealedSecret (Docker registry, project-secret)

**hello-world.yaml:**
- nginx 3 replicas (검증용)
- NodePort 서비스 (80/tcp)
- HPA (min 2, max 6 pods)

### 3.4 Garmin MCP 애플리케이션 (src/garmin_mcp/)

프로젝트의 핵심 애플리케이션인 **Garmin Connect MCP Server**는 Python 3.12 + MCP (Model Context Protocol)로 구현되었습니다.

#### 3.4.1 아키텍처

```
[Hermes Agent] ←(MCP tools)→ [Garmin MCP Server] ←(unofficial-garmin-api)→ [Garmin Connect API]
```

- **MCP Server:** FastMCP 프레임워크 (stdio + http/streamable-http 두 가지 전송 모드 지원)
- **K8s 배포:** `garmin-mcp-http` 진입점 (streamable-http, 포트 8000)
- **로컬 실행:** `garmin-mcp` 진입점 (stdio, Claude Desktop용)

#### 3.4.2 인증 (auth.py)

Garmin Connect OAuth2 로그인 프로세스:
1. `GET /auth/login-page` — 로그인 페이지에서 CSRF 토큰 추출
2. `POST /authn/client/auth/login` — 자격증명 제출 (username, password, client_id)
3. 응답에서 `sub` (response_token) 및 `oauthToken`, `oauthSecret` 추출

토글 2FA 지원:
- `TWO_FA_KEY` 환경변수로 HMAC 기반 OTP 생성
- 실패 시 `RequestAuthorizationUrl` 반환 (수동 2FA 코드 입력 필요)

#### 3.4.3 API 클라이언트 (client.py)

`unofficial-garmin-api` 라이브러리를 래핑한 클라이언트. 주요 기능:

| API | 용도 |
|-----|------|
| `get_activities()` | 활동 목록 (limit/offset分页) |
| `get_activity()` | 활동 상세 (summaryDTO, activityTypeDTO) |
| `get_activities_by_date()` | 날짜 range로 활동 조회 |
| `get_activity_splits()` | km/mile별 split 데이터 |
| `get_activity_weather()` | 활동 당시 날씨 |
| `get_activity_typed_splits()` | ClimbPro 구간 데이터 |
| `get_training_status()` | 현재 훈련 상태 |
| `get_training_readiness()` | 훈련 준비도 점수 |
| `get_max_metrics()` | VO2max, 최대 심박 등 |
| `get_fitnessage_data()` | 피트니스_age |
| `get_race_predictions()` | 5K/10K/HM/Marathon 예측 |
| `get_lactate_threshold()` |Attachment啦啦 |
| `get_endurance_score()` | 지구력 점수 |
| `get_hill_score()` | Hill score (climbing strength) |
| `get_running_tolerance()` | 주간 내구성 (부상 위험 지표) |
| `get_sleep_data()` | 수면 데이터 |
| `get_stress_data()` | 스트레스 점수 |
| `get_body_battery()` | Body Battery |
| `get_spo2_data()` | 혈중 산소 포화도 |
| `get_respiration_data()` | 호흡수 |
| `get_personal_record()` | 개인 기록 (1K~ Marathon) |
| `get_goals()` | 운동 목표 및 진행도 |

#### 3.4.4 MCP Tool 모듈 (총 44개 tools)

| 모듈 | tool 수 | 주요 기능 |
|------|---------|-----------|
| `activities.py` | 5 | 활동 목록, 날짜 range, 상세, split, 날씨, typed splits |
| `training.py` | 6 | 훈련 상태, 준비도, VO2max, race predictions, lactate threshold, training load |
| `wellness.py` | 3 | 수면, 일간 웰빙 (stress/body battery/SpO2/respiration), 주간 웰빙 요약 |
| `records.py` | 2 | 개인 기록, 목표 및 진행도 |
| `condition.py` | 8 | 컨디션 기록 (추가/조회), 컨디션 트렌드, 앱별 컨디션, 심박대 연결 |
| `gear.py` | 3 | 장비 목록, 장비 사용량, 장비 등록/수리 |
| `heart_rate.py` | 5 | 심박대 연결/해제, 연결 상태, 데이터 수집 |
| `summary.py` | 5 | 일간/주간/월간/년간 활동 요약, 주간活動趨勢 |
| `tcx.py` | 7 | TCX 파일 조작 (추가/삭제/수정) |
| `workout.py` | 8 | 운동处方 조회, 생성, 수정, 삭제 |

**총 49개 MCP Tool** (activities 5 + training 6 + wellness 3 + records 2 + condition 8 + gear 3 + heart_rate 5 + summary 5 + tcx 7 + workout 8 = 52).

> ※ 모dfications: activities 5 + training 6 + wellness 3 + records 2 + condition 8 + gear 3 + heart_rate 5 + summary 5 + tcx 7 + workout 8 = 52 tools.

#### 3.4.5 보안 (sanitize.py)

모든 Garmin API 응답에서 PII(개인 식별 정보)를 제거하는 sanitize 모듈이 적용되어 있습니다. `strip_pii()`는 `first_name`, `firstName`, `last_name`, `lastName`, `email`, `username`, `userId`, `userIdStr` 등 30여개의 PII 필드를 recursive하게 제거합니다.

### 3.5 Docker 및 빌드 파이프라인

**Dockerfile_garmin_mcp** (K8s용):
- `python:3.12-slim` 베이스
- `uv` 패키지 매니저 사용 (pyproject.toml + uv.lock)
- `/app` 작업 디렉토리
- `garmin-mcp-http` 진입점 (streamable-http, 포트 8000)
- `/health` 엔드포인트를 사용한 헬스체크

**Dockerfile_garmin_mcp_build** (로컬용):
- `garmin-mcp` PyPI 패키지를 직접 설치 (uv pip install --system)
- `garmin-mcp` 진입점 (stdio 모드)

### 3.6 Docker 이미지 전송 파이프라인

**garmin-mcp-build.yml:**
1. node-1에서 기존 `garmin_mcp:latest` 이미지 삭제
2. 로컬 소스 코드를 node-1의 `/opt/garmin-mcp/`로 복사
3. `Dockerfile_garmin_mcp`를 `Dockerfile`로 이름 변경
4. `docker build -t garmin_mcp:latest` 실행
5. `docker save`로 tarball (`/tmp/garmin-mcp-latest.tar`) 생성

**garmin-mcp-transfer.yml:**
1. node-1의 tarball을 로컬 컨트롤러로 scp.download (sshpass admin)
2. 로컬에서 node-2로 scp.upload
3. node-2에서 `docker load -i`로 이미지 로드
4. 양쪽 노드에서 tarball 정리

> ⚠️ **보안 이슈:** sshpass에 비밀번호 `admin`이 하드코딩되어 있음.

### 3.7 ApplicationSet 적용 파이프라인

**applicationset-apply-playbook.yml:**
1. `kubeconfig-setup` 역할: node-1에 admin.kubeconfig 복사
2. `applicationset-apply` 역할: `applicationset.yaml`을 kubectl로 클러스터에 적용

**argocd-cli-install-playbook.yml:**
- node-1에 ArgoCD CLI 설치

---

## 4. 현재 진행 상태

### 완료됨 (โค้드 작성 완료, 미검증)

| 레이어 | 내용 |
|--------|------|
| 0-infra | `make bootstrap` — VM clone, 정적 IP, bridged 네트워크 (실제 검증됨) |
| 1-cluster | 8개 Ansible 역할 (common → kubeadm → calico → metallb → gateway-api → istio → sealed-secrets → argocd) |
| 5-gitops | ApplicationSet + 3종 Helm chart (hello-world, garmin-basic, garmin-complete) |
| 5-gitops | Garmin MCP 애플리케이션 소스 코드 (52개 MCP Tool, 인증, API 클라이언트) |
| 5-gitops | Docker 빌드 + 이미지 전송 파이프라인 |
| 5-gitops | Bootstrap & Deploy 자동화 스크립트 |

### 미완료 / 미작성

| 항목 | 상태 |
|------|------|
| `2-services/` 폴더 | 미작성 — 서비스 정의 |
| `3-workloads/` 폴더 | 미작성 — 워크로드 정의 |
| `4-tools/` 폴더 | 미작성 — 도구 정의 |
| 1-cluster Ansible 플레이북 실행 | 미검증 — VM에 실제로 적용 안 해봄 |
| ArgoCD Application 상태 | 미검증 |
| Garmin MCP 실제 동작 | 미검증 |
| Istio Gateway API (HTTPRoute, DestinationRule) | 미검증 |
| Sealed Secrets | 미검증 (0-byte placeholder 파일 다수) |
| HPA (HorizontalPodAutoscaler) | 미검증 |

---

## 5. 알려진 문제점

### 5.1 인프라 관련

1. **machine-id clone 충돌:** `tart clone` 후 `/etc/machine-id`가 동일해 DHCP DUID 충돌 발생 → `cloud-init clean --machine-id`로 해결 (ies RELIEVED).
2. **노드2 IP 무응답:** netplan 적용 전 cloud-init이 완료되지 않아 정적 IP가 적용되지 않음 → `configure-network` 단계에서 해결.
3. **Bridged 네트워크:** `en8` (USB AX88179B) 인터페이스 사용 — `en0` 아님. 네트워크가 완전히 붙을 때까지 60초 대기 필요.

### 5.2 Ansible 관련

1. **모든 역할 미검증:** 8개 역할이 작성되었지만 VM에 실제 적용되지 않은 상태.
2. **sshpass 하드코딩:** `garmin-mcp-transfer.yml`에서 `sshpass -p 'admin'`으로 비밀번호가 코드에 고정됨.
3. **bootstrap-and-deploy.sh:** `ansible-playbook site.yml`만 호출 — 기존 playbook.yml과 동일하지만 5-gitops/의 별도 Ansible playbook들이 호출되지 않음.

### 5.3 Helm/ArgoCD 관련

1. **ApplicationSet duplicate name:** `.path.basenameNormalized` 렌더링 오류로 중복 충돌 발생.
2. **0-byte template 파일들:** `argocd-garmin-templates/templates/`의 `destination-rule.yaml`, `sealed-secret.yaml`이 존재하지만 내용이 비어 있음. (프로덕션 차트는 `argocd-project-templates`에 완성판 있음).
3. **SealedSecret values 누락:** 실제 encryptedData가 values 파일에 없고, ark村의 `secrets` 폴더는 리포지토리에 없음 (산 out of repo 관리 필요).

### 5.4 보안 관련

1. **sshpass 하드코딩:** bcrypt HMAC 키가 코드에 직접 노출.
2. ** 인증 토큰:** Garmin Connect OAuth 토큰은 Secret으로 관리하지만, `.env.example`이 리포지토리에 커밋됨.
3. **Docker registry credential:** `sealed-secret`로 관리해야 하지만 encryptedData가 누락.

---

## 6. Next Steps (권장 순서)

### Phase 1: 클러스터 검증 (우선순위 높음)

1. **`make bootstrap` 실행:** VM 기동, 정적 IP 적용, 네트워크 확인
2. **`ansible-playbook playbook.yml` 실행:** 8개 역할 적용
3. **`kubectl get nodes,pods -A` 확인:** 클러스터 상태 검증
4. **Calico CNI 확인:** pod 간 네트워크 통신 테스트
5. **MetalLB IP 확인:** `.206`~`.239` 중 IP 할당 확인
6. **ArgoCD Dashboard 확인:** ArgoCD UI 접근 및 Application 상태 확인
7. **Istio 확인:** `istio-system` 네임스페이스 pod 상태 확인

### Phase 2: Garmin MCP 배포

1. **`garmin-mcp-build.yml` 실행:** node-1에서 Docker 이미지 빌드
2. **`garmin-mcp-transfer.yml` 실행:** node-1 → node-2로 이미지 전송
3. **ApplicationSet 적용:** `applicationset-apply-playbook.yml` 실행
4. **ArgoCD에서 Garmin MCP Application 확인**
5. **Garmin Connect OAuth 설정:** `.env.example`에 실제 자격증명 적용
6. **MCP Server 연결 테스트:** `http://garmin-mcp.<namespace>.cluster.local:8000/health`

### Phase 3: 고도화

1. **`2-services/` 폴더 설계:** 마이크로서비스 정의
2. **`3-workloads/` 폴더 설계:** 워크로드 (Deployment, StatefulSet 등) 정의
3. **`4-tools/` 폴더 설계:** 개발/운영 도구 정의
4. **SealedSecret完善:** encryptedData 생성 및 values 파일에 적용
5. **HPA 검증:** 부하 테스트를 통한 자동 스케일링 확인

### Phase 4: 운영 안정화

1. **모니터링:** Prometheus/Grafana 구축 (Mimir/Loki 등)
2. **백업:** etcd, ArgoCD 애플리케이션 백업 자동화
3. ** disaster recovery:** VM snapstshot 기반 복구 절차 문서화

---

## 7. 코드 품질 분석

### 7.1 Garmin MCP 애플리케이션

| 항목 | 평가 | 비고 |
|------|------|------|
| PII 처리 | ✅ 우수 | `sanitize.py`가 모든 API 응답에서 30+ PII 필드를 제거 |
| API 래핑 | ✅ 우수 | `unofficial-garmin-api`를 잘 래핑한 `client.py` |
| Tool 모듈화 | ✅ 우수 | 10개 모듈, 52개 tool — 영역별 분류가 명확 |
| Dockerfile | ✅ 우수 | `uv` 캐시 활용, 레이어 최적화, 헬스체크 포함 |
| 인증 처리 | ✅ 우수 | OAuth2 + 2FA (HMAC OTP) 처리 |
| 에러 처리 | △ 보통 | `get_fitness_age()`, `get_wellness()` 등에서 `except Exception`으로 흡수 |
| 테스트 | ❌ 없음 | 테스트 코드, pytest, mock 없음 |

### 7.2 Ansible 역할

| 항목 | 평가 | 비고 |
|------|------|------|
| 역할 분리 | ✅ 우수 | common, kubeadm, calico, metallb 등 역할별 분리 |
| 변수 관리 | △ 보통 | `group_vars/all.yml`이 단순함 — 역할별 vars 부족 |
| 에러 처리 | △ 보통 | `failed_when: false`가 다수 (정당한 경우가 많으나) |
| 검증 | ❌ 없음 | Ansible lint, unittest 부족 |

### 7.3 Helm Charts

| 항목 | 평가 | 비고 |
|------|------|------|
| 차트 구조 | ✅ 우수 | standard Helm chart 구조 (Chart.yaml, templates/, values.yaml) |
| Gateway API | ✅ 우수 | HTTPRoute, DestinationRule (Istio) 반영 |
| SealedSecret | △ 보통 | 0-byte placeholder 다수 (프로덕션 차트에는 완성됨) |
| HPA | ✅ 우수 | min/max replica 설정 가능 |

---

## 8. 파일별 상세 통계

| 카테고리 | 파일 수 | 크기 (KB) | 주요 파일 |
|-----------|---------|-----------|-----------|
| Python (Garmin MCP) | 24 | 103 | activities.py (15KB), tcx.py (11KB), workout.py (10KB), client.py (7.5KB) |
| Helm Templates | 15 | 7 | project-templates (6개 템플릿), hello-world (2개), garmin (3개) |
| Ansible Playbooks | 9 | 22 | garmin-mcp-build.yml, garmin-mcp-transfer.yml |
| YAML Config | 5 | 5 | applicationset.yaml, values files |
| Documentation | 4 | 22 | PROJECT_STATUS.md, HISTORY.md, README.md |
| Shell/Other | 5 | 3 | bootstrap-and-deploy.sh |

---

## 9. 결론

이 프로젝트는 **인프라 코드 작성까지 완료되었으나 실제 실행 검증은 한 번도 수행되지 않은** 상태입니다.

Infra-as-Code (Tart VM → Kubeadm K8s → Calico → MetalLB → Istio → ArgoCD → Garmin MCP)의 전 과정을 자동화하는 데 이미 상당한 노력을 들였으며, 특히 **Garmin Connect MCP Server의 52개 MCP Tool**은 러닝, 훈련, 웰빙, 컨디션, 장비, 심박대, TCX 파일, 운동处方 등 Garmin Connect API의 거의 모든 기능을 MCP Tool로 exposing하고 있습니다.

**다음 단계는 `make bootstrap` 후 `ansible-playbook playbook.yml`을 실행하여 클러스터를 실제로 기동하고, Garmin MCP를 배포해 MCP Tool이 실제로 동작하는 것을 확인하는 것**입니다.

---

*이 보고서는 2026-10-02 기준 리포지토리 전체 소스 코드를 분석하여 작성하였습니다.*
