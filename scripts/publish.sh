#!/usr/bin/env bash
#
# Project-policy publisher. Run it from anywhere inside a Flutter/Android repo:
#
#   publish.sh                 # prepare fresh store artifacts (Shorebird baseline may be registered)
#   publish.sh --upload-prepared # upload the exact artifacts inspected after preparation
#   publish.sh --store play    # one store only  (play | agc | asc)
#   publish.sh --check         # local readiness only; no build or upload
#   publish.sh --check-online  # also verify Shorebird app and release role using GET only
#   publish.sh --acknowledge-usage-warning # only after user approves this operation's usage warning
#   publish.sh --build         # accepted for compatibility; builds are always clean
#   publish.sh --store agc --upload-prepared --submit # AppGallery review, only when requested
#
# Everything else is discovered: the app module, the package name, the version, the
# artifact paths, and selected credentials. Runtime/stores follow project policy.
#
set -uo pipefail

die() { printf 'error: %s\n' "$*" >&2; exit 1; }
STORE=all SUBMIT=0 TRACK=internal CHECK=0 MODE=prepare ONLINE=0 ACK_USAGE=0
while [ $# -gt 0 ]; do
  case "$1" in
    --store)  [ $# -ge 2 ] && [ -n "$2" ] || die '--store needs a value'; STORE="$2"; shift 2 ;;
    --track)  [ $# -ge 2 ] && [ -n "$2" ] || die '--track needs a value'; TRACK="$2"; shift 2 ;;
    --build)  shift ;;
    --check)  CHECK=1; shift ;;
    --check-online) CHECK=1; ONLINE=1; shift ;;
    --acknowledge-usage-warning) ACK_USAGE=1; shift ;;
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
APP=$(python3 -c 'import sys; sys.path.insert(0, sys.argv[1]); from release_request import discover; print(discover(sys.argv[2]))' "$(dirname "$0")" "$PWD") || die 'application discovery failed; select the exact application module'

# Project policy, rather than the operator's account, selects runtime and stores.
POLICY_OUTPUT=$(python3 "$(dirname "$0")/publish_policy.py" "$APP" --store "$STORE") || die 'project policy could not be resolved'
RUNTIME=$(printf '%s\n' "$POLICY_OUTPUT" | sed -n '1p')
SELECTED_STORES=$(printf '%s\n' "$POLICY_OUTPUT" | sed -n '2p')
READINESS_ARGS=("$APP" --store "$STORE")
[ "$ACK_USAGE" = 0 ] || READINESS_ARGS+=(--acknowledge-usage-warning)
check_readiness() { python3 "$(dirname "$0")/publish_readiness.py" "${READINESS_ARGS[@]}"; }

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
log "runtime: $RUNTIME (store release; this command never publishes OTA patches)"

# ---------------------------------------------------------------- decide the stores

want() { case " $SELECTED_STORES " in *" $1 "*) return 0 ;; *) return 1 ;; esac; }

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
ASC_OK=0
ASC_P8=''
if want asc; then
  # shellcheck source=/dev/null
  [ -f "$HOME/.config/asc/config" ] && { set -a; . "$HOME/.config/asc/config"; set +a; }
  ASC_P8="$HOME/.appstoreconnect/private_keys/AuthKey_${ASC_KEY_ID:-}.p8"
  [ -n "${ASC_KEY_ID:-}" ] && [ -n "${ASC_ISSUER_ID:-}" ] \
    && [ -f "$ASC_P8" ] && ASC_OK=1
fi

DO_PLAY=0; DO_AGC=0; DO_ASC=0
want play && [ -n "$PLAY_KEY" ] && DO_PLAY=1
want agc  && [ -n "$AGC_KEY"  ] && DO_AGC=1
want asc  && [ "$ASC_OK" = 1 ] && [ -n "$BUNDLE" ] && DO_ASC=1

want play && [ "$DO_PLAY" = 0 ] && die 'Play is selected but its credential is missing'
want agc && [ "$DO_AGC" = 0 ] && die 'AppGallery is selected but its credential is missing'
if want asc && [ "$DO_ASC" = 0 ]; then
  die 'App Store is selected but its app configuration or credential is missing'
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
[ "$RUNTIME" != shorebird ] || command -v shorebird >/dev/null || die 'Shorebird app detected but shorebird CLI is not installed; do not fall back to flutter build'
[ "$DO_PLAY" = 0 ] || command -v fastlane >/dev/null || die 'fastlane is not installed'
[ "$DO_AGC" = 0 ] || command -v python3 >/dev/null || die 'python3 is not installed'
[ "$DO_ASC" = 0 ] || command -v asc >/dev/null || die 'asc CLI is not installed'
if [ "$CHECK" = 1 ]; then
  if [ "$ONLINE" = 1 ]; then
    check_readiness || die 'online readiness check failed; no build or upload performed'
  fi
  log 'local credentials and tools found (store permissions, signing and version availability still need verification)'
  exit 0
fi

# One clean operation for all requested artifacts, before building any of them.
# Reusing arbitrary files in build/ can silently publish another revision/version.
if [ "$MODE" = prepare ]; then
  check_readiness || die 'project access is not ready; no build started'
  ( cd "$APP" && flutter clean && flutter pub get ) || die 'clean/dependency resolution failed'
  if [ "$RUNTIME" = shorebird ]; then
    platforms=()
    [ $((DO_PLAY + DO_AGC)) -eq 0 ] || platforms+=(android)
    [ "$DO_ASC" = 0 ] || platforms+=(ios)
    platform_list=$(IFS=,; echo "${platforms[*]}")
    release_args=(release --platforms "$platform_list" --flutter-version system)
    [ "$DO_AGC" = 0 ] || release_args+=(--artifact apk)
    log 'building with Shorebird and registering the new store-release baseline; no store upload or OTA patch'
    ( cd "$APP" && shorebird "${release_args[@]}" ) || die 'Shorebird release failed; inspect any partially registered baseline before retrying'
  fi
fi

# ---------------------------------------------------------------- build what's needed

build_artifact() { # <artifact> <flutter build target>
  if [ "$MODE" = prepare ] && [ "$RUNTIME" = flutter ]; then
    log "building $2"
    ( cd "$APP" && flutter build "$2" --release ) || die "$2 build failed"
  fi
  [ -f "$1" ] || die "$2 did not produce the expected artifact"
}

[ "$DO_PLAY" = 1 ] && build_artifact "$AAB" appbundle
[ "$DO_AGC"  = 1 ] && build_artifact "$APK" apk

IPA=""
if [ "$DO_ASC" = 1 ]; then
  if [ "$MODE" = prepare ] && [ "$RUNTIME" = flutter ]; then
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
[ "$RUNTIME" != shorebird ] || artifacts+=("$APP/shorebird.yaml")
[ ! -f "$APP/mobile-publish.config.json" ] || artifacts+=("$APP/mobile-publish.config.json")
MANIFEST="$APP/build/mobile-publish.json"
IDENTITY="$PACKAGE|$BUNDLE|$VERSION|$DO_PLAY|$DO_AGC|$DO_ASC|$TRACK|$RUNTIME"
if [ "$MODE" = prepare ]; then
  python3 "$(dirname "$0")/prepared_release.py" record "$MANIFEST" "$IDENTITY" "${artifacts[@]}" || die 'could not record prepared artifacts'
  log 'prepared only; no store upload or OTA patch performed. Inspect signatures, versions and runtime behavior, then use --upload-prepared with the same store/track.'
  exit 0
fi
python3 "$(dirname "$0")/prepared_release.py" verify "$MANIFEST" "$IDENTITY" "${artifacts[@]}" || die 'prepared artifact verification failed'
check_readiness || die 'project access is not ready; no upload attempted'

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
