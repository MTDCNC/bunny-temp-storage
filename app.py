from flask import Flask, request, jsonify
import requests
import os
from urllib.parse import urlparse, unquote

app = Flask(__name__)

BUNNY_API_KEY = "4d1223b1-d399-462e-97f6e0a7f9c8-7c8f-4767"
BUNNY_ZONE_NAME = "zapier-temp-files"
CDN_PREFIX = "https://zapier-temp-cdn.b-cdn.net"

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

@app.route("/upload-to-bunny", methods=["POST"])
def upload_to_bunny():
    data = request.json
    dropbox_link = data.get("dropbox_shared_link")

    if not dropbox_link:
        return jsonify({"error": "Missing Dropbox shared link"}), 400

    # Extract file name
    parsed = urlparse(dropbox_link)
    file_name = unquote(parsed.path.split('/')[-1])
    print(f"📥 Starting upload for file: {file_name}")

    try:
        # 🔑 Get fresh Dropbox token
        access_token = get_dropbox_access_token()

        # 1. Download from Dropbox
        dropbox_headers = {
            "Authorization": f"Bearer {access_token}",
            "Dropbox-API-Arg": f'{{"url": "{dropbox_link}"}}'
        }

        print("🔍 Dropbox Header Preview:")
        print(f"Authorization: Bearer {access_token[:8]}...")  # Redacted
        print("Dropbox-API-Arg:", dropbox_headers["Dropbox-API-Arg"])
        
        resp = requests.post(
            "https://content.dropboxapi.com/2/sharing/get_shared_link_file",
            headers=dropbox_headers, stream=True
        )
        resp.raise_for_status()
        print("✅ File downloaded from Dropbox.")

        # 2. Upload to Bunny
        bunny_url = f"https://uk.storage.bunnycdn.com/{BUNNY_ZONE_NAME}/{file_name}"
        print(f"📤 Uploading to Bunny: {bunny_url}")
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
        print(f"✅ File uploaded to Bunny. CDN: {cdn_url}")
        return jsonify({"cdn_url": cdn_url, "file_name": file_name}), 200

    except Exception as e:
        print(f"❌ Upload failed: {str(e)}")
        return jsonify({"error": "Upload failed", "details": str(e)}), 500

@app.route("/", methods=["GET"])
def home():
    return "Up & Running", 200
