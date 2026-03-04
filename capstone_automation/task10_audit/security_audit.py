#!/usr/bin/env python3
"""
task10_audit/security_audit.py
Bigfork IT — Capstone Lab

Task 10: Full Lab Security Audit
Comprehensive validation of all 9 previous tasks.
Run from Ubu-WS01 (10.10.10.108) on MGMT_NET.

Tests:
  ✓ Task 1 — Network segmentation & reachability
  ✓ Task 2 — GUEST RFC1918 isolation (from MGMT side)
  ✓ Task 3 — SSH banner availability (port checks)
  ✓ Task 4 — Static IP inventory reachability
  ✓ Task 5 — STP state on all switches
  ✓ Task 6 — Syslog UDP 514 on Ubu-WS01
  ✓ Task 7 — VLAN presence on switches
  ✓ Task 8 — Branch site reachability
  ✓ Task 9 — IPSec VPN tunnel endpoints
  ✓ Bonus  — pfSense HTTPS and SSH availability

Usage:
  python3 security_audit.py
  python3 security_audit.py --output-dir /home/osboxes
  python3 security_audit.py --task 5     # single task check only
"""

import argparse
import json
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    ping_host, port_open, EXOSSwitch,
    HQ_SWITCHES, BRANCH_SWITCHES, LAB_VLANS,
    PFSENSE_HQ_IP, PFSENSE_BRANCH_IP, SYSLOG_IP
)

# ─── AUDIT REGISTRY ───────────────────────────────────────────────────────────

AUDIT_RESULTS = {
    "timestamp":  None,
    "hostname":   None,
    "tasks":      {},
    "summary":    {},
}

total_pass = 0
total_fail = 0
total_warn = 0


def record(task_key, label, passed, detail="", warn_only=False):
    global total_pass, total_fail, total_warn
    status = "PASS" if passed else ("WARN" if warn_only else "FAIL")
    entry = {"label": label, "status": status, "detail": detail}

    if task_key not in AUDIT_RESULTS["tasks"]:
        AUDIT_RESULTS["tasks"][task_key] = []
    AUDIT_RESULTS["tasks"][task_key].append(entry)

    if passed:
        ok(f"{label}")
        total_pass += 1
    elif warn_only:
        warn(f"{label}{' — ' + detail if detail else ''}")
        total_warn += 1
    else:
        fail(f"{label}{' — ' + detail if detail else ''}")
        total_fail += 1

    return passed


# ─── TASK CHECKS ──────────────────────────────────────────────────────────────

def check_task1():
    """Task 1 — Network Segmentation & Reachability"""
    section("Task 1 — Network Segmentation")
    t = "task1"

    hosts = {
        "HQ-FW1 MGMT gw (10.10.10.1)":    ("10.10.10.1",    True),
        "HQ-FW1 CORP gw (172.16.1.1)":     ("172.16.1.1",    True),
        "HQ-FW1 DMZ gw (192.168.100.1)":   ("192.168.100.1", True),
        "HQ-FW1 GUEST gw (192.168.200.1)": ("192.168.200.1", True),
        "Internet (8.8.8.8)":               ("8.8.8.8",       True),
        "pfSense HTTPS (443)":              (None,            True),  # port check below
    }

    for label, (host, expected) in hosts.items():
        if host is None:
            result = port_open(PFSENSE_HQ_IP, 443)
            record(t, label, result == expected, "check port 443")
        else:
            result = ping_host(host)
            record(t, label, result == expected)

    # Switch MGMT IPs
    for sw_name, sw_info in HQ_SWITCHES.items():
        result = ping_host(sw_info["ip"])
        record(t, f"Switch {sw_name} ({sw_info['ip']})", result)


def check_task2():
    """Task 2 — GUEST ACL (MGMT-side perspective)"""
    section("Task 2 — Guest ACL")
    t = "task2"

    # MGMT can reach GUEST gateway (pfSense GUEST interface)
    result = ping_host("192.168.200.1")
    record(t, "GUEST gateway 192.168.200.1 reachable from MGMT", result)

    # Internet is reachable (proxy for guest internet working)
    result = ping_host("8.8.8.8")
    record(t, "Internet 8.8.8.8 reachable (internet path functional)", result)

    info("Manual check required — from a GUEST VLAN device:")
    info("  ping 10.10.10.1  # must FAIL")
    info("  ping 8.8.8.8     # must PASS")


def check_task3():
    """Task 3 — Banners (SSH port availability)"""
    section("Task 3 — Login Banners")
    t = "task3"

    # We can verify SSH is open; banner display itself requires manual check
    all_targets = {
        "HQ-FW1 SSH": PFSENSE_HQ_IP,
        **{name: info_["ip"] for name, info_ in HQ_SWITCHES.items()},
        "BR-SW1": BRANCH_SWITCHES.get("BR-SW1", {}).get("ip", "10.20.10.21"),
    }
    for label, host in all_targets.items():
        result = port_open(host, 22)
        record(t, f"SSH port open — {label} ({host})", result,
               warn_only=not result)

    info("Manual: ssh case@10.10.10.11 — verify banner appears before login prompt")


def check_task4():
    """Task 4 — DHCP & Static Addressing"""
    section("Task 4 — DHCP & Static Addressing")
    t = "task4"

    static_ips = [
        ("HQ-FW1 MGMT",  "10.10.10.1"),
        ("HQ-FW1 CORP",  "172.16.1.1"),
        ("HQ-FW1 DMZ",   "192.168.100.1"),
        ("HQ-FW1 GUEST", "192.168.200.1"),
        ("Ubu-WS01",     SYSLOG_IP),
    ]
    for sw_name, sw_info in HQ_SWITCHES.items():
        static_ips.append((sw_name, sw_info["ip"]))

    for label, host in static_ips:
        result = ping_host(host)
        record(t, f"Static IP reachable — {label} ({host})", result)


def check_task5():
    """Task 5 — STP via SSH to each switch"""
    section("Task 5 — Spanning Tree Protocol")
    t = "task5"

    for sw_name, sw_info in HQ_SWITCHES.items():
        ip       = sw_info["ip"]
        expected = sw_info.get("stp_priority", 32768)

        if not ping_host(ip):
            record(t, f"STP check {sw_name} ({ip})", False, "host unreachable")
            continue

        try:
            with EXOSSwitch(ip) as sw:
                out = sw.cmd("show stpd s0")

                # STP enabled?
                stp_enabled = "Enabled" in out or "enabled" in out
                record(t, f"{sw_name}: STP domain s0 enabled", stp_enabled)

                # Priority correct?
                p = re.search(r'Bridge\s+Priority\s*:\s*(\d+)', out)
                actual_pri = int(p.group(1)) if p else None
                pri_ok = (actual_pri == expected)
                record(t, f"{sw_name}: STP priority {actual_pri} (expected {expected})", pri_ok)

                # Root bridge check
                if expected == 4096:
                    is_root = "Root Bridge" in out or "This bridge is the root" in out
                    record(t, f"{sw_name}: Is root bridge", is_root)

        except Exception as e:
            record(t, f"STP check {sw_name}", False, str(e))


def check_task6():
    """Task 6 — Syslog & NTP"""
    section("Task 6 — Syslog & NTP")
    t = "task6"

    # Check rsyslog UDP 514 on this host
    try:
        result = subprocess.run(
            ["ss", "-ulnp"], capture_output=True, text=True, timeout=5
        )
        syslog_ok = ":514" in result.stdout
        record(t, f"rsyslog UDP 514 listening on {SYSLOG_IP}", syslog_ok,
               "run: sudo systemctl start rsyslog" if not syslog_ok else "")
    except Exception as e:
        record(t, "rsyslog UDP 514 check", False, str(e))

    # Check NTP reachability
    result = port_open(PFSENSE_HQ_IP, 123)
    record(t, f"NTP port 123 on pfSense ({PFSENSE_HQ_IP})", result, warn_only=True)

    # Verify syslog config on a sample switch
    try:
        sample_sw = list(HQ_SWITCHES.values())[0]
        with EXOSSwitch(sample_sw["ip"]) as sw:
            syslog_out = sw.cmd("show log configuration")
            has_syslog = SYSLOG_IP in syslog_out
            record(t, f"Syslog target {SYSLOG_IP} configured on SW1-CORE", has_syslog, warn_only=True)
    except Exception as e:
        record(t, "Syslog config check on SW1", False, str(e))


def check_task7():
    """Task 7 — VLANs"""
    section("Task 7 — VLAN Segmentation")
    t = "task7"

    expected_vlans = ["MGMT_NET", "CORP_NET", "DMZ_NET", "GUEST_NET"]

    for sw_name, sw_info in HQ_SWITCHES.items():
        if not ping_host(sw_info["ip"]):
            record(t, f"VLAN check {sw_name}", False, "host unreachable")
            continue
        try:
            with EXOSSwitch(sw_info["ip"]) as sw:
                out = sw.cmd("show vlan")
                for vlan_name in expected_vlans:
                    present = vlan_name in out
                    record(t, f"{sw_name}: VLAN {vlan_name}", present)
        except Exception as e:
            record(t, f"VLAN check {sw_name}", False, str(e))


def check_task8():
    """Task 8 — Branch Site"""
    section("Task 8 — Branch Site")
    t = "task8"

    checks = [
        ("Branch FW LAN",   "10.20.10.1",   "ping"),
        ("Branch SW1 MGMT", "10.20.10.21",  "ping"),
        ("Branch FW WAN",   "100.64.0.2",   "ping"),
        ("Branch SSH (FW)", "10.20.10.1",   "ssh"),
        ("Branch SSH (SW)", "10.20.10.21",  "ssh"),
    ]

    for label, host, check_type in checks:
        if check_type == "ping":
            result = ping_host(host)
        else:
            result = port_open(host, 22)
        record(t, f"{label} ({host})", result, warn_only=not result)


def check_task9():
    """Task 9 — IPSec VPN"""
    section("Task 9 — IPSec VPN")
    t = "task9"

    checks = [
        ("HQ WAN endpoint (100.64.0.1)",   "100.64.0.1",  "ping"),
        ("Branch WAN endpoint (100.64.0.2)","100.64.0.2", "ping"),
        ("Branch LAN via VPN (10.20.10.1)", "10.20.10.1", "ping"),
        ("Branch SW1 via VPN (10.20.10.21)","10.20.10.21","ping"),
    ]

    for label, host, check_type in checks:
        result = ping_host(host)
        record(t, label, result, warn_only=not result)

    # Try to check IPSec status via pfSense shell
    try:
        from utils.exos_helper import PFSenseSSH
        with PFSenseSSH(PFSENSE_HQ_IP) as fw:
            out = fw.shell("ipsec statusall 2>&1 | grep -E 'ESTABLISHED|CONNECTING|IKE'")
            established = "ESTABLISHED" in out
            record(t, "IPSec tunnel ESTABLISHED (pfSense shell check)", established,
                   detail=out.strip()[:100] if not established else "")
    except Exception as e:
        warn(f"Could not check IPSec via shell: {e}")
        info("Verify manually: pfSense GUI → Status → IPSec")


# ─── SUMMARY ──────────────────────────────────────────────────────────────────

def print_final_summary():
    banner_print("SECURITY AUDIT — FINAL RESULTS")
    print(f"""
  ┌─────────────────────────────────────────────────┐
  │  Total Checks:   {total_pass + total_fail + total_warn:<5}                           │
  │  ✅ PASS:        {total_pass:<5}                           │
  │  ❌ FAIL:        {total_fail:<5}                           │
  │  ⚠️  WARN:        {total_warn:<5}                           │
  └─────────────────────────────────────────────────┘
""")

    if total_fail > 0:
        print("  Failed checks:")
        for task_key, entries in AUDIT_RESULTS["tasks"].items():
            for e in entries:
                if e["status"] == "FAIL":
                    print(f"    ❌  [{task_key}] {e['label']}")
                    if e.get("detail"):
                        print(f"         → {e['detail']}")
    print()


# ─── MAIN ─────────────────────────────────────────────────────────────────────

TASK_MAP = {
    1: check_task1,
    2: check_task2,
    3: check_task3,
    4: check_task4,
    5: check_task5,
    6: check_task6,
    7: check_task7,
    8: check_task8,
    9: check_task9,
}


def main():
    parser = argparse.ArgumentParser(description="Task 10: Full Lab Security Audit")
    parser.add_argument("--output-dir", default=".", help="Directory to write reports")
    parser.add_argument("--task", type=int, choices=range(1, 10),
                        help="Run only this task's checks (1-9)")
    args = parser.parse_args()

    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    AUDIT_RESULTS["timestamp"] = datetime.now().isoformat()
    try:
        import socket
        AUDIT_RESULTS["hostname"] = socket.gethostname()
    except Exception:
        AUDIT_RESULTS["hostname"] = "unknown"

    banner_print("Bigfork IT — Capstone Lab Security Audit")
    info(f"Running from: {AUDIT_RESULTS['hostname']}")
    info(f"Timestamp:    {AUDIT_RESULTS['timestamp']}")

    if args.task:
        TASK_MAP[args.task]()
    else:
        for task_num in sorted(TASK_MAP.keys()):
            TASK_MAP[task_num]()

    AUDIT_RESULTS["summary"] = {
        "total": total_pass + total_fail + total_warn,
        "passed": total_pass,
        "failed": total_fail,
        "warned": total_warn,
    }

    print_final_summary()

    # Write report
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = out_dir / f"security_audit_{timestamp}.json"
    text_path   = out_dir / f"security_audit_{timestamp}.txt"

    report_path.write_text(json.dumps(AUDIT_RESULTS, indent=2, default=str))
    ok(f"JSON report: {report_path}")

    # Text report
    lines = [
        "=" * 60,
        "  Bigfork IT — Capstone Lab Security Audit Report",
        f"  {AUDIT_RESULTS['timestamp']}",
        "=" * 60,
        "",
        f"  PASS: {total_pass}  |  FAIL: {total_fail}  |  WARN: {total_warn}",
        "",
    ]
    for task_key, entries in AUDIT_RESULTS["tasks"].items():
        lines.append(f"\n  [{task_key}]")
        for e in entries:
            icon = {"PASS": "✓", "FAIL": "✗", "WARN": "⚠"}.get(e["status"], "?")
            lines.append(f"    {icon}  {e['label']}")
            if e.get("detail"):
                lines.append(f"       → {e['detail']}")

    text_path.write_text("\n".join(lines))
    ok(f"Text report: {text_path}")


if __name__ == "__main__":
    main()
