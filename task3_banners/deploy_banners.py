#!/usr/bin/env python3
"""
task3_banners/deploy_banners.py
Bigfork IT — Capstone Lab

Task 3: Login Banners — Security & Compliance
Deploys legal login banners to all EXOS switches via SSH.
Generates pfSense and Windows banner configs for manual steps.

Run from ANY directory — path handling is automatic.

Usage:
  python3 task3_banners/deploy_banners.py                   # deploy to all switches
  python3 task3_banners/deploy_banners.py --hq-only
  python3 task3_banners/deploy_banners.py --branch-only
  python3 task3_banners/deploy_banners.py --generate-only   # print guides, no SSH
  python3 task3_banners/deploy_banners.py --verify-only     # check banners, no changes
  python3 task3_banners/deploy_banners.py --host 10.10.10.11
"""

import argparse
import sys
import time
from datetime import datetime
from pathlib import Path

# Works whether you run from root OR from task3_banners/
_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from utils.exos_helper import (
    ok, fail, warn, info, section, banner_print,
    EXOSSwitch, HQ_SWITCHES, BRANCH_SWITCHES,
    save_report, print_summary
)

BANNER = """\
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
*   Disconnect NOW if you are not an         *
*   authorized user.                          *
*                                             *
***********************************************"""


# ─── EXOS ─────────────────────────────────────────────────────────────────────

def deploy_banner_to_switch(name, ip):
    section(f"Deploying banner to {name} ({ip})")
    try:
        with EXOSSwitch(ip) as sw:
            sw.conn.send_command_timing("configure banner", delay_factor=1)
            time.sleep(0.5)
            for line in BANNER.splitlines():
                sw.conn.send_command_timing(line if line.strip() else " ", delay_factor=0.5)
                time.sleep(0.05)
            sw.conn.send_command_timing(".", delay_factor=1)
            time.sleep(0.5)
            sw.save()
            ok(f"{name}: deployed and saved")
            return True
    except Exception as e:
        fail(f"{name}: {e}")
        return False


def verify_banner(name, ip):
    try:
        with EXOSSwitch(ip) as sw:
            out = sw.cmd("show banner")
            if "AUTHORIZED" in out or "Bigfork" in out:
                ok(f"{name}: banner verified")
                return True
            else:
                warn(f"{name}: banner not found in show banner output")
                return False
    except Exception as e:
        fail(f"{name}: verify failed — {e}")
        return False


# ─── PFSENSE GUIDE ────────────────────────────────────────────────────────────

def print_pfsense_guide():
    print("""
=============================================================
  pfSense SSH Banner — MANUAL (GNS3 console option 8)
=============================================================
1. Open HQ-FW1 console in GNS3
2. Select option 8 (Shell)
3. Paste this entire block:

cat > /etc/issue.net << 'BANNEREOF'
***********************************************
*   AUTHORIZED ACCESS ONLY                   *
*   This system is property of Bigfork IT.  *
*   All activity is monitored and logged.    *
*   Unauthorized access is prohibited.       *
*   Disconnect NOW if not authorized.         *
***********************************************
BANNEREOF

grep -q 'Banner /etc/issue.net' /etc/ssh/sshd_config || \\
    echo 'Banner /etc/issue.net' >> /etc/ssh/sshd_config
/etc/rc.d/sshd onerestart
echo "Done."

4. Press Ctrl+D to exit shell
5. Test: ssh admin@10.10.10.1 — banner should show before password

TIP: Also set in GUI to survive reboots:
  System > Advanced > Admin Access > SSH Banner field
=============================================================
""")


# ─── WINDOWS GUIDE + PS1 ──────────────────────────────────────────────────────

def generate_windows_banner():
    ps1 = r'''# deploy_windows_banner.ps1
# Bigfork IT Capstone Lab — Task 3 — Windows Login Banner
# RIGHT-CLICK this file and select "Run with PowerShell" as Administrator

$title = "AUTHORIZED ACCESS ONLY"
$body  = "This system is property of Bigfork IT. All activity is monitored and logged. Unauthorized access is prohibited and will be prosecuted to the full extent of applicable law. Disconnect now if you are not an authorized user."

$reg = "HKLM:\SOFTWARE\Microsoft\Windows\CurrentVersion\Policies\System"
Set-ItemProperty -Path $reg -Name "legalnoticecaption" -Value $title -Type String
Set-ItemProperty -Path $reg -Name "legalnoticetext"    -Value $body  -Type String

Write-Host "Banner set successfully." -ForegroundColor Green
Write-Host "Lock screen (Win+L) then click your user to verify popup appears."
'''
    ps1_path = _ROOT / "task3_banners" / "deploy_windows_banner.ps1"
    ps1_path.write_text(ps1)
    ok(f"Windows script written: {ps1_path.name}")

    print("""
=============================================================
  Windows 10 Login Banner — HOW TO APPLY
=============================================================

OPTION A — PowerShell script (easiest):
  1. Copy deploy_windows_banner.ps1 to the Win10 VM
     (drag into VM, or paste contents into Notepad and save as .ps1)
  2. Right-click the file → Run with PowerShell
     If execution policy blocks it, run first in PowerShell:
       Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
  3. Lock screen (Win+L) — click your username
     Banner popup appears before password prompt — click OK

OPTION B — Manual registry (if PowerShell blocked):
  1. Win+R → regedit → Run as Administrator
  2. Navigate to:
     HKEY_LOCAL_MACHINE\\SOFTWARE\\Microsoft\\Windows\\
     CurrentVersion\\Policies\\System
  3. Double-click "legalnoticecaption" → set to: AUTHORIZED ACCESS ONLY
  4. Double-click "legalnoticetext"    → paste full banner body text
  5. Close regedit — no reboot needed

OPTION C — Group Policy:
  gpedit.msc → Computer Configuration → Windows Settings →
  Security Settings → Local Policies → Security Options →
    "Interactive logon: Message title for users"
    "Interactive logon: Message text for users"

VERIFY: Win+L → click user → banner popup should require clicking OK
=============================================================
""")


# ─── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Task 3: Deploy login banners")
    parser.add_argument("--hq-only",       action="store_true")
    parser.add_argument("--branch-only",   action="store_true")
    parser.add_argument("--generate-only", action="store_true", help="Print guides only — no SSH")
    parser.add_argument("--verify-only",   action="store_true", help="Verify only — no changes")
    parser.add_argument("--host",          metavar="IP",        help="Single switch IP")
    args = parser.parse_args()

    banner_print("Task 3 — Login Banner Deployment")

    # Always write text files and print guides
    (Path(_ROOT) / "task3_banners" / "standard_banner.txt").write_text(BANNER)
    print_pfsense_guide()
    generate_windows_banner()

    if args.generate_only:
        info("Generate-only mode — no SSH connections made.")
        return

    # Build target list
    if args.host:
        all_sw = {**HQ_SWITCHES, **BRANCH_SWITCHES}
        targets = {k: v for k, v in all_sw.items() if v["ip"] == args.host}
        if not targets:
            targets = {args.host: {"ip": args.host}}
    elif args.branch_only:
        targets = BRANCH_SWITCHES
    elif args.hq_only:
        targets = HQ_SWITCHES
    else:
        targets = {**HQ_SWITCHES, **BRANCH_SWITCHES}

    results = {}
    for name, sw_info in targets.items():
        ip = sw_info["ip"]
        if args.verify_only:
            success = verify_banner(name, ip)
        else:
            success = deploy_banner_to_switch(name, ip)
            if success:
                verify_banner(name, ip)
        results[name] = {"success": success}

    print_summary(results)
    save_report(
        {"timestamp": datetime.now().isoformat(), "results": results},
        _ROOT / "task3_banners" / "task3_banner_report.json",
        "Task 3 report"
    )


if __name__ == "__main__":
    main()
