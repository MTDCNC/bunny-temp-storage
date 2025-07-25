from flask import Flask, request, jsonify
import requests
from urllib.parse import urlparse, unquote

app = Flask(__name__)

DROPBOX_ACCESS_TOKEN = "sl.u.AF0pHoVWDdhLnP3feG_MrzetFPziDONTC65BdhAYf-8ydJv0X8T3KdE3VmYnEiklupbq7aH04j9ikGAaADd3rQBq71ydSbAPxtx7a-uIsOtU-U_20NWNLHfxyOiyhkjiZwawrxeTZNen94IFqLJTwA3K21EHu2lrEfUhOJ6gG0B8zz3jkEZNxcdQkI2kEms7C1Qe-b3nqCd6sJThOr_q094v-_T6M1SrQz_UC9DcCCBeMefknMFnHFJFXL8UOrLTYKBDKLEa0MMqxZg7JiBHIRnm5_cMi9-ypHA8LagDWTjBpY09yIjRkt3uFHolrcabh5bEHMJUo6Dk3Xgb6oilBXAnzyGKIlXxVyMC70QTrDNCKwRwjzr7ir2NrWqpnFImMEjhWDUnVaUpnn8U3lsMa6_RClple-95mug-5JT2hgUDwOyUZM9RaXJRLKShxdkadv9Vh9IDWSGDrCpbY-jDuyq2fH5Ovon1l2oYzwevsEeQ4XR82WtBiU3ppmKxBeNgDHpAOopguwD1JJZCCwITbP03Ybfrf_WP1O2XnnS2qB1X-fCzE49iXWPrVO7afdrp9-mWnQLDsDoZf_OkYKWn7UR6-UjhmZLwHGvwPvDu0J2eygGkZMxnACHUDWwQTrrXAmO7F0ETWRwks8ZkL3HUYd7j6EDpfZmSyfEc5wpTLn_Xqugr5Mab1Umb1HW2HltG7jOSCl2xNHzFKP2sRMpAetQSXAgKvhK8xikCtukBTAF02uXR9SQSRXVJTvM_E-vEjZgRXRW0NhosVXRd2_R9UbhVEpXsWwJ5oOqm23lIZ46PofXQZOKjoOTK3DvQynPx9qTagFfAM4HUeW-VZlvPWc6wV_zlRSRKKNDVXFB90Cck_E6ZZd31ymT5Rfn6p2Edra8kIuDZmyFBK2IpJio6JzvqLvi0z6qU2yRfECP1dZorXQM7-5A4a8Ex8vi8CY8i-zoXLmOkLV-ELy7CO3L2WY8-fCbSgMvPrwiP1w4AB0EHdL2aH5Nktxn97KL89G--LVfVPvRSTpLoYavpJtmvWR_MiNbKgqGTBbT9lYA1S3dGLwd9W9DhwL4AnKpN0p9GQzDGbWJtQf11ug9zK1naXV06adfAa_SpEh2yeo4Qcxy0eAuvdBDIEMdmiAYLPtgzEkyIPInnpKpLIKNby6vUehRPkat2uY_gwyrZRISAauZ8kGpc827Juwvw5pB7piQaFonGyXhOsHFmI0rHwIGEWKBjolrI4rBrLx0oMkRfFgKu4Xc5FiGdPlNAFUhyY2LbZJcR1PUNnQtQIsLwZVFFNXM9_oR1pZejOwNwmrBA1qMZJlzqpdYYWApwkuaoVdB3572cQgEFP6_TlfPUrqXCJG7MiHjZqcbZ7G6_WTaxdeecOA"
BUNNY_API_KEY = "4d1223b1-d399-462e-97f6e0a7f9c8-7c8f-4767"
BUNNY_ZONE_NAME = "zapier-temp-files"
CDN_PREFIX = "https://zapier-temp-cdn.b-cdn.net"

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
        # 1. Download from Dropbox
        dropbox_headers = {
            "Authorization": f"Bearer {DROPBOX_ACCESS_TOKEN}",
            "Dropbox-API-Arg": f'{{"url": "{dropbox_link}"}}'            
        }

        print("🔍 Dropbox Header Preview:")
        print(f"Authorization: Bearer {DROPBOX_ACCESS_TOKEN[:8]}...")  # Redacted for safety
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
