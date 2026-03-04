#!/usr/bin/env python3
"""
task9_ipsec/configure_ipsec.py
Bigfork IT — Capstone Lab

Task 9: IPSec Site-to-Site VPN — HQ ↔ Branch
Generates pfSense IPSec configuration guides for both ends
and validates the tunnel is up after manual configuration.

VPN Parameters:
  IKE:      IKEv2
  Enc:      AES-256
  Hash:     SHA-256
  DH Group: 14 (2048-bit)
  Auth:     Pre-Shared Key
  HQ WAN:   100.64.0.1
  BR WAN:   100.64.0.2

Tunnel networks:
  HQ CORP:   172.16.1.0/24
  HQ DMZ:    192.168.100.0/24
  Branch LAN: 10.20.10.0/24

Usage:
  python3 configure_ipsec.py --generate       # Print config guides
  python3 configure_ipsec.py --validate       # Test tunnel connectivity
  python3 configure_ipsec.py                  # Both
"""

import argparse
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    ping_host, port_open, save_report, PFSenseSSH
)

HQ_WAN      = "100.64.0.1"
BR_WAN      = "100.64.0.2"
HQ_CORP     = "172.16.1.0/24"
HQ_DMZ      = "192.168.100.0/24"
BR_LAN      = "10.20.10.0/24"
PSK         = "BigforkIT_Lab_PSK_2026!"   # Change this in production


# ─── CONFIG GUIDES ────────────────────────────────────────────────────────────

def print_hq_ipsec_guide():
    print(f"""
=============================================================
HQ-FW1 IPSec Configuration — Task 9
pfSense GUI: VPN → IPSec
=============================================================

── PHASE 1 (IKE) ──────────────────────────────────────────
  Click: Add P1

  General:
    Key Exchange Version:  IKEv2
    Interface:             WAN
    Remote Gateway:        {BR_WAN}
    Description:           HQ-to-Branch-VPN

  Authentication:
    Auth Method:           Mutual PSK
    My Identifier:         My IP Address
    Peer Identifier:       Peer IP Address
    Pre-Shared Key:        {PSK}

  Encryption:
    Encryption Algorithm:  AES   |  256 bits
    Hash Algorithm:        SHA256
    DH Group:              14 (2048 bit)
    Lifetime:              28800

  Advanced:
    Dead Peer Detection:   ✓ Enabled
    Delay: 10  |  Maxfail: 3

  Save

── PHASE 2 (IPSec SA) — First pair ────────────────────────
  Click: Show Phase 2 Entries → Add P2

  SA #1 — CORP:
    Description:       HQ-CORP to Branch
    Local Network:     Network  172.16.1.0/24
    Remote Network:    Network  {BR_LAN}
    Encryption:        AES 256 | SHA256 | PFS Group 14
    Lifetime:          3600
    Save

  SA #2 — DMZ:
    Description:       HQ-DMZ to Branch
    Local Network:     Network  192.168.100.0/24
    Remote Network:    Network  {BR_LAN}
    Encryption:        AES 256 | SHA256 | PFS Group 14
    Lifetime:          3600
    Save

  Apply Changes

── FIREWALL RULES (IPSec interface) ───────────────────────
  Firewall → Rules → IPSec tab → Add:
    Pass | Source: {BR_LAN} | Dest: 172.16.1.0/24 | Any
    Pass | Source: {BR_LAN} | Dest: 192.168.100.0/24 | Any

  Apply Changes

=============================================================
""")


def print_branch_ipsec_guide():
    print(f"""
=============================================================
BR-CA-Irv-FW1 IPSec Configuration — Task 9
pfSense GUI: VPN → IPSec
=============================================================

── PHASE 1 (IKE) ──────────────────────────────────────────
  Key Exchange Version:  IKEv2
  Interface:             WAN
  Remote Gateway:        {HQ_WAN}
  Description:           Branch-to-HQ-VPN

  Auth Method:           Mutual PSK
  Pre-Shared Key:        {PSK}    ← MUST MATCH HQ EXACTLY

  Encryption:            AES 256 | SHA256 | DH Group 14
  Lifetime:              28800
  Save

── PHASE 2 (IPSec SA) ─────────────────────────────────────
  SA #1:
    Local Network:   {BR_LAN}
    Remote Network:  172.16.1.0/24   (HQ CORP)
    Enc: AES 256 | SHA256 | PFS 14  |  Lifetime: 3600
    Save

  SA #2:
    Local Network:   {BR_LAN}
    Remote Network:  192.168.100.0/24  (HQ DMZ)
    Enc: AES 256 | SHA256 | PFS 14  |  Lifetime: 3600
    Save

  Apply Changes

── FIREWALL RULES (IPSec interface) ───────────────────────
  Firewall → Rules → IPSec tab → Add:
    Pass | Source: {BR_LAN} | Dest: 172.16.1.0/24 | Any
    Pass | Source: {BR_LAN} | Dest: 192.168.100.0/24 | Any

  Apply Changes

── INITIATE TUNNEL ────────────────────────────────────────
  Status → IPSec → Click [Connect P1 and P2s]
  Both Phase 1 and Phase 2 should show: ESTABLISHED

=============================================================
""")


# ─── VPN VALIDATION ───────────────────────────────────────────────────────────

def validate_vpn():
    results = []
    passed = failed = 0

    section("IPSec VPN Tunnel Validation")

    # Basic WAN endpoint reachability
    checks = [
        ("HQ WAN endpoint",       HQ_WAN,         True, "ping"),
        ("Branch WAN endpoint",   BR_WAN,          True, "ping"),
        ("Branch LAN via VPN",    "10.20.10.1",    True, "ping"),
        ("Branch SW1 via VPN",    "10.20.10.21",   True, "ping"),
        ("HQ CORP gateway",       "172.16.1.1",    True, "ping"),
        ("HQ DMZ gateway",        "192.168.100.1", True, "ping"),
        ("pfSense HQ HTTPS",      "10.10.10.1",    True, "https"),
    ]

    for label, host, should_pass, check_type in checks:
        if check_type == "ping":
            result = ping_host(host)
        elif check_type == "https":
            result = port_open(host, 443)
        else:
            result = ping_host(host)

        if result == should_pass:
            ok(f"{label:<40} {host}")
            passed += 1
            status = "PASS"
        else:
            fail(f"{label:<40} {host} — NOT REACHABLE")
            failed += 1
            status = "FAIL"

        results.append({"label": label, "host": host, "status": status})

    section("Tunnel Traffic Validation (requires VPN established)")
    info("For full validation, run these from Branch PC1 (10.20.10.x):")
    info(f"  ping {HQ_WAN}        # HQ WAN endpoint")
    info(f"  ping 172.16.1.1     # HQ CORP gateway via tunnel")
    info(f"  ping 192.168.100.1  # HQ DMZ via tunnel")
    info("")
    info("And from Ubu-WS01 (HQ MGMT):")
    info(f"  ping 10.20.10.1     # Branch gateway via tunnel")
    info(f"  ping 10.20.10.100   # Branch PC1 via tunnel")

    return results, passed, failed


# ─── STATUS CHECK VIA PFSENSE SHELL ──────────────────────────────────────────

def check_ipsec_status_shell():
    """Try to get IPSec status via pfSense SSH shell."""
    section("Checking IPSec Status via pfSense Shell")
    try:
        with PFSenseSSH("10.10.10.1") as fw:
            out = fw.shell("ipsec statusall 2>&1 | head -40")
            if "ESTABLISHED" in out:
                ok("IPSec tunnel ESTABLISHED")
            elif "CONNECTING" in out:
                warn("IPSec tunnel is CONNECTING — may need a moment to establish")
            else:
                fail("IPSec tunnel does not appear ESTABLISHED")
                info("Run in pfSense GUI: Status → IPSec → Connect")
            info(f"IPSec status output:\n{out[:500]}")
    except Exception as e:
        warn(f"Could not check IPSec status via SSH: {e}")
        warn("Check manually: pfSense GUI → Status → IPSec")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task 9: IPSec VPN Configuration & Validation")
    parser.add_argument("--generate", action="store_true", help="Print config guides only")
    parser.add_argument("--validate", action="store_true", help="Validate tunnel only")
    args = parser.parse_args()

    banner_print("Task 9 — IPSec Site-to-Site VPN")

    if not args.validate:
        print_hq_ipsec_guide()
        print_branch_ipsec_guide()

    if not args.generate:
        check_ipsec_status_shell()
        results, passed, failed = validate_vpn()

        report = {
            "timestamp": datetime.now().isoformat(),
            "task": "Task 9 — IPSec VPN",
            "psk_reminder": "PSK must match on both firewalls",
            "validation": results,
            "summary": {"passed": passed, "failed": failed},
        }
        save_report(report, "task9_ipsec_report.json", "Task 9 report")
        banner_print(f"Results: {passed} PASS | {failed} FAIL")

        if failed > 0:
            warn("VPN tunnel validation failed. Check:")
            warn("  - Both pfSense nodes running in GNS3")
            warn("  - PSK matches exactly on both sides")
            warn("  - Phase 1 and Phase 2 parameters identical")
            warn("  - pfSense GUI → Status → IPSec → Connect P1 and P2s")


if __name__ == "__main__":
    main()
