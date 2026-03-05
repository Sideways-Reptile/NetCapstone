#!/usr/bin/env python3
"""
task8_branch/configure_branch.py
Bigfork IT — Capstone Lab

Task 8: Branch Site Build — BR-CA-Irv-FW1 & Branch Switch
Generates Branch pfSense config guide, configures BR-SW1,
and validates the Branch site is operational.

Branch addressing:
  WAN:     100.64.0.2/30 (IPSec tunnel endpoint)
  LAN:     10.20.10.0/24
  Gateway: 10.20.10.1 (BR-CA-Irv-FW1)
  BR-SW1:  10.20.10.21

Usage:
  python3 configure_branch.py             # full run
  python3 configure_branch.py --generate  # pfSense config guide only
  python3 configure_branch.py --sw-only   # switch config only
  python3 configure_branch.py --validate  # validation only
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    EXOSSwitch, BRANCH_SWITCHES, ping_host, port_open,
    save_report, BANNER_TEXT
)

BRANCH_FW_IP  = "10.20.10.1"
BRANCH_FW_WAN = "100.64.0.2"
HQ_FW_WAN     = "100.64.0.1"
BRANCH_SW_IP  = "10.20.10.21"
BRANCH_SUBNET = "10.20.10.0/24"


# ─── PFSENSE BRANCH CONFIG GUIDE ──────────────────────────────────────────────

def print_pfsense_branch_guide():
    print(f"""
=============================================================
Branch pfSense (BR-CA-Irv-FW1) Configuration — Task 8
This must be done via pfSense console + GUI
=============================================================

STEP 1: Console — Assign Interfaces
  Option 1: Assign Interfaces
    em0 = WAN
    em1 = LAN
  Confirm: y

STEP 2: Console — Set Interface IPs
  Option 2: Set interface(s) IP address

  WAN (em0):
    Configure IPv4 via static: y
    IP: {BRANCH_FW_WAN}
    Subnet: 30
    Upstream gateway: {HQ_FW_WAN}

  LAN (em1):
    Configure IPv4: y
    IP: {BRANCH_FW_IP}
    Subnet: 24
    Enable DHCP on LAN: y
    DHCP range: 10.20.10.50 - 10.20.10.150

STEP 3: GUI — https://{BRANCH_FW_IP}
  Default creds: admin / pfsense

STEP 4: GUI — Services → DHCP Server → LAN
  Enable: ✓
  Range: 10.20.10.50 → 10.20.10.150
  DNS: 8.8.8.8
  Gateway: {BRANCH_FW_IP}

STEP 5: GUI — Firewall → Rules → LAN
  Add: Allow LAN to Any (for initial setup)
  (VPN rules added in Task 9)

=============================================================
""")


# ─── BRANCH SWITCH CONFIG ─────────────────────────────────────────────────────

def build_branch_sw_commands():
    """EXOS commands for BR-SW1 initial setup (run after SSH enabled via console)."""
    banner_lines = BANNER_TEXT.strip().split('\n')
    return [
        # MGMT VLAN IP
        f"configure vlan Default ipaddress {BRANCH_SW_IP} 255.255.255.0",
        f"configure iproute add default {BRANCH_FW_IP}",
        # SSH (if not enabled — enable ssh2 must be done on console first)
        "enable ssh2",
        "configure ssh2 key",       # generates RSA key if not present
        # SNMP disabled for security
        "disable snmp",
        # NTP
        f"enable sntp-client",
        f"configure sntp-client server primary {BRANCH_FW_IP}",
        # Syslog to HQ (via VPN — configure after Task 9 is complete)
        # For now, log locally
        "enable log target console",
        "configure log target console severity informational",
    ]


def configure_branch_switch():
    section(f"Configuring BR-SW1 ({BRANCH_SW_IP})")
    try:
        with EXOSSwitch(BRANCH_SW_IP) as sw:
            cmds = build_branch_sw_commands()
            for cmd in cmds:
                out = sw.cmd(cmd)
                if "Error" in out or "Invalid" in out:
                    warn(f"  ⚠ {cmd!r}")
                else:
                    info(f"  ✓ {cmd}")

            # Deploy banner
            banner_lines = BANNER_TEXT.strip().split('\n')
            sw.conn.send_command_timing("configure banner")
            import time
            for line in banner_lines:
                sw.conn.send_command_timing(line if line else " ")
                time.sleep(0.05)
            sw.conn.send_command_timing(".")
            sw.save()
            ok("BR-SW1 configured successfully")
            return True
    except Exception as e:
        fail(f"BR-SW1 configuration failed: {e}")
        return False


# ─── VALIDATION ───────────────────────────────────────────────────────────────

def validate_branch():
    results = []
    passed = failed = 0

    section("Branch Site Validation")

    checks = [
        ("Branch FW LAN",     BRANCH_FW_IP,   True,  "ping"),
        ("Branch SW1 MGMT",   BRANCH_SW_IP,   True,  "ping"),
        ("Branch FW WAN",     BRANCH_FW_WAN,  True,  "ping"),
        ("HQ FW WAN",         HQ_FW_WAN,      True,  "ping"),
        ("Branch SSH (FW)",   BRANCH_FW_IP,   True,  "ssh"),
        ("Branch SSH (SW)",   BRANCH_SW_IP,   True,  "ssh"),
    ]

    for label, host, should_pass, check_type in checks:
        if check_type == "ping":
            alive = ping_host(host)
        else:
            alive = port_open(host, 22)

        if alive == should_pass:
            ok(f"{label:<35} {host}")
            passed += 1
            status = "PASS"
        else:
            fail(f"{label:<35} {host} — NOT REACHABLE")
            failed += 1
            status = "FAIL"

        results.append({
            "label": label, "host": host,
            "check": check_type, "status": status
        })

    return results, passed, failed


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task 8: Branch Site Configuration")
    parser.add_argument("--generate", action="store_true", help="Print pfSense guide only")
    parser.add_argument("--sw-only",  action="store_true", help="Configure branch switch only")
    parser.add_argument("--validate", action="store_true", help="Validate only")
    args = parser.parse_args()

    banner_print("Task 8 — Branch Site Build")

    if not args.validate and not args.sw_only:
        print_pfsense_branch_guide()

    if args.generate:
        return

    sw_success = True
    if not args.validate and not args.generate:
        sw_success = configure_branch_switch()

    results, passed, failed = validate_branch()

    report = {
        "timestamp": datetime.now().isoformat(),
        "task": "Task 8 — Branch Site",
        "switch_configured": sw_success,
        "validation": results,
        "summary": {"passed": passed, "failed": failed},
    }
    save_report(report, "task8_branch_report.json", "Task 8 report")
    banner_print(f"Results: {passed} PASS | {failed} FAIL")


if __name__ == "__main__":
    main()
