#!/usr/bin/env python3
"""
task2_guest_acl/configure_guest_acl.py
Bigfork IT — Capstone Lab

Task 2: Guest Network ACL — Internet-Only Access
Generates pfSense firewall rule configuration and validates isolation.

This script:
  1. Generates the pfSense alias and firewall rule config (printed for copy-paste)
  2. Tests GUEST isolation from a MGMT-side perspective
  3. Saves a validation report

NOTE: pfSense rule changes must be applied via the GUI or pfSense API.
      This script generates the config and validates the result.

Usage:
  python3 configure_guest_acl.py             # generate + validate
  python3 configure_guest_acl.py --generate  # generate config only
  python3 configure_guest_acl.py --validate  # validate only
"""

import argparse
import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print, ping_host,
    port_open, save_report
)

# ─── CONFIG ───────────────────────────────────────────────────────────────────
GUEST_GATEWAY   = "192.168.200.1"
GUEST_NETWORK   = "192.168.200.0/24"
INTERNAL_HOSTS  = ["10.10.10.1", "172.16.1.1", "192.168.100.1"]
INTERNET_HOSTS  = ["8.8.8.8", "1.1.1.1"]
PUBLIC_DNS      = ["8.8.8.8", "8.8.4.4", "1.1.1.1", "1.0.0.1"]


# ─── PFSENSE CONFIG GENERATOR ─────────────────────────────────────────────────

def generate_pfsense_config():
    """
    Print pfSense alias and firewall rule config.
    Apply manually in GUI: Firewall → Aliases then Firewall → Rules → GUEST
    """
    config = """
=============================================================
pfSense GUEST ACL Configuration — Task 2
=============================================================
Apply in pfSense GUI:

STEP 1: Create Aliases
  Firewall → Aliases → IP → Add

  Alias 1:
    Name:        RFC1918_ALL
    Type:        Network(s)
    Networks:    10.0.0.0/8
                 172.16.0.0/12
                 192.168.0.0/16
    Description: All RFC1918 Private Networks

  Alias 2:
    Name:        PUBLIC_DNS
    Type:        Host(s)
    Hosts:       8.8.8.8
                 8.8.4.4
                 1.1.1.1
                 1.0.0.1
    Description: Public DNS Servers

STEP 2: Apply Aliases → click [Apply Changes]

STEP 3: Firewall → Rules → GUEST
  (Delete any existing Allow All rule first)

  Rule 1 (HIGHEST PRIORITY — must be at top):
    Action:      Block
    Interface:   GUEST
    Protocol:    Any
    Source:      GUEST net
    Destination: RFC1918_ALL
    Log:         ✓ (checked)
    Description: Block GUEST to RFC1918 Internal Networks

  Rule 2:
    Action:      Pass
    Interface:   GUEST
    Protocol:    UDP
    Source:      GUEST net
    Destination: PUBLIC_DNS  Port: 53
    Log:         ✓
    Description: Allow GUEST DNS to Public Servers

  Rule 3:
    Action:      Pass
    Interface:   GUEST
    Protocol:    Any
    Source:      GUEST net
    Destination: any
    Log:         ✓
    Description: Allow GUEST Internet Access

STEP 4: Apply Changes

=============================================================
Verify rule ORDER matches above (Rule 1 must be first).
pfSense processes rules top-to-bottom, first match wins.
=============================================================
"""
    print(config)


# ─── VALIDATION ───────────────────────────────────────────────────────────────

def validate_from_mgmt():
    """
    From MGMT perspective, test that GUEST gateway is reachable
    but validate that expected isolation is in place.
    
    Full GUEST-side testing requires a device on GUEST VLAN.
    This script tests what's reachable from MGMT (Ubu-WS01).
    """
    results = []
    passed = failed = 0

    section("Validating GUEST Gateway Reachability (from MGMT)")
    # MGMT should always be able to reach GUEST gateway
    alive = ping_host(GUEST_GATEWAY)
    if alive:
        ok(f"GUEST gateway {GUEST_GATEWAY} reachable from MGMT")
        passed += 1
        results.append({"test": "MGMT→GUEST gw", "status": "PASS"})
    else:
        fail(f"GUEST gateway {GUEST_GATEWAY} NOT reachable — check VLAN 40 on pfSense")
        failed += 1
        results.append({"test": "MGMT→GUEST gw", "status": "FAIL"})

    section("Internet Reachability Test (from this host)")
    for host in INTERNET_HOSTS:
        alive = ping_host(host)
        if alive:
            ok(f"Internet {host} reachable")
            passed += 1
            results.append({"test": f"Internet {host}", "status": "PASS"})
        else:
            warn(f"Internet {host} not reachable — check WAN/NAT")
            results.append({"test": f"Internet {host}", "status": "WARN"})

    section("pfSense Port Checks")
    for host in INTERNAL_HOSTS:
        alive = ping_host(host)
        status = "PASS" if alive else "WARN"
        label = f"pfSense interface {host}"
        if alive:
            ok(f"{label} UP")
        else:
            warn(f"{label} not responding — check subinterface")
        results.append({"test": label, "status": status})

    return results, passed, failed


def print_manual_tests():
    """Print the manual GUEST-side tests that require a device on GUEST VLAN."""
    print("""
=============================================================
Manual GUEST-Side Validation (run from a GUEST VLAN device)
=============================================================
These tests MUST be run from a device on GUEST VLAN (192.168.200.x):

  Should FAIL (timeout expected):
    ping 10.10.10.1      # MGMT gateway — BLOCKED
    ping 172.16.1.1      # CORP gateway — BLOCKED
    ping 192.168.100.1   # DMZ gateway  — BLOCKED

  Should PASS:
    ping 8.8.8.8         # Google DNS   — ALLOWED
    ping 1.1.1.1         # Cloudflare   — ALLOWED
    ping google.com      # DNS + HTTP   — ALLOWED

After testing, check pfSense logs:
  Status → System Logs → Firewall
  Look for: Block GUEST to RFC1918 entries
=============================================================
""")


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task 2: Guest ACL Configuration & Validation")
    parser.add_argument("--generate", action="store_true", help="Generate pfSense config only")
    parser.add_argument("--validate", action="store_true", help="Validate only")
    args = parser.parse_args()

    banner_print("Task 2 — Guest ACL: Internet-Only Access")

    if not args.validate:
        generate_pfsense_config()

    if not args.generate:
        results, passed, failed = validate_from_mgmt()
        print_manual_tests()

        report = {
            "timestamp": datetime.now().isoformat(),
            "task": "Task 2 — Guest ACL",
            "tests": results,
            "summary": {"passed": passed, "failed": failed},
        }
        save_report(report, "task2_guest_acl_report.json", "Task 2 report")

        banner_print(f"Automated checks: {passed} PASS | {failed} FAIL")
        if failed == 0:
            ok("Automated checks passed. Complete manual GUEST-side tests above.")


if __name__ == "__main__":
    main()
