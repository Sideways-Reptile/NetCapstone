#!/usr/bin/env python3
"""
task7_vlans/configure_vlans.py
Bigfork IT — Capstone Lab

Task 7: VLAN Segmentation & 802.1Q Trunking
Configures all VLANs on all EXOS switches, sets up trunk ports
between switches, and configures access ports for endpoints.

EXOS VLAN model:
  - Tagged ports = trunk (carry multiple VLANs with 802.1Q headers)
  - Untagged ports = access (carry one VLAN, no tag added)
  - Default VLAN (tag 1) = native/untagged base

Trunk topology (HQ):
  pfSense em1 ←→ SW1-CORE (port 1)
  SW1-CORE port2 ←→ SW2-DIST-1 port1  (trunk)
  SW1-CORE port3 ←→ SW3-DIST-2 port1  (trunk)
  SW1-CORE port4 ←→ Ubu-WS01   (untagged MGMT)
  SW2-DIST-1 port2 ←→ SW4-ACCESS1-CORP port1
  SW2-DIST-1 port3 ←→ SW3-DIST-2 port3 (cross-link)
  SW3-DIST-2 port2 ←→ SW5-ACCESS2-DMZ port1
  SW3-DIST-2 port4 ←→ WS-Gst    (untagged GUEST)
  SW4-ACCESS1-CORP port3 ←→ WIN10-WS2 / PC2 (untagged CORP)
  SW5-ACCESS2-DMZ  port3 ←→ FILE-SVR1        (untagged DMZ)

Usage:
  python3 configure_vlans.py              # configure all switches
  python3 configure_vlans.py --verify     # verify VLANs only
  python3 configure_vlans.py --host 10.10.10.11
"""

import argparse
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    EXOSSwitch, HQ_SWITCHES, BRANCH_SWITCHES,
    LAB_VLANS, save_report, print_summary
)

# ─── VLAN DEFINITIONS ─────────────────────────────────────────────────────────
VLANS = [
    {"tag": 10, "name": "MGMT_NET",  "mgmt": True},
    {"tag": 20, "name": "CORP_NET",  "mgmt": False},
    {"tag": 30, "name": "DMZ_NET",   "mgmt": False},
    {"tag": 40, "name": "GUEST_NET", "mgmt": False},
]

# ─── PORT TOPOLOGY MAP ────────────────────────────────────────────────────────
# Defines which ports are trunks (tagged) and which are access (untagged)
# Port numbering is typical for EXOS in GNS3 — adjust if yours differs.

SWITCH_PORT_CONFIG = {
    "SW1-CORE": {
        # Port 1 = uplink to pfSense em1 trunk
        # Port 2 = trunk to SW2-DIST-1
        # Port 3 = trunk to SW3-DIST-2
        # Port 4 = Ubu-WS01 untagged MGMT
        "trunk_ports":  [1, 2, 3, 4],
        "access_ports": {},   # {port: vlan_tag}
        "mgmt_ip":      "10.10.10.11",
        # Port 4 untagged MGMT for Ubu-WS01
        "mgmt_vlan":    10,
    },
    "SW2-DIST-1": {
        # Port 1 = uplink to SW1-CORE
        # Ports 3,5 = downlinks to Access switches (trunks)
        # Port 4 = Win10 GUEST client (untagged — GUEST_NET VLAN 40)
        "trunk_ports":  [1, 2, 3, 5],
        "access_ports": {4: 40},    # port 4 = GUEST_NET — Win10 guest machine
        "mgmt_ip":      "10.10.10.12",
        "mgmt_vlan":    10,
    },
    "SW3-DIST-2": {
        # Port 1 = uplink to SW2-DIST-1 or SW3-DIST-2
        # Port 24 = access port for CORP endpoint
        "trunk_ports":  [1],
        "access_ports": {3: 20},    # port 3 = CORP devices (WIN10-WS2/PC2)
        "mgmt_ip":      "10.10.10.13",
        "mgmt_vlan":    10,
    },
    "SW4-ACCESS1-CORP": {
        # Port 1 = uplink to SW2-DIST-1 or SW3-DIST-2
        # Port 24 = access for DMZ endpoint
        "trunk_ports":  [1],
        "access_ports": {3: 30},    # port 3 = FILE-SVR1 (DMZ)
        "mgmt_ip":      "10.10.10.14",
        "mgmt_vlan":    10,
    },
    "SW5-ACCESS2-DMZ": {
        # Port 1 = uplink to SW3-DIST-2
        # Port 24 = access for GUEST endpoint
        "trunk_ports":  [1],
        "access_ports": {4: 40},    # port 4 = WS-Gst (GUEST_NET untagged)
        "mgmt_ip":      "10.10.10.15",
        "mgmt_vlan":    10,
    },
    "BR-SW1": {
        # Port 1 = uplink to BR-CA-Irv-FW1
        # Port 24 = Branch PC / Ubu-WS02
        "trunk_ports":  [1],
        "access_ports": {24: 1},    # default VLAN for branch
        "mgmt_ip":      "10.20.10.21",
        "mgmt_vlan":    1,
    },
}


# ─── COMMAND BUILDERS ─────────────────────────────────────────────────────────

def build_vlan_commands(sw_name, port_config):
    """Build all VLAN creation and port assignment commands for one switch."""
    cmds = []
    vlan_tag_to_name = {v["tag"]: v["name"] for v in VLANS}

    # Create VLANs
    for vlan in VLANS:
        cmds.append(f"create vlan {vlan['name']} tag {vlan['tag']}")

    # Configure MGMT IP on this switch
    mgmt_ip   = port_config.get("mgmt_ip")
    mgmt_vlan = port_config.get("mgmt_vlan", 10)
    mgmt_name = vlan_tag_to_name.get(mgmt_vlan, "MGMT_NET")

    if mgmt_ip:
        gw = mgmt_ip.rsplit(".", 1)[0] + ".1"  # infer gateway
        cmds += [
            f"configure vlan {mgmt_name} ipaddress {mgmt_ip} 255.255.255.0",
            f"configure iproute add default {gw}",
        ]

    # Trunk ports — add all VLANs tagged
    trunk_ports = port_config.get("trunk_ports", [])
    if trunk_ports:
        port_str = ",".join(str(p) for p in trunk_ports)
        for vlan in VLANS:
            cmds.append(
                f"configure vlan {vlan['name']} add ports {port_str} tagged"
            )

    # Access ports — add one VLAN untagged
    for port_num, vlan_tag in port_config.get("access_ports", {}).items():
        vlan_name = vlan_tag_to_name.get(vlan_tag, f"vlan_{vlan_tag}")
        cmds.append(f"configure vlan {vlan_name} add ports {port_num} untagged")

    return cmds


# ─── VERIFICATION ─────────────────────────────────────────────────────────────

def verify_vlans(sw, sw_name):
    """Check VLANs exist on switch."""
    out = sw.cmd("show vlan")
    results = {}
    for vlan in VLANS:
        if vlan["name"] in out or str(vlan["tag"]) in out:
            ok(f"  {sw_name}: VLAN {vlan['tag']} ({vlan['name']}) present")
            results[vlan["name"]] = True
        else:
            fail(f"  {sw_name}: VLAN {vlan['tag']} ({vlan['name']}) MISSING")
            results[vlan["name"]] = False
    return results


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def configure_all(switch_dict):
    all_results = {}

    for sw_name, sw_info in switch_dict.items():
        ip = sw_info["ip"]
        port_config = SWITCH_PORT_CONFIG.get(sw_name, {})

        if not port_config:
            warn(f"{sw_name}: No port config found in SWITCH_PORT_CONFIG — skipping")
            continue

        section(f"Configuring VLANs on {sw_name} ({ip})")
        try:
            with EXOSSwitch(ip) as sw:
                cmds = build_vlan_commands(sw_name, port_config)
                info(f"Sending {len(cmds)} commands...")
                for cmd in cmds:
                    out = sw.cmd(cmd)
                    if "already exists" in out.lower():
                        info(f"  (already exists) {cmd}")
                    elif "Error" in out or "Invalid" in out:
                        warn(f"  ⚠ {cmd!r} → {out.strip()[:60]}")
                    else:
                        info(f"  ✓ {cmd}")

                # Verify
                vlan_check = verify_vlans(sw, sw_name)
                sw.save()

                all_results[sw_name] = {
                    "success": all(vlan_check.values()),
                    "vlans": vlan_check,
                }

        except Exception as e:
            fail(f"{sw_name}: {e}")
            all_results[sw_name] = {"success": False, "error": str(e)}

    return all_results


def main():
    parser = argparse.ArgumentParser(description="Task 7: Configure VLANs on EXOS switches")
    parser.add_argument("--verify",      action="store_true", help="Verify VLANs only")
    parser.add_argument("--hq-only",     action="store_true")
    parser.add_argument("--branch-only", action="store_true")
    parser.add_argument("--host",        help="Single switch IP")
    args = parser.parse_args()

    banner_print("Task 7 — VLAN Segmentation & 802.1Q Trunking")

    if args.host:
        all_sw = {**HQ_SWITCHES, **BRANCH_SWITCHES}
        target = {k: v for k, v in all_sw.items() if v["ip"] == args.host}
        if not target:
            target = {args.host: {"ip": args.host, "role": "access"}}
    elif args.branch_only:
        target = BRANCH_SWITCHES
    elif args.hq_only:
        target = HQ_SWITCHES
    else:
        target = {**HQ_SWITCHES, **BRANCH_SWITCHES}

    if args.verify:
        for sw_name, sw_info in target.items():
            section(f"Verifying {sw_name} ({sw_info['ip']})")
            try:
                with EXOSSwitch(sw_info["ip"]) as sw:
                    verify_vlans(sw, sw_name)
            except Exception as e:
                fail(f"{sw_name}: {e}")
    else:
        results = configure_all(target)
        print_summary(results)
        report = {
            "timestamp": datetime.now().isoformat(),
            "task": "Task 7 — VLANs",
            "results": results,
        }
        save_report(report, "task7_vlan_report.json", "Task 7 report")


if __name__ == "__main__":
    main()
