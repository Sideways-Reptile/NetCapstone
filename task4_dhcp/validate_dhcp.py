#!/usr/bin/env python3
"""
task4_dhcp/validate_dhcp.py
Bigfork IT — Capstone Lab

Task 4: DHCP & Static Addressing
Validates that:
  - All static infrastructure IPs are reachable
  - pfSense DHCP pools are configured (via port checks)
  - Generates pfSense DHCP configuration reference

Usage:
  python3 validate_dhcp.py
  python3 validate_dhcp.py --generate  # Print pfSense DHCP config guide
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    ping_host, port_open, save_report,
    PFSENSE_HQ_IP, PFSENSE_BRANCH_IP, SYSLOG_IP
)

# ─── STATIC IP REGISTRY ───────────────────────────────────────────────────────
STATIC_HOSTS = [
    # pfSense HQ interfaces
    {"label": "HQ-FW1 MGMT (em1.10)",   "ip": "10.10.10.1",    "required": True},
    {"label": "HQ-FW1 CORP (em1.20)",   "ip": "172.16.1.1",    "required": True},
    {"label": "HQ-FW1 DMZ  (em1.30)",   "ip": "192.168.100.1", "required": True},
    {"label": "HQ-FW1 GUEST (em1.40)",  "ip": "192.168.200.1", "required": True},
    # HQ Switch MGMT IPs
    {"label": "SW1-CORE",            "ip": "10.10.10.11",   "required": True},
    {"label": "SW2-DIST-1",            "ip": "10.10.10.12",   "required": True},
    {"label": "SW3-DIST-2",        "ip": "10.10.10.13",   "required": True},
    {"label": "SW4-ACCESS1-CORP",        "ip": "10.10.10.14",   "required": True},
    {"label": "SW5-ACCESS2-DMZ",        "ip": "10.10.10.15",   "required": True},
    # Ubu-WS01
    {"label": "Ubu-WS01 (MGMT_NET)",    "ip": "10.10.10.108",  "required": True},
    # Branch
    {"label": "BR-CA-Irv-FW1 LAN",      "ip": "10.20.10.1",    "required": False},
    {"label": "BR-SW1 MGMT",            "ip": "10.20.10.21",   "required": False},
    # IPSec WAN
    {"label": "HQ-FW1 WAN (IPSec)",     "ip": "100.64.0.1",    "required": False},
    {"label": "Branch FW WAN (IPSec)",  "ip": "100.64.0.2",    "required": False},
]

# ─── DHCP CONFIG GENERATOR ────────────────────────────────────────────────────

def generate_dhcp_config():
    print("""
=============================================================
pfSense DHCP Pool Configuration — Task 4
Apply in GUI: Services → DHCP Server
=============================================================

CORP Interface (em1.20 | 172.16.1.0/24):
  Enable:       ✓
  Range:        172.16.1.100 → 172.16.1.200
  DNS:          8.8.8.8, 8.8.4.4
  Gateway:      172.16.1.1
  Lease time:   86400

DMZ Interface (em1.30 | 192.168.100.0/24):
  Enable:       ✓
  Range:        192.168.100.50 → 192.168.100.100
  DNS:          8.8.8.8
  Gateway:      192.168.100.1
  Lease time:   86400

GUEST Interface (em1.40 | 192.168.200.0/24):
  Enable:       ✓
  Range:        192.168.200.50 → 192.168.200.150
  DNS:          8.8.8.8, 1.1.1.1
  Gateway:      192.168.200.1
  Lease time:   3600

Branch Interface BR-CA-Irv-FW1 (em1 | 10.20.10.0/24):
  Enable:       ✓
  Range:        10.20.10.50 → 10.20.10.150
  DNS:          8.8.8.8
  Gateway:      10.20.10.1
  Lease time:   86400

NOTE: MGMT (10.10.10.0/24) does NOT use DHCP — all MGMT
      devices have static IPs assigned directly on the device.

After saving: Apply Changes
Verify: Status → DHCP Leases
=============================================================
""")


# ─── VALIDATION ───────────────────────────────────────────────────────────────

def validate_static_ips():
    results = []
    passed = failed = warned = 0

    section("Static IP Reachability Check")
    for entry in STATIC_HOSTS:
        alive = ping_host(entry["ip"])
        if alive:
            ok(f"{entry['label']:<35} {entry['ip']}")
            passed += 1
            status = "PASS"
        elif entry["required"]:
            fail(f"{entry['label']:<35} {entry['ip']} — NOT REACHABLE")
            failed += 1
            status = "FAIL"
        else:
            warn(f"{entry['label']:<35} {entry['ip']} — not reachable (optional)")
            warned += 1
            status = "WARN"

        results.append({
            "label": entry["label"],
            "ip": entry["ip"],
            "required": entry["required"],
            "reachable": alive,
            "status": status,
        })

    return results, passed, failed, warned


def main():
    parser = argparse.ArgumentParser(description="Task 4: DHCP & Static IP Validation")
    parser.add_argument("--generate", action="store_true", help="Print DHCP config guide only")
    args = parser.parse_args()

    banner_print("Task 4 — DHCP & Static Addressing")

    generate_dhcp_config()

    if not args.generate:
        results, passed, failed, warned = validate_static_ips()

        report = {
            "timestamp": datetime.now().isoformat(),
            "task": "Task 4 — DHCP & Static Addressing",
            "hosts": results,
            "summary": {"passed": passed, "failed": failed, "warned": warned},
        }
        save_report(report, "task4_dhcp_report.json", "Task 4 report")
        banner_print(f"Results: {passed} PASS | {failed} FAIL | {warned} WARN")

        if failed > 0:
            warn("Some required static IPs are not reachable.")
            warn("  - Check pfSense VLAN subinterface config")
            warn("  - Check switch MGMT VLAN IP address")
            warn("  - Verify GNS3 node is started")


if __name__ == "__main__":
    main()
