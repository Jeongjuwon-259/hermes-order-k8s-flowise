# 0-infra/Makefile — Tart VM 프로비저닝 (tart CLI 직접 래핑)
#
# 네트워킹: tart ip / ARP 리졸버가 bridged+Ubuntu Server 조합에서 공식 미해결 버그라
# (https://github.com/cirruslabs/tart/issues/460) 자동 IP조회에 의존하지 않는다.
# 흐름: 1) NAT로 최초 기동(make up) 2) 게스트에 정적 IP 주입(make configure-network)
#       3) bridged로 재기동(make bridged-up) — 이후 node-1/2 IP는 항상 고정값
#
# --- 2026-09-16 실전 트러블슈팅에서 확정된 교훈 (재발 방지, 반드시 유지) ---
# 1. NET_IFACE 하드코딩 금지: en0는 이 Mac mini에서 media: none(미연결) 상태였고,
#    실제 인터넷 붙은 물리 인터페이스는 en8(USB 이더넷)이었다. `route get default`로
#    실제 게이트웨이 인터페이스를 자동 감지해서 쓴다 (아래 NET_IFACE 참조).
# 2. scp로 netplan yaml을 옮기면 간헐적으로 0바이트/손상된 파일이 된다(원인 미상 —
#    아마 mv 타이밍이나 cloud-init 경합). ssh heredoc(`cat <<EOF | sudo tee ...`)으로
#    원격에서 직접 파일을 써서 손상 위험을 없앤다.
# 3. **cloud-init이 재부팅마다 /etc/netplan/*, /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
#    를 초기화(리셋)한다.** 즉 "netplan apply 후 reboot/재기동을 거치면" 설정이 날아간다.
#    반드시 "netplan apply → (재부팅 없이) 곧바로 tart stop → bridged 모드로 tart run"
#    순서를 지켜야 한다. 중간에 NAT 상태로 재부팅하면 cloud-init이 다시 개입해 실패한다.
# 4. netplan apply 실행 후 SSH 연결이 끊기는 것이 정상 — 하지만 완료 여부를 확인하지 않고
#    바로 죽이면 파일 write가 덜 끝난 채 stop될 수 있다. `sudo netplan generate`로 먼저
#    문법 검증 후 apply하고, apply 명령 자체가 끝나길(SSH 세션 종료) 기다린 뒤 stop한다.
# 5. bridged-up 이후 ping이 바로 안 뜰 수 있음 — 최소 30~40초 대기 후 재확인.
# 6. `tart run ... &`를 make 자식 프로세스로만 띄우면, make 자체가 kill되거나
#    타임아웃될 때 VM 프로세스까지 같이 죽는다. 반드시 `nohup ... & disown`으로
#    쉘/make의 프로세스 그룹에서 완전히 분리해서 기동한다.

export TART_HOME ?= /Users/blue/iac-project

IMAGE       ?= ghcr.io/cirruslabs/ubuntu:24.04
CPU_COUNT   ?= 4
MEMORY_MB   ?= 14336
DISK_GB     ?= 170
NODES       := node-1 node-2
INVENTORY   := ../1-cluster/ansible/inventory/hosts.ini

# 실제 기본 게이트웨이로 나가는 물리 인터페이스를 자동 감지 (en0 하드코딩 금지 — 교훈 #1)
NET_IFACE   ?= $(shell route get default 2>/dev/null | awk '/interface:/{print $$2}')
SSH_USER    ?= admin
SSH_PASS    ?= admin
# ↑ Tart 공식 이미지 기본 계정(admin/admin) — 운영 전 교체 권장 (주석을 같은 줄에 달면
#   Makefile이 trailing space까지 값에 포함시켜 sshpass 인증이 깨진다 — 반드시 별도 줄로)
SSH_OPTS    := -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ConnectTimeout=10 -o ServerAliveInterval=5 -o ServerAliveCountMax=6

NODE1_IP    := 192.168.0.201
NODE2_IP    := 192.168.0.202

.PHONY: all pull up down status ip inventory clean $(NODES) \
        configure-network configure-network-node-1 configure-network-node-2 bridged-up \
        bootstrap verify

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
## nohup으로 기동: make 프로세스 자체가 죽어도 VM 프로세스는 살아남아야 한다(교훈 #6)
up: $(NODES)
	@for n in $(NODES); do \
		if tart get $$n --format json 2>/dev/null | grep -q '"Running" *: *true'; then \
			echo "$$n 이미 실행 중 — run 스킵"; \
		else \
			nohup tart run $$n --no-graphics >/tmp/tart-$$n.log 2>&1 & disown; \
		fi; \
	done
	@echo "NAT 모드로 부팅 중... 'make ip'로 확인 후 'make configure-network' 진행"

## 노드 상태 확인
status:
	tart list

## 노드 IP 확인 — NAT 부트스트랩 단계에서만 신뢰 가능. bridged 전환 후에는 NODE1_IP/NODE2_IP 고정값 사용.
ip:
	@echo "node-1: $$(tart ip node-1 --wait 60)"
	@echo "node-2: $$(tart ip node-2 --wait 60)"

## [2단계] NAT IP로 SSH 접속해 게스트에 정적 IP netplan 주입 (최초 1회, up 이후 실행)
## 주의(교훈 #2,#3,#4): scp 대신 ssh heredoc으로 원격에서 직접 파일 작성 —
## netplan generate로 문법 검증 → apply까지 이 타깃 안에서 끝내고, 재부팅 없이
## 바로 down+bridged-up으로 넘어가야 한다 (NAT 상태로 재부팅하면 cloud-init이
## 설정을 다시 초기화해서 실패한다).
configure-network: configure-network-node-1 configure-network-node-2

configure-network-node-1:
	@echo "[node-1] NAT IP 대기 중..."
	$(eval NATIP1 := $(shell tart ip node-1 --wait 60))
	@echo "[node-1] NAT IP=$(NATIP1), 인터페이스명 확인 중..."
	$(eval IFNAME1 := $(shell sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP1) "ip -o link show | awk -F': ' '{print \$$2}' | grep -v lo" | head -1))
	@echo "[node-1] 게스트 인터페이스=$(IFNAME1) → 정적 IP $(NODE1_IP)로 전환"
	@# 1) 파일만 먼저 쓰고 즉시 크기 검증 (netplan apply와 분리 — SSH가 중간에 끊겨도 재시도 가능)
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP1) ' \
		printf "network: {config: disabled}\n" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg >/dev/null && \
		{ \
			printf "network:\n"; \
			printf "  version: 2\n"; \
			printf "  ethernets:\n"; \
			printf "    $(IFNAME1):\n"; \
			printf "      dhcp4: no\n"; \
			printf "      addresses: [$(NODE1_IP)/24]\n"; \
			printf "      routes: [{to: default, via: 192.168.0.1}]\n"; \
			printf "      nameservers: {addresses: [168.126.63.1, 168.126.63.2]}\n"; \
		} | sudo tee /etc/netplan/99-static.yaml >/dev/null && \
		sudo chmod 600 /etc/netplan/99-static.yaml && \
		sudo rm -f /etc/netplan/50-cloud-init.yaml && \
		sudo test -s /etc/netplan/99-static.yaml && \
		sudo test -s /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg && \
		echo WRITE_VERIFIED_OK'
	@# 2) netplan generate/apply는 별도 SSH 호출 + nohup으로 세션 종료와 분리 (apply가 SSH를 끊어도 명령 자체는 끝까지 실행됨)
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP1) \
		'sudo netplan generate && sudo nohup netplan apply >/tmp/netplan-apply.log 2>&1 & disown; sleep 2; echo APPLY_TRIGGERED' \
		|| echo "[node-1] SSH 연결 끊김 감지 (정상 — apply는 백그라운드에서 계속 진행됨)"

configure-network-node-2:
	@echo "[node-2] NAT IP 대기 중..."
	$(eval NATIP2 := $(shell tart ip node-2 --wait 60))
	@echo "[node-2] NAT IP=$(NATIP2), 인터페이스명 확인 중..."
	$(eval IFNAME2 := $(shell sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP2) "ip -o link show | awk -F': ' '{print \$$2}' | grep -v lo" | head -1))
	@echo "[node-2] 게스트 인터페이스=$(IFNAME2) → 정적 IP $(NODE2_IP)로 전환"
	@# 1) 파일만 먼저 쓰고 즉시 크기 검증 (netplan apply와 분리 — SSH가 중간에 끊겨도 재시도 가능)
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP2) ' \
		printf "network: {config: disabled}\n" | sudo tee /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg >/dev/null && \
		{ \
			printf "network:\n"; \
			printf "  version: 2\n"; \
			printf "  ethernets:\n"; \
			printf "    $(IFNAME2):\n"; \
			printf "      dhcp4: no\n"; \
			printf "      addresses: [$(NODE2_IP)/24]\n"; \
			printf "      routes: [{to: default, via: 192.168.0.1}]\n"; \
			printf "      nameservers: {addresses: [168.126.63.1, 168.126.63.2]}\n"; \
		} | sudo tee /etc/netplan/99-static.yaml >/dev/null && \
		sudo chmod 600 /etc/netplan/99-static.yaml && \
		sudo rm -f /etc/netplan/50-cloud-init.yaml && \
		sudo test -s /etc/netplan/99-static.yaml && \
		sudo test -s /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg && \
		echo WRITE_VERIFIED_OK'
	@# 2) netplan generate/apply는 별도 SSH 호출 + nohup으로 세션 종료와 분리
	sshpass -p '$(SSH_PASS)' ssh $(SSH_OPTS) $(SSH_USER)@$(NATIP2) \
		'sudo netplan generate && sudo nohup netplan apply >/tmp/netplan-apply.log 2>&1 & disown; sleep 2; echo APPLY_TRIGGERED' \
		|| echo "[node-2] SSH 연결 끊김 감지 (정상 — apply는 백그라운드에서 계속 진행됨)"

## [3단계] 정적 IP 적용 직후(재부팅 없이!) down 상태에서 bridged 모드로 재기동
## 이미 실행 중이면 스킵. bridged 기동 후 IP 응답까지 30~40초 소요될 수 있음(교훈 #5).
bridged-up:
	@for n in $(NODES); do \
		if tart get $$n --format json 2>/dev/null | grep -q '"Running" *: *true'; then \
			echo "$$n 이미 실행 중 — run 스킵"; \
		else \
			nohup tart run $$n --net-bridged=$(NET_IFACE) --no-graphics >/tmp/tart-$$n.log 2>&1 & disown; \
		fi; \
	done
	@echo "bridged 기동됨 — node-1=$(NODE1_IP), node-2=$(NODE2_IP) (NET_IFACE=$(NET_IFACE))"
	@echo "30~40초 후 'make verify'로 응답 확인할 것 (tart ip 조회는 불신뢰)"

## 부트스트랩 전체 자동화: up → configure-network → down → bridged-up → verify
## VM을 지웠다가 처음부터 다시 만들 때 이 타깃 하나로 끝까지 간다.
bootstrap: up
	@echo "NAT 부팅 완료, 정적 IP 주입 전 20초 대기..."
	@sleep 20
	$(MAKE) configure-network
	@echo "netplan apply 완료, 재부팅 없이 bridged로 전환..."
	@sleep 5
	$(MAKE) down
	@sleep 3
	$(MAKE) bridged-up
	@echo "bridged 부팅 대기 40초..."
	@sleep 40
	$(MAKE) verify

## bridged 정적 IP 응답 확인 (ping + ssh)
verify:
	@for ip in $(NODE1_IP) $(NODE2_IP); do \
		echo "--- $$ip ---"; \
		ping -c 2 -t 3 $$ip || echo "[FAIL] $$ip ping 실패"; \
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
down:
	-tart stop node-1
	-tart stop node-2

## 완전 삭제 (VM/디스크 모두 제거)
clean: down
	-tart delete node-1
	-tart delete node-2
