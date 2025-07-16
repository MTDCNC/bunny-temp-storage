from flask import Flask, request, jsonify
import requests
from urllib.parse import urlparse, unquote

app = Flask(__name__)

BUNNY_API_KEY = "4d1223b1-d399-462e-97f6e0a7f9c8-7c8f-4767"
BUNNY_ZONE_NAME = "zapier-temp-files"
CDN_PREFIX = "https://zapier-temp-cdn.b-cdn.net"

@app.route("/upload-to-bunny", methods=["POST"])
def upload_to_bunny():
    data = request.json
    dropbox_url = data.get("dropbox_url")
    if not dropbox_url:
        return jsonify({"error": "dropbox_url required"}), 400

    parsed_url = urlparse(dropbox_url)
    file_name = unquote(parsed_url.path.split('/')[-1])
    dropbox_direct = dropbox_url.replace("?dl=0", "?raw=1")

    with requests.get(dropbox_direct, stream=True) as resp:
        resp.raise_for_status()

        bunny_url = f"https://uk.storage.bunnycdn.com/{BUNNY_ZONE_NAME}/{file_name}"
        headers = {
            "AccessKey": BUNNY_API_KEY,
            "Content-Type": "application/octet-stream"
        }
        upload_resp = requests.put(bunny_url, data=resp.iter_content(chunk_size=1048576), headers=headers)
        upload_resp.raise_for_status()

    cdn_url = f"{CDN_PREFIX}/{file_name}"
    return jsonify({"cdn_url": cdn_url, "file_name": file_name})

@app.route("/", methods=["GET"])
def home():
    return "Ready", 200
