#!/usr/bin/env bash
# One-time: trust Steampipe's root CA so "steampipe query" can connect to the local service (port 9193)
# without "x509: certificate signed by unknown authority". Required on macOS when the worker runs Steampipe.
set -e
STEAMPIPE_HOME="${STEAMPIPE_INSTALL_DIR:-$HOME/.steampipe}"
ROOT_CRT=$(find "$STEAMPIPE_HOME/db" -name "root.crt" 2>/dev/null | head -1)
if [ -z "$ROOT_CRT" ] || [ ! -f "$ROOT_CRT" ]; then
  echo "Steampipe root cert not found. Run 'steampipe query' once (or ensure Steampipe is installed), then retry."
  echo "Searched under: $STEAMPIPE_HOME/db"
  exit 1
fi
echo "Found root cert: $ROOT_CRT"
echo "Adding to system keychain (requires sudo)..."
if sudo security add-trusted-cert -d trustRoot -k /Library/Keychains/System.keychain "$ROOT_CRT" 2>/dev/null; then
  echo "Done. Restart the worker and run an execution again."
  exit 0
fi
# Fallback: add to login keychain without trust (avoids SecTrustSettingsSetTrustSettings error)
echo "System keychain failed; adding cert to login keychain (you must trust it manually)."
if ! security add-certificates -k "$HOME/Library/Keychains/login.keychain-db" "$ROOT_CRT" 2>/dev/null && ! security add-certificates -k "$HOME/Library/Keychains/login.keychain" "$ROOT_CRT" 2>/dev/null; then
  echo "(Cert may already be in keychain.)"
fi
echo ""
echo ">>> One-time manual step: Open Keychain Access → left sidebar: 'login' → search or scroll to 'root'"
echo "    Double-click the root cert → Trust section → set 'Secure Sockets Layer (SSL)' to 'Always Trust'"
echo "    Close (enter password if asked). Then restart the worker."
echo ""
