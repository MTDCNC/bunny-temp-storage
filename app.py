from flask import Flask, request, jsonify
import requests
import os
import json
import threading
from urllib.parse import urlparse, unquote

app = Flask(__name__)

BUNNY_API_KEY = os.environ.get("BUNNY_API_KEY")  # Set this in Render
BUNNY_ZONE_NAME = "zapier-temp-files"
CDN_PREFIX = "https://zapier-temp-cdn.b-cdn.net"
BUNNY_STATUS_FILE = "bunny_status.json"

def get_dropbox_access_token():
    response = requests.post(
        "https://api.dropboxapi.com/oauth2/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": os.environ["DROPBOX_REFRESH_TOKEN"],
            "client_id": os.environ["DROPBOX_CLIENT_ID"],
            "client_secret": os.environ["DROPBOX_CLIENT_SECRET"]
        }
    )
    response.raise_for_status()
    return response.json()["access_token"]

def save_bunny_status(file_name, cdn_url):
    status = {}
    if os.path.exists(BUNNY_STATUS_FILE):
        with open(BUNNY_STATUS_FILE, "r") as f:
            status = json.load(f)
    status[file_name] = cdn_url
    with open(BUNNY_STATUS_FILE, "w") as f:
        json.dump(status, f)

def upload_file_to_bunny(dropbox_link, file_name):
    try:
        print(f"⬇️ [Async] Starting download for {file_name}...")

        access_token = get_dropbox_access_token()
        dropbox_headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": f'{{"url": "{dropbox_link}"}}'
        }

        resp = requests.post(
            "https://content.dropboxapi.com/2/sharing/get_shared_link_file",
            headers=dropbox_headers, stream=True
        )
        resp.raise_for_status()
        print("✅ [Async] File downloaded from Dropbox.")

        bunny_url = f"https://uk.storage.bunnycdn.com/{BUNNY_ZONE_NAME}/{file_name}"
        print(f"📤 [Async] Uploading to Bunny: {bunny_url}")
        bunny_headers = {
            "AccessKey": BUNNY_API_KEY,
            "Content-Type": "application/octet-stream"
        }
        bunny_resp = requests.put(
            bunny_url,
            data=resp.iter_content(chunk_size=1048576),
            headers=bunny_headers
        )
        print(f"🔁 Bunny response: {bunny_resp.status_code}")
        print(f"📝 Bunny body: {bunny_resp.text}")
        bunny_resp.raise_for_status()

        cdn_url = f"{CDN_PREFIX}/{file_name}"
        print(f"✅ [Async] File uploaded. CDN: {cdn_url}")

        save_bunny_status(file_name, cdn_url)
    except Exception as e:
        print(f"❌ [Async] Upload failed for {file_name}: {e}")

@app.route("/upload-to-bunny", methods=["POST"])
def upload_to_bunny():
    data = request.json
    dropbox_link = data.get("dropbox_shared_link")

    if not dropbox_link:
        return jsonify({"error": "Missing Dropbox shared link"}), 400

    parsed = urlparse(dropbox_link)
    file_name = unquote(parsed.path.split('/')[-1])
    print(f"📥 Received upload request for: {file_name}")

    # 🔁 Start upload in background
    thread = threading.Thread(target=upload_file_to_bunny, args=(dropbox_link, file_name))
    thread.start()

    # 🔁 Return immediately
    return jsonify({"status": "processing", "filename": file_name}), 202

@app.route("/bunny-status-check", methods=["GET"])
def bunny_status_check():
    filename = request.args.get("filename")
    if not filename:
        return jsonify({"error": "Missing filename parameter"}), 400

    if not os.path.exists(BUNNY_STATUS_FILE):
        return jsonify({"error": "No status file found"}), 404

    with open(BUNNY_STATUS_FILE, "r") as f:
        status = json.load(f)

    cdn_url = status.get(filename)
    if cdn_url:
        return jsonify({"cdn_url": cdn_url}), 200
    else:
        return jsonify({"error": "CDN URL not found"}), 404

@app.route("/", methods=["GET"])
def home():
    return "Bunny Async Uploader is live!", 200
