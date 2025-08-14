# === app.py for Bunny Temp Storage Service ===
from flask import Flask, request, jsonify
import requests
import os
import json
import threading
import sys
from urllib.parse import (
    urlparse, unquote, unquote_plus, parse_qs, urlencode, urlunparse, quote
)
import os.path as op

app = Flask(__name__)

# Config
BUNNY_API_KEY   = os.environ.get("BUNNY_API_KEY")
BUNNY_ZONE_NAME = "zapier-temp-files"
CDN_PREFIX      = "https://zapier-temp-cdn.b-cdn.net"
STATUS_FILENAME = "bunny_status.json"

# Always unbuffer stdout
sys.stdout.reconfigure(line_buffering=True)

# -----------------------
# Helpers
# -----------------------

def normalize_shared_link(link: str) -> str:
    """Ensure Dropbox shared link is a direct download link (dl=1)."""
    parsed = urlparse(link)
    qs = parse_qs(parsed.query)
    qs['dl'] = ['1']
    new_query = urlencode(qs, doseq=True)
    return urlunparse(parsed._replace(query=new_query))

def get_dropbox_access_token():
    resp = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={
            "grant_type":    "refresh_token",
            "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"],
            "client_id":     os.environ["DROPBOX_CLIENT_ID"],
            "client_secret": os.environ["DROPBOX_CLIENT_SECRET"],
        },
        timeout=30
    )
    resp.raise_for_status()
    return resp.json()["access_token"]

def _canon(s: str) -> str:
    """Canonical key: basename, strip, lower."""
    return op.basename(s or "").strip().lower()

def _variants(name: str):
    """Filename variants we want to recognize interchangeably."""
    a = name
    b = name.replace("-", " ")
    c = name.replace(" ", "-")
    # De-dup while preserving order
    seen, out = set(), []
    for v in (a, b, c):
        if v not in seen:
            out.append(v)
            seen.add(v)
    return out

def _load_status():
    try:
        with open(STATUS_FILENAME, "r") as f:
            return json.load(f)
    except (FileNotFoundError, ValueError):
        return {}

def _write_status(d: dict):
    with open(STATUS_FILENAME, "w") as f:
        json.dump(d, f)
        f.flush()
        os.fsync(f.fileno())

def save_bunny_status(filename: str, cdn_url: str = None, error: str = None):
    """
    Save a result under multiple interchangeable keys so lookups
    by spaces/dashes/case all succeed.
    """
    data = _load_status()
    entry = {}
    if cdn_url:
        entry["cdn_url"] = cdn_url
    if error:
        entry["error"] = error

    # Save under original + variants + canonical (lowercased)
    for key in _variants(filename) + [_canon(filename)]:
        data[key] = entry

    _write_status(data)

# -----------------------
# Core worker
# -----------------------

def upload_file_to_bunny(shared_link: str, filename: str):
    """
    Download from Dropbox then upload to Bunny.
    Retries once if we see a 409 by normalizing the link.
    Detects deleted files via HTML response heuristic.
    """
    attempts = 0
    resp = None
    while attempts < 2:
        link = shared_link if attempts == 0 else normalize_shared_link(shared_link)
        try:
            print(f"⬇️ [Async] Downloading {filename} from Dropbox (attempt {attempts+1})...", flush=True)
            token = get_dropbox_access_token()
            headers = {
                "Authorization":   f"Bearer {token}",
                "Dropbox-API-Arg": json.dumps({"url": link}),
            }
            resp = requests.post(
                "https://content.dropboxapi.com/2/sharing/get_shared_link_file",
                headers=headers,
                stream=True,
                timeout=120
            )
            resp.raise_for_status()

            # Check for HTML error page (deleted file)
            ctype = resp.headers.get("Content-Type", "")
            if "text/html" in ctype:
                body = resp.text[:1000]
                if "This item was deleted" in body:
                    print(f"❌ [Async] File deleted on Dropbox: {filename}", flush=True)
                    save_bunny_status(filename, error="file_deleted")
                    return

            print("✅ [Async] Download complete", flush=True)
            break
        except requests.HTTPError as err:
            code = err.response.status_code if err.response else None
            print(f"⚠️ [Async] Dropbox download error (code {code}): {err}", flush=True)
            if code == 409 and attempts == 0:
                print("⬆️ [Async] Retrying with dl=1 parameter...", flush=True)
                attempts += 1
                continue
            elif code == 404:
                print(f"❌ [Async] File not found: {filename}", flush=True)
                save_bunny_status(filename, error="file_not_found")
                return
            else:
                print(f"❌ [Async] Failed to download {filename}, aborting.", flush=True)
                save_bunny_status(filename, error=str(err))
                return
        except Exception as err:
            print(f"❌ [Async] Download error: {err}", flush=True)
            save_bunny_status(filename, error=str(err))
            return

    if resp is None:
        print(f"❌ [Async] Download never succeeded for {filename}, aborting.", flush=True)
        save_bunny_status(filename, error="download_failed")
        return

    # Upload to Bunny
    try:
        bunny_url = f"https://uk.storage.bunnycdn.com/{BUNNY_ZONE_NAME}/{filename}"
        print(f"📤 [Async] Uploading to Bunny: {bunny_url}", flush=True)
        put_headers = {
            "AccessKey": BUNNY_API_KEY,
            "Content-Type": "application/octet-stream",
        }
        put_resp = requests.put(bunny_url, data=resp.iter_content(1048576), headers=put_headers, timeout=600)
        print(f"🔁 Bunny response: {put_resp.status_code}", flush=True)
        put_resp.raise_for_status()

        # Return a URL-encoded path component so spaces are always valid
        cdn_url = f"{CDN_PREFIX}/{quote(filename)}"
        print(f"✅ [Async] File live at {cdn_url}", flush=True)
        save_bunny_status(filename, cdn_url=cdn_url)
    except Exception as err:
        print(f"❌ [Async] Bunny upload error for {filename}: {err}", flush=True)
        save_bunny_status(filename, error=str(err))

# -----------------------
# Routes
# -----------------------

@app.route("/upload-to-bunny", methods=["POST"])
def upload_to_bunny():
    data = request.json or {}
    link = data.get("dropbox_shared_link")
    if not link:
        return jsonify({"error": "Missing dropbox_shared_link"}), 400

    # Filename from the Dropbox URL path (handles both spaces and dashes)
    parsed_link = urlparse(link)
    filename = op.basename(parsed_link.path)
    filename = unquote(filename).strip()
    print(f"📦 Normalized filename: {filename}", flush=True)

    thread = threading.Thread(target=upload_file_to_bunny, args=(link, filename), daemon=True)
    thread.start()
    return jsonify({"status": "processing", "filename": filename}), 202

@app.route("/bunny-status-check", methods=["GET"])
def bunny_status_check():
    raw = request.args.get("filename", "")
    if not raw:
        return jsonify({"error": "Missing filename"}), 400

    # Accept + or %20 as spaces; take only basename
    name = op.basename(unquote_plus(raw)).strip()
    data = _load_status()
    if not data:
        return jsonify({"error": "No status file"}), 404

    # Build a case-insensitive map
    ci_map = {_canon(k): v for k, v in data.items()}

    # Try exact + variants (case-insensitive)
    for cand in _variants(name) + [_canon(name)]:
        hit = ci_map.get(_canon(cand))
        if hit:
            if "error" in hit:
                return jsonify({"error": hit["error"]}), 404
            url = hit.get("cdn_url") if isinstance(hit, dict) else hit
            return jsonify({"cdn_url": url}), 200

    return jsonify({"error": "Not found"}), 404

@app.route("/", methods=["GET"])
def home():
    return "Bunny Async Uploader is live!", 200
