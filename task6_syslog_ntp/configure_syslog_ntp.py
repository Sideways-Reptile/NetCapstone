#!/usr/bin/env python3
"""
task6_syslog_ntp/configure_syslog_ntp.py
Bigfork IT — Capstone Lab

Task 6: Syslog & NTP — Centralized Logging & Time Sync
Configures:
  - Syslog forwarding to Ubu-WS01 (10.10.10.108:514) on all EXOS switches
  - SNTP client pointing to pfSense HQ (10.10.10.1) on all EXOS switches
  - Prints pfSense syslog/NTP config for GUI application
  - Validates rsyslog is running on Ubu-WS01

Usage:
  python3 configure_syslog_ntp.py          # full config
  python3 configure_syslog_ntp.py --syslog-only
  python3 configure_syslog_ntp.py --ntp-only
  python3 configure_syslog_ntp.py --verify
"""

import argparse
import socket
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    EXOSSwitch, HQ_SWITCHES, BRANCH_SWITCHES,
    save_report, print_summary, SYSLOG_IP, port_open, ping_host,
    PFSENSE_HQ_IP
)

SYSLOG_PORT = 514
NTP_SERVER  = PFSENSE_HQ_IP   # pfSense acts as NTP server for the lab
TIMEZONE    = "PST"
TZ_OFFSET   = -480             # PST = UTC-8 in minutes


# ─── SYSLOG COMMANDS ──────────────────────────────────────────────────────────

def build_syslog_commands(sw_name, sw_info):
    """EXOS syslog configuration commands."""
    return [
        # Remove old entry if present (ignore error)
        f"unconfig log",
        # Add syslog target
        f"configure syslog add {SYSLOG_IP}:{SYSLOG_PORT} vr VR-Default local7",
        # Enable log target
        f"enable log target syslog {SYSLOG_IP}:{SYSLOG_PORT} vr VR-Default",
        # Log severity: warnings and above to syslog
        f"configure log target syslog {SYSLOG_IP}:{SYSLOG_PORT} vr VR-Default severity warning",
        # Log filter — all events
        f"configure log filter DefaultFilter add events all",
        # Also enable local console logging
        f"enable log target console",
        f"configure log target console severity info",
    ]


# ─── NTP COMMANDS ─────────────────────────────────────────────────────────────

def build_ntp_commands(sw_name, sw_info):
    """EXOS SNTP client configuration commands."""
    return [
        # Set timezone
        f"configure timezone name {TIMEZONE} {TZ_OFFSET}",
        # Enable SNTP client
        f"enable sntp-client",
        # Set primary NTP server (OPNSense)
        f"configure sntp-client primary {NTP_SERVER}",
        # Set secondary (public)
        f"configure sntp-client secondary 0.pool.ntp.org",
        # Sync interval
        f"configure sntp-client update-interval 300",
    ]


# ─── PFSENSE CONFIG GUIDE ─────────────────────────────────────────────────────

def print_pfsense_syslog_guide():
    print(f"""
=============================================================
pfSense Syslog Configuration — Task 6
Apply in GUI: Status → System Logs → Settings
=============================================================

  Enable Remote Logging:    ✓ (checked)
  Remote syslog servers:    {SYSLOG_IP}
  Remote syslog port:       {SYSLOG_PORT}
  Protocol:                 UDP
  Log categories to check:
    ✓ Firewall events
    ✓ DHCP events
    ✓ Authentication events
    ✓ General system events
    ✓ VPN events

  Save → Apply Changes

=============================================================
pfSense NTP Configuration — Task 6
Apply in GUI: Services → NTP
=============================================================

  Interface:       MGMT_NET (em1.10)  also check LAN
  NTP Time Server: 0.pool.ntp.org
  NTP Time Server: 1.pool.ntp.org

  Enable NTP Server for local clients: ✓
    (allows switches to use pfSense as NTP source)

  Save

=============================================================
""")


# ─── LOCAL RSYSLOG VALIDATION ─────────────────────────────────────────────────

def validate_local_rsyslog():
    """Check if rsyslog UDP 514 is running on this host."""
    section("Validating rsyslog on Ubu-WS01")
    # Check if UDP 514 is listening
    try:
        result = subprocess.run(
            ["ss", "-ulnp"],
            capture_output=True, text=True, timeout=5
        )
        if ":514" in result.stdout:
            ok(f"rsyslog UDP {SYSLOG_PORT} is listening on this host")
            return True
        else:
            fail(f"rsyslog UDP {SYSLOG_PORT} NOT listening — run:")
            fail("  sudo apt install -y rsyslog")
            fail("  sudo systemctl enable rsyslog && sudo systemctl start rsyslog")
            fail("  # Edit /etc/rsyslog.conf — uncomment: module(load='imudp')")
            fail("  # and: input(type='imudp' port='514')")
            fail("  sudo systemctl restart rsyslog")
            return False
    except Exception as e:
        warn(f"Could not check rsyslog: {e}")
        return False


def print_rsyslog_setup():
    print("""
=============================================================
Ubu-WS01 rsyslog Setup (run once if not already done)
=============================================================

sudo apt update && sudo apt install -y rsyslog

# Edit /etc/rsyslog.conf:
# Find and uncomment these two lines:
#   module(load="imudp")
#   input(type="imudp" port="514")
# Or add them if not present.

sudo systemctl restart rsyslog
sudo systemctl enable rsyslog

# Verify:
sudo ss -ulnp | grep 514
# Should show: udp UNCONN 0 0 0.0.0.0:514

# Watch live syslog:
sudo tail -f /var/log/syslog

=============================================================
""")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def configure_switches(switch_dict, syslog=True, ntp=True):
    results = {}

    for sw_name, sw_info in switch_dict.items():
        ip = sw_info["ip"]
        section(f"Configuring {sw_name} ({ip})")
        try:
            with EXOSSwitch(ip) as sw:
                commands = []
                if syslog:
                    commands += build_syslog_commands(sw_name, sw_info)
                if ntp:
                    commands += build_ntp_commands(sw_name, sw_info)

                for cmd in commands:
                    out = sw.cmd(cmd)
                    if "Error" in out or "Invalid" in out:
                        warn(f" WARN {cmd!r} → {out.strip()[:60]}")
                    else:
                        info(f" PASS {cmd}")

                sw.save()
                results[sw_name] = {"success": True}
                ok(f"{sw_name}: syslog/NTP configured")

        except Exception as e:
            fail(f"{sw_name}: {e}")
            results[sw_name] = {"success": False, "error": str(e)}

    return results


def verify_ntp_sync(switch_dict):
    """Check NTP sync status on each switch."""
    section("NTP Verification")
    for sw_name, sw_info in switch_dict.items():
        try:
            with EXOSSwitch(sw_info["ip"]) as sw:
                out = sw.cmd("show sntp-client")
                if "synchronized" in out.lower() or "stratum" in out.lower():
                    ok(f"{sw_name}: NTP synchronized")
                else:
                    warn(f"{sw_name}: NTP may not be synced yet — check after ~60s")
                    info(f"  Output: {out.strip()[:100]}")
        except Exception as e:
            fail(f"{sw_name}: {e}")


def main():
    parser = argparse.ArgumentParser(description="Task 6: Configure Syslog & NTP on EXOS switches")
    parser.add_argument("--syslog-only", action="store_true")
    parser.add_argument("--ntp-only",    action="store_true")
    parser.add_argument("--verify",      action="store_true")
    parser.add_argument("--hq-only",     action="store_true")
    parser.add_argument("--branch-only", action="store_true")
    args = parser.parse_args()

    banner_print("Task 6 — Syslog & NTP Configuration")

    print_rsyslog_setup()
    validate_local_rsyslog()
    print_pfsense_syslog_guide()

    target = {**HQ_SWITCHES, **BRANCH_SWITCHES}
    if args.hq_only:
        target = HQ_SWITCHES
    elif args.branch_only:
        target = BRANCH_SWITCHES

    do_syslog = not args.ntp_only
    do_ntp    = not args.syslog_only

    if args.verify:
        verify_ntp_sync(target)
    else:
        results = configure_switches(target, syslog=do_syslog, ntp=do_ntp)
        print_summary(results)

        if not args.syslog_only:
            import time
            info("Waiting 10s for NTP to sync...")
            time.sleep(10)
            verify_ntp_sync(target)

        report = {
            "timestamp": datetime.now().isoformat(),
            "task": "Task 6 — Syslog & NTP",
            "results": results,
        }
        save_report(report, "task6_syslog_ntp_report.json", "Task 6 report")


if __name__ == "__main__":
    main()
