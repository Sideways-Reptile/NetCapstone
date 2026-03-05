#!/usr/bin/env python3
"""
utils/exos_helper.py
Shared helpers for all Bigfork IT capstone automation scripts.
Import this in any script: from utils.exos_helper import EXOSSwitch, PFSense
"""

import json
import re
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

try:
    from netmiko import ConnectHandler
    from netmiko.exceptions import NetmikoTimeoutException, NetmikoAuthenticationException
except ImportError:
    print("ERROR: netmiko not installed. Run: pip install netmiko --break-system-packages")
    sys.exit(1)

# ─── LAB CONSTANTS ────────────────────────────────────────────────────────────

LAB_VLANS = {
    10: {"name": "MGMT_NET",  "subnet": "10.10.10.0/24",    "gateway": "10.10.10.1"},
    20: {"name": "CORP_NET",  "subnet": "172.16.1.0/24",    "gateway": "172.16.1.1"},
    30: {"name": "DMZ_NET",   "subnet": "192.168.100.0/24", "gateway": "192.168.100.1"},
    40: {"name": "GUEST_NET", "subnet": "192.168.200.0/24", "gateway": "192.168.200.1"},
}

HQ_SWITCHES = {
    "SW1-CORE":     {"ip": "10.10.10.11", "role": "core",         "stp_priority": 4096},
    "SW2-DIST-1":     {"ip": "10.10.10.12", "role": "distribution", "stp_priority": 8192},
    "SW3-DIST-2": {"ip": "10.10.10.13", "role": "access",       "stp_priority": 8192},
    "SW4-ACCESS1-CORP": {"ip": "10.10.10.14", "role": "access",       "stp_priority": 16384},
    "SW5-ACCESS2-DMZ": {"ip": "10.10.10.15", "role": "access",       "stp_priority": 16384},
}

BRANCH_SWITCHES = {
    "BR-SW1": {"ip": "10.20.10.21", "role": "branch_access", "stp_priority": 32768},
}

SWITCH_CREDS = {
    "username": "case",
    "password": "sidewaays",
    "device_type": "extreme_exos",
    "timeout": 15,
    "session_timeout": 30,
    "fast_cli": False,
}

PFSENSE_HQ_IP     = "10.10.10.1"
PFSENSE_BRANCH_IP = "10.20.10.1"
SYSLOG_IP         = "10.10.10.108"

BANNER_TEXT = """\
***********************************************
*                                             *
*   AUTHORIZED ACCESS ONLY                   *
*                                             *
*   This system is property of Bigfork IT.  *
*   All activity is monitored and logged.    *
*   Unauthorized access is prohibited and   *
*   will be prosecuted to the full extent   *
*   of applicable law.                       *
*                                             *
*   Disconnect now if you are not an         *
*   authorized user.                          *
*                                             *
***********************************************
"""

NTP_SERVERS = ["0.pool.ntp.org", "1.pool.ntp.org"]
SYSLOG_PORT = 514


# ─── PRINT HELPERS ────────────────────────────────────────────────────────────

def ok(msg):      print(f"  ✅  {msg}")
def warn(msg):    print(f"  ⚠️   {msg}")
def fail(msg):    print(f"  ❌  {msg}")
def info(msg):    print(f"  ℹ️   {msg}")
def section(msg): print(f"\n{'─'*60}\n  {msg}\n{'─'*60}")
def banner_print(msg):
    print(f"\n{'='*60}")
    print(f"  {msg}")
    print('='*60)


def ping_host(host, count=2, timeout=2):
    """Return True if host responds to ping."""
    try:
        result = subprocess.run(
            ["ping", "-c", str(count), "-W", str(timeout), host],
            capture_output=True, text=True, timeout=10
        )
        return result.returncode == 0
    except Exception:
        return False


def port_open(host, port, timeout=3):
    """Return True if TCP port is open."""
    try:
        s = socket.create_connection((host, port), timeout=timeout)
        s.close()
        return True
    except Exception:
        return False


def save_report(data, path, label="Report"):
    """Save dict/list as JSON, print confirmation."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(data, indent=2, default=str))
    ok(f"{label} saved: {p}")


# ─── EXOS SWITCH CLASS ────────────────────────────────────────────────────────

class EXOSSwitch:
    """
    Manages an SSH connection to one EXOS switch.
    Usage:
        with EXOSSwitch("10.10.10.11") as sw:
            output = sw.cmd("show vlan")
    """

    def __init__(self, host, username=None, password=None):
        self.host     = host
        self.username = username or SWITCH_CREDS["username"]
        self.password = password or SWITCH_CREDS["password"]
        self.conn     = None
        self.hostname = host

    def connect(self):
        try:
            self.conn = ConnectHandler(
                device_type=SWITCH_CREDS["device_type"],
                host=self.host,
                username=self.username,
                password=self.password,
                timeout=SWITCH_CREDS["timeout"],
                session_timeout=SWITCH_CREDS["session_timeout"],
                fast_cli=SWITCH_CREDS["fast_cli"],
            )
            # Grab hostname from prompt
            prompt = self.conn.find_prompt()
            self.hostname = prompt.strip().rstrip("#").rstrip(">").strip()
            ok(f"Connected: {self.hostname} ({self.host})")
            return True
        except NetmikoTimeoutException:
            fail(f"Timeout: {self.host}")
            return False
        except NetmikoAuthenticationException:
            fail(f"Auth failed: {self.host} — check username/password")
            return False
        except Exception as e:
            fail(f"Connect failed {self.host}: {e}")
            return False

    def disconnect(self):
        if self.conn:
            try:
                self.conn.disconnect()
            except Exception:
                pass
            self.conn = None

    def cmd(self, command, expect_string=None):
        """Send a single command, return output."""
        if not self.conn:
            raise RuntimeError(f"Not connected to {self.host}")
        try:
            if expect_string:
                return self.conn.send_command(command, expect_string=expect_string, read_timeout=30)
            return self.conn.send_command(command, read_timeout=30)
        except Exception as e:
            fail(f"Command failed on {self.hostname}: {command!r} — {e}")
            return ""

    def cmds(self, commands):
        """Send a list of commands, return list of outputs."""
        return [self.cmd(c) for c in commands]

    def send_config(self, commands):
        """
        Send a list of config commands (EXOS doesn't use config mode,
        so this just sends each command in order).
        """
        results = []
        for cmd in commands:
            out = self.cmd(cmd)
            results.append((cmd, out))
        return results

    def save(self):
        """Save running config to startup (EXOS: save configuration)."""
        out = self.cmd("save configuration primary")
        ok(f"{self.hostname}: configuration saved")
        return out

    def __enter__(self):
        if not self.connect():
            raise ConnectionError(f"Could not connect to {self.host}")
        return self

    def __exit__(self, *args):
        self.disconnect()


# ─── BATCH OPERATIONS ─────────────────────────────────────────────────────────

def run_on_all_switches(commands_fn, switch_dict=None, save=True):
    """
    Run commands on all switches.
    commands_fn: callable(switch_name, switch_info) -> list of command strings
    Returns dict: hostname -> {success, results, error}
    """
    if switch_dict is None:
        switch_dict = {**HQ_SWITCHES, **BRANCH_SWITCHES}

    results = {}
    for name, info_dict in switch_dict.items():
        ip = info_dict["ip"]
        section(f"Configuring {name} ({ip})")
        try:
            with EXOSSwitch(ip) as sw:
                commands = commands_fn(name, info_dict)
                if not commands:
                    info(f"No commands for {name} — skipping")
                    results[name] = {"success": True, "results": [], "skipped": True}
                    continue
                cmd_results = sw.send_config(commands)
                if save:
                    sw.save()
                results[name] = {
                    "success": True,
                    "results": cmd_results,
                    "skipped": False,
                }
        except Exception as e:
            fail(f"{name}: {e}")
            results[name] = {"success": False, "error": str(e), "skipped": False}

    return results


def print_summary(results):
    """Print a final pass/fail summary table."""
    banner_print("Summary")
    passed = [h for h, r in results.items() if r.get("success")]
    failed = [h for h, r in results.items() if not r.get("success")]
    for h in passed:
        ok(h)
    for h in failed:
        fail(h)
    print()
    print(f"  Total: {len(results)} | Passed: {len(passed)} | Failed: {len(failed)}")


# ─── PFSENSE HELPER ───────────────────────────────────────────────────────────

class PFSenseSSH:
    """
    SSH to pfSense shell for commands that can't be done via the API.
    Uses Netmiko with generic_termserver device type.
    """

    def __init__(self, host=PFSENSE_HQ_IP, username="admin", password="pfsense"):
        self.host     = host
        self.username = username
        self.password = password
        self.conn     = None

    def connect(self):
        try:
            self.conn = ConnectHandler(
                device_type="generic_termserver",
                host=self.host,
                username=self.username,
                password=self.password,
                timeout=15,
            )
            ok(f"pfSense SSH connected: {self.host}")
            return True
        except Exception as e:
            fail(f"pfSense SSH failed {self.host}: {e}")
            return False

    def shell(self, command):
        if not self.conn:
            raise RuntimeError("Not connected")
        return self.conn.send_command(command, expect_string=r'\$|#', read_timeout=20)

    def disconnect(self):
        if self.conn:
            try:
                self.conn.disconnect()
            except Exception:
                pass

    def __enter__(self):
        if not self.connect():
            raise ConnectionError(f"Could not SSH to pfSense {self.host}")
        return self

    def __exit__(self, *args):
        self.disconnect()
