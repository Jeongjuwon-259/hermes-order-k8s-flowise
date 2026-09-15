# 0-infra/Makefile — Tart VM 프로비저닝 (tart CLI 직접 래핑)
#
# Terraform의 cirruslabs/tart provider는 실존하지 않음을 확인 (2026-09-15) —
# 선언적 Terraform 대신, tart CLI를 감싼 이 Makefile로 VM 생명주기를 관리한다.

IMAGE      ?= ghcr.io/cirruslabs/ubuntu:24.04
CPU_COUNT  ?= 4
MEMORY_MB  ?= 14336
DISK_GB    ?= 170
NODES      := node-1 node-2
INVENTORY  := ../1-cluster/ansible/inventory/hosts.ini

.PHONY: all pull up down status ip inventory clean $(NODES)

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

## node-1, node-2 생성 + 백그라운드 기동
up: $(NODES)
	tart run node-1 --no-graphics &
	tart run node-2 --no-graphics &
	@echo "부팅 대기 중... 'make ip'로 확인"

## 노드 상태 확인
status:
	tart list

## 노드 IP 확인 (부팅 완료까지 대기)
ip:
	@echo "node-1: $$(tart ip node-1 --wait 60)"
	@echo "node-2: $$(tart ip node-2 --wait 60)"

## 1-cluster/ansible용 동적 인벤토리 생성
inventory:
	@mkdir -p $(dir $(INVENTORY))
	@echo "[control_plane]" > $(INVENTORY)
	@echo "node-1 ansible_host=$$(tart ip node-1 --wait 60)" >> $(INVENTORY)
	@echo "" >> $(INVENTORY)
	@echo "[workers]" >> $(INVENTORY)
	@echo "node-2 ansible_host=$$(tart ip node-2 --wait 60)" >> $(INVENTORY)
	@echo "인벤토리 생성됨: $(INVENTORY)"

## graceful 종료 (VM/디스크는 유지)
down:
	-tart stop node-1
	-tart stop node-2

## 완전 삭제 (VM/디스크 모두 제거)
clean: down
	-tart delete node-1
	-tart delete node-2
