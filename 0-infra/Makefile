# 0-infra/Makefile — Tart VM 프로비저닝 (tart CLI 직접 래핑)
#
# 네트워킹: tart ip / ARP 리졸버가 bridged+Ubuntu Server 조합에서 공식 미해결 버그라
# (https://github.com/cirruslabs/tart/issues/460) 자동 IP조회에 의존하지 않는다.
# 흐름: 1) NAT로 최초 기동(make up) 2) 게스트에 정적 IP 주입(make configure-network)
#       3) bridged로 재기동(make bridged-up) — 이후 node-1/2 IP는 항상 고정값

export TART_HOME ?= /Users/blue/iac-project

IMAGE       ?= ghcr.io/cirruslabs/ubuntu:24.04
CPU_COUNT   ?= 4
MEMORY_MB   ?= 14336
DISK_GB     ?= 170
NODES       := node-1 node-2
INVENTORY   := ../1-cluster/ansible/inventory/hosts.ini

NET_IFACE   ?= en0        # macOS 호스트 브리지 인터페이스 — `networksetup -listallhardwareports`로 확인
SSH_USER    ?= admin
SSH_PASS    ?= admin      # Tart 공식 이미지 기본 계정(admin/admin) — 운영 전 교체 권장
SSH_OPTS    := -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null

NODE1_IP    := 192.168.0.201
NODE2_IP    := 192.168.0.202

.PHONY: all pull up down status ip inventory clean $(NODES) \
        configure-network configure-network-node-1 configure-network-node-2 bridged-up

all: up

## base 이미지 로컬 pull
pull:
	tart pull $(IMAGE)

## 개별 노드 생성 (clone + spec 적용). 이미 존재하면 스킵.
$(NODES): pull
	@if tart list --quiet | grep -qx "$@"; then \
		echo "$@ 이미 존재함 — clone 스킵"; \
	else \
		tart clone $(IMAGE) $@; \
		tart set $@ --cpu $(CPU_COUNT) --memory $(MEMORY_MB) --disk-size $(DISK_GB); \
	fi

## [1단계] node-1, node-2 NAT 모드로 생성 + 기동 (부트스트랩 전용 — tart ip가 여기서만 신뢰 가능)
up: $(NODES)
	tart run node-1 --no-graphics &
	tart run node-2 --no-graphics &
	@echo "NAT 모드로 부팅 중... 'make ip'로 확인 후 'make configure-network' 진행"

## 노드 상태 확인
status:
	tart list

## 노드 IP 확인 — NAT 부트스트랩 단계에서만 신뢰 가능. bridged 전환 후에는 NODE1_IP/NODE2_IP 고정값 사용.
ip:
	@echo "node-1: $$(tart ip node-1 --wait 60)"
	@echo "node-2: $$(tart ip node-2 --wait 60)"

## [2단계] NAT IP로 SSH 접속해 게스트에 정적 IP netplan 주입 (최초 1회, up 이후 실행)
configure-network: configure-network-node-1 configure-network-node-2

configure-network-node-1:
	@echo "[node-1] NAT IP 대기 중..."
	$(eval NATIP1 := $(shell tart ip node-1 --wait 60))
	@echo "[node-1] NAT IP=$(NATIP1) → 정적 IP $(NODE1_IP)로 전환"
	sshpass -p '$(SSH_PASS)' scp $(SSH_OPTS) netplan/node-1.yaml $(SSH_USER)@$(NATIP1):/tmp/99-static.yaml
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP1) '\
		sudo mkdir -p /etc/cloud/cloud.cfg.d && \
		echo "network: {config: disabled}" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg >/dev/null && \
		sudo rm -f /etc/netplan/50-cloud-init.yaml && \
		sudo mv /tmp/99-static.yaml /etc/netplan/99-static.yaml && \
		sudo netplan apply' || true
	@echo "[node-1] 정적 IP 적용 시도 완료 (netplan apply 순간 NAT 연결이 끊기는 것이 정상) — 'make down' 후 'make bridged-up'으로 진행"

configure-network-node-2:
	@echo "[node-2] NAT IP 대기 중..."
	$(eval NATIP2 := $(shell tart ip node-2 --wait 60))
	@echo "[node-2] NAT IP=$(NATIP2) → 정적 IP $(NODE2_IP)로 전환"
	sshpass -p '$(SSH_PASS)' scp $(SSH_OPTS) netplan/node-2.yaml $(SSH_USER)@$(NATIP2):/tmp/99-static.yaml
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP2) '\
		sudo mkdir -p /etc/cloud/cloud.cfg.d && \
		echo "network: {config: disabled}" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg >/dev/null && \
		sudo rm -f /etc/netplan/50-cloud-init.yaml && \
		sudo mv /tmp/99-static.yaml /etc/netplan/99-static.yaml && \
		sudo netplan apply' || true
	@echo "[node-2] 정적 IP 적용 시도 완료 (netplan apply 순간 NAT 연결이 끊기는 것이 정상) — 'make down' 후 'make bridged-up'으로 진행"

## [3단계] 정적 IP 적용 후: down 상태에서 bridged 모드로 재기동
bridged-up:
	tart run node-1 --net-bridged=$(NET_IFACE) --no-graphics &
	tart run node-2 --net-bridged=$(NET_IFACE) --no-graphics &
	@echo "bridged 기동됨 — node-1=$(NODE1_IP), node-2=$(NODE2_IP) (tart ip 조회 불필요/불신뢰)"

## 1-cluster/ansible용 인벤토리 생성 — bridged+정적 IP 확정 이후엔 고정값 사용 (tart ip 조회 안 함)
inventory:
	@mkdir -p $(dir $(INVENTORY))
	@echo "[control_plane]" > $(INVENTORY)
	@echo "node-1 ansible_host=$(NODE1_IP)" >> $(INVENTORY)
	@echo "" >> $(INVENTORY)
	@echo "[workers]" >> $(INVENTORY)
	@echo "node-2 ansible_host=$(NODE2_IP)" >> $(INVENTORY)
	@echo "인벤토리 생성됨: $(INVENTORY)"

## graceful 종료 (VM/디스크는 유지)
down:
	-tart stop node-1
	-tart stop node-2

## 완전 삭제 (VM/디스크 모두 제거)
clean: down
	-tart delete node-1
	-tart delete node-2
