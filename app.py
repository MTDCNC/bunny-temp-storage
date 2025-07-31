# === app.py for Bunny Temp Storage Service ===
from flask import Flask, request, jsonify
import requests
import os
import json
import threading
import sys
from urllib.parse import urlparse, unquote

app = Flask(__name__)

# Config
BUNNY_API_KEY     = os.environ.get("BUNNY_API_KEY")
BUNNY_ZONE_NAME   = "zapier-temp-files"
CDN_PREFIX        = "https://zapier-temp-cdn.b-cdn.net"
STATUS_FILENAME   = "bunny_status.json"

# Always unbuffer stdout
sys.stdout.reconfigure(line_buffering=True)


def get_dropbox_access_token():
    resp = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={
            "grant_type":    "refresh_token",
            "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"],
            "client_id":     os.environ["DROPBOX_CLIENT_ID"],
            "client_secret": os.environ["DROPBOX_CLIENT_SECRET"]
        }
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def save_bunny_status(filename, cdn_url):
    # Load existing
    try:
        with open(STATUS_FILENAME, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        data = {}

    data[filename] = cdn_url
    # Write + flush + fsync
    with open(STATUS_FILENAME, 'w') as f:
        json.dump(data, f)
        f.flush()
        os.fsync(f.fileno())


def upload_file_to_bunny(shared_link, filename):
    try:
        print(f"⬇️ [Async] Downloading {filename} from Dropbox...", flush=True)
        token = get_dropbox_access_token()
        headers = {
            'Authorization':           f"Bearer {token}",
            'Dropbox-API-Arg':         json.dumps({"url": shared_link})
        }
        resp = requests.post("https://content.dropboxapi.com/2/sharing/get_shared_link_file", headers=headers, stream=True)
        resp.raise_for_status()
        print("✅ [Async] Download complete", flush=True)

        bunny_url = f"https://uk.storage.bunnycdn.com/{BUNNY_ZONE_NAME}/{filename}"
        print(f"📤 [Async] Uploading to Bunny: {bunny_url}", flush=True)
        put_headers = { 'AccessKey': BUNNY_API_KEY, 'Content-Type': 'application/octet-stream' }
        put_resp = requests.put(bunny_url, data=resp.iter_content(1048576), headers=put_headers)
        print(f"🔁 Bunny response: {put_resp.status_code}", flush=True)
        put_resp.raise_for_status()

        cdn_url = f"{CDN_PREFIX}/{filename}"
        print(f"✅ [Async] File live at {cdn_url}", flush=True)
        save_bunny_status(filename, cdn_url)
    except Exception as err:
        print(f"❌ [Async] Error for {filename}: {err}", flush=True)


@app.route('/upload-to-bunny', methods=['POST'])
def upload_to_bunny():
    data = request.json or {}
    link = data.get('dropbox_shared_link')
    if not link:
        return jsonify({"error": "Missing dropbox_shared_link"}), 400

    filename = unquote(urlparse(link).path.split('/')[-1])
    print(f"📥 Received: {filename}, starting async upload...", flush=True)
    thread = threading.Thread(target=upload_file_to_bunny, args=(link, filename), daemon=True)
    thread.start()
    return jsonify({"status": "processing", "filename": filename}), 202


@app.route('/bunny-status-check', methods=['GET'])
def bunny_status_check():
    name = request.args.get('filename')
    if not name:
        return jsonify({"error": "Missing filename"}), 400
    try:
        with open(STATUS_FILENAME, 'r') as f:
            data = json.load(f)
    except (FileNotFoundError, ValueError):
        return jsonify({"error": "No status file"}), 404

    url = data.get(name)
    if url:
        return jsonify({"cdn_url": url}), 200
    return jsonify({"error": "Not found"}), 404


@app.route('/', methods=['GET'])
def home():
    return "Bunny Async Uploader is live!", 200
