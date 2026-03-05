#!/usr/bin/env python3
"""
Task 10 — Port Security: Sticky MAC + Port Isolation
Bigfork IT GNS3 Capstone

Usage:
    python3 task10_audit/configure_port_security.py               # configure all
    python3 task10_audit/configure_port_security.py --verify-only # verify only
    python3 task10_audit/configure_port_security.py --host 10.10.10.14 # single switch

Design:
    CORP / DMZ access ports  → Sticky MAC + Port Isolation
    GUEST access port        → Port Isolation only (high-churn, no MAC lock)
    Branch access ports      → Sticky MAC + Port Isolation
    Trunk ports              → Never locked or isolated
"""

import sys
import argparse
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from utils.exos_helper import EXOSSwitch, SWITCH_INVENTORY

# ── Port security configuration per switch ────────────────────────────────────
PORT_SECURITY_CONFIG = {
    "SW4-ACCESS1-CORP": {
        "ip": "10.10.10.14",
        "mac_lock_ports": [
            {"port": 3, "vlan": "CORP_NET", "desc": "CORP devices (WIN10-WS2/PC2)"},
        ],
        "isolate_ports": [3],
        "note": "Fixed CORP workstations — MAC lock + isolation",
    },
    "SW5-ACCESS2-DMZ": {
        "ip": "10.10.10.15",
        "mac_lock_ports": [
            {"port": 3, "vlan": "DMZ_NET", "desc": "FILE-SVR1 (DMZ server)"},
        ],
        "isolate_ports": [3],
        "note": "DMZ server — MAC lock + isolation",
    },
    "SW3-DIST-2": {
        "ip": "10.10.10.13",
        "mac_lock_ports": [],   # GUEST = no MAC locking
        "isolate_ports": [4],   # port 4 = WS-Gst (GUEST_NET)
        "note": "GUEST port — isolation only, no MAC lock (high-churn environment)",
    },
    "BR-SW1": {
        "ip": "10.20.10.21",
        "mac_lock_ports": [
            {"port": 2, "vlan": "Default", "desc": "WIN10-WS1"},
            {"port": 3, "vlan": "Default", "desc": "PC1 (VPCS)"},
        ],
        "isolate_ports": [2, 3],
        "note": "Branch fixed endpoints — MAC lock + isolation",
    },
}

# ── Helpers ───────────────────────────────────────────────────────────────────
results = []

def header(title):
    line = f"\n{'='*60}\n  {title}\n{'='*60}"
    print(line)
    results.append(line)

def ok(msg, detail=""):
    line = f"  ✅ PASS  {msg}"
    if detail:
        line += f"\n         → {detail}"
    print(line)
    results.append(line)

def fail(msg, detail=""):
    line = f"  ❌ FAIL  {msg}"
    if detail:
        line += f"\n         → {detail}"
    print(line)
    results.append(line)

def info(msg):
    line = f"  ℹ  INFO  {msg}"
    print(line)
    results.append(line)

# ── Configure ─────────────────────────────────────────────────────────────────

def configure_switch(name, cfg):
    ip = cfg["ip"]
    header(f"Configuring {name} ({ip})")
    info(cfg["note"])

    try:
        with EXOSSwitch(ip) as sw:

            # Enable MAC locking globally if any ports need it
            if cfg["mac_lock_ports"]:
                sw.send_command("enable mac-locking")
                ok("MAC locking enabled globally")

                for entry in cfg["mac_lock_ports"]:
                    port = entry["port"]
                    vlan = entry["vlan"]
                    desc = entry["desc"]
                    cmds = [
                        f"enable mac-locking ports {port} vlan {vlan}",
                        f"configure mac-locking ports {port} vlan {vlan} maximum-MAC-addresses 1",
                        f"configure mac-locking ports {port} vlan {vlan} learn-until-lock",
                    ]
                    for cmd in cmds:
                        sw.send_command(cmd)
                    ok(f"MAC lock configured: port {port} vlan {vlan}", desc)
            else:
                info("No MAC locking configured (GUEST port — isolation only)")

            # Port isolation
            for port in cfg["isolate_ports"]:
                sw.send_command(f"configure port {port} isolation on")
                ok(f"Port {port} isolation enabled")

            sw.send_command("save configuration")
            ok("Configuration saved")

    except Exception as e:
        fail(f"Could not connect to {name} ({ip})", str(e))


def verify_switch(name, cfg):
    ip = cfg["ip"]
    header(f"Verifying {name} ({ip})")

    try:
        with EXOSSwitch(ip) as sw:

            # Verify MAC locking
            if cfg["mac_lock_ports"]:
                for entry in cfg["mac_lock_ports"]:
                    port = entry["port"]
                    vlan = entry["vlan"]
                    output = sw.send_command(f"show mac-locking ports {port}")
                    if "enabled" in output.lower() or "locked" in output.lower():
                        ok(f"MAC locking active: port {port} vlan {vlan}")
                    else:
                        fail(f"MAC locking NOT active: port {port} vlan {vlan}",
                             "Run configure_port_security.py to apply")
            else:
                info("GUEST port — MAC locking intentionally not configured")

            # Verify port isolation
            iso_output = sw.send_command("show port isolation")
            for port in cfg["isolate_ports"]:
                if str(port) in iso_output:
                    ok(f"Port {port} isolation verified")
                else:
                    fail(f"Port {port} isolation NOT found in output",
                         "Run configure_port_security.py to apply")

    except Exception as e:
        fail(f"Could not connect to {name} ({ip})", str(e))


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Configure port security on EXOS switches")
    parser.add_argument("--verify-only", action="store_true",
                        help="Verify current state without making changes")
    parser.add_argument("--host", metavar="IP",
                        help="Target a single switch by IP address")
    args = parser.parse_args()

    print("\n" + "="*60)
    print("  BIGFORK IT — PORT SECURITY CONFIGURATION")
    print("  Task 10 — Sticky MAC + Port Isolation")
    print("="*60)

    # Filter to single host if specified
    targets = PORT_SECURITY_CONFIG.items()
    if args.host:
        targets = [(n, c) for n, c in targets if c["ip"] == args.host]
        if not targets:
            print(f"\n  ERROR: No switch found with IP {args.host}")
            print(f"  Known IPs: {[c['ip'] for c in PORT_SECURITY_CONFIG.values()]}")
            sys.exit(1)

    if args.verify_only:
        print("\n  MODE: Verify only — no changes will be made\n")
        for name, cfg in targets:
            verify_switch(name, cfg)
    else:
        print("\n  MODE: Configure + Verify\n")
        print("  ⚠  NOTE: Plug in all legitimate devices BEFORE running this script.")
        print("  ⚠  The switch must see each device's MAC before MAC locking is applied.\n")
        for name, cfg in targets:
            configure_switch(name, cfg)
        print("\n" + "="*60)
        print("  Verifying configuration was applied...")
        for name, cfg in targets:
            verify_switch(name, cfg)

    # Save report
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = Path(__file__).parent / f"port_security_report_{ts}.txt"
    with open(report_path, "w") as f:
        f.write("BIGFORK IT — PORT SECURITY REPORT\n")
        f.write(f"Generated: {datetime.now()}\n\n")
        f.write("\n".join(results))
    print(f"\n  📄 Report saved: {report_path.name}\n")


if __name__ == "__main__":
    main()
