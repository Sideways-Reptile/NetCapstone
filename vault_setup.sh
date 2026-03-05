#!/bin/bash
# =============================================================
# Bigfork IT — Ansible Vault Setup Script
# Run once from ~/capstone_automation on Ubu-WS01
#
# What this does:
#   1. Creates group_vars/all/ directory structure
#   2. Writes vars.yml (plain, safe to commit)
#   3. Creates encrypted vault.yml with switch password
#   4. Creates ~/.vault_pass so no password prompt on runs
#   5. Updates ansible.cfg to use vault_password_file
#   6. Adds .vault_pass to .gitignore
#   7. Strips hardcoded credentials from all playbooks
#
# Usage:
#   chmod +x vault_setup.sh
#   ./vault_setup.sh
# =============================================================

set -e

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VAULT_PASS_FILE="$HOME/.vault_pass"
GROUP_VARS="$REPO_DIR/group_vars/all"

echo ""
echo "================================================="
echo "  Bigfork IT — Ansible Vault Setup"
echo "================================================="
echo ""

# ── STEP 1: Get vault password ────────────────────────────────
echo "Step 1: Choose a vault password."
echo "        This encrypts your switch credentials."
echo "        Store it somewhere safe (password manager)."
echo ""
read -s -p "  Enter vault password: " VAULT_PASS
echo ""
read -s -p "  Confirm vault password: " VAULT_PASS2
echo ""

if [ "$VAULT_PASS" != "$VAULT_PASS2" ]; then
    echo "  ERROR: Passwords do not match. Exiting."
    exit 1
fi
echo "  ✅ Passwords match."
echo ""

# ── STEP 2: Write ~/.vault_pass ───────────────────────────────
echo "Step 2: Writing vault password to $VAULT_PASS_FILE"
echo "$VAULT_PASS" > "$VAULT_PASS_FILE"
chmod 600 "$VAULT_PASS_FILE"
echo "  ✅ $VAULT_PASS_FILE created (chmod 600)"
echo ""

# ── STEP 3: Create group_vars structure ───────────────────────
echo "Step 3: Creating group_vars/all/ directory"
mkdir -p "$GROUP_VARS"
echo "  ✅ $GROUP_VARS created"
echo ""

# ── STEP 4: Write vars.yml ────────────────────────────────────
echo "Step 4: Writing group_vars/all/vars.yml"
cat > "$GROUP_VARS/vars.yml" << 'EOF'
# group_vars/all/vars.yml
# Plain vars — references encrypted vault values
# Safe to commit to GitHub

ansible_user: case
ansible_password: "{{ vault_switch_password }}"
ansible_connection: ssh
ansible_shell_type: sh
ansible_python_interpreter: none
ansible_ssh_common_args: >-
  -o StrictHostKeyChecking=no
  -o KexAlgorithms=+diffie-hellman-group14-sha1
  -o HostKeyAlgorithms=+ssh-rsa
  -o PubkeyAcceptedKeyTypes=+ssh-rsa
EOF
echo "  ✅ vars.yml written"
echo ""

# ── STEP 5: Create encrypted vault.yml ───────────────────────
echo "Step 5: Creating encrypted vault.yml"
VAULT_CONTENT="vault_switch_password: sidewaays"

# Write plaintext to temp file, encrypt it, remove temp
TMPFILE=$(mktemp)
echo "$VAULT_CONTENT" > "$TMPFILE"
ansible-vault encrypt "$TMPFILE" --vault-password-file "$VAULT_PASS_FILE" --output "$GROUP_VARS/vault.yml"
rm -f "$TMPFILE"
echo "  ✅ group_vars/all/vault.yml encrypted with ansible-vault"
echo ""

# ── STEP 6: Update ansible.cfg ────────────────────────────────
echo "Step 6: Updating ansible.cfg"
if grep -q "vault_password_file" "$REPO_DIR/ansible.cfg" 2>/dev/null; then
    echo "  ℹ️  vault_password_file already set in ansible.cfg — skipping"
else
    # Add vault_password_file to [defaults] section
    sed -i '/^\[defaults\]/a vault_password_file = ~/.vault_pass' "$REPO_DIR/ansible.cfg"
    echo "  ✅ vault_password_file added to ansible.cfg"
fi
echo ""

# ── STEP 7: Update .gitignore ─────────────────────────────────
echo "Step 7: Updating .gitignore"
GITIGNORE="$REPO_DIR/.gitignore"
touch "$GITIGNORE"

if ! grep -q ".vault_pass" "$GITIGNORE"; then
    cat >> "$GITIGNORE" << 'EOF'

# Ansible Vault password file — NEVER commit this
.vault_pass
*.vault_pass

# Security audit reports
security_audit_*.json
security_audit_*.txt
EOF
    echo "  ✅ .vault_pass added to .gitignore"
else
    echo "  ℹ️  .vault_pass already in .gitignore — skipping"
fi
echo ""

# ── STEP 8: Strip hardcoded credentials from playbooks ────────
echo "Step 8: Removing hardcoded credentials from playbooks"
PLAYBOOKS=$(find "$REPO_DIR" -name "*.yml" -not -path "*/group_vars/*" -not -name "vault*.yml")

for playbook in $PLAYBOOKS; do
    if grep -q "ansible_password:" "$playbook" 2>/dev/null; then
        # Remove the hardcoded credential lines from vars: blocks
        sed -i '/^\s*ansible_user: case/d' "$playbook"
        sed -i '/^\s*ansible_password:/d' "$playbook"
        sed -i '/^\s*ansible_connection: ssh/d' "$playbook"
        sed -i '/^\s*ansible_shell_type: sh/d' "$playbook"
        sed -i '/^\s*ansible_python_interpreter: none/d' "$playbook"
        sed -i '/^\s*ansible_ssh_common_args/,/^\s*-o PubkeyAcceptedKeyTypes/d' "$playbook"
        echo "  ✅ Stripped credentials from: $(basename $playbook)"
    fi
done
echo ""

# ── STEP 9: Commit to GitHub ──────────────────────────────────
echo "Step 9: Committing changes to GitHub"
cd "$REPO_DIR"
git add group_vars/ ansible.cfg .gitignore
git add -u  # stage modified playbooks
git commit -m "security: move credentials to ansible-vault, remove hardcoded passwords"
git push
echo "  ✅ Pushed to GitHub"
echo ""

# ── DONE ──────────────────────────────────────────────────────
echo "================================================="
echo "  ✅ VAULT SETUP COMPLETE"
echo "================================================="
echo ""
echo "  What changed:"
echo "    ~/.vault_pass          — vault password (local only, never pushed)"
echo "    group_vars/all/vars.yml  — plain vars (safe to commit)"
echo "    group_vars/all/vault.yml — encrypted credentials (safe to commit)"
echo "    ansible.cfg            — vault_password_file added"
echo "    .gitignore             — .vault_pass excluded"
echo "    All playbooks          — hardcoded credentials removed"
echo ""
echo "  Running playbooks:"
echo "    ansible-playbook -i ansible_inventory.yml <playbook>.yml"
echo "    (no password prompt — vault_pass_file handles it automatically)"
echo ""
echo "  To rotate switch password later:"
echo "    1. ansible-vault edit group_vars/all/vault.yml"
echo "    2. Update vault_switch_password value"
echo "    3. git add group_vars/all/vault.yml && git push"
echo ""
