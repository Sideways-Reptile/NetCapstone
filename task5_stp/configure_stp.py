#!/usr/bin/env python3
"""
task5_stp/configure_stp.py
Bigfork IT — Capstone Lab

Task 5: Spanning Tree Protocol (STP) — Layer 2 Redundancy
Configures Rapid STP on all EXOS switches via SSH.

EXOS STP uses MSTP (Multiple STP) — NOT Cisco rapid-pvst syntax.
SSH must already be enabled on switches (manual step — see guide).

Usage:
  python3 configure_stp.py              # configure all switches
  python3 configure_stp.py --verify     # verify only (no config changes)
  python3 configure_stp.py --host 10.10.10.11  # single switch
  python3 configure_stp.py --hq-only   # HQ switches only
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    EXOSSwitch, HQ_SWITCHES, BRANCH_SWITCHES,
    save_report, print_summary
)

# STP domain name used in EXOS
STP_DOMAIN = "s0"
LAB_VLANS  = ["Default", "MGMT_NET", "CORP_NET", "DMZ_NET", "GUEST_NET"]


# ─── STP COMMANDS ─────────────────────────────────────────────────────────────

def build_stp_commands(sw_name, sw_info):
    """Build EXOS STP configuration commands for one switch."""
    priority = sw_info.get("stp_priority", 32768)

    cmds = [
        # Ensure STP domain exists and is enabled
        f"create stpd {STP_DOMAIN}",          # safe if already exists
        f"enable stpd {STP_DOMAIN}",
        f"configure stpd {STP_DOMAIN} mode mstp cist",
        f"configure stpd {STP_DOMAIN} priority {priority}",
    ]

    # Add all known VLANs to STP domain
    for vlan in LAB_VLANS:
        cmds.append(f"configure stpd {STP_DOMAIN} add vlan {vlan} ports all")

    # PortFast equivalent on EXOS (edge ports on access switches)
    if sw_info.get("role") == "access":
        # Apply edge/auto-edge on access ports — EXOS uses 'edge' port mode
        cmds.append(
            f"configure stpd {STP_DOMAIN} ports mode edge all"
        )

    cmds.append(f"enable stpd {STP_DOMAIN} auto-bind vlan Default")

    return cmds


# ─── VERIFY STP ───────────────────────────────────────────────────────────────

def verify_stp(sw, sw_name, expected_priority):
    """
    SSH to switch and verify STP state.
    Returns dict with verification results.
    """
    result = {
        "hostname": sw_name,
        "host": sw.host,
        "stp_enabled": False,
        "priority": None,
        "is_root": False,
        "root_port": None,
        "blocked_ports": [],
        "status": "FAIL",
    }

    out = sw.cmd(f"show stpd {STP_DOMAIN}")
    if not out:
        return result

    # Check enabled
    if "Enabled" in out or "enabled" in out:
        result["stp_enabled"] = True

    # Parse priority
    p = re.search(r'Bridge\s+Priority\s*:\s*(\d+)', out)
    if p:
        result["priority"] = int(p.group(1))

    # Check if root
    if "Root Bridge" in out or "This bridge is the root" in out:
        result["is_root"] = True
    elif expected_priority == 4096:
        # Should be root
        warn(f"{sw_name}: Priority 4096 but not showing as root bridge")

    # Check priority matches expectation
    if result["priority"] == expected_priority:
        ok(f"{sw_name}: STP priority {result['priority']} ✓")
    else:
        warn(f"{sw_name}: Expected priority {expected_priority}, got {result.get('priority', 'N/A')}")

    if result["stp_enabled"]:
        result["status"] = "PASS"

    return result


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def configure_all_switches(switch_dict, verify_after=True):
    all_results = {}

    for sw_name, sw_info in switch_dict.items():
        ip       = sw_info["ip"]
        priority = sw_info.get("stp_priority", 32768)
        section(f"Configuring STP on {sw_name} ({ip}) | Priority: {priority}")

        try:
            with EXOSSwitch(ip) as sw:
                commands = build_stp_commands(sw_name, sw_info)
                info(f"Sending {len(commands)} STP commands...")
                for cmd in commands:
                    out = sw.cmd(cmd)
                    # EXOS returns error messages inline — check for common errors
                    if "Error" in out or "Invalid" in out:
                        warn(f"  ⚠ {cmd!r} → {out.strip()[:80]}")
                    else:
                        info(f"  ✓ {cmd!r}")

                sw.save()

                if verify_after:
                    vr = verify_stp(sw, sw_name, priority)
                    all_results[sw_name] = {
                        "success": vr["status"] == "PASS",
                        "verify": vr,
                    }
                else:
                    all_results[sw_name] = {"success": True}

        except Exception as e:
            fail(f"{sw_name}: {e}")
            all_results[sw_name] = {"success": False, "error": str(e)}

    return all_results


def verify_only(switch_dict):
    all_results = {}
    for sw_name, sw_info in switch_dict.items():
        ip       = sw_info["ip"]
        priority = sw_info.get("stp_priority", 32768)
        section(f"Verifying STP on {sw_name} ({ip})")
        try:
            with EXOSSwitch(ip) as sw:
                vr = verify_stp(sw, sw_name, priority)
                all_results[sw_name] = vr
        except Exception as e:
            fail(f"{sw_name}: {e}")
            all_results[sw_name] = {"status": "FAIL", "error": str(e)}
    return all_results


def print_verification_table(results):
    banner_print("STP Verification Results")
    print(f"  {'Switch':<25} {'Priority':<10} {'Root?':<8} {'Status'}")
    print(f"  {'─'*25} {'─'*10} {'─'*8} {'─'*8}")
    for name, r in results.items():
        v = r.get("verify", r)
        pri  = v.get("priority", "?")
        root = "YES" if v.get("is_root") else "no"
        stat = v.get("status", "?")
        icon = "✅" if stat == "PASS" else "❌"
        print(f"  {name:<25} {str(pri):<10} {root:<8} {icon} {stat}")


def main():
    parser = argparse.ArgumentParser(description="Task 5: Configure STP on EXOS switches")
    parser.add_argument("--verify",     action="store_true", help="Verify only — no config changes")
    parser.add_argument("--hq-only",    action="store_true", help="HQ switches only")
    parser.add_argument("--branch-only",action="store_true", help="Branch switch only")
    parser.add_argument("--host",       help="Single switch IP")
    args = parser.parse_args()

    banner_print("Task 5 — Spanning Tree Protocol Configuration")

    # Build target dict
    if args.host:
        # Try to look up by IP
        all_sw = {**HQ_SWITCHES, **BRANCH_SWITCHES}
        target = {k: v for k, v in all_sw.items() if v["ip"] == args.host}
        if not target:
            target = {args.host: {"ip": args.host, "role": "access", "stp_priority": 32768}}
    elif args.branch_only:
        target = BRANCH_SWITCHES
    elif args.hq_only:
        target = HQ_SWITCHES
    else:
        target = {**HQ_SWITCHES, **BRANCH_SWITCHES}

    if args.verify:
        results = verify_only(target)
        print_verification_table({k: {"verify": v} for k, v in results.items()})
    else:
        results = configure_all_switches(target, verify_after=True)
        print_verification_table(results)
        print_summary(results)

    report = {
        "timestamp": datetime.now().isoformat(),
        "task": "Task 5 — STP Configuration",
        "mode": "verify" if args.verify else "configure",
        "results": results,
    }
    save_report(report, "task5_stp_report.json", "Task 5 report")


if __name__ == "__main__":
    main()
