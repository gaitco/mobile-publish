#!/usr/bin/env bash
#
# Zero-configuration publisher. Run it from anywhere inside a Flutter/Android repo:
#
#   publish.sh                 # upload to every store this app is set up for
#   publish.sh --store play    # one store only  (play | agc | asc)
#   publish.sh --build         # rebuild first instead of using the existing artifact
#   publish.sh --submit        # also send for review / promote past the holding track
#
# Everything else is discovered: the app module, the package name, the version, the
# artifact paths, and the credentials. Nothing to configure per project.
#
set -uo pipefail

STORE=all BUILD=0 SUBMIT=0 TRACK=internal
while [ $# -gt 0 ]; do
  case "$1" in
    --store)  STORE="${2:-all}"; shift 2 ;;
    --track)  TRACK="${2:-internal}"; shift 2 ;;
    --build)  BUILD=1; shift ;;
    --submit) SUBMIT=1; shift ;;
    -h|--help) sed -n '2,13p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
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

GRADLE=$(ls "$APP"/android/app/build.gradle.kts "$APP"/android/app/build.gradle 2>/dev/null | head -1)
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
[ -f "$HOME/.config/asc/config" ] && { set -a; . "$HOME/.config/asc/config"; set +a; }
ASC_OK=0
[ -n "${ASC_KEY_ID:-}" ] && [ -n "${ASC_ISSUER_ID:-}" ] \
  && [ -f "$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID}.p8" ] && ASC_OK=1

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

# ---------------------------------------------------------------- build what's needed

build_if_missing() { # <artifact> <flutter build target>
  if [ "$BUILD" = 1 ] || [ ! -f "$1" ]; then
    log "building $2"
    ( cd "$APP" && flutter build "$2" --release ) || die "$2 build failed"
  else
    log "using existing $(basename "$1") ($(du -h "$1" | cut -f1), built $(date -r "$1" '+%Y-%m-%d %H:%M'))"
  fi
}

[ "$DO_PLAY" = 1 ] && build_if_missing "$AAB" appbundle
[ "$DO_AGC"  = 1 ] && build_if_missing "$APK" apk

IPA=""
if [ "$DO_ASC" = 1 ]; then
  IPA=$(ls -t "$IPA_DIR"/*.ipa 2>/dev/null | head -1)
  if [ "$BUILD" = 1 ] || [ -z "$IPA" ]; then
    log "building ipa (needs a valid signing setup in Xcode)"
    ( cd "$APP" && flutter build ipa --release ) || die "ipa build failed"
    IPA=$(ls -t "$IPA_DIR"/*.ipa 2>/dev/null | head -1)
  else
    log "using existing $(basename "$IPA") ($(du -h "$IPA" | cut -f1))"
  fi
  [ -n "$IPA" ] || die "no .ipa produced in $IPA_DIR"
fi

ok=() failed=()

# ---------------------------------------------------------------- Google Play

if [ "$DO_PLAY" = 1 ]; then
  log "Google Play → track $TRACK"
  # A repo with its own fastlane lanes encodes decisions a generic call would lose
  # (changelogs from metadata/, custom artifact paths). Prefer them.
  if [ -f "$APP/android/fastlane/Appfile" ]; then
    log "using this repo's fastlane lanes"
    if ( cd "$APP/android" && PLAY_STORE_JSON_KEY="$PLAY_KEY" fastlane upload track:"$TRACK" ); then
      ok+=("play"); else failed+=("play"); fi
  else
    if fastlane supply --json_key "$PLAY_KEY" --package_name "$PACKAGE" --aab "$AAB" \
        --track "$TRACK" --skip_upload_metadata true --skip_upload_images true \
        --skip_upload_screenshots true --skip_upload_changelogs true \
        $([ "$SUBMIT" = 0 ] && echo "--changes_not_sent_for_review true"); then
      ok+=("play"); else failed+=("play"); fi
  fi
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
  # Without --submit, validate only: altool's dry run runs Apple's real checks
  # (signing, entitlements, Info.plist) without putting a build in App Store Connect.
  if [ "$SUBMIT" = 1 ]; then ACT=(--upload-app -f "$IPA"); else ACT=(--validate-app -f "$IPA"); fi
  [ "$SUBMIT" = 1 ] || log "validating only — pass --submit to actually upload the build"
  if xcrun altool "${ACT[@]}" -t ios \
       --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"; then
    ok+=("appstore"); else failed+=("appstore"); fi
fi

# ---------------------------------------------------------------- report

echo
log "done — succeeded: ${ok[*]:-none}   failed: ${failed[*]:-none}"
[ "$SUBMIT" = 1 ] || echo "   uploaded to holding areas only; re-run with --submit to send for review" >&2
[ ${#failed[@]} -eq 0 ]
