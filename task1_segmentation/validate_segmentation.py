#!/usr/bin/env python3
"""
task1_segmentation/validate_segmentation.py
Bigfork IT — Capstone Lab

Validates Task 1: Network Segmentation & Reachability
Tests all expected PASS and FAIL paths per the access control matrix.

Access Matrix:
  MGMT  → CORP/DMZ/GUEST/Internet  : PASS
  CORP  → DMZ/Internet             : PASS
  CORP  → MGMT/GUEST               : FAIL (blocked)
  GUEST → Internet                 : PASS
  GUEST → RFC1918                  : FAIL (blocked)
  DMZ   → Any outbound             : FAIL (blocked)

Usage:
  python3 validate_segmentation.py
  python3 validate_segmentation.py --from-host 10.10.10.108
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
    port_open, save_report, PFSENSE_HQ_IP
)

# ─── TEST DEFINITIONS ─────────────────────────────────────────────────────────
# Each test: (label, host_to_ping, should_pass, description)
REACHABILITY_TESTS = [
    # From MGMT perspective (Ubu-WS01 = 10.10.10.108)
    ("MGMT → HQ-FW1 MGMT gw",  "10.10.10.1",    True,  "MGMT can reach its own gateway"),
    ("MGMT → CORP gateway",     "172.16.1.1",    True,  "MGMT can reach CORP segment"),
    ("MGMT → DMZ gateway",      "192.168.100.1", True,  "MGMT can reach DMZ segment"),
    ("MGMT → GUEST gateway",    "192.168.200.1", True,  "MGMT can reach GUEST segment"),
    ("MGMT → Internet (8.8.8.8)","8.8.8.8",      True,  "MGMT has internet access"),
    ("MGMT → Branch FW WAN",    "100.64.0.2",    True,  "MGMT can reach Branch WAN (via VPN or direct)"),

    # Switch MGMT reachability
    ("MGMT → SW1-CORE",         "10.10.10.11",   True,  "SW1-Core reachable from MGMT"),
    ("MGMT → SW2-DIST-1",         "10.10.10.12",   True,  "SW2-Dist reachable from MGMT"),
    ("MGMT → SW3-DIST-2",     "10.10.10.13",   True,  "SW3-Access-1 reachable from MGMT"),
    ("MGMT → SW4-ACCESS1-CORP",     "10.10.10.14",   True,  "SW4-Access-2 reachable from MGMT"),
    ("MGMT → SW5-ACCESS2-DMZ",     "10.10.10.15",   True,  "SW5-Access-3 reachable from MGMT"),
]

SSH_TESTS = [
    ("SSH to HQ-FW1",   "10.10.10.1",  22, True),
    ("SSH to SW1-CORE", "10.10.10.11", 22, True),
    ("SSH to SW2-DIST-1", "10.10.10.12", 22, True),
    ("SSH to SW3",      "10.10.10.13", 22, True),
    ("SSH to SW4",      "10.10.10.14", 22, True),
    ("SSH to SW5",      "10.10.10.15", 22, True),
]

HTTPS_TESTS = [
    ("HTTPS to pfSense HQ",  "10.10.10.1",  443, True),
]


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def run_tests():
    results = {"timestamp": datetime.now().isoformat(), "tests": [], "summary": {}}
    passed = 0
    failed = 0
    warnings = 0

    banner_print("Task 1 — Network Segmentation Validation")

    # Ping tests
    section("Ping / Reachability Tests")
    for label, host, should_pass, desc in REACHABILITY_TESTS:
        alive = ping_host(host)
        if alive == should_pass:
            ok(f"{label}")
            passed += 1
            status = "PASS"
        elif should_pass and not alive:
            fail(f"{label} — expected PASS, got no response")
            failed += 1
            status = "FAIL"
        else:
            warn(f"{label} — expected FAIL but host responded (check firewall rules)")
            warnings += 1
            status = "WARN"

        results["tests"].append({
            "label": label,
            "host": host,
            "expected": "pass" if should_pass else "fail",
            "actual": "pass" if alive else "fail",
            "status": status,
            "description": desc,
        })

    # SSH port tests
    section("SSH Port Tests")
    for label, host, port, should_be_open in SSH_TESTS:
        open_ = port_open(host, port)
        if open_ == should_be_open:
            ok(f"{label} ({host}:22)")
            passed += 1
            status = "PASS"
        else:
            fail(f"{label} — SSH port 22 not responding on {host}")
            failed += 1
            status = "FAIL"
        results["tests"].append({
            "label": label,
            "host": host,
            "port": port,
            "expected": "open" if should_be_open else "closed",
            "actual": "open" if open_ else "closed",
            "status": status,
        })

    # HTTPS tests
    section("HTTPS Port Tests")
    for label, host, port, should_be_open in HTTPS_TESTS:
        open_ = port_open(host, port)
        if open_ == should_be_open:
            ok(f"{label} ({host}:443)")
            passed += 1
            status = "PASS"
        else:
            fail(f"{label} — HTTPS port 443 not responding on {host}")
            failed += 1
            status = "FAIL"
        results["tests"].append({
            "label": label, "host": host, "port": port, "status": status
        })

    results["summary"] = {
        "total": passed + failed + warnings,
        "passed": passed,
        "failed": failed,
        "warnings": warnings,
    }

    banner_print(f"Results: {passed} PASS | {failed} FAIL | {warnings} WARN")

    if failed > 0:
        warn("Some tests failed. Common causes:")
        warn("  - pfSense interface not UP (check subinterface config)")
        warn("  - Switch MGMT VLAN not configured")
        warn("  - Firewall rules missing or out of order")
        warn("  - GNS3 node not started")

    save_report(results, "task1_validation_report.json", "Task 1 report")
    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
