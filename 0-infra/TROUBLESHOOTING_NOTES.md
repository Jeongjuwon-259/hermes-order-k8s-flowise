# 0-infra 참고 메모 (트러블슈팅 힌트)

과거 작업 중 겪었던 문제와 근본 원인, 해결 방법을 기록. 인프라 재구성/디버깅 시 참고.

## [해결됨] node-2 bridged 모드 무응답 — clone된 VM의 machine-id 충돌

### 증상
`tart clone`으로 만든 node-1/node-2가 완전히 같은 절차(netplan 정적 IP
주입 → bridged 전환)를 거치는데도 node-2만 정적 IP(`192.168.0.202`)에
ping/ssh 응답이 없었음. node-1은 항상 정상.

### 근본 원인
`tart clone`은 `/etc/machine-id`도 그대로 복사한다. systemd-networkd의
DHCPv4 ClientIdentifier(DUID)는 이 machine-id를 해시해서 만들기 때문에,
NAT 부트스트랩 단계에서 macOS(host) DHCP 서버가 node-1과 node-2를
**같은 클라이언트**로 착각 → node-2의 DHCP lease가 오염되고, 이게
`configure-network`가 참조하는 NAT IP/설정에 영향을 줘서 이후 정적 IP
전환도 꼬임.

### 해결
`up` 직후, `configure-network` 이전에 `fix-identity` 단계를 추가해
`cloud-init clean --machine-id` + reboot로 clone된 VM마다 새
machine-id를 발급받게 함. `bootstrap` 타깃에 이미 연결되어 있어
별도 조치 불필요 — `make bootstrap` 한 번으로 처리됨.

### 힌트 — 앞으로 비슷한 문제를 만나면
- **"두 VM 중 하나만 네트워크가 이상하다"** 증상이 다시 보이면, 가장 먼저
  `ssh <VM> "cat /etc/machine-id"`로 두 VM의 machine-id가 서로 다른지
  확인할 것. 같으면 range clone 이후 identity fix가 빠진 것.
- tart/cloud-init 이미지를 clone해서 여러 대 굴릴 때는 항상
  identity(`machine-id`, SSH host key 등)를 clone 직후 재발급하는 습관을
  들일 것 — DHCP뿐 아니라 SSH host key 충돌, systemd journal 병합 등
  다른 문제도 같은 원인 계열로 발생할 수 있음.

---

## 주의사항 — netplan/SSH 관련

1. **scp로 netplan YAML을 옮기지 말 것.** 과거 scp 전송 중 파일이
   손상되어 `Invalid YAML: aliases are not supported` (exit 78) 에러가
   난 적이 있음. 반드시 SSH heredoc(`cat <<EOF | sudo tee ...` 또는
   Makefile의 `printf` 체인)으로 원격에서 직접 작성할 것.
2. **netplan 파일 작성과 `netplan apply`는 별도 SSH 호출로 분리.**
   한 세션 안에서 파일 쓰기 + apply를 같이 하면, apply가 네트워크를
   끊는 순간 파일 쓰기 자체가 검증되지 않은 채 넘어갈 수 있다. 파일을
   쓴 직후 `sudo test -s <file>`로 즉시 비어있지 않은지 확인하고,
   그 다음 별도 SSH 호출로 `netplan apply`를 트리거할 것.
3. **`netplan apply`는 `nohup ... & disown`으로 SSH 세션과 분리해서
   실행.** SSH 연결이 끊겨도(정상적으로 끊김) apply 프로세스 자체가
   중간에 죽지 않도록 하기 위함.
4. **정적 IP 적용 후 재부팅하지 말고 바로 bridged로 전환할 것.**
   재부팅하면 cloud-init이 `/etc/netplan/50-cloud-init.yaml`을
   재생성하고 disable-network-config를 초기화해버려서 설정이 날아간다.
   순서: `netplan apply`(NAT 세션) → `tart stop` → `tart run
   --net-bridged=...` — 이 사이에 reboot 없이 바로 넘어가야 함.
5. **호스트 bridge 인터페이스는 `ifconfig`로 실제 연결된 것 확인 후
   지정.** `en0`이 기본값처럼 보여도 실제로 unplugged(media: none)일 수
   있다. 이 Mac mini는 `en8`(USB AX88179B 이더넷)이 실제 사용 인터페이스.
6. **`tart run ... &`는 반드시 `nohup ... & disown`으로 기동.** make
   프로세스가 죽거나 타임아웃되면 자식으로 물린 VM 프로세스까지 같이
   죽는다.
7. **SSH_PASS 등 Makefile 변수에 인라인 주석(`값 # 주석`) 달지 말 것.**
   trailing space까지 값에 포함되어 인증이 깨진다. 주석은 반드시 별도
   줄에 작성.
8. **`sudo`로 쓴 파일을 검증할 때 `$(sudo cmd < file)` 형태의
   리다이렉션을 쓰지 말 것.** 리다이렉션은 sudo 없는 셸에서 먼저 열려서
   Permission denied가 난다. `sudo test -s <file>`을 사용할 것.

## 재현 절차 (검증됨)
```
export TART_HOME=/Users/blue/iac-project
cd 0-infra
make clean       # VM 완전 삭제
make bootstrap   # up → fix-identity → configure-network → down → bridged-up → verify
```
`make bootstrap` 실행 결과 node-1(`192.168.0.201`), node-2
(`192.168.0.202`) 모두 ping/ssh 정상 확인됨 (2026-09-16).

---

## [해결됨] 2026-09-18 재발 — bridged 전환 후 ping/ssh 전부 무응답 (복합 원인 3가지)

`make clean && make bootstrap`을 재실행했을 때 `verify` 단계에서 두 노드
모두 100% 패킷 손실, SSH 타임아웃이 재발함. 원인을 하나씩 분리해서
확인한 결과 아래 3가지가 겹쳐서 발생했다.

### 원인 1 — `tart stop` 이후에도 이전 프로세스가 좀비로 남음
`nohup tart run $n ... & disown`으로 띄운 프로세스가 `tart stop $n`
실행 후에도 `ps aux`에 그대로 남아있었다. 이 상태에서 bridged 모드로
새 `tart run`을 또 띄우면 **같은 VM에 대해 프로세스가 두 개(구 NAT +
신규 bridged) 동시에 실행되는 상태**가 되어 네트워크가 완전히 꼬인다.
- 확인: `ps aux | grep "tart run node-1"` 등으로 같은 노드 이름의
  프로세스가 1개보다 많으면 이 문제.
- 해결: `down` 타깃에 `tart stop` 이후 남은 프로세스를 `pgrep -f "tart
  run <node> "` + `kill -9`로 강제 정리하는 로직 추가함 (Makefile 참고).

### 원인 2 — macOS ARP 캐시 stale REJECT 엔트리
`route get 192.168.0.201`로 확인했을 때 `flags: REJECT`가 붙어있었다.
이전 시도에서 "Host is down"으로 학습된 캐시가 만료 전까지 남아 새
패킷을 즉시 차단한다.
- 확인: `route get <ip>` 결과에 `REJECT` 플래그 확인.
- 해결: `sudo arp -d <ip>`로 캐시 삭제 (sudo 필요 — 에이전트가 대신
  비밀번호를 입력하지 말고 사용자가 직접 실행). 자연 만료(수 분~20분)
  대기도 가능.

### 원인 3(오판이었음, 정정) — netplan apply 후 NAT IP 재검증은 하지 말 것
초기 대응 때 "apply 후 실제 IP가 반영됐는지 NAT IP로 재확인, 안 되면
재시도" 로직을 Makefile에 넣었으나, 이는 **오판**이었다. 정적 IP를
적용하는 순간 게스트 인터페이스에서 NAT 주소(192.168.64.x)가 사라지는
것이 정상 동작이므로, apply 직후 NAT IP로 재접속하면 (bridged 전환
전이라) 항상 타임아웃된다. 이걸 "cloud-init이 설정을 초기화했다"는
신호로 착각해 재시도 루프를 넣었더니 오히려 정상 케이스를 실패로
처리해 `make bootstrap`이 깨지는 사고가 났다. **netplan apply 이후의
실제 성공 여부는 반드시 bridged-up 이후 `verify` 단계(TARGET_IP로
ping/ssh)에서만 판단할 것 — NAT IP로 되돌아가 확인하는 로직은 절대
넣지 말 것.**

### 원인 4 (재현, 2026-09-18) — 두 노드 순차 configure 시 마지막 노드의 apply 반영 시간 부족
`configure-network`가 node-1 → node-2 순으로 순차 실행되는데, `bootstrap`은
전체 `configure-network` 완료 후 일괄로 10초만 대기하고 `down`으로 넘어갔다.
이 경우 **먼저 처리된 node-1은 apply 후 충분히 시간이 지나 안정화되지만,
나중에 처리된 node-2는 apply 직후 곧바로 stop되어 netplan 설정이 디스크에
완전히 반영(systemd-networkd reload, 파일 flush)되기 전에 종료됨** —
결과적으로 node-2만 bridged 전환 후에도 `/etc/netplan/99-static.yaml`이
0바이트로 비어있고 DHCP(NAT IP)로 되돌아간 상태가 재현됨.
- 증상: node-1은 ping/ssh 정상, node-2만 100% 실패. ARP `sudo arp -d`로도
  해결 안 됨(ARP 문제가 아니라 VM이 실제로 다른 서브넷의 DHCP IP를 쓰고
  있었음).
- 확인: node-2를 NAT로 재부팅해 `sudo cat /etc/netplan/99-static.yaml` →
  빈 파일 확인.
- 해결: `bootstrap`의 `configure-network` 완료 후 `down` 진입 전 대기를
  10초 → 30초로 늘림. 근본적으로는 노드별로 configure 직후 개별 안정화
  시간을 주는 것이 이상적이나, 현재는 전체 완료 후 일괄 대기로 완화.

### 부수 발견 — make 3.81 패턴 규칙 버그
`configure-network-node-%:` 같은 암묵적 패턴 규칙을 이 Makefile
조합에서 실행하면 `make --debug=b`에 "Successfully remade target
file" 로그가 찍히는데도 실제로는 레시피가 실행되지 않고 "Nothing to
be done for..."로 끝나는 경우가 있었다 (macOS 기본 CommandLineTools
make 3.81). **패턴 규칙(%) 대신 개별 구체 타깃 + `define/call`로
공통 로직을 재사용하는 방식으로 되돌림.** 이 Makefile을 다시
"간결하게 리팩터링"하고 싶어질 때 %-패턴을 쓰지 말 것.

### 검증
위 3가지를 모두 반영한 뒤 `make bootstrap` 재실행 → node-1
(192.168.0.201), node-2(192.168.0.202) ping 0% loss, SSH hostname
정상 확인 (2026-09-18).
