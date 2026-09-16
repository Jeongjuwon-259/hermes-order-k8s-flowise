# 0-infra 알려진 이슈 (미해결)

## [OPEN] node-2: bridged 모드 전환 후 정적 IP 무응답

### 증상
`make bootstrap` 실행 시 node-1은 완전히 성공(정적 IP `192.168.0.201`,
ping/ssh 정상)하지만, node-2는 `bridged-up` 이후 정적 IP `192.168.0.202`에
ping/ssh 응답이 없음 (`Operation timed out` / `100% packet loss`).

### 확인된 사실
- `configure-network-node-2` 타깃의 netplan 파일 쓰기는 **정상 완료됨**
  (`sudo test -s ...` 검증 통과, `WRITE_VERIFIED_OK` 출력 확인됨).
- `netplan apply`는 nohup으로 트리거되었고, 트리거 직후 SSH 세션이
  "Timeout, server not responding"으로 끊김 — 이 자체는 node-1과 동일한
  패턴이라 정상 동작으로 간주됨.
- `bridged-up` 이후 40~70초 대기해도 `192.168.0.202` ping/ssh 무응답.
- `tart ip node-2 --wait`도 무응답 (다만 이건 bridged 모드에서 원래
  신뢰 불가한 것으로 알려짐 — README/Makefile 주석 참고).
- NAT 모드로 재부팅하면 node-2는 정상적으로 NAT IP를 받음 → 게스트 OS
  자체나 네트워크 인터페이스가 죽은 것은 아님.
- node-1과 node-2는 완전히 동일한 이미지 클론이고 동일한 절차를
  거치므로, 코드 경로상 차이는 없음 — **타이밍/레이스 컨디션**이거나
  bridged 인터페이스(`en8`) 쪽 host-level 리소스 경합(예: 동시에 두 VM이
  같은 물리 인터페이스에 bridge를 붙일 때의 초기화 순서 문제)일 가능성.

### 미확인/추정 원인 (다음 조사 시 확인 필요)
1. `bootstrap` 흐름에서 node-1 configure 이후 곧바로 node-2 configure가
   진행되며, 두 netplan apply/bridge 전환이 시간차를 두고 겹치는데,
   이 겹침 자체가 `en8` bridge 초기화 순서에 영향을 줄 수 있음.
2. `netplan apply`가 `nohup ... & disown`으로 백그라운드 실행되는데,
   SSH 세션이 너무 빨리 끊기면(`ServerAliveInterval=5`) apply 프로세스가
   실제로 끝까지 실행됐는지 게스트 쪽에서 재확인이 안 된 상태 — NAT
   모드로 재진입해 `/tmp/netplan-apply.log`, `ip a`, `cat
   /etc/netplan/99-static.yaml` 실제 반영 여부를 직접 확인 필요.
3. bridged 모드 재진입 시 `enp0s1`의 MAC 주소가 유지되는지, ARP 캐시가
   호스트 쪽에 꼬여있는지 확인 필요 (`arp -a | grep 192.168.0.202`).

### 다음 액션 (재개 시)
1. `tart stop node-2` → NAT 모드로 재기동 → SSH 접속해 다음을 확인:
   - `cat /etc/netplan/99-static.yaml` 내용이 실제 반영됐는지
   - `cat /tmp/netplan-apply.log` apply 로그
   - `ip a show enp0s1` 인터페이스 상태
2. 문제없다면 `bridged-up`으로 전환 후 즉시(재부팅 없이) `ip a`를 다시
   확인해 정적 IP가 실제로 붙었는지 게스트 콘솔에서 직접 검증.
3. node-1/node-2를 순차적으로(동시에 X) bridged 전환하도록 Makefile을
   수정해서 레이스 컨디션 가설을 검증.

### 임시 우회
node-2 네트워크 문제 발생 시: `tart stop node-2 && tart delete node-2`
후 `make node-2 configure-network-node-2 down bridged-up verify`로
node-2만 재생성/재구성 (node-1은 그대로 둠).
