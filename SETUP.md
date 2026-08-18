# Setup

One credential per store, stored centrally, covering **every app** you publish. Do this once
and no project ever asks again.

If you find yourself creating a key per app, it was scoped too narrowly at creation.

## Where credentials are looked for

`scripts/publish.sh` resolves each store in this order and **skips any store whose credential
is missing** rather than failing, so you can set up one store now and the rest later.

| Store | Resolution order |
|---|---|
| AppGallery | `$AGC_KEY_FILE` → `<app>/android/agc-service-account.json` → `~/.config/agc/service-account.json` |
| Play | `$PLAY_STORE_JSON_KEY` → `<app>/android/play-store-key.json` → `~/.config/play/service-account.json` |
| App Store | `~/.config/asc/config` (for `ASC_KEY_ID` + `ASC_ISSUER_ID`) plus `~/.appstoreconnect/private_keys/AuthKey_<KEYID>.p8` |

The last entry in each row is the shared location. Prefer it — the in-project paths exist only
for repos that already had a key committed to a private repo, and are a worse default.

**Never commit any of these.** The bundled `.gitignore` covers the filenames, but the safe
habit is to move keys straight from `~/Downloads` into `~/.config/` and never near a repo.

## Prerequisites

| Tool | Needed for | Install |
|---|---|---|
| `python3`, `curl`, `openssl` | AppGallery | preinstalled on macOS |
| `jq` | helper snippets | `brew install jq` |
| `fastlane` | Play, App Store | `brew install fastlane` |
| Xcode + command line tools | App Store only | Mac App Store |

No gems, plugins, or per-project config beyond this.

---

## Huawei AppGallery

**Get the key.** AGC console → **Users and permissions** → **API key** → **Service account**
tab → Create. Give it the **App administrator** role. The download is a JSON file containing
`private_key`, `key_id`, and `sub_account`.

```bash
mkdir -p ~/.config/agc && chmod 700 ~/.config/agc
mv ~/Downloads/agc-apiclient-*.json ~/.config/agc/service-account.json
chmod 600 ~/.config/agc/service-account.json
```

**Verify:**

```bash
AGC_PACKAGE=com.your.app python3 scripts/agc.py app-id
```

### Two traps worth knowing up front

- **A Service account and a Connect API client are different credentials.** Both exist in the
  same console section. This tooling uses the **Service account**; a Connect API client
  (`client_id` + `client_secret`) has shown *less* app visibility, returning an empty
  `appid-list` for apps the service account resolves fine.
- **A brand-new draft app has no package binding yet**, so lookup by package finds nothing on
  the very first upload. Pass `AGC_APP_ID=<id>` for that one run. The appId is the **first**
  number in the console URL `#/myApp/<appId>/<projectId>` — roughly 9 digits, where the
  projectId is 17–19. Reversing them produces a 403 that reads exactly like a permissions
  failure.

---

## Google Play

**Start from Play Console, not Google Cloud.** Starting on the GCP side is the classic mistake
— you end up with a key Play has never heard of.

1. Play Console → **Developer account** → **API access** (left sidebar, below Download
   reports — *not* under Settings)
2. Link a Google Cloud project if prompted, then **Create new service account** (it hands you
   to GCP and back)
3. In GCP, create a **JSON key** for that account and download it
4. Back in Play Console → **Users and permissions**, grant it **Release** permissions for the
   apps it should publish

```bash
mkdir -p ~/.config/play && chmod 700 ~/.config/play
mv ~/Downloads/<downloaded>.json ~/.config/play/service-account.json
chmod 600 ~/.config/play/service-account.json
```

**Verify:**

```bash
fastlane run validate_play_store_json_key json_key:~/.config/play/service-account.json
```

Grants take a few minutes to propagate — a 401 straight after granting is usually propagation,
not misconfiguration.

**The first release of a new app must be manual.** Google does not allow the API to upload an
app's first version. Do that one by hand in the console; every release after is one command.

---

## Apple App Store

**Get the key.** App Store Connect → **Users and Access** → **Integrations** → **App Store
Connect API** → generate a key. **Developer** role can upload builds; **App Manager** or
**Admin** is required for listing changes. The `.p8` downloads **once** — losing it means
revoking and reissuing.

```bash
mkdir -p ~/.appstoreconnect/private_keys && chmod 700 ~/.appstoreconnect/private_keys
mv ~/Downloads/AuthKey_XXXXXXXXXX.p8 ~/.appstoreconnect/private_keys/
chmod 600 ~/.appstoreconnect/private_keys/AuthKey_XXXXXXXXXX.p8

mkdir -p ~/.config/asc && chmod 700 ~/.config/asc
cat > ~/.config/asc/config <<'CFG'
ASC_KEY_ID=XXXXXXXXXX
ASC_ISSUER_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
CFG
```

That `.p8` path is Apple's convention, not ours — its tools look there by name, which is why
`altool` takes only `--apiKey <KEYID>` and no path. A key left in `~/Downloads` will not work.

The **Issuer ID** is one UUID for the whole team, shared by every key. It is an identifier, not
a secret, and it is **not** recoverable from the `.p8` — copy it from the console once.

**Verify:**

```bash
. ~/.config/asc/config
xcrun altool --list-apps --apiKey "$ASC_KEY_ID" --apiIssuer "$ASC_ISSUER_ID"
```

That lists every app the key can reach, which also confirms the role is right.

---

## Android signing (both Android stores)

Both Play and AppGallery reject debug-signed artifacts. A Flutter app needs
`android/key.properties` pointing at your release keystore.

**Neither the keystore nor `key.properties` may be committed** — a committed keystore lets
anyone sign releases as you, and the passwords sit in plaintext next to it. Both are in this
repo's `.gitignore`; make sure they are in your app's too.

Confirm any artifact carries the real key before uploading:

```bash
export JAVA_HOME=/opt/homebrew/opt/openjdk@17
"$ANDROID_HOME"/build-tools/*/apksigner verify --print-certs <artifact>
```

The certificate DN should name your organization, not `CN=Android Debug`.

> When Play App Signing is enabled, Google re-signs with its own key, so an AppGallery build
> carries a **different** signature and users cannot update across the two stores. That is
> expected, not a defect.

## Check everything at once

```bash
ls -l ~/.config/agc/service-account.json \
      ~/.config/play/service-account.json \
      ~/.config/asc/config \
      ~/.appstoreconnect/private_keys/
```

Anything missing means that store is skipped, not that publishing fails.
