#!/usr/bin/env bash
#
# Zero-configuration publisher. Run it from anywhere inside a Flutter/Android repo:
#
#   publish.sh                 # prepare fresh artifacts for inspection (no upload)
#   publish.sh --upload-prepared # upload the exact artifacts inspected after preparation
#   publish.sh --store play    # one store only  (play | agc | asc)
#   publish.sh --check         # local readiness only; no build or upload
#   publish.sh --build         # accepted for compatibility; builds are always clean
#   publish.sh --submit        # also send for review / promote past the holding track
#
# Everything else is discovered: the app module, the package name, the version, the
# artifact paths, and the credentials. Nothing to configure per project.
#
set -uo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
STORE=all SUBMIT=0 TRACK=internal CHECK=0 MODE=prepare
while [ $# -gt 0 ]; do
  case "$1" in
    --store)  [ $# -ge 2 ] && [ -n "$2" ] || die '--store needs a value'; STORE="$2"; shift 2 ;;
    --track)  [ $# -ge 2 ] && [ -n "$2" ] || die '--track needs a value'; TRACK="$2"; shift 2 ;;
    --build)  shift ;;
    --check)  CHECK=1; shift ;;
    --prepare) MODE=prepare; shift ;;
    --upload-prepared) MODE=upload; shift ;;
    --submit) SUBMIT=1; shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

case "$STORE" in all|play|agc|asc) ;; *) die "unknown store: $STORE" ;; esac
case "$TRACK" in internal|alpha|beta|production) ;; *) die "unsupported track: $TRACK" ;; esac
[ "$SUBMIT" = 0 ] || [ "$STORE" = agc ] || die '--submit is supported only for --store agc; use the store-specific review workflow for Apple/Play'
[ "$TRACK" != production ] || die 'production promotion requires the project-specific release workflow'
log() { printf '\033[1m==> %s\033[0m\n' "$*" >&2; }

# ---------------------------------------------------------------- discover the app

# The Flutter module is the directory holding pubspec.yaml. Repos here put it at the
# root, or under flutter/ or mobile/, so search upward then one level down.
APP=""
d="$PWD"
while [ "$d" != "/" ]; do
  if [ -f "$d/pubspec.yaml" ]; then APP="$d"; break; fi
  for sub in flutter mobile app; do
    [ -f "$d/$sub/pubspec.yaml" ] && { APP="$d/$sub"; break 2; }
  done
  d=$(dirname "$d")
done
[ -n "$APP" ] || die "no pubspec.yaml found from $PWD upward — is this a Flutter repo?"

GRADLE=''
for candidate in "$APP/android/app/build.gradle.kts" "$APP/android/app/build.gradle"; do
  if [ -f "$candidate" ]; then GRADLE="$candidate"; break; fi
done
[ -n "$GRADLE" ] || die "no android/app/build.gradle(.kts) under $APP"

# applicationId = "com.x.y"   (kts)   or   applicationId "com.x.y"   (groovy)
PACKAGE=$(grep -oE 'applicationId[[:space:]]*=?[[:space:]]*"[^"]+"' "$GRADLE" | head -1 | grep -oE '"[^"]+"' | tr -d '"')
[ -n "$PACKAGE" ] || die "could not read applicationId from $GRADLE"

VERSION=$(grep -m1 '^version:' "$APP/pubspec.yaml" | sed 's/version:[[:space:]]*//')
NAME=$(basename "$(dirname "$APP")")

AAB="$APP/build/app/outputs/bundle/release/app-release.aab"
APK="$APP/build/app/outputs/flutter-apk/app-release.apk"
IPA_DIR="$APP/build/ios/ipa"

# iOS bundle id is independent of the Android applicationId — read it, don't assume.
PBX="$APP/ios/Runner.xcodeproj/project.pbxproj"
BUNDLE=""
[ -f "$PBX" ] && BUNDLE=$(grep -oE 'PRODUCT_BUNDLE_IDENTIFIER = [^;]+;' "$PBX" \
  | sed 's/PRODUCT_BUNDLE_IDENTIFIER = //;s/;//' | grep -v RunnerTests | head -1 | tr -d '"')

log "$NAME — $PACKAGE — version $VERSION"
log "module: $APP"

# ---------------------------------------------------------------- decide the stores

want() { [ "$STORE" = all ] || [ "$STORE" = "$1" ]; }

AGC_KEY="${AGC_KEY_FILE:-}"
for c in "$APP/android/agc-service-account.json" "$HOME/.config/agc/service-account.json"; do
  [ -n "$AGC_KEY" ] && break
  [ -f "$c" ] && AGC_KEY="$c"
done
PLAY_KEY="${PLAY_STORE_JSON_KEY:-}"
for c in "$APP/android/play-store-key.json" "$HOME/.config/play/service-account.json"; do
  [ -n "$PLAY_KEY" ] && break
  [ -f "$c" ] && PLAY_KEY="$c"
done

# App Store Connect: key id + issuer id from env or the shared config; the .p8 itself
# must sit in ~/.appstoreconnect/private_keys/ where Apple's tools look for it.
# shellcheck source=/dev/null
[ -f "$HOME/.config/asc/config" ] && { set -a; . "$HOME/.config/asc/config"; set +a; }
ASC_OK=0
ASC_P8="$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID:-}.p8"
[ -n "${ASC_KEY_ID:-}" ] && [ -n "${ASC_ISSUER_ID:-}" ] \
  && [ -f "$ASC_P8" ] && ASC_OK=1

DO_PLAY=0; DO_AGC=0; DO_ASC=0
want play && [ -n "$PLAY_KEY" ] && DO_PLAY=1
want agc  && [ -n "$AGC_KEY"  ] && DO_AGC=1
want asc  && [ "$ASC_OK" = 1 ] && [ -n "$BUNDLE" ] && DO_ASC=1

want play && [ -z "$PLAY_KEY" ] && echo "  (skipping Play — no credential found)" >&2
want agc  && [ -z "$AGC_KEY"  ] && echo "  (skipping AppGallery — no credential found)" >&2
if want asc && [ "$DO_ASC" = 0 ]; then
  if [ -z "$BUNDLE" ]; then echo "  (skipping App Store — no ios/Runner.xcodeproj)" >&2
  else echo "  (skipping App Store — set ASC_KEY_ID/ASC_ISSUER_ID in ~/.config/asc/config)" >&2; fi
fi
[ $((DO_PLAY + DO_AGC + DO_ASC)) -gt 0 ] || die "no store to publish to"
[ "$DO_PLAY" = 0 ] || [ -r "$PLAY_KEY" ] || die 'configured Play credential is missing or unreadable'
[ "$DO_AGC" = 0 ] || [ -r "$AGC_KEY" ] || die 'configured AppGallery credential is missing or unreadable'
if [ "$DO_PLAY" = 1 ] && [ -f "$APP/android/fastlane/Fastfile" ]; then
  die 'project Fastfile found; inspect and use its actual upload lane rather than guessing its name'
fi
if grep -q 'productFlavors' "$GRADLE"; then
  die 'product flavors found; use the project-specific release workflow with an explicit production flavor'
fi

# Fail before an expensive build when a required local tool is missing.
command -v flutter >/dev/null || die 'flutter is not installed'
command -v python3 >/dev/null || die 'python3 is not installed'
[ "$DO_PLAY" = 0 ] || command -v fastlane >/dev/null || die 'fastlane is not installed'
[ "$DO_AGC" = 0 ] || command -v python3 >/dev/null || die 'python3 is not installed'
[ "$DO_ASC" = 0 ] || command -v asc >/dev/null || die 'asc CLI is not installed'
if [ "$CHECK" = 1 ]; then
  log 'local credentials and tools found (store permissions, signing and version availability still need verification)'
  exit 0
fi

# One clean operation for all requested artifacts, before building any of them.
# Reusing arbitrary files in build/ can silently publish another revision/version.
if [ "$MODE" = prepare ]; then
  ( cd "$APP" && flutter clean && flutter pub get ) || die 'clean/dependency resolution failed'
fi

# ---------------------------------------------------------------- build what's needed

build_artifact() { # <artifact> <flutter build target>
  if [ "$MODE" = prepare ]; then
    log "building $2"
    ( cd "$APP" && flutter build "$2" --release ) || die "$2 build failed"
  fi
  [ -f "$1" ] || die "$2 did not produce the expected artifact"
}

[ "$DO_PLAY" = 1 ] && build_artifact "$AAB" appbundle
[ "$DO_AGC"  = 1 ] && build_artifact "$APK" apk

IPA=""
if [ "$DO_ASC" = 1 ]; then
  if [ "$MODE" = prepare ]; then
    log "building ipa (needs a valid signing setup in Xcode)"
    ( cd "$APP" && flutter build ipa --release ) || die "ipa build failed"
  fi
  shopt -s nullglob
  ipas=("$IPA_DIR"/*.ipa)
  [ "${#ipas[@]}" -eq 1 ] || die 'expected exactly one newly built IPA'
  IPA="${ipas[0]}"
  [ -n "$IPA" ] || die "no .ipa produced in $IPA_DIR"
fi

artifacts=()
[ "$DO_PLAY" = 0 ] || artifacts+=("$AAB")
[ "$DO_AGC" = 0 ] || artifacts+=("$APK")
[ "$DO_ASC" = 0 ] || artifacts+=("$IPA")
MANIFEST="$APP/build/mobile-publish.json"
IDENTITY="$PACKAGE|$BUNDLE|$VERSION|$DO_PLAY|$DO_AGC|$DO_ASC|$TRACK"
if [ "$MODE" = prepare ]; then
  python3 "$(dirname "$0")/prepared_release.py" record "$MANIFEST" "$IDENTITY" "${artifacts[@]}" || die 'could not record prepared artifacts'
  log 'prepared only; no upload performed. Inspect signatures, versions and runtime behavior, then use --upload-prepared with the same store/track.'
  exit 0
fi
python3 "$(dirname "$0")/prepared_release.py" verify "$MANIFEST" "$IDENTITY" "${artifacts[@]}" || die 'prepared artifact verification failed'

ok=() failed=()

# ---------------------------------------------------------------- Google Play

if [ "$DO_PLAY" = 1 ]; then
  log "Google Play → track $TRACK"
    if fastlane supply --json_key "$PLAY_KEY" --package_name "$PACKAGE" --aab "$AAB" \
        --track "$TRACK" --skip_upload_metadata true --skip_upload_images true \
        --skip_upload_screenshots true --skip_upload_changelogs true \
        --release_status draft --changes_not_sent_for_review true; then
      ok+=("play"); else failed+=("play"); fi
fi

# ---------------------------------------------------------------- Huawei AppGallery

if [ "$DO_AGC" = 1 ]; then
  log "Huawei AppGallery"
  CMD=upload; [ "$SUBMIT" = 1 ] && CMD=publish
  if AGC_KEY_FILE="$AGC_KEY" AGC_PACKAGE="$PACKAGE" python3 "$(dirname "$0")/agc.py" "$CMD" "$APK"; then
    ok+=("appgallery"); else failed+=("appgallery"); fi
fi

# ---------------------------------------------------------------- Apple App Store

if [ "$DO_ASC" = 1 ]; then
  log "App Store Connect — $BUNDLE"
  # Uploading to ASC is separate from submitting for App Store review.
  # --wait propagates processing failures instead of treating transport as acceptance.
  if ASC_KEY_ID="$ASC_KEY_ID" ASC_ISSUER_ID="$ASC_ISSUER_ID" \
       ASC_PRIVATE_KEY_PATH="$ASC_P8" \
       asc builds upload --app "$BUNDLE" --ipa "$IPA" --wait; then
    ok+=("appstore"); else failed+=("appstore"); fi
fi

# ---------------------------------------------------------------- report

echo
log "done — succeeded: ${ok[*]:-none}   failed: ${failed[*]:-none}"
[ "$SUBMIT" = 1 ] || echo "   review submission is a separate store-specific action; inspect any failed stores above" >&2
[ ${#failed[@]} -eq 0 ]
