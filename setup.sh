#!/bin/bash
# Mythos setup dispatcher - delegates to the right platform script.
# Run: ./setup.sh

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

OS="$(uname -s)"

if [[ "$OS" == "Darwin" ]]; then
 exec "$SCRIPT_DIR/setup-macos.sh" "$@"
elif [[ "$OS" == "Linux" ]]; then
 exec "$SCRIPT_DIR/setup_for_linux.sh" "$@"
else
 echo "ERROR: Unsupported OS '$OS'"
 echo " Windows users: run .\setup-windows.ps1 in PowerShell"
 exit 1
fi
