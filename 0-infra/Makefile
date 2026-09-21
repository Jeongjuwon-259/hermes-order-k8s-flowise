# 0-infra/Makefile — Tart VM 프로비저닝 (tart CLI 직접 래핑)
#
# 네트워킹: tart ip / ARP 리졸버가 bridged+Ubuntu Server 조합에서 공식 미해결 버그라
# (https://github.com/cirruslabs/tart/issues/460) 자동 IP조회에 의존하지 않는다.
# 흐름: 1) NAT로 최초 기동(make up) 2) machine-id 재생성(make fix-identity)
#       3) 게스트에 정적 IP 주입(make configure-network) 4) bridged로 재기동(make bridged-up)
#       — 이후 node-1/2 IP는 항상 고정값. 전체 자동화는 `make bootstrap`.
#
# 각 단계의 순서/타이밍이 중요한 이유(재부팅 시 cloud-init이 netplan을 초기화하는 문제,
# machine-id 중복으로 인한 DHCP 충돌, 좀비 프로세스, ARP stale 캐시 등)는 실전
# 트러블슈팅으로 확정된 것이며, 상세 증상/원인/해결 서사는 저장소 루트의
# `HISTORY.md` §2에서 관리한다. 아래 각 타깃의 주석은 "왜 이 순서/방식이어야 하는지"만
# 간단히 남긴다 — 이 파일을 %-패턴 등으로 재구조화하기 전에 반드시 HISTORY.md §2를 먼저 읽을 것.

export TART_HOME ?= /Users/blue/iac-project

IMAGE       ?= ghcr.io/cirruslabs/ubuntu:24.04
CPU_COUNT   ?= 4
MEMORY_MB   ?= 14336
DISK_GB     ?= 170
NODES       := node-1 node-2
INVENTORY   := ../1-cluster/ansible/inventory/hosts.ini

# 실제 기본 게이트웨이로 나가는 물리 인터페이스를 자동 감지 (en0 하드코딩 금지 — HISTORY.md §2)
NET_IFACE   ?= $(shell route get default 2>/dev/null | awk '/interface:/{print $$2}')
SSH_USER    ?= admin
SSH_PASS    ?= admin
# ↑ Tart 공식 이미지 기본 계정(admin/admin) — 운영 전 교체 권장 (주석을 같은 줄에 달면
#   Makefile이 trailing space까지 값에 포함시켜 sshpass 인증이 깨진다 — 반드시 별도 줄로)
SSH_OPTS    := -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=6

NODE1_IP    := 192.168.0.201
NODE2_IP    := 192.168.0.202
# clean 시 known_hosts 정리 대상 — 두 IP 모두 포함 (HISTORY.md §2)
# NAT fallback: 192.168.64.x 대역 (node-1/node-2 NAT IP)
NODE1_IP_FALLBACK := 192.168.64.5 192.168.64.24

.PHONY: all pull up down status ip inventory clean $(NODES) \
        configure-network configure-network-node-1 configure-network-node-2 bridged-up \
        bootstrap verify fix-identity fix-identity-node-1 fix-identity-node-2

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

## [1단계] node-1, node-2 NAT 모드로 생성 + 기동 (부트스트랩 전용 — tart ip가 여기서만 신뢰 가능, 이미 실행 중이면 스킵)
## nohup으로 기동: make 프로세스 자체가 죽어도 VM 프로세스는 살아남아야 한다
up: $(NODES)
	@for n in $(NODES); do \
		if tart get $$n --format json 2>/dev/null | grep -q '"Running" *: *true'; then \
			echo "$$n 이미 실행 중 — run 스킵"; \
		else \
			nohup tart run $$n --no-graphics >/tmp/tart-$$n.log 2>&1 & disown; \
		fi; \
	done
	@echo "NAT 모드로 부팅 중... IP 획득 대기 (최대 120초)"
	@for n in $(NODES); do \
		for i in $(seq 1 24); do \
			IP=$$(tart ip $$n 2>/dev/null | head -1); \
			[ -n "$$IP" ] && echo "$$n NAT IP: $$IP" && break; \
			echo "$$n IP 대기 중... ($$i/24)"; \
			sleep 5; \
		done; \
	done
	@echo "NAT 부팅 완료. 'make configure-network' 진행"

## 노드 상태 확인
status:
	tart list

## 노드 IP 확인 — NAT 부트스트랩 단계에서만 신뢰 가능. bridged 전환 후에는 NODE1_IP/NODE2_IP 고정값 사용.
ip:
	@echo "node-1: $$(tart ip node-1 --wait 120)"
	@echo "node-2: $$(tart ip node-2 --wait 120)"

## [1.5단계] clone VM의 machine-id/DUID 중복 해결 (배경: HISTORY.md §2) — up 직후, configure-network 전에 실행.
## DHCP가 node-1/node-2를 같은 클라이언트로 착각해 lease를 충돌시키는 문제를 방지한다.
## cloud-init 공식 권장 방식(golden image clone 대응)으로 재부팅 시 고유 ID를 재생성시킨다.
fix-identity: fix-identity-node-1 fix-identity-node-2

fix-identity-node-1:
	@echo "[node-1] NAT IP 대기 중... (최대 120초)"
	@NATIP=$$(tart ip node-1 --wait 120); \
	if [ -z "$$NATIP" ]; then \
		echo "[node-1] ERROR: NAT IP 못 찾음"; \
		exit 1; \
	fi; \
	echo "[node-1] NAT IP=$$NATIP — machine-id 초기화 후 재부팅"; \
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP 'sudo cloud-init clean --machine-id && sudo reboot' || true; \
	echo "[node-1] 재부팅 중... 60초 대기 (cloud-init clean 재부팅은 오래 걸림)"; \
	sleep 60

fix-identity-node-2:
	@echo "[node-2] NAT IP 대기 중... (최대 120초)"
	@NATIP=$$(tart ip node-2 --wait 120); \
	if [ -z "$$NATIP" ]; then \
		echo "[node-2] ERROR: NAT IP 못 찾음"; \
		exit 1; \
	fi; \
	echo "[node-2] NAT IP=$$NATIP — machine-id 초기화 후 재부팅"; \
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP 'sudo cloud-init clean --machine-id && sudo reboot' || true; \
	echo "[node-2] 재부팅 중... 60초 대기 (cloud-init clean 재부팅은 오래 걸림)"; \
	sleep 60

## [2단계] NAT IP로 SSH 접속해 게스트에 정적 IP netplan 주입 (최초 1회, fix-identity 이후 실행)
## 주의(배경: HISTORY.md §2): scp 대신 ssh heredoc으로 원격에서 직접 파일 작성 —
## netplan generate로 문법 검증 -> apply까지 이 타깃 안에서 끝내고, 재부팅 없이
## 바로 down+bridged-up으로 넘어가야 한다. apply 후 실제 IP가 반영됐는지 확인하고
## 안 되면 자동 재시도한다 (cloud-init 재개입 대응).
configure-network: configure-network-node-1 configure-network-node-2

## 공통 로직은 define으로 뽑아 node-1/node-2 개별 구체 타깃에서 재사용한다.
## (%-패턴 규칙은 이 make 버전에서 no-op 버그가 있어 사용 금지 — HISTORY.md §2)
## (netplan apply 직후 NAT IP로 재검증하지 않는다 — 정상적으로도 실패함, HISTORY.md §2)
## $(1)=NODE, $(2)=TARGET_IP
define configure-network-body
	@NODE=$(1); TARGET_IP=$(2); \
	echo "[$$NODE] NAT IP 대기 중..."; \
	NATIP=$$(tart ip $$NODE --wait 120); \
	if [ -z "$$NATIP" ]; then echo "[$$NODE] ERROR: NAT IP 못 찾음"; exit 1; fi; \
	echo "[$$NODE] NAT IP=$$NATIP, 인터페이스명 확인 중..."; \
	IFNAME=$$(sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP "ip -o link show | awk -F': ' '{print \$$2}' | grep -v lo" | head -1); \
	if [ -z "$$IFNAME" ]; then \
		echo "[$$NODE] WARNING: 인터페이스명 못 찾음 — 'en*'로 매칭 시도"; \
		IFNAME=$$(sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP "ip -o link show | awk -F': ' '{print \$$2}' | grep -v lo | grep 'en'" | head -1); \
	fi; \
	if [ -z "$$IFNAME" ]; then echo "[$$NODE] ERROR: 인터페이스명 검색 실패 — 수동 확인 필요"; exit 1; fi; \
	echo "[$$NODE] 게스트 인터페이스=$$IFNAME -> 정적 IP $$TARGET_IP로 전환"; \
	echo "[$$NODE] 파일 쓰기 중..."; \
	NETPLAN_YAML="network:\n  version: 2\n  ethernets:\n    $$IFNAME:\n      dhcp4: no\n      addresses: [$$TARGET_IP/24]\n      routes: [{to: default, via: 192.168.0.1}]\n      nameservers: {addresses: [168.126.63.1, 168.126.63.2]}\n"; \
	printf "$$NETPLAN_YAML" | sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP ' \
		printf "network: {config: disabled}\n" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg >/dev/null && \
		sudo tee /etc/netplan/99-static.yaml >/dev/null && \
		sudo chmod 600 /etc/netplan/99-static.yaml && \
		sudo rm -f /etc/netplan/50-cloud-init.yaml && \
		sudo test -s /etc/netplan/99-static.yaml && \
		sudo test -s /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg && \
		echo WRITE_VERIFIED_OK'; \
	STATUS=$$?; \
	if [ "$$STATUS" -ne 0 ]; then echo "[$$NODE] ERROR: netplan 파일 쓰기 실패 (exit $$STATUS)"; exit 1; fi; \
	echo "[$$NODE] netplan generate 중..."; \
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP 'sudo netplan generate 2>&1 && echo GENERATE_OK'; \
	if [ "$$?" -ne 0 ]; then echo "[$$NODE] ERROR: netplan generate 실패"; exit 1; fi; \
	echo "[$$NODE] netplan apply 실행 (SSH 끊김은 정상)..."; \
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$NATIP \
		'sudo netplan apply 2>&1; echo APPLY_COMPLETED' || echo "[$$NODE] SSH 연결 끊김 (netplan apply 적용 중 — 정상)"; \
	echo "[$$NODE] netplan apply 완료 대기 중 (5초)..."; \
	sleep 5
endef

configure-network-node-1:
	$(call configure-network-body,node-1,$(NODE1_IP))

configure-network-node-2:
	$(call configure-network-body,node-2,$(NODE2_IP))

## [3단계] 정적 IP 적용 직후(재부팅 없이!) down 상태에서 bridged 모드로 재기동
## 이미 실행 중이면 스킵. bridged 기동 후 IP 응답까지 30~40초 소요될 수 있음.
bridged-up:
	@for n in $(NODES); do \
		if tart get $$n --format json 2>/dev/null | grep -q '"Running" *: *true'; then \
			echo "$$n 이미 실행 중 — run 스킵"; \
		else \
			nohup tart run $$n --net-bridged=$(NET_IFACE) --no-graphics >/tmp/tart-$$n.log 2>&1 & disown; \
		fi; \
	done
	@echo "bridged 기동됨 — node-1=$(NODE1_IP), node-2=$(NODE2_IP) (NET_IFACE=$(NET_IFACE))"
	@echo "IP 응답 대기 중... (최대 120초)"
	@for ip in $(NODE1_IP) $(NODE2_IP); do \
		for i in $(seq 1 24); do \
			ping -c 1 -t 2 $$ip >/dev/null 2>&1 && echo "$$ip 응답 확인" && break; \
			echo "$$ip 대기 중... ($$i/24)"; \
			sleep 5; \
		done; \
	done
	@echo "bridged 부팅 완료"

## 부트스트랩 전체 자동화: up -> fix-identity -> configure-network -> down -> bridged-up -> verify
## VM을 지웠다가 처음부터 다시 만들 때 이 타깃 하나로 끝까지 간다.
bootstrap: up
	@echo "NAT 부팅 완료, machine-id 중복 해결 전 60초 대기..."
	@sleep 60
	$(MAKE) fix-identity
	@echo "machine-id 재생성 완료, 정적 IP 주입 전 30초 대기..."
	@sleep 30
	$(MAKE) configure-network
	@echo "netplan apply 완료, 재부팅 없이 bridged로 전환 전 안정화 대기(마지막 노드는 apply 반영 시간이 상대적으로 짧으므로 여유있게 대기, HISTORY.md §2)..."
	@sleep 30
	$(MAKE) down
	@sleep 10
	$(MAKE) bridged-up
	@echo "bridged 부팅 대기 120초..."
	@sleep 120
	$(MAKE) verify

## bridged 정적 IP 응답 확인 (ping + ssh)
verify:
	@for ip in $(NODE1_IP) $(NODE2_IP); do \
		echo "--- $$ip ---"; \
		ping -c 3 -t 10 $$ip || echo "[FAIL] $$ip ping 실패"; \
		sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$$ip 'hostname' || echo "[FAIL] $$ip ssh 실패"; \
	done

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
## tart stop만으로는 이전 nohup/disown 프로세스가 좀비로 남을 수 있으므로(HISTORY.md §2),
## stop 이후 실제 프로세스 종료 여부를 확인하고 남아있으면 강제 종료한다.
down:
	-tart stop node-1
	-tart stop node-2
	@sleep 2
	@for n in $(NODES); do \
		PIDS=$$(pgrep -f "tart run $$n " 2>/dev/null); \
		if [ -n "$$PIDS" ]; then \
			echo "[$$n] WARNING: stop 이후에도 프로세스가 남아있음(PID: $$PIDS) — 강제 종료"; \
			kill -9 $$PIDS 2>/dev/null || true; \
		fi; \
	done

## 완전 삭제 (VM/디스크 모두 제거)
## [개선] 삭제 시 known_hosts에서 관련 IP의 호스트 키도 자동 정리 —
##  재부팅/재설치 시 "REMOTE HOST IDENTIFICATION HAS CHANGED" 오류 방지 (HISTORY.md §2).
clean: down
	-tart delete node-1
	-tart delete node-2
	@echo "[clean] known_hosts 정리 (노드 IP + NAT fallback)"; \
	for ip in $(NODE1_IP) $(NODE2_IP) $(NODE1_IP_FALLBACK); do \
		ssh-keygen -R $$ip >/dev/null 2>&1 || true; \
	done
