from flask import Flask, render_template, request, jsonify
import os

from services.api_handler import fetch_tiktok_data
from utils.validators import is_valid_tiktok_url
from services.logger import logger

app = Flask(
    __name__,
    template_folder="templates",
    static_folder="static"
)


@app.route("/")
def home():
    """Render Home Page"""
    return render_template("index.html")


@app.route("/health")
def health():
    """Health Check Endpoint"""
    return jsonify({
        "status": "online",
        "service": "Tik2BD",
        "message": "Server is running successfully."
    })


@app.route("/download", methods=["POST"])
def download():
    """Main Download API"""

    try:

        if not request.is_json:
            return jsonify({
                "success": False,
                "error": "Invalid request format."
            }), 400

        data = request.get_json()

        if not data:
            return jsonify({
                "success": False,
                "error": "Request body is empty."
            }), 400

        video_url = (data.get("url") or "").strip()

        if not video_url:
            return jsonify({
                "success": False,
                "error": "TikTok URL is required."
            }), 400

        if not is_valid_tiktok_url(video_url):
            logger.warning(f"Invalid URL: {video_url}")

            return jsonify({
                "success": False,
                "error": "Invalid TikTok URL provided."
            }), 400

        logger.info(f"Processing: {video_url}")

        result = fetch_tiktok_data(video_url)

        if result.get("success"):

            logger.info("Download completed successfully.")

            return jsonify(result), 200

        logger.warning(result.get("error"))

        return jsonify(result), 400

    except Exception as e:

        logger.exception(f"Unexpected Error: {e}")

        return jsonify({
            "success": False,
            "error": "Internal server error."
        }), 500


@app.errorhandler(404)
def not_found(error):
    return jsonify({
        "success": False,
        "error": "Page not found."
    }), 404


@app.errorhandler(500)
def internal_error(error):
    return jsonify({
        "success": False,
        "error": "Internal server error."
    }), 500


if __name__ == "__main__":

    port = int(os.environ.get("PORT", 5000))

    app.run(
        host="0.0.0.0",
        port=port
    )
