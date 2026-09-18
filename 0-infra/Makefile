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
#    반드시 "netplan apply -> (재부팅 없이) 곧바로 tart stop -> bridged 모드로 tart run"
#    순서를 지켜야 한다. 중간에 NAT 상태로 재부팅하면 cloud-init이 다시 개입해 실패한다.
# 4. netplan apply 실행 후 SSH 연결이 끊기는 것이 정상 — 하지만 완료 여부를 확인하지 않고
#    바로 죽이면 파일 write가 덜 끝난 채 stop될 수 있다. `sudo netplan generate`로 먼저
#    문법 검증 후 apply하고, apply 명령 자체가 끝나길(SSH 세션 종료) 기다린 뒤 stop한다.
# 5. bridged-up 이후 ping이 바로 안 뜰 수 있음 — 최소 30~40초 대기 후 재확인.
# 6. `tart run ... &`를 make 자식 프로세스로만 띄우면, make 자체가 kill되거나
#    타임아웃될 때 VM 프로세스까지 같이 죽는다. 반드시 `nohup ... & disown`으로
#    쉘/make의 프로세스 그룹에서 완전히 분리해서 기동한다.
# 7. clone 직후 node-1/node-2는 /etc/machine-id가 동일함. systemd-networkd DHCPv4의
#    기본 ClientIdentifier=duid는 이 machine-id를 해시해서 만들어지므로, 두 VM이
#    macOS DHCP 서버에게 "같은 클라이언트"로 보여 lease가 충돌/오염될 수 있다
#    (node-2 bridged 무응답 이슈의 유력 원인, KNOWN_ISSUES.md 참고). NAT 부팅 직후
#    `cloud-init clean --machine-id` + 재부팅으로 고유 ID를 재생성시킨다(fix-identity).
#    이 재부팅은 안전함 — 아직 netplan static 설정 전이라 교훈#3의 위험과 무관.
#
# --- 2026-09-18 재발 트러블슈팅에서 추가로 확정된 교훈 (반드시 유지) ---
# 8. **`tart stop`으로 VM을 내려도, `nohup tart run ... & disown`으로 띄운 이전
#    프로세스가 그대로 좀비/유령 프로세스로 남아있는 경우가 있다.** 이 상태에서
#    bridged 모드로 새 `tart run`을 또 띄우면 같은 VM 디스크에 대해 프로세스가
#    사실상 중복 실행되어(구 NAT 프로세스 + 신규 bridged 프로세스) 네트워크가
#    꼬여 ping/ssh가 전부 응답하지 않는다. `down`/재기동 전에는 반드시
#    `ps aux | grep "tart run"`으로 대상 VM 이름의 프로세스가 실제로 종료됐는지
#    확인하고, 남아있으면 `kill -9`로 확실히 제거한 뒤 새로 기동한다.
# 9. **macOS ARP 캐시에 REJECT 플래그가 낀 stale 엔트리가 있으면 ping/ssh가
#    "No route to host"/timeout으로 막힌다** (`route get <ip>`로 REJECT 플래그
#    확인 가능). VM을 재기동해도 macOS 쪽 ARP 캐시가 자동으로 안 지워질 수 있으니
#    응답이 없으면 `sudo arp -d <ip>`로 캐시를 지우고 재시도한다(사용자 sudo 필요 —
#    비밀번호를 스크립트/에이전트가 대신 입력하지 말 것).
# 10. **주의: netplan apply 직후 NAT IP로 재접속해서 "정적 IP가 반영됐는지"를
#    검증하려는 시도는 그 자체가 오판을 유발한다.** 정적 IP를 적용하는 순간
#    게스트 인터페이스에서 NAT 주소(192.168.64.x) 자체가 사라지므로, apply 후
#    NAT IP로의 SSH/재확인은 (아직 bridged 전환 전이라) 항상 실패하는 게 정상
#    동작이다. 이걸 "cloud-init이 설정을 초기화했다"는 신호로 착각해 재시도
#    루프를 넣었다가 오히려 정상 케이스를 실패 처리해서 부트스트랩을 깨뜨린
#    사고가 있었다(2026-09-18). **netplan apply 이후의 실제 검증은 반드시
#    bridged-up 이후 TARGET_IP(192.168.0.20x)로 ping/ssh하는 `verify` 단계에서만
#    할 것 — NAT IP로 되돌아가서 확인하지 말 것.**
# 11. **make 3.81(macOS 기본 CommandLineTools make)은 이 Makefile 조합에서
#    암묵적 패턴 규칙(`configure-network-node-%:`)의 레시피를 실행하지 않고
#    "Nothing to be done for ..."을 내며 조용히 no-op 처리하는 버그가 있다**
#    (`make --debug=b`로 "Successfully remade target file" 로그는 나오는데 실제
#    레시피는 안 도는 것으로 확인됨). 따라서 node-1/node-2 로직은 반드시 개별
#    구체 타깃(configure-network-node-1, configure-network-node-2)으로 유지하고,
#    공통 로직은 `define ... endef` + `$(call ...)`로 재사용한다. %-패턴 규칙으로
#    다시 리팩터링하지 말 것.

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
## nohup으로 기동: make 프로세스 자체가 죽어도 VM 프로세스는 살아남아야 한다(교훈 #6)
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

## [1.5단계] clone VM의 machine-id/DUID 중복 해결 (교훈 #7) — up 직후, configure-network 전에 실행.
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
## 주의(교훈 #2,#3,#4,#10): scp 대신 ssh heredoc으로 원격에서 직접 파일 작성 —
## netplan generate로 문법 검증 -> apply까지 이 타깃 안에서 끝내고, 재부팅 없이
## 바로 down+bridged-up으로 넘어가야 한다. apply 후 실제 IP가 반영됐는지 확인하고
## 안 되면 자동 재시도한다 (cloud-init 재개입 대응).
configure-network: configure-network-node-1 configure-network-node-2

## 공통 로직은 define으로 뽑아 node-1/node-2 개별 구체 타깃에서 재사용한다.
## (교훈 #11: %-패턴 규칙은 이 make 버전에서 no-op 버그가 있어 사용 금지)
## (교훈 #10: netplan apply 직후 NAT IP로 재검증하지 않는다 — 정상적으로도 실패함)
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
	@echo "netplan apply 완료, 재부팅 없이 bridged로 전환 전 안정화 대기(교훈 #12: 마지막 노드는 apply 반영 시간이 상대적으로 짧으므로 여유있게 대기)..."
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
## 교훈 #8: tart stop만으로는 이전 nohup/disown 프로세스가 좀비로 남을 수 있으므로,
## stop 이후 실제 프로세스 종료 여부를 확인하고 남아있으면 강제 종료한다.
down:
	-tart stop node-1
	-tart stop node-2
	@sleep 2
	@for n in $(NODES); do \
		PIDS=$$(pgrep -f "tart run $$n " 2>/dev/null); \
		if [ -n "$$PIDS" ]; then \
			echo "[$$n] WARNING: stop 이후에도 프로세스가 남아있음(PID: $$PIDS) — 강제 종료(교훈 #8)"; \
			kill -9 $$PIDS 2>/dev/null || true; \
		fi; \
	done

## 완전 삭제 (VM/디스크 모두 제거)
clean: down
	-tart delete node-1
	-tart delete node-2
