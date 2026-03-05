#!/bin/bash
# Bigfork IT — Capstone Lab
# install_collections.sh
# Run once on Ubu-WS01 to install required Ansible collections
# Usage: bash utils/install_collections.sh

echo "Installing Ansible collections for Capstone Lab..."
echo ""

# Extreme Networks EXOS collection
ansible-galaxy collection install extremenetworks.exos
echo ""

# Ansible netcommon (needed by many network modules)
ansible-galaxy collection install ansible.netcommon
echo ""

# Verify
echo "Installed collections:"
ansible-galaxy collection list | grep -E "extreme|netcommon|network"
echo ""
echo "Done. You can now run playbooks with full EXOS module support."
echo "If install failed (no internet), playbooks will fall back to raw SSH automatically."
