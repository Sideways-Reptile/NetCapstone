#!/usr/bin/env python3
"""
task3_banners/set_banners.py
Bigfork IT — Capstone Lab — Task 3
Deploys login banners to all HQ EXOS switches using paramiko.
Handles the interactive 'configure banner' prompt reliably.

Usage:
  python3 task3_banners/set_banners.py
"""

import time
import sys
import paramiko

SWITCHES = [
    ("SW1-CORE",         "10.10.10.11"),
    ("SW2-DIST-1",       "10.10.10.12"),
    ("SW3-DIST-2",       "10.10.10.13"),
    ("SW4-ACCESS1-CORP", "10.10.10.14"),
    ("SW5-ACCESS2-DMZ",  "10.10.10.15"),
]

USERNAME = "case"
PASSWORD = "sidewaays"

BANNER_LINES = [
    "***********************************************",
    "*                                             *",
    "*   AUTHORIZED ACCESS ONLY                    *",
    "*                                             *",
    "*   This system is property of Bigfork IT.    *",
    "*   All activity is monitored and logged.     *",
    "*   Unauthorized access is prohibited and     *",
    "*   will be prosecuted to the full extent     *",
    "*   of applicable law.                        *",
    "*                                             *",
    "*   Disconnect NOW if you are not an          *",
    "*   authorized user.                          *",
    "*                                             *",
    "***********************************************",
]

def send(chan, text, delay=0.3):
    chan.send(text + "\n")
    time.sleep(delay)
    out = ""
    while chan.recv_ready():
        out += chan.recv(4096).decode("utf-8", errors="ignore")
    return out

def deploy(name, ip):
    print(f"\n[{name}] Connecting to {ip}...")
    try:
        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            ip, username=USERNAME, password=PASSWORD,
            look_for_keys=False, allow_agent=False,
            disabled_algorithms={"kex": [], "keys": []},
            timeout=15
        )
        chan = client.invoke_shell()
        time.sleep(2)
        chan.recv(4096)  # clear welcome

        # Start banner config
        send(chan, "configure banner", delay=1)

        # Send each banner line
        for line in BANNER_LINES:
            send(chan, line, delay=0.1)

        # Terminate with dot
        chan.send(chr(26))
        time.sleep(2)

        # Save
        out = send(chan, "save configuration primary", delay=2)
        print(f"[{name}] Save output: {out.strip()[:80]}")

        # Verify
        out = send(chan, "show banner", delay=1)
        if "AUTHORIZED" in out:
            print(f"[{name}] ✅ BANNER VERIFIED")
        else:
            print(f"[{name}] ⚠️  Banner not confirmed in show banner — check manually")
            print(f"[{name}] Output: {out.strip()[:200]}")

        chan.close()
        client.close()
        return True

    except Exception as e:
        print(f"[{name}] ❌ FAILED: {e}")
        return False

if __name__ == "__main__":
    print("=" * 55)
    print("  Task 3 — Deploy Login Banners to HQ Switches")
    print("=" * 55)

    passed = 0
    failed = 0
    for name, ip in SWITCHES:
        if deploy(name, ip):
            passed += 1
        else:
            failed += 1

    print(f"\n{'=' * 55}")
    print(f"  Results: {passed} PASS | {failed} FAIL")
    print(f"{'=' * 55}")
    if failed:
        sys.exit(1)
