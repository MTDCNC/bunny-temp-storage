from flask import Flask, request, jsonify
import requests
from urllib.parse import urlparse, unquote

app = Flask(__name__)

DROPBOX_ACCESS_TOKEN = "sl.u.AF3jw8OEuZGENDyprYonRjfrREsB2wpEKSZMrzmwnr9lakNy14mF9o3DqCrZJxEcdNGILvMtKB7c7gDiS8sAbreEs0uvRTXO7VYAV6gDb0hZqFye1UsOhGRwOVbdK0lwyB3fKWeH9Pu72OPxd6CMU_eDiZrJCydZwEUO3leONJ45PZnWzaNn2aP_BlBCRohbRddQUb7Q8xvhl_NvpwXpOtGOiRO2onxrFKEs7mE_oIB4P7pK6FRpiVwQMczmy7H0QT31VPjEhpuMcYidV70TtbW-oVmGo1eucqBoRMczBhyA5TWcj-X_QUuQ2AiqjlhoHI-ua1-_KyHIlmTOewNDUKN56LdyGuFNgkij50ryEZvx5iy1VHLUlPsMFOS2GY2XWcd1v7hlwQWDsRtH_K2eXdBAUCGN5fu03n8OJZD5-wbzT26FIIMqOKKhzh7r9yus6SsJqsqWyHygetacOScX2mqsU19Q115MSQqI_rZNcjKYvPnUv663pERVou--Nyc2sbXpTPez3aiBswEblL4naarJQI3vXrr1bYU1kHuPYIktFOEqEmSyZcprSQw1x8S3VsWacrSywmtUxOdE5trCwwAmptqwiPAh1LrMjlwFIaVT2F3rrSWHry7rYUjXnsI2eqcKWh93svZyTS1H6LAFIx6K6sxFSigvKBoFJixz2blwykjEy8G1oxYDp66pnK0YDuLmqE2bzGkb9qVQD0b4JhKU3dWmq3BhrCF846J6B4U_p0YlCvgcR_4bQB7k_lxIuHRLSyp0WgwHvy31IplG551l09hbArm3XQ3yJdJwwGn0vRFq24UUrQ8LfNlQXfIk5D8zX9RnY20eMfThnBSxaCHd2UjczXqzW_Mq2l_3GXN0V1uFLx7MlvmMVtlXPvyqexq9LDZTy7Q1mYxqpKINU2MlRNrzLot7luMCDkEIglJlt3XP5p6kFCpPFe88gQfdC5xUsNv9GZQ_O3HoY9mjqNhxF6w43WnFHO53TrF5bwqRAl-2n9RwAJ5mb6ncdyDSGCtWzGeMSEdHPUEQWeKCXlHvGbe7MR1KAanVW2AnXSbSKhfbDxNKgWTHiRGICEtsfGBrttkCK1mP0RvJr5QrIHjuEdWJ34tg17adDIXez2fj0Jm0VGRjarY6opA5aP2GOiFDAEVBJw-PO64L2c4dXEhPJpAqsf8CL1Jjn4X0E5vg8js-KrF7_Tl0vlQblr8hUIznoISdCZ2O-ej7gL-_tUtBr-bmOnCDD7aKhN-vMrD47JXzJvfXvVU4ziHJw-5hwfUjvt1lXf2TBKFTC7v7LBsTT8Qa-HwXvD3ncOIQXH0e9X8lbAjqsWiP9o4g-K1q7Lu98Lqgj-LVgRsJVbwFJ1nRObrVep5Vi0Ybsrp85XyJTw"
BUNNY_API_KEY = "4d1223b1-d399-462e-97f6e0a7f9c8-7c8f-4767"
BUNNY_ZONE_NAME = "zapier-temp-files"
CDN_PREFIX = "https://zapier-temp-cdn.b-cdn.net"

@app.route("/upload-to-bunny", methods=["POST"])
def upload_to_bunny():
    data = request.json
    dropbox_link = data.get("dropbox_shared_link")

    if not dropbox_link:
        return jsonify({"error": "Missing Dropbox shared link"}), 400

    # Extract file name from URL
    parsed = urlparse(dropbox_link)
    file_name = unquote(parsed.path.split('/')[-1])

    # 1. Download from Dropbox API (shared link streaming)
    dropbox_headers = {
        "Authorization": f"Bearer {DROPBOX_ACCESS_TOKEN}",
        "Dropbox-API-Arg": f'{{"url": "{dropbox_link}"}}'
    }
    resp = requests.post("https://content.dropboxapi.com/2/sharing/get_shared_link_file",
                         headers=dropbox_headers, stream=True)
    resp.raise_for_status()

    # 2. Upload to Bunny
    bunny_url = f"https://uk.storage.bunnycdn.com/{BUNNY_ZONE_NAME}/{file_name}"
    bunny_headers = {
        "AccessKey": BUNNY_API_KEY,
        "Content-Type": "application/octet-stream"
    }
    bunny_resp = requests.put(bunny_url, data=resp.iter_content(chunk_size=1048576), headers=bunny_headers)
    bunny_resp.raise_for_status()

    cdn_url = f"{CDN_PREFIX}/{file_name}"
    return jsonify({"cdn_url": cdn_url, "file_name": file_name}), 200

@app.route("/", methods=["GET"])
def home():
    return "Up & Running", 200
