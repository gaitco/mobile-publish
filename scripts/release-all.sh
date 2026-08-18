#!/usr/bin/env bash
#
# Batch AppGallery uploads: one line per app in apps.tsv, tab-separated,
# '#' comments ignored:
#
#   <name>	<package-name>	<path-to-apk>
#
# agc.py resolves the appId from the package name, so nothing else is needed.
# Credentials: ~/.config/agc/service-account.json (or $AGC_KEY_FILE).
#
# Uploads only — never submits for review. Submit per app deliberately with
# `agc.py submit` once you have looked at the draft.
#
set -uo pipefail   # deliberately no -e: one bad app must not abort the rest

cd "$(dirname "$0")"
MANIFEST="${1:-apps.tsv}"
[ -f "$MANIFEST" ] || { echo "no manifest: $MANIFEST" >&2; exit 1; }

ok=() failed=()

while IFS=$'\t' read -r name package apk; do
  case "${name:-}" in ''|\#*) continue ;; esac
  echo "───────── $name ─────────"

  if [ ! -f "${apk:-}" ]; then
    echo "  skipped: build not found at ${apk:-<empty>}" >&2
    failed+=("$name (no build)")
    continue
  fi

  # Continue on failure: these are independent app releases, so one stale build
  # or unlisted app should not block the others. The summary below is the report.
  if AGC_PACKAGE="$package" python3 ./agc.py upload "$apk"; then
    ok+=("$name")
  else
    failed+=("$name (upload failed)")
  fi
done < "$MANIFEST"

echo
echo "succeeded: ${#ok[@]}   failed: ${#failed[@]}"
[ ${#failed[@]} -eq 0 ] || { printf '  - %s\n' "${failed[@]}"; exit 1; }
