# Task Reference Card — All 10 Tasks
## Bigfork IT Network Lab | Quick Validation Guide

---

## Task 1 — Network Segmentation & Device Discovery
**Status:** ✅ Complete

**What it proves:** Multiple network segments with controlled inter-zone access.

**Key config:**
- 4 VLANs (10/20/30/40) on EXOS switches via 802.1q trunking
- pfSense enforcing zone policies

**Validation:**
```bash
# From Ubu-WS01 (MGMT)
ping 10.10.10.1     # HQ-FW1 MGMT gateway — PASS
ping 172.16.1.1     # CORP gateway — PASS
ping 192.168.100.1  # DMZ gateway — PASS
ping 192.168.200.1  # GUEST gateway — PASS
ping 8.8.8.8        # Internet — PASS
```

---

## Task 2 — Guest ACL (RFC1918 Blocking)
**Status:** ✅ Complete

**What it proves:** Guest devices can reach internet but cannot reach any internal network.

**Key config:**
- Alias RFC1918_ALL: 10.0.0.0/8, 172.16.0.0/12, 192.168.0.0/16
- GUEST rule 1: Block → RFC1918_ALL (must be first)
- GUEST rule 2: Pass → Any

**Validation:**
```
# From WS-Gst (192.168.200.x)
ping 172.16.1.1    → FAIL (blocked)
ping 10.10.10.1    → FAIL (blocked)
ping 8.8.8.8       → PASS
```

---

## Task 3 — Login Banners
**Status:** ✅ Complete

**What it proves:** Security compliance — all devices display AUP banner before login.

**Key config:**
- EXOS: `configure banner` then paste text, Ctrl+Z to end
- pfSense: System → Advanced → Admin Access → Login Banner

**Validation:**
```bash
ssh case@10.10.10.11   # Banner displays before password prompt
ssh case@10.10.10.12
ssh case@10.10.10.13
```

---

## Task 4 — DHCP & Static Addressing
**Status:** ✅ Complete

**What it proves:** Dynamic addressing for users, static for infrastructure.

**Key config:**
- DHCP pools on MGMT/CORP/DMZ/GUEST/BRANCH
- pfSense gateways all static
- FILE-SVR1, PRINT-SVR1 = static via DHCP reservation or manual

**Validation:**
```
# From any VPCS
dhcp
show ip    # Should show address in correct subnet
```

---

## Task 5 — Layer 2 Redundancy & STP (802.1w)
**Status:** ✅ Complete

**What it proves:** Redundant Layer 2 paths without loops; automatic failover.

**Key config:**
- RSTP (dot1w) on all 5 switches
- SW1-CORE root bridge (priority 4096)
- SW2/SW3 priority 8192, SW4/SW5 priority 16384
- Cross-links: SW2↔SW4, SW2↔SW5, SW3↔SW4, SW3↔SW5

**Validation:**
```
# On SW1-CORE
show stpd s0 ports
# Look for: this bridge is root, all ports FORWARDING or DESIGNATED
```

---

## Task 6 — Syslog & NTP
**Status:** ✅ Complete

**What it proves:** Centralized logging and time synchronization across all devices.

**Key config:**
- rsyslog on Ubu-WS01 listening UDP 514
- pfSense sending all log categories to 10.10.10.108
- All EXOS switches sending syslog + syncing NTP via pfSense

**Validation:**
```bash
# On Ubu-WS01
sudo tail -f /var/log/syslog | grep pfsense
# Should see filterlog entries flowing in real time
```

---

## Task 7 — VLANs & 802.1q Trunking
**Status:** ✅ Complete

**What it proves:** Layer 2 segmentation per department/function with inter-switch trunking.

**Key config:**
- VLANs 10/20/30/40 on all 5 switches
- All inter-switch ports tagged (trunk)
- All endpoint ports untagged on appropriate VLAN
- pfSense port 1 = full trunk (all VLANs tagged)

**Validation:**
```
# On any switch
show vlan         # All 4 VLANs present
show ports info   # Trunk ports showing 4 VLANs
```

---

## Task 8 — Advanced Networking (5-Switch Hierarchy)
**Status:** ✅ Complete

**What it proves:** Enterprise Core-Distribution-Access architecture with full redundancy.

**Key config:**
- SW1-CORE (root) → SW2/SW3 (dist) → SW4/SW5 (access)
- Redundant cross-links at dist-to-access layer
- RSTP handling automatic failover
- Per-VLAN IP forwarding on all switches
- All 5 switches reachable via MGMT from Ubu-WS01

**Validation:**
```bash
# From Ubu-WS01 — ping all switch management IPs
ping 10.10.10.11  # SW1-CORE
ping 10.10.10.12  # SW2-DIST-1
ping 10.10.10.13  # SW3-DIST-2
ping 10.10.10.14  # SW4-ACCESS1-CORP
ping 10.10.10.15  # SW5-ACCESS2-DMZ
# All should PASS
```

---

## Task 9 — IPSec Site-to-Site VPN
**Status:** ✅ Complete

**What it proves:** Encrypted tunnel between HQ and Branch; Branch can access HQ resources.

**Key config:**
- IKEv2 / AES-256 / SHA-256 / DH Group 14
- PSK authentication
- Tunnel endpoints: 100.64.0.1 (HQ) ↔ 100.64.0.2 (Branch)
- P2 #1: HQ CORP (172.16.1.0/24) ↔ Branch LAN (10.20.10.0/24)
- P2 #2: HQ DMZ (192.168.100.0/24) ↔ Branch LAN (10.20.10.0/24)
- MGMT intentionally excluded (security feature)

**Validation:**
```
# From PC1 (Branch — 10.20.10.x)
ping 172.16.1.1    → PASS  (CORP via tunnel)
ping 192.168.100.1 → PASS  (DMZ via tunnel)
ping 10.10.10.1    → FAIL  (MGMT blocked — by design ✅)

# From WIN10-WS1 (HQ CORP — 172.16.1.x)
ping 10.20.10.1    → PASS  (Branch via tunnel)
```

**Tunnel commands:**
```bash
ipsec statusall      # Check SA status
ipsec up con1        # Force tunnel up
ipsec down con1      # Tear down tunnel
```

---

## Task 10 — Network Security (Defense-in-Depth)
**Status:** ✅ Complete

**What it proves:** Layered security across L2, L3, L4 with monitoring.

**Key config:**

*Layer 2 — Port Security (SW4-ACCESS1-CORP, port 3):*
```
enable mac-locking
enable mac-locking ports 3
configure mac-locking ports 3 first-arrival limit-learning 1
configure mac-locking ports 3 first-arrival link-down-action retain-macs
configure mac-locking ports 3 learn-limit-action remain-enabled
configure mac-locking ports 3 log violation on
```

*Layer 3 — Zone Firewall Policies:*
- MGMT: full access
- CORP: internet + DMZ + Branch (via VPN)
- DMZ: internet only
- GUEST: internet only, RFC1918 blocked
- IPSec: Branch ↔ CORP + DMZ

*Layer 4 — Logging:*
- All firewall rules have logging enabled
- External syslog to Ubu-WS01 (10.10.10.108)
- NTP synchronized across all devices

**Validation:**
```bash
# Run the audit script from Ubu-WS01
python3 task10_security_audit.py

# Or Ansible version
ansible-playbook security_audit.yml
```

---

## Full Lab Health Check
Run this sequence to verify everything at once:

```bash
# From Ubu-WS01
echo "=== HQ Gateways ===" 
for ip in 10.10.10.1 172.16.1.1 192.168.100.1 192.168.200.1; do
  ping -c 1 -W 1 $ip > /dev/null && echo "PASS: $ip" || echo "FAIL: $ip"
done

echo "=== Switch Management ==="
for ip in 10.10.10.11 10.10.10.12 10.10.10.13 10.10.10.14 10.10.10.15; do
  ping -c 1 -W 1 $ip > /dev/null && echo "PASS: $ip" || echo "FAIL: $ip"
done

echo "=== IPSec Tunnel ==="
for ip in 100.64.0.1 100.64.0.2 10.20.10.1; do
  ping -c 1 -W 2 $ip > /dev/null && echo "PASS: $ip" || echo "FAIL: $ip"
done

echo "=== Internet ==="
ping -c 1 -W 2 8.8.8.8 > /dev/null && echo "PASS: 8.8.8.8" || echo "FAIL: 8.8.8.8"
```
