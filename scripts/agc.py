#!/usr/bin/env python3
"""Huawei AppGallery publishing CLI (AGC Publishing API, service-account auth).

Credentials: agc-service-account.json next to this script (gitignored) — the
key file downloaded from AGC console > Users & permissions > API key >
Service account. Override path with AGC_KEY_FILE. See
docs/appgallery-submission.md.

Commands:
  app-id                       print the AppGallery appId for the package
  info                         print current app state (release state, version)
  upload <apk>                 upload an APK (no review submission)
  listing <listing.json>       write the listing (text, privacy URL, country, category)
  screenshots <png...>         upload 3-8 screenshots via OBS and attach them
  ready                        show what still blocks submission
  submit [--changelog <file>]  submit the uploaded build for review
  publish <apk> [--changelog <file>]   upload + wait + submit

Auth: PS256 JWT built from the service-account key, used directly as the
Bearer token (verified working 2026-07-31; the jwt-bearer exchange grant is
NOT supported by Huawei's token endpoint).
"""
import base64
import json
import os
import subprocess
import sys
import tempfile
import time
import urllib.parse

# Portable: the app is identified per-invocation, not baked in.
PACKAGE = os.environ.get("AGC_PACKAGE", "")
API = "https://connect-api.cloud.huawei.com/api/publish/v2"
def _default_key_file() -> str:
    """Prefer a repo-local key (matches existing per-app setups), then the shared one."""
    for c in ("agc-service-account.json",
              os.path.expanduser("~/.config/agc/service-account.json")):
        if os.path.exists(c):
            return c
    return os.path.expanduser("~/.config/agc/service-account.json")


KEY_FILE = os.environ.get("AGC_KEY_FILE") or _default_key_file()


def b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def make_token(creds: dict) -> str:
    now = int(time.time())
    header = {"alg": "PS256", "typ": "JWT", "kid": creds["key_id"]}
    payload = {"iss": creds["sub_account"], "aud": creds["token_uri"],
               "iat": now, "exp": now + 3600}
    signing_input = (b64url(json.dumps(header, separators=(",", ":")).encode())
                     + "." + b64url(json.dumps(payload, separators=(",", ":")).encode()))
    with tempfile.NamedTemporaryFile("w", suffix=".pem") as kf:
        kf.write(creds["private_key"])
        kf.flush()
        sig = subprocess.run(
            ["openssl", "dgst", "-sha256", "-binary",
             "-sigopt", "rsa_padding_mode:pss", "-sigopt", "rsa_pss_saltlen:digest",
             "-sign", kf.name],
            input=signing_input.encode(), capture_output=True, check=True).stdout
    return signing_input + "." + b64url(sig)


def curl(method: str, url: str, headers: dict, body_file: str = None, body: str = None) -> dict:
    cmd = ["curl", "-sS", "--fail-with-body", "-X", method, "--max-time", "600", url]
    for k, v in headers.items():
        cmd += ["-H", f"{k}: {v}"]
    if body_file:
        cmd += ["--data-binary", f"@{body_file}"]
    elif body is not None:
        cmd += ["--data-binary", body]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit(f"HTTP {method} {url} failed: {proc.stderr.strip()}\n{proc.stdout[:500]}")
    return json.loads(proc.stdout) if proc.stdout.strip() else {}


class Agc:
    def __init__(self):
        if not os.path.exists(KEY_FILE):
            sys.exit(f"Missing {KEY_FILE} — see docs/appgallery-submission.md")
        creds = json.load(open(KEY_FILE))
        self.headers = {
            "Authorization": f"Bearer {make_token(creds)}",
            "client_id": creds["sub_account"],
            "Content-Type": "application/json",
        }

    def api(self, method: str, path_qs: str, body: str = None) -> dict:
        res = curl(method, f"{API}/{path_qs}", self.headers, body=body)
        ret = res.get("ret", {})
        if ret.get("code") != 0:
            sys.exit(f"AGC error on {path_qs}: {json.dumps(ret, ensure_ascii=False)}")
        return res

    def app_id(self) -> str:
        # AGC_APP_ID override: needed for the FIRST upload — a fresh draft app has
        # no package name bound yet, so lookup by package finds nothing.
        if os.environ.get("AGC_APP_ID"):
            return os.environ["AGC_APP_ID"]
        if not PACKAGE:
            sys.exit("Set AGC_PACKAGE=<com.x.y> (or AGC_APP_ID=<id>) so the app can be identified.")
        ids = self.api("GET", f"appid-list?packageName={PACKAGE}")["appids"]
        if not ids:
            sys.exit(f"No AppGallery app with package {PACKAGE} — create it in the "
                     "AGC console first (New app; see docs/appgallery-submission.md).")
        return ids[0]["value"]

    def info(self, app_id: str) -> dict:
        return self.api("GET", f"app-info?appId={app_id}")["appInfo"]

    def upload(self, app_id: str, apk: str):
        size = os.path.getsize(apk)
        # Preferred path: direct-to-OBS PUT. It fails on apps whose listing has no
        # distribution countries yet (204144694 "distContryList is empty"), which is
        # normal for a listing still being filled in — so fall back rather than block.
        res = curl("GET", f"{API}/upload-url/for-obs?appId={app_id}&fileName=release.apk"
                          f"&contentLength={size}&suffix=apk", self.headers)
        if res.get("ret", {}).get("code") == 0 and "urlInfo" in res:
            url_info = res["urlInfo"]
            print(f"Uploading {apk} ({size / 1e6:.0f} MB) to OBS…")
            curl("PUT", url_info["url"], url_info["headers"], body_file=apk)
            dest, extra = url_info["objectId"], {}
        else:
            print(f"OBS upload unavailable ({res.get('ret', {}).get('code')}), "
                  f"using the classic upload endpoint…")
            slot = self.api("GET", f"upload-url?appId={app_id}&suffix=apk")
            print(f"Uploading {apk} ({size / 1e6:.0f} MB)…")
            out = subprocess.run(
                ["curl", "-sS", "-X", "POST", slot["uploadUrl"],
                 "-F", f"authCode={slot['authCode']}", "-F", "fileCount=1",
                 "-F", "parseType=1", "-F", f"file=@{apk}"],
                capture_output=True, text=True, check=True).stdout
            info = json.loads(out)["result"]["UploadFileRsp"]["fileInfoList"][0]
            # Huawei misspells this field in the response but expects the correct
            # spelling in the request below.
            dest = info.get("fileDestUlr") or info["fileDestUrl"]
            extra = {"size": info.get("size", size)}

        self.api("PUT", f"app-file-info?appId={app_id}", body=json.dumps({
            "fileType": 5,
            "files": [dict({"fileName": "release.apk", "fileDestUrl": dest}, **extra)],
        }))
        print("Upload attached to the draft release.")

    def obs_put(self, app_id: str, path: str) -> str:
        """Upload one image and return its objectId. Images only work through OBS —
        the classic upload endpoint yields URLs the listing rejects as unsigned."""
        size = os.path.getsize(path)
        name = os.path.basename(path)
        res = curl("GET", f"{API}/upload-url/for-obs?appId={app_id}&fileName={name}"
                          f"&contentLength={size}&suffix={name.rsplit('.', 1)[-1]}", self.headers)
        if res.get("ret", {}).get("code") != 0 or "urlInfo" not in res:
            sys.exit(f"No OBS slot for {name}: {res.get('ret')} "
                     "(distContryList empty? set publishCountry first)")
        url_info = res["urlInfo"]
        curl("PUT", url_info["url"], url_info["headers"], body_file=path)
        return url_info["objectId"]

    def screenshots(self, app_id: str, paths: list, lang: str = None):
        if not 3 <= len(paths) <= 8:
            sys.exit("AppGallery takes 3-8 screenshots.")
        lang = lang or self.info(app_id).get("defaultLang", "en-US")
        files = [{"fileName": os.path.basename(p), "fileDestUrl": self.obs_put(app_id, p)}
                 for p in paths]
        self.api("PUT", f"app-file-info?appId={app_id}",
                 body=json.dumps({"lang": lang, "fileType": 2, "files": files}))
        print(f"Attached {len(files)} screenshots ({lang}).")

    def listing(self, app_id: str, spec: dict):
        """Write listing text and app-level fields, then read back what actually landed."""
        lang = spec.get("lang") or self.info(app_id).get("defaultLang", "en-US")
        text = {k: spec[k] for k in ("appName", "appDesc", "briefInfo", "newFeatures")
                if spec.get(k)}
        if text:
            self.api("PUT", f"app-language-info?appId={app_id}",
                     body=json.dumps(dict(text, lang=lang), ensure_ascii=False))
        app = {k: spec[k] for k in ("privacyPolicy", "publishCountry",
                                    "parentType", "childType", "grandChildType")
               if spec.get(k) is not None}
        if app:
            self.api("PUT", f"app-info?appId={app_id}", body=json.dumps(app, ensure_ascii=False))
        self.ready(app_id)

    def ready(self, app_id: str):
        """AGC returns ret.code 0 for fields it ignored, so report the stored state."""
        res = self.api("GET", f"app-info?appId={app_id}")
        info, langs = res["appInfo"], res.get("languages") or [{}]
        lang = langs[0]
        dm = (lang.get("deviceMaterials") or [{}])[0]
        checks = {
            "package": bool(info.get("versionCode")),
            "country": bool(info.get("publishCountry")),
            "category": all(info.get(k) not in (None, -1)
                            for k in ("parentType", "childType", "grandChildType")),
            "brief text": bool(lang.get("briefInfo")),
            "full text": bool(lang.get("appDesc")),
            "privacy URL": bool(info.get("privacyPolicy")),
            "screenshots": len(dm.get("screenShots") or []) >= 3,
            "icon (console only)": bool(lang.get("icon") or dm.get("appIcon")),
        }
        for k, ok in checks.items():
            print(f"  {'OK  ' if ok else 'MISS'} {k}")
        print(f"  version {info.get('versionNumber')} ({info.get('versionCode')}), "
              f"last change {info.get('updateTime')}")
        missing = [k for k, ok in checks.items() if not ok]
        if missing:
            print("Submission will be refused until: " + ", ".join(missing))
        # No API surface exists for these — no endpoint, no app-info field. They are
        # invisible to this check but still block review, so name them every time.
        print("Console-only, not checkable here: privacy tags, AI function declaration, "
              "content rating questionnaire, review test account")
        # Verified against a live submission: an empty distributeDeviceTypes does NOT
        # block app-submit. Do not promote this to a blocking check — a false blocker
        # stops releases that would have shipped fine.
        if not info.get("distributeDeviceTypes"):
            print("  note: Compatible devices is unset in the console (does not block submit)")
        return not missing

    def submit(self, app_id: str, changelog: str = None):
        qs = f"app-submit?appId={app_id}"
        if changelog:
            notes = open(changelog).read().strip()
            if not 10 <= len(notes) <= 300:
                sys.exit("Changelog must be 10–300 characters.")
            qs += "&remark=" + urllib.parse.quote(notes)
        # ponytail: AGC needs time to process the package; retry instead of guessing
        for attempt in range(5):
            res = curl("POST", f"{API}/{qs}", self.headers)
            if res.get("ret", {}).get("code") == 0:
                print("Submitted for review.")
                return
            print(f"Submit not accepted yet ({res.get('ret')}), retrying in 60 s…")
            time.sleep(60)
        sys.exit("Submit failed after 5 attempts — check the release draft in the AGC console.")


def main():
    args = sys.argv[1:]
    if not args or args[0] not in {"app-id", "info", "ready", "listing", "screenshots",
                                   "upload", "submit", "publish"}:
        sys.exit(__doc__)
    cmd, agc = args[0], Agc()
    changelog = args[args.index("--changelog") + 1] if "--changelog" in args else None

    app_id = agc.app_id()
    if cmd == "app-id":
        print(app_id)
    elif cmd == "info":
        info = agc.info(app_id)
        print(json.dumps({k: info.get(k) for k in
                          ("releaseState", "versionNumber", "onShelfVersionNumber",
                           "appName", "updateTime")}, indent=2, ensure_ascii=False))
    elif cmd in {"upload", "publish"}:
        apk = next((a for a in args[1:] if a.endswith(".apk")), None)
        if not apk or not os.path.exists(apk):
            sys.exit("Pass a path to an existing .apk")
        agc.upload(app_id, apk)
        if cmd == "publish":
            print("Waiting 60 s for AGC package processing…")
            time.sleep(60)
            agc.submit(app_id, changelog)
    elif cmd == "ready":
        agc.ready(app_id)
    elif cmd == "listing":
        spec_file = next((a for a in args[1:] if a.endswith(".json")), None)
        if not spec_file or not os.path.exists(spec_file):
            sys.exit("Pass a listing .json (lang, appName, appDesc, briefInfo, newFeatures, "
                     "privacyPolicy, publishCountry, parentType, childType, grandChildType)")
        agc.listing(app_id, json.load(open(spec_file)))
    elif cmd == "screenshots":
        shots = [a for a in args[1:] if a.lower().endswith((".png", ".jpg", ".jpeg"))]
        if not shots:
            sys.exit("Pass 3-8 image paths")
        agc.screenshots(app_id, shots)
    elif cmd == "submit":
        agc.submit(app_id, changelog)


if __name__ == "__main__":
    main()
