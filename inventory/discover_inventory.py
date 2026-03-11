#!/usr/bin/env python3
"""
Bigfork IT — Capstone Lab
discover_inventory.py

Connects to all known EXOS switches via SSH, discovers:
  - Hostname
  - MGMT IP
  - VLANs (name, tag, IP)
  - Port assignments
  - STP role

Outputs:
  - ansible_inventory.yml  (ready to use with all playbooks)
  - inventory_report.json  (full discovery data)
  - inventory_report.txt   (human-readable summary)

Usage:
  python3 discover_inventory.py
  python3 discover_inventory.py --output-dir /path/to/output
  python3 discover_inventory.py --extra-host 10.10.10.16

Prerequisites on Ubu-WS01:
  pip install netmiko paramiko --break-system-packages
  ~/.ssh/config must have EXOS legacy algorithm entries (see README)
"""

import argparse
import json
import re
import sys
from datetime import datetime
from pathlib import Path

try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    print("ERROR: netmiko not installed. Run:")
    print("  pip install netmiko --break-system-packages")
    sys.exit(1)

# ─── KNOWN DEVICES ────────────────────────────────────────────────────────────
# Edit IPs here if your lab uses different addresses
HQ_SWITCHES = [
    {"host": "10.10.10.11", "expected_hostname": "SW1-CORE",     "role": "core"},
    {"host": "10.10.10.12", "expected_hostname": "SW2-DIST-1",     "role": "distribution"},
    {"host": "10.10.10.13", "expected_hostname": "SW3-DIST-2", "role": "access"},
    {"host": "10.10.10.14", "expected_hostname": "SW4-ACCESS1-CORP", "role": "access"},
    {"host": "10.10.10.15", "expected_hostname": "SW5-ACCESS2-DMZ", "role": "access"},
]

BRANCH_SWITCHES = [
    {"host": "10.20.10.21", "expected_hostname": "BR-SW1", "role": "branch_access"},
]

SWITCH_CREDS = {
    "username": "case",
    "password": "sidewaays",
    "device_type": "extreme_exos",
    "timeout": 15,
    "session_timeout": 30,
}

PFSENSE_HQ     = "10.10.10.1"
PFSENSE_BRANCH = "10.20.10.1"
SYSLOG_HOST    = "10.10.10.108"


# ─── HELPERS ──────────────────────────────────────────────────────────────────

def banner(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)

def ok(msg):   print(f"  PASS  {msg}")
def warn(msg): print(f"  WARN   {msg}")
def fail(msg): print(f"  FAIL  {msg}")
def info(msg): print(f"  INFO   {msg}")


def ssh_connect(host, creds):
    """Return a Netmiko connection or None on failure."""
    conn_params = {**creds, "host": host}
    try:
        conn = ConnectHandler(**conn_params)
        return conn
    except NetmikoTimeoutException:
        fail(f"Timeout connecting to {host}")
        return None
    except NetmikoAuthenticationException:
        fail(f"Auth failed on {host} — check credentials")
        return None
    except Exception as e:
        fail(f"Could not connect to {host}: {e}")
        return None


def parse_hostname(output):
    """Extract hostname from 'show switch' output."""
    for line in output.splitlines():
        if "SysName" in line or "System Name" in line:
            parts = line.split()
            if len(parts) >= 2:
                return parts[-1].strip()
    # Fallback: grab prompt text
    match = re.search(r'(\S+)\s*#', output)
    if match:
        return match.group(1)
    return "unknown"


def parse_vlans(output):
    """
    Parse 'show vlan' output from EXOS.
    Returns list of dicts: {name, tag, ip, mask, ports_tagged, ports_untagged}
    """
    vlans = []
    # EXOS vlan output format varies — parse by looking for VLAN entries
    current = None
    for line in output.splitlines():
        line = line.strip()
        # New VLAN entry line: "VLAN_NAME    Tag:N   ..."  or "Name: VLAN_NAME"
        tag_match = re.search(r'Tag:\s*(\d+)', line)
        name_match = re.search(r'^(\S+)\s+Tag:', line)
        if name_match and tag_match:
            if current:
                vlans.append(current)
            current = {
                "name": name_match.group(1),
                "tag": int(tag_match.group(1)),
                "ip": None,
                "mask": None,
                "ports_tagged": [],
                "ports_untagged": [],
            }
            continue
        if current is None:
            continue
        # IP address line
        ip_match = re.search(r'IP addr:\s*([\d.]+)\s*/\s*([\d.]+)', line)
        if not ip_match:
            ip_match = re.search(r'([\d.]+)\s+([\d.]+)\s+VLAN', line)
        if ip_match:
            current["ip"] = ip_match.group(1)
            current["mask"] = ip_match.group(2)
        # Tagged ports
        if "Tagged" in line:
            ports = re.findall(r'\d+(?::\d+)?', line.replace("Tagged", ""))
            current["ports_tagged"].extend(ports)
        # Untagged ports
        if "Untagged" in line:
            ports = re.findall(r'\d+(?::\d+)?', line.replace("Untagged", ""))
            current["ports_untagged"].extend(ports)

    if current:
        vlans.append(current)

    # Fallback: simpler line-by-line parse for compact output
    if not vlans:
        for line in output.splitlines():
            m = re.match(r'\s*(\S+)\s+(\d+)\s+([\d.]+)\s+', line)
            if m:
                vlans.append({
                    "name": m.group(1),
                    "tag": int(m.group(2)),
                    "ip": m.group(3),
                    "mask": None,
                    "ports_tagged": [],
                    "ports_untagged": [],
                })
    return vlans


def parse_stp(output):
    """Parse 'show stpd s0' for role and priority."""
    result = {"enabled": False, "priority": None, "role": "unknown", "root_mac": None}
    for line in output.splitlines():
        if "Enabled" in line or "enabled" in line:
            result["enabled"] = True
        p = re.search(r'Bridge Priority\s*:\s*(\d+)', line)
        if p:
            result["priority"] = int(p.group(1))
        r = re.search(r'Root Identifier.*?(\w{2}:\w{2}:\w{2}:\w{2}:\w{2}:\w{2})', line)
        if r:
            result["root_mac"] = r.group(1)
        if "Root Bridge" in line or "This bridge is the root" in line:
            result["role"] = "root"
    return result


# ─── MAIN DISCOVERY ───────────────────────────────────────────────────────────

def discover_switch(switch_info, extra=False):
    """SSH to one switch, collect all data. Returns dict or None."""
    host = switch_info["host"]
    expected = switch_info.get("expected_hostname", host)
    role = switch_info.get("role", "access")

    info(f"Connecting to {expected} ({host})...")

    conn = ssh_connect(host, SWITCH_CREDS)
    if not conn:
        return None

    try:
        sw_output    = conn.send_command("show switch")
        vlan_output  = conn.send_command("show vlan detail")
        if not vlan_output.strip():
            vlan_output = conn.send_command("show vlan")
        stp_output   = conn.send_command("show stpd s0")
        port_output  = conn.send_command("show ports information")
        conn.disconnect()
    except Exception as e:
        fail(f"Command failed on {host}: {e}")
        try:
            conn.disconnect()
        except Exception:
            pass
        return None

    hostname = parse_hostname(sw_output) or expected
    vlans    = parse_vlans(vlan_output)
    stp      = parse_stp(stp_output)

    ok(f"Discovered: {hostname} | VLANs: {len(vlans)} | STP priority: {stp.get('priority', 'N/A')}")

    return {
        "hostname":   hostname,
        "host":       host,
        "role":       role,
        "site":       "branch" if "20.10" in host else "hq",
        "vlans":      vlans,
        "stp":        stp,
        "raw": {
            "switch": sw_output,
            "vlan":   vlan_output,
            "stp":    stp_output,
            "ports":  port_output,
        }
    }


def build_ansible_inventory(switches):
    """
    Generate a full ansible_inventory.yml from discovered switch data.
    Groups: hq_switches, branch_switches, core, distribution, access, all_switches
    """
    hq = [s for s in switches if s["site"] == "hq"]
    br = [s for s in switches if s["site"] == "branch"]

    def sw_entry(s, indent=8):
        pad = " " * indent
        lines = [
            f"{pad}{s['hostname']}:",
            f"{pad}  ansible_host: {s['host']}",
            f"{pad}  ansible_user: {SWITCH_CREDS['username']}",
            f"{pad}  ansible_password: \"{SWITCH_CREDS['password']}\"",
            f"{pad}  ansible_connection: ssh",
            f"{pad}  ansible_shell_type: sh",
            f"{pad}  ansible_python_interpreter: none",
            f"{pad}  switch_role: {s['role']}",
        ]
        if s["vlans"]:
            vlan_tags = [str(v["tag"]) for v in s["vlans"] if v["tag"] != 1]
            if vlan_tags:
                lines.append(f"{pad}  vlan_ids: [{', '.join(vlan_tags)}]")
        if s["stp"].get("priority"):
            lines.append(f"{pad}  stp_priority: {s['stp']['priority']}")
        return "\n".join(lines)

    lines = [
        "---",
        "# Ansible Inventory — Bigfork IT Capstone Lab",
        f"# Auto-generated by discover_inventory.py on {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "# Do not edit manually — re-run discover_inventory.py to refresh",
        "",
        "all:",
        "  vars:",
        "    ansible_user: case",
        "    ansible_password: \"sidewaays\"",
        "    ansible_connection: ssh",
        "    ansible_shell_type: sh",
        "    ansible_python_interpreter: none",
        "    ansible_become: no",
        "    # pfSense targets (used by pfSense playbooks)",
        "    pfsense_hq_ip: \"10.10.10.1\"",
        "    pfsense_branch_ip: \"10.20.10.1\"",
        "    syslog_server: \"10.10.10.108\"",
        "",
        "  children:",
        "",
        "    # ── HQ Site ──────────────────────────────────────",
        "    hq_switches:",
        "      hosts:",
    ]
    for s in hq:
        lines.append(sw_entry(s))

    lines += [
        "",
        "    # ── Branch Site ───────────────────────────────────",
        "    branch_switches:",
        "      hosts:",
    ]
    for s in br:
        lines.append(sw_entry(s))

    # Role-based groups
    lines += ["", "    # ── Role Groups ───────────────────────────────────"]
    for role in ["core", "distribution", "access", "branch_access"]:
        members = [s for s in switches if s["role"] == role]
        if members:
            lines.append(f"    {role}:")
            lines.append("      hosts:")
            for s in members:
                lines.append(f"        {s['hostname']}:")

    # all_switches convenience group
    lines += [
        "",
        "    # ── All Switches ──────────────────────────────────",
        "    all_switches:",
        "      children:",
        "        hq_switches:",
        "        branch_switches:",
        "",
        "    # ── pfSense Firewalls (SSH targets) ───────────────",
        "    firewalls:",
        "      hosts:",
        "        HQ-FW1:",
        "          ansible_host: 10.10.10.1",
        "          ansible_user: admin",
        "          ansible_password: \"sidewaays\"",
        "          ansible_network_os: pfsense",
        "          ansible_connection: ssh",
        "          site: branch",
    ]

    return "\n".join(lines)


def build_text_report(switches):
    lines = [
        "=" * 60,
        "  Bigfork IT — Switch Inventory Discovery Report",
        f"  Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        "=" * 60,
        "",
    ]
    for s in switches:
        lines += [
            f"  Hostname : {s['hostname']}",
            f"  Host IP  : {s['host']}",
            f"  Site     : {s['site'].upper()}",
            f"  Role     : {s['role']}",
            f"  STP Pri  : {s['stp'].get('priority', 'N/A')}",
            f"  STP Role : {s['stp'].get('role', 'N/A')}",
            "  VLANs:",
        ]
        for v in s["vlans"]:
            ip_str = f" ({v['ip']}/{v['mask']})" if v["ip"] else ""
            lines.append(f"    Tag {v['tag']:>4}  {v['name']:<20}{ip_str}")
        lines.append("")
    return "\n".join(lines)


# ─── ENTRY POINT ──────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Discover EXOS switches and generate Ansible inventory")
    parser.add_argument("--output-dir", default=".", help="Directory to write output files")
    parser.add_argument("--extra-host", action="append", default=[], help="Additional switch IP to discover")
    parser.add_argument("--skip-branch", action="store_true", help="Skip branch switches")
    args = parser.parse_args()

    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)

    banner("Bigfork IT — Switch Inventory Discovery")
    print(f"  Output directory: {out.resolve()}")

    targets = list(HQ_SWITCHES)
    if not args.skip_branch:
        targets += BRANCH_SWITCHES
    for ip in args.extra_host:
        targets.append({"host": ip, "expected_hostname": ip, "role": "access"})

    discovered = []
    failed_hosts = []

    for sw in targets:
        result = discover_switch(sw)
        if result:
            discovered.append(result)
        else:
            failed_hosts.append(sw["host"])

    if not discovered:
        fail("No switches discovered. Check SSH connectivity and credentials.")
        sys.exit(1)

    banner(f"Discovery complete — {len(discovered)} switches found")

    # Strip raw output from JSON (keep it clean)
    clean_data = []
    for s in discovered:
        d = {k: v for k, v in s.items() if k != "raw"}
        clean_data.append(d)

    # Write outputs
    inventory_path = out / "ansible_inventory.yml"
    report_json    = out / "inventory_report.json"
    report_txt     = out / "inventory_report.txt"

    inventory_path.write_text(build_ansible_inventory(discovered))
    ok(f"Ansible inventory written: {inventory_path}")

    report_json.write_text(json.dumps(clean_data, indent=2))
    ok(f"JSON report written:       {report_json}")

    report_txt.write_text(build_text_report(discovered))
    ok(f"Text report written:       {report_txt}")

    if failed_hosts:
        warn(f"Failed to reach: {', '.join(failed_hosts)}")
        warn("Add SSH config entries for EXOS if not already done:")
        warn("  See docs/SSH_SETUP.md")

    print()
    print("  Next step: use ansible_inventory.yml with any playbook:")
    print("  ansible-playbook -i ansible_inventory.yml task5_stp/stp_configure.yml")
    print()


if __name__ == "__main__":
    main()
