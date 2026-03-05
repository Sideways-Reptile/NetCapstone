# Bigfork IT Network Lab — Complete Rebuild Guide
## Tasks 1–10 | First-Time Build Reference

> This guide walks through rebuilding the entire lab from zero.
> Estimated time: ~5–6 hours. With automation scripts: ~3 hours.

---

## Lab Overview

```
TOPOLOGY SUMMARY
─────────────────────────────────────────────────────
HQ Site:
  HQ-FW1 (pfSense 2.7)         — Firewall / Router / VPN
  SW1-CORE (EXOS)               — Core switch, root bridge
  SW2-DIST-1, SW3-DIST-2 (EXOS) — Distribution layer
  SW4-ACCESS1-CORP (EXOS)       — Access: CORP + MGMT
  SW5-ACCESS2-DMZ (EXOS)        — Access: DMZ + GUEST
  Ubu-WS01 (Ubuntu)             — Admin workstation (MGMT)
  WIN10-WS1, WIN10-WS2 (Win10)  — CORP users
  FILE-SVR1, PRINT-SVR1 (VPCS)  — DMZ servers
  WS-Gst (Win10)                — Guest device

Branch Site:
  BR-CA-Irv-FW1 (pfSense 2.6)  — Branch firewall / IPSec endpoint
  SW1-Br-CORE (EXOS)            — Branch switch
  PC1 (VPCS)                    — Branch endpoint
  Ubu-WS02 (Ubuntu)             — Branch workstation

Clouds:
  Cloud1 (VMnet8/NAT)           — HQ internet
  Cloud2 (VMnet2/Host-Only)     — IPSec tunnel segment
  Switch1 (GNS3 Ethernet Switch)— Shared tunnel switch
```

---

## Network Addressing

| VLAN | Name      | Subnet              | Gateway       | DHCP Range                    |
|------|-----------|---------------------|---------------|-------------------------------|
| 10   | MGMT_NET  | 10.10.10.0/24       | 10.10.10.1    | 10.10.10.100–10.10.10.200     |
| 20   | CORP_NET  | 172.16.1.0/24       | 172.16.1.1    | 172.16.1.100–172.16.1.200     |
| 30   | DMZ_NET   | 192.168.100.0/24    | 192.168.100.1 | 192.168.100.100–192.168.100.200|
| 40   | GUEST_NET | 192.168.200.0/24    | 192.168.200.1 | 192.168.200.100–192.168.200.200|
| —    | BRANCH_LAN| 10.20.10.0/24       | 10.20.10.1    | 10.20.10.100–10.20.10.200     |
| —    | TUNNEL    | 100.64.0.0/30       | —             | Static only                   |

## Switch Management IPs (MGMT_NET)

| Device           | IP           |
|------------------|--------------|
| HQ-FW1 (MGMT)   | 10.10.10.1   |
| SW1-CORE         | 10.10.10.11  |
| SW2-DIST-1       | 10.10.10.12  |
| SW3-DIST-2       | 10.10.10.13  |
| SW4-ACCESS1-CORP | 10.10.10.14  |
| SW5-ACCESS2-DMZ  | 10.10.10.15  |

## Credentials

| Device     | Username | Password    |
|------------|----------|-------------|
| EXOS switches | case  | sidewaays   |
| HQ-FW1 GUI | admin   | (your password) |
| Branch FW GUI | admin | (your password) |

---

## GNS3 Port Wiring — HQ

| From              | Port | To                | Port |
|-------------------|------|-------------------|------|
| Cloud1            | —    | HQ-FW1            | em0  |
| HQ-FW1            | em1  | SW1-CORE          | 1    |
| HQ-FW1            | em2  | Switch1           | —    |
| SW1-CORE          | 2    | SW2-DIST-1        | 1    |
| SW1-CORE          | 3    | SW3-DIST-2        | 1    |
| SW1-CORE          | 4    | Ubu-WS01          | ens3 |
| SW2-DIST-1        | 2    | SW4-ACCESS1-CORP  | 1    |
| SW2-DIST-1        | 3    | SW5-ACCESS2-DMZ   | 2    |
| SW3-DIST-2        | 2    | SW5-ACCESS2-DMZ   | 1    |
| SW3-DIST-2        | 3    | SW4-ACCESS1-CORP  | 2    |
| SW4-ACCESS1-CORP  | 3    | WIN10-WS1         | —    |
| SW4-ACCESS1-CORP  | 4    | WIN10-WS2         | —    |
| SW5-ACCESS2-DMZ   | 3    | FILE-SVR1         | —    |
| SW5-ACCESS2-DMZ   | 4    | PRINT-SVR1        | —    |

## GNS3 Port Wiring — Branch / Tunnel

| From              | Port | To                | Port |
|-------------------|------|-------------------|------|
| Cloud2            | —    | Switch1           | —    |
| Switch1           | —    | BR-CA-Irv-FW1     | em0  |
| BR-CA-Irv-FW1     | em1  | SW1-Br-CORE       | 1    |
| SW1-Br-CORE       | 2    | PC1               | —    |
| SW1-Br-CORE       | 3    | Ubu-WS02          | —    |

> **NOTE:** HQ-FW1 em2 also connects to Switch1 (same switch as Branch WAN).
> Switch1 is the shared tunnel segment — no cloud needed on HQ side of Switch1.

---

## PHASE 1 — GNS3 Setup

### Critical EXOS Template Setting
Before adding ANY EXOS node: edit the QEMU template → enable **"Use linked base VM"**.
Without this, all EXOS instances share one disk and corrupt each other.

### Boot Order
Always boot switches in this order with 30-second gaps:
1. SW1-CORE (wait 3 min before proceeding)
2. SW2-DIST-1
3. SW3-DIST-2
4. SW4-ACCESS1-CORP
5. SW5-ACCESS2-DMZ

---

## PHASE 2 — pfSense HQ Initial Config

### Step 1: Interface Assignment (console option 1)
```
WAN  = em0
LAN  = em1.10   (MGMT_NET)
OPT1 = em1.20   (CORP_NET)
OPT2 = em1.30   (DMZ_NET)
OPT3 = em1.40   (GUEST_NET)
OPT4 = em2      (IPSec WAN)
```

> **CRITICAL:** Assign VLANs (em1.10 etc.) as interfaces — NOT em1 directly.
> If you assign em1 as LAN, DHCP will not reach VLAN-tagged devices.

### Step 2: VLAN Creation
GUI → Interfaces → Assignments → VLANs → Add:

| Parent | Tag | Description |
|--------|-----|-------------|
| em1    | 10  | MGMT_NET    |
| em1    | 20  | CORP_NET    |
| em1    | 30  | DMZ_NET     |
| em1    | 40  | GUEST_NET   |

### Step 3: Interface IPs (console option 2 OR GUI)

| Interface | IP              |
|-----------|-----------------|
| em1.10    | 10.10.10.1/24   |
| em1.20    | 172.16.1.1/24   |
| em1.30    | 192.168.100.1/24|
| em1.40    | 192.168.200.1/24|
| em2       | 100.64.0.1/30   |

### Step 4: DHCP Pools (GUI → Services → DHCP Server)

Enable on each interface with ranges from the addressing table above. Set DNS to 8.8.8.8 on all.

### Step 5: Firewall Aliases (GUI → Firewall → Aliases)

| Name        | Type     | Value                                           |
|-------------|----------|-------------------------------------------------|
| RFC1918_ALL | Networks | 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16     |

### Step 6: Firewall Rules

**GUEST (OPT3):**
1. Block — Source: GUEST net — Dest: RFC1918_ALL — Log ✓
2. Pass  — Source: GUEST net — Dest: Any — Log ✓

**CORP (OPT1):**
1. Pass — Source: CORP net — Dest: Any — Log ✓
2. Pass — Source: CORP net — Dest: 10.20.10.0/24 — Description: CORP to Branch VPN

**IPSec tab:**
1. Pass — Source: 10.20.10.0/24 — Dest: Any — Description: Allow Branch VPN traffic

Enable logging on ALL rules.

### Step 7: Outbound NAT
GUI → Firewall → NAT → Outbound → Hybrid mode.
Verify all VLANs have outbound NAT rules to WAN.

---

## PHASE 3 — EXOS Switch Bootstrap

Paste the following into each switch console. Boot SW1 first, wait 3 min.

### SW1-CORE Bootstrap
```
configure snmp sysname SW1-CORE
create vlan MGMT_NET tag 10
create vlan CORP_NET tag 20
create vlan DMZ_NET tag 30
create vlan GUEST_NET tag 40
configure MGMT_NET ipaddress 10.10.10.11/24
enable ipforwarding vlan MGMT_NET
enable ipforwarding vlan CORP_NET
enable ipforwarding vlan DMZ_NET
enable ipforwarding vlan GUEST_NET

# Port 1 = uplink to pfSense (tagged trunk)
configure vlan MGMT_NET add ports 1 tagged
configure vlan CORP_NET add ports 1 tagged
configure vlan DMZ_NET add ports 1 tagged
configure vlan GUEST_NET add ports 1 tagged

# Port 2 = uplink to SW2-DIST-1 (tagged trunk)
configure vlan MGMT_NET add ports 2 tagged
configure vlan CORP_NET add ports 2 tagged
configure vlan DMZ_NET add ports 2 tagged
configure vlan GUEST_NET add ports 2 tagged

# Port 3 = uplink to SW3-DIST-2 (tagged trunk)
configure vlan MGMT_NET add ports 3 tagged
configure vlan CORP_NET add ports 3 tagged
configure vlan DMZ_NET add ports 3 tagged
configure vlan GUEST_NET add ports 3 tagged

# Port 4 = Ubu-WS01 (untagged MGMT)
configure vlan MGMT_NET add ports 4 untagged

# STP
disable stpd s0
configure stpd s0 mode dot1w
configure stpd s0 default-encapsulation dot1d
configure stpd s0 priority 4096
configure vlan MGMT_NET add ports 1,2,3,4 stpd s0
configure vlan CORP_NET add ports 1,2,3 stpd s0
configure vlan DMZ_NET add ports 1,2,3 stpd s0
configure vlan GUEST_NET add ports 1,2,3 stpd s0
enable stpd s0

# SSH
configure ssh2 key
enable ssh2
save configuration
```

### SW2-DIST-1 Bootstrap
```
configure snmp sysname SW2-DIST-1
create vlan MGMT_NET tag 10
create vlan CORP_NET tag 20
create vlan DMZ_NET tag 30
create vlan GUEST_NET tag 40
configure MGMT_NET ipaddress 10.10.10.12/24
enable ipforwarding vlan MGMT_NET

# Port 1 = uplink to SW1-CORE
configure vlan MGMT_NET add ports 1 tagged
configure vlan CORP_NET add ports 1 tagged
configure vlan DMZ_NET add ports 1 tagged
configure vlan GUEST_NET add ports 1 tagged

# Port 2 = downlink to SW4-ACCESS1-CORP
configure vlan MGMT_NET add ports 2 tagged
configure vlan CORP_NET add ports 2 tagged
configure vlan DMZ_NET add ports 2 tagged
configure vlan GUEST_NET add ports 2 tagged

# Port 3 = downlink to SW5-ACCESS2-DMZ
configure vlan MGMT_NET add ports 3 tagged
configure vlan CORP_NET add ports 3 tagged
configure vlan DMZ_NET add ports 3 tagged
configure vlan GUEST_NET add ports 3 tagged

disable stpd s0
configure stpd s0 mode dot1w
configure stpd s0 default-encapsulation dot1d
configure stpd s0 priority 8192
configure vlan MGMT_NET add ports 1,2,3 stpd s0
configure vlan CORP_NET add ports 1,2,3 stpd s0
configure vlan DMZ_NET add ports 1,2,3 stpd s0
configure vlan GUEST_NET add ports 1,2,3 stpd s0
enable stpd s0
configure ssh2 key
enable ssh2
save configuration
```

### SW3-DIST-2 Bootstrap
```
configure snmp sysname SW3-DIST-2
create vlan MGMT_NET tag 10
create vlan CORP_NET tag 20
create vlan DMZ_NET tag 30
create vlan GUEST_NET tag 40
configure MGMT_NET ipaddress 10.10.10.13/24
enable ipforwarding vlan MGMT_NET

configure vlan MGMT_NET add ports 1 tagged
configure vlan CORP_NET add ports 1 tagged
configure vlan DMZ_NET add ports 1 tagged
configure vlan GUEST_NET add ports 1 tagged
configure vlan MGMT_NET add ports 2 tagged
configure vlan CORP_NET add ports 2 tagged
configure vlan DMZ_NET add ports 2 tagged
configure vlan GUEST_NET add ports 2 tagged
configure vlan MGMT_NET add ports 3 tagged
configure vlan CORP_NET add ports 3 tagged
configure vlan DMZ_NET add ports 3 tagged
configure vlan GUEST_NET add ports 3 tagged
configure vlan GUEST_NET add ports 4 untagged
disable stpd s0
configure stpd s0 mode dot1w
configure stpd s0 default-encapsulation dot1d
configure stpd s0 priority 8192
configure vlan MGMT_NET add ports 1,2,3 stpd s0
configure vlan CORP_NET add ports 1,2,3 stpd s0
configure vlan DMZ_NET add ports 1,2,3 stpd s0
configure vlan GUEST_NET add ports 1,2,3 stpd s0
enable stpd s0
configure ssh2 key
enable ssh2
save configuration
```

### SW4-ACCESS1-CORP Bootstrap
```
configure snmp sysname SW4-ACCESS1-CORP
create vlan MGMT_NET tag 10
create vlan CORP_NET tag 20
create vlan DMZ_NET tag 30
create vlan GUEST_NET tag 40
configure MGMT_NET ipaddress 10.10.10.14/24
enable ipforwarding vlan MGMT_NET

# Ports 1,2 = uplinks to dist switches (tagged)
configure vlan MGMT_NET add ports 1,2 tagged
configure vlan CORP_NET add ports 1,2 tagged
configure vlan DMZ_NET add ports 1,2 tagged
configure vlan GUEST_NET add ports 1,2 tagged

# Port 3,4 = CORP user devices (untagged CORP)
configure vlan CORP_NET add ports 3,4 untagged

disable stpd s0
configure stpd s0 mode dot1w
configure stpd s0 default-encapsulation dot1d
configure stpd s0 priority 16384
configure vlan MGMT_NET add ports 1,2 stpd s0
configure vlan CORP_NET add ports 1,2,3,4 stpd s0
enable stpd s0
configure ssh2 key
enable ssh2
save configuration
```

### SW5-ACCESS2-DMZ Bootstrap
```
configure snmp sysname SW5-ACCESS2-DMZ
create vlan MGMT_NET tag 10
create vlan CORP_NET tag 20
create vlan DMZ_NET tag 30
create vlan GUEST_NET tag 40
configure MGMT_NET ipaddress 10.10.10.15/24
enable ipforwarding vlan MGMT_NET

configure vlan MGMT_NET add ports 1,2 tagged
configure vlan CORP_NET add ports 1,2 tagged
configure vlan DMZ_NET add ports 1,2 tagged
configure vlan GUEST_NET add ports 1,2 tagged

# Port 3,4 = DMZ servers (untagged DMZ)
configure vlan DMZ_NET add ports 3,4 untagged

disable stpd s0
configure stpd s0 mode dot1w
configure stpd s0 default-encapsulation dot1d
configure stpd s0 priority 16384
configure vlan MGMT_NET add ports 1,2 stpd s0
configure vlan DMZ_NET add ports 1,2,3,4 stpd s0
enable stpd s0
configure ssh2 key
enable ssh2
save configuration
```

---

## PHASE 4 — Syslog & NTP (Task 6)

### On Ubu-WS01 — Set up rsyslog server
```bash
sudo apt install rsyslog -y
sudo nano /etc/rsyslog.conf
# Uncomment these two lines:
# module(load="imudp")
# input(type="imudp" port="514")
sudo systemctl restart rsyslog
```

### On HQ-FW1 GUI
Status → System Logs → Settings:
- Remote syslog server: `10.10.10.108` (Ubu-WS01 IP)
- Check: Firewall events, DHCP events, VPN events
- Save

### On each EXOS switch
```
configure syslog add 10.10.10.108 local7 informational
configure ntp add 10.10.10.1
enable ntp
save configuration
```

---

## PHASE 5 — Login Banners (Task 3)

### EXOS switches
```
configure banner
```
Paste banner text, then press Ctrl+Z to end.

### pfSense
GUI → System → Advanced → Admin Access → Login Banner field.

---

## PHASE 6 — Port Security (Task 10)

On SW4-ACCESS1-CORP, with WIN10-WS1 plugged into port 3:
```
enable mac-locking
enable mac-locking ports 3
configure mac-locking ports 3 first-arrival limit-learning 1
configure mac-locking ports 3 first-arrival link-down-action retain-macs
configure mac-locking ports 3 learn-limit-action remain-enabled
configure mac-locking ports 3 log violation on
configure mac-locking ports 3 trap violation on
save configuration
```

Verify:
```
show mac-locking ports 3
```

---

## PHASE 7 — IPSec VPN (Task 9)

### Branch pfSense Setup (BR-CA-Irv-FW1)

Console option 1 — assign interfaces:
```
WAN = em0  → 100.64.0.2/30  (static, no gateway)
LAN = em1  → 10.20.10.1/24  (enable DHCP 10.20.10.100-200)
```

### HQ-FW1 — VPN → IPsec → Add P1

| Field              | Value          |
|--------------------|----------------|
| Key Exchange       | IKEv2          |
| Interface          | OPT4 (em2)     |
| Remote Gateway     | 100.64.0.2     |
| Auth Method        | Mutual PSK     |
| Pre-Shared Key     | LabIPSec2026   |
| Encryption         | AES 256        |
| Hash               | SHA256         |
| DH Group           | 14 (2048 bit)  |
| Lifetime           | 28800          |

### HQ-FW1 — Phase 2 entries

| ID | Local             | Remote           | Description        |
|----|-------------------|------------------|--------------------|
| 1  | 172.16.1.0/24     | 10.20.10.0/24    | HQ-CORP-to-Branch  |
| 2  | 192.168.100.0/24  | 10.20.10.0/24    | HQ-DMZ-to-Branch   |

### Branch — VPN → IPsec → Add P1

Same settings as HQ but:
- Interface: WAN (em0)
- Remote Gateway: `100.64.0.1`

### Branch — Phase 2 entries

| ID | Local | Remote            | Description        |
|----|-------|-------------------|--------------------|
| 1  | LAN   | 172.16.1.0/24     | Branch-to-HQ-CORP  |
| 2  | LAN   | 192.168.100.0/24  | Branch-to-HQ-DMZ   |

### Firewall Rules for IPSec

**HQ — Firewall → Rules → IPsec:**
- Pass | Source: 10.20.10.0/24 | Dest: Any | Allow Branch VPN traffic

**HQ — Firewall → Rules → OPT1 (CORP):**
- Pass | Source: 172.16.1.0/24 | Dest: 10.20.10.0/24 | CORP to Branch VPN

**Branch — Firewall → Rules → IPsec:**
- Pass | Source: 172.16.1.0/24 | Dest: Any | Allow HQ VPN traffic

### Bring tunnel up
From HQ-FW1 shell:
```bash
ipsec up con1
```

---

## PHASE 8 — Validation Checklist

### Per-Task Verification

**Task 1 — Segmentation:**
```
# From Ubu-WS01
ping 10.10.10.1    # PASS
ping 172.16.1.1    # PASS
ping 192.168.100.1 # PASS
ping 8.8.8.8       # PASS
```

**Task 2 — Guest ACL:**
```
# From WS-Gst (GUEST)
ping 172.16.1.1    # FAIL (RFC1918 blocked)
ping 8.8.8.8       # PASS
```

**Task 3 — Banners:**
```
ssh case@10.10.10.11    # Banner should display before login
```

**Task 5 — STP:**
```
# On SW1-CORE
show stpd s0 ports
# Should show SW1 as root, ports FORWARDING
```

**Task 6 — Syslog:**
```bash
# On Ubu-WS01
sudo tail -f /var/log/syslog | grep pfsense
```

**Task 7 — VLANs:**
```
# On any switch
show vlan
# Should show MGMT_NET, CORP_NET, DMZ_NET, GUEST_NET
```

**Task 9 — IPSec:**
```
# From PC1 (Branch)
ping 172.16.1.1    # PASS (via tunnel)
ping 192.168.100.1 # PASS (via tunnel)
ping 10.10.10.1    # FAIL (MGMT not in tunnel — by design)
```

**Task 10 — Port Security:**
```
# On SW4-ACCESS1-CORP
show mac-locking ports 3
# Plug in second device — should fail to get DHCP
```

---

## EXOS Quick Reference

```
show vlan                          # List all VLANs
show ports info                    # Port status overview
show fdb                           # MAC address table
show ipconfig                      # IP interfaces
show stpd s0 ports                 # STP port states
show mac-locking ports 3           # Port security status
show log                           # System log
ping <ip>                          # Ping from switch
save configuration                 # Save (ALWAYS do this!)
```

## pfSense Shell Quick Reference

```bash
ifconfig                           # All interfaces
ifconfig em1.10 | grep inet        # Specific VLAN IP
ping -c 3 <ip>                     # Ping test
tcpdump -i em1 -n                  # Capture on interface
ipsec statusall                    # IPSec tunnel status
ipsec up con1                      # Bring tunnel up
ipsec down con1                    # Tear tunnel down
```

---

## Known Gotchas

1. **EXOS "Mgmt" VLAN** — the built-in Mgmt VLAN (4095) is immutable. Use MGMT_NET (tag 10) instead.
2. **pfSense interface shuffle** — adding a new physical interface (em2 etc.) can break VLAN subinterface assignments. Always reassign via console option 1 after adding interfaces.
3. **VMware NAT blocks inter-VM traffic** — two pfSense instances on VMnet8 cannot ping each other. Use a host-only or internal segment for the IPSec tunnel link.
4. **EXOS SSH key** — pre-generated keys exist. Run `configure ssh2 key` only once. Running it again during boot will hang for 30+ seconds.
5. **STP convergence** — allow 30–60 seconds after topology changes before testing.
6. **GNS3 link ghosts** — a link can show green but pass no traffic. Delete and redraw the cable to fix.
7. **DHCP on em1 vs em1.10** — always assign the LAN interface to the VLAN subinterface (em1.10), never to the raw em1 trunk. em1 carries only tagged frames.
