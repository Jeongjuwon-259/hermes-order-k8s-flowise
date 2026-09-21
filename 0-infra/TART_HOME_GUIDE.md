# TART_HOME 가이드 — Tart VM 위치 통일 및 중복 방지

---

## 0. 핵심 문제

기존에 Tart VM이 두 곳에 동시에 존재할 수 있었음:

- `~/.tart` (Tart 기본 위치)
- `/Users/blue/iac-project` (Makefile에서 `export TART_HOME`으로 지정한 위치)

둘 다 `tart list`에서 별도로 취급되어 `make clean`이 한 곳만 정리하고 다른 곳에 VM이 남아있는 문제가 발생함.

---

## 1. 최종 설정: TART_HOME = /Users/blue/tart-home

Makefile, 문서 파일, 셸 명령어 등 모든 곳에서 통일:

```bash
# Makefile (line 15)
export TART_HOME ?= /Users/blue/tart-home

# 셸 환경 (bootstrap-and-deploy.sh)
export TART_HOME=/Users/blue/tart-home
```

**중요**: `/Users/blue/tart-home` (셸 환경에서 `TART_HOME` 설정 필요)

---

## 2. 디렉토리 구조

```
/Users/blue/tart-home/
├── vms/
│   ├── node-1/
│   │   ├── config.json
│   │   ├── control.sock
│   │   ├── disk.img
│   │   └── nvram.bin
│   └── node-2/
│       ├── config.json
│       ├── control.sock
│       ├── disk.img
│       └── nvram.bin
├── tmp/
└── cache/
```

---

## 3. 명령어별 동작 확인

```bash
# 1. 정상 tart list (TART_HOME이 설정된 상태)
TART_HOME=/Users/blue/tart-home tart list

# 2. 기본 tart list (TART_HOME 미설정 → ~/.tart 조회)
#    → VM이 표시되지 않음 (기존 ~/.tart 디렉토리 존재하면 OCI 이미지만 표시)

# 3. Makefile에서 export TART_HOME이 설정됨
make -p | grep TART_HOME
```

---

## 4. 문제 시나리오 & 해결

### 4.1. VM이 `tart list`에 안 뜨는 경우

```bash
# 원인: TART_HOME이 기본 ~/.tart를 조회 중
TART_HOME=/Users/blue/tart-home tart list  # ← 명시적 지정
```

### 4.2. `make clean`으로 VM 삭제 후 재구성은 반드시 `make bootstrap`

```bash
cd 0-infra
make clean    # VM 삭제 + known_hosts 정리 + TART_HOME 디렉토리 삭제
make bootstrap # up → fix-identity → configure-network → bridged-up → verify
```

### 4.3. `tart-home` 디렉토리가 없는 경우

`make clean`은 TART_HOME 전체 디렉토리를 삭제합니다. 재실행 시 `make bootstrap`이 새로운 `tart-home`을 생성합니다.

**확인 방법**:

```bash
ls -la /Users/blue/tart-home/
# 디렉토리가 없으면 Makefile에서 export 하므로 bootstrap이 새로 생성함
```

---

## 5. Makefile 관전 사항

- Makefile에서 `export TART_HOME`이 반드시 세션 전역에서 설정됨 (Makefile이 직접 export함).
- 직접 명령어를 실행할 때 `TART_HOME=/Users/blue/tart-home` 명시 필요.
- `TART_HOME`이 `/Users/blue/tart-home`로 반드시 입력되어야 함 (`.blue` 아님).

---

## 6. 각 타깃의 주요 흐름

```
make bootstrap:
  up → fix-identity → configure-network → bridged-up → verify
    |                      |                         |
    1.tart create          2.cloud-init              3.netplan Apply
    2.tart ip (NAT)        4.statis IP 설정            5.bridge IP 획득

make clean:
  down → delete → known_hosts 정리 → TART_HOME 삭제 → ~/.tart 삭제
    |                     |
    tart stop             tart delete
    pgkill zombie 프로세스 known_hosts 에서 노드IP, NATIP 정리
```

---

## 7. 참고 사항

- MAC 주소: node-1=`7a:79:ab:dd:65:bd`, node-2=`2a:3:89:df:4c:d7`
- 고정 IP: node-1=`192.168.0.201`, node-2=`192.168.0.202` (netplan 정적 IP)
- Bridge 인터페이스: `en8` (USB AX88179B)
- 게이트웨이: iptime BE3600QCA (192.168.0.1)
- `tart ip`는 bridged+Ubuntu Server 조합에서 공식 버그 (cirruslabs/tart#460)
  → netplan 정적 IP로 해결.
- `make bootstrap` 후 60초 대기 필수 (네트워크가 완전히 붙을 때까지).
- TART_HOME이 기본값(`~/.tart`)과 달라서 VM을 확인하려면 반드시 `TART_HOME=/Users/blue/tart-home tart list` 실행 필요.
