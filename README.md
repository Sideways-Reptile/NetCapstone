# Bigfork IT — Capstone Lab Automation Suite
## GNS3 Network Engineering Lab — Tasks 1–10

---

## Quick Start

```bash
# 1. Clone to Ubu-WS01 (10.10.10.108)
git clone <your-repo-url> capstone_automation
cd capstone_automation

# 2. Install Python dependencies
pip install -r requirements.txt --break-system-packages

# 3. Enable SSH on switches (MANUAL — console required first time)
#    See: SSH_SETUP.md

# 4. Generate Ansible inventory from live switches
python3 inventory/discover_inventory.py

# 5. Run all automated tasks
ansible-playbook -i ansible_inventory.yml run_all_tasks.yml

# 6. Run final audit
python3 task10_audit/security_audit.py
```

---

## What Is Automated vs Manual

| Task | What Automation Does | Manual Steps Required |
|------|---------------------|-----------------------|
| **Task 1** | Validates reachability | pfSense VLAN subinterfaces via GUI |
| **Task 2** | Generates config guide, validates | Apply rules in pfSense GUI |
| **Task 3** | Deploys banners to all EXOS switches | pfSense SSH banner via console |
| **Task 4** | Validates all static IPs, prints DHCP guide | Apply DHCP pools in pfSense GUI |
| **Task 5** | Full STP config on all EXOS switches | None |
| **Task 6** | Syslog + NTP config on all EXOS switches | pfSense syslog settings in GUI |
| **Task 7** | VLAN creation + port assignment on all switches | pfSense subinterface verification |
| **Task 8** | Branch switch config | Branch pfSense console + GUI |
| **Task 9** | Generates config guides, validates tunnel | IPSec config in pfSense GUI (both ends) |
| **Task 10** | Full automated security audit | Screenshot capture for documentation |

---

## SSH Must Be Enabled on Switches First (Console Step)

SSH cannot be automated on a brand new switch — it must be enabled via the
physical/GNS3 console before any Python or Ansible scripts can connect.

**On each EXOS switch console:**
```
enable ssh2
configure ssh2 key
configure vlan Default ipaddress 10.10.10.2X 255.255.255.0
configure iproute add default 10.10.10.1
save configuration
```

After this one-time step, all further configuration is fully automated.

---

## Script Reference

### Inventory
```bash
python3 inventory/discover_inventory.py
# Discovers all connected switches, generates ansible_inventory.yml
# Options:
#   --output-dir /path    write files here
#   --extra-host 10.x.x.x  add extra switch
#   --skip-branch         skip branch switches
```

### Task 1 — Segmentation Validation
```bash
python3 task1_segmentation/validate_segmentation.py
```

### Task 2 — Guest ACL
```bash
python3 task2_guest_acl/configure_guest_acl.py           # generate + validate
python3 task2_guest_acl/configure_guest_acl.py --generate  # config guide only
python3 task2_guest_acl/configure_guest_acl.py --validate  # validate only
```

### Task 3 — Banners
```bash
# Python:
python3 task3_banners/deploy_banners.py          # deploy to all switches
python3 task3_banners/deploy_banners.py --hq-only
python3 task3_banners/deploy_banners.py --generate-only  # print guides only

# Ansible:
ansible-playbook -i ansible_inventory.yml task3_banners/banners.yml
```

### Task 4 — DHCP Validation
```bash
python3 task4_dhcp/validate_dhcp.py
python3 task4_dhcp/validate_dhcp.py --generate  # DHCP config guide only
```

### Task 5 — STP
```bash
# Python:
python3 task5_stp/configure_stp.py              # configure all
python3 task5_stp/configure_stp.py --verify     # verify only
python3 task5_stp/configure_stp.py --host 10.10.10.11  # single switch

# Ansible:
ansible-playbook -i ansible_inventory.yml task5_stp/stp_configure.yml
ansible-playbook -i ansible_inventory.yml task5_stp/stp_configure.yml --tags verify
```

### Task 6 — Syslog & NTP
```bash
# Python:
python3 task6_syslog_ntp/configure_syslog_ntp.py
python3 task6_syslog_ntp/configure_syslog_ntp.py --syslog-only
python3 task6_syslog_ntp/configure_syslog_ntp.py --ntp-only
python3 task6_syslog_ntp/configure_syslog_ntp.py --verify

# Ansible:
ansible-playbook -i ansible_inventory.yml task6_syslog_ntp/syslog_ntp.yml
ansible-playbook -i ansible_inventory.yml task6_syslog_ntp/syslog_ntp.yml --tags syslog
ansible-playbook -i ansible_inventory.yml task6_syslog_ntp/syslog_ntp.yml --tags ntp
```

### Task 7 — VLANs
```bash
# Python:
python3 task7_vlans/configure_vlans.py
python3 task7_vlans/configure_vlans.py --verify

# Ansible:
ansible-playbook -i ansible_inventory.yml task7_vlans/vlans_configure.yml
ansible-playbook -i ansible_inventory.yml task7_vlans/vlans_configure.yml --tags verify
```

### Task 8 — Branch Site
```bash
python3 task8_branch/configure_branch.py
python3 task8_branch/configure_branch.py --generate   # pfSense guide only
python3 task8_branch/configure_branch.py --sw-only    # BR-SW1 config only
python3 task8_branch/configure_branch.py --validate
```

### Task 9 — IPSec VPN
```bash
python3 task9_ipsec/configure_ipsec.py           # generate guides + validate
python3 task9_ipsec/configure_ipsec.py --generate  # config guides only
python3 task9_ipsec/configure_ipsec.py --validate  # validate tunnel only
```

### Task 10 — Security Audit
```bash
python3 task10_audit/security_audit.py
python3 task10_audit/security_audit.py --output-dir /home/osboxes
python3 task10_audit/security_audit.py --task 5    # single task check
```

### Run Everything (Ansible)
```bash
ansible-playbook -i ansible_inventory.yml run_all_tasks.yml
ansible-playbook -i ansible_inventory.yml run_all_tasks.yml --tags task5
```

---

## Lab Addressing Reference

| Device | IP | Notes |
|--------|----|-------|
| HQ-FW1 MGMT (em1.10) | 10.10.10.1 | pfSense MGMT gateway |
| HQ-FW1 CORP (em1.20) | 172.16.1.1 | pfSense CORP gateway |
| HQ-FW1 DMZ (em1.30) | 192.168.100.1 | pfSense DMZ gateway |
| HQ-FW1 GUEST (em1.40) | 192.168.200.1 | pfSense GUEST gateway |
| SW1-CORE | 10.10.10.11 | Root Bridge, STP priority 4096 |
| SW2-DIST-1 | 10.10.10.12 | Distribution, STP priority 8192 |
| SW3-DIST-2 | 10.10.10.13 | Access, STP priority 32768 |
| SW4-ACCESS1-CORP | 10.10.10.14 | Access, STP priority 32768 |
| SW5-ACCESS2-DMZ | 10.10.10.15 | Access, STP priority 32768 |
| Ubu-WS01 | 10.10.10.108 | Syslog + automation host |
| BR-CA-Irv-FW1 LAN | 10.20.10.1 | Branch gateway |
| BR-CA-Irv-FW1 WAN | 100.64.0.2 | IPSec tunnel endpoint |
| HQ-FW1 WAN | 100.64.0.1 | IPSec tunnel endpoint |
| BR-SW1 | 10.20.10.21 | Branch switch MGMT |

Switch credentials: `case` / `sidewaays`
pfSense credentials: `admin` / `pfsense`

---

## Credentials & Security Note
Credentials in these scripts are lab defaults. Change them before using
this codebase in any production or real environment.
