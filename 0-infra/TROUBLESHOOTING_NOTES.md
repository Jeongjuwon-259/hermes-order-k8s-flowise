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
