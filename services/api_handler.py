import logging
import requests

from config import key_manager, TIMEOUT

API_URL = "https://tiktok-video-no-watermark2.p.rapidapi.com/"


def fetch_tiktok_data(video_url):
    """
    Fetch TikTok Video / Photo data with automatic API key rotation.
    """

    total_keys = len(key_manager.keys)

    if total_keys == 0:
        logging.error("No API Keys configured.")
        return {
            "success": False,
            "error": "Server configuration error."
        }

    for _ in range(total_keys):

        key_obj = key_manager.get_active_key()

        if key_obj is None:
            logging.error("All API Keys exhausted.")
            return {
                "success": False,
                "error": "All API keys have reached their usage limit. Please try again later."
            }

        current_key = key_obj["val"]

        headers = {
            "x-rapidapi-host": "tiktok-video-no-watermark2.p.rapidapi.com",
            "x-rapidapi-key": current_key,
            "Content-Type": "application/x-www-form-urlencoded"
        }

        try:

            response = requests.post(
                API_URL,
                headers=headers,
                data={
                    "url": video_url,
                    "hd": "1"
                },
                timeout=TIMEOUT
            )

            # API Limit Reached
            if response.status_code == 429:
                logging.warning(
                    f"API quota exceeded: {current_key[:6]}******"
                )
                key_manager.mark_failed(current_key)
                continue

            # Temporary Server Error
            if response.status_code >= 500:
                logging.warning(
                    f"RapidAPI Server Error: {response.status_code}"
                )
                continue

            # Other HTTP Errors
            if response.status_code != 200:
                logging.warning(
                    f"Unexpected HTTP Status: {response.status_code}"
                )
                continue

            result = response.json()

            # Success
            if result.get("code") == 0:

                key_manager.reset_key(current_key)

                data = result.get("data", {})

                # Photo Mode
                if data.get("images"):

                    return {
                        "success": True,
                        "is_photo": True,
                        "images": data.get("images", []),
                        "title": data.get("title") or "TikTok Photos",
                        "author": (
                            data.get("author", {})
                            .get("unique_id", "Unknown")
                        )
                    }

                # Video Mode
                return {
                    "success": True,
                    "is_photo": False,
                    "hd_url": data.get("hdplay") or data.get("play"),
                    "sd_url": data.get("play"),
                    "thumbnail": data.get("cover"),
                    "title": data.get("title") or "Untitled Video",
                    "author": (
                        data.get("author", {})
                        .get("unique_id", "Unknown")
                    ),
                    "duration": data.get("duration", 0)
                }

            # API returned error
            error_msg = result.get("msg", "").lower()

            if "private" in error_msg:
                return {
                    "success": False,
                    "error": "This TikTok video is private."
                }

            if "not found" in error_msg:
                return {
                    "success": False,
                    "error": "Video not found."
                }

            return {
                "success": False,
                "error": "Unable to process this TikTok link."
            }

        except requests.exceptions.Timeout:
            logging.error("RapidAPI request timeout.")
            continue

        except requests.exceptions.ConnectionError:
            logging.error("Connection error while contacting RapidAPI.")
            continue

        except Exception as e:
            logging.exception(f"Unexpected Error: {e}")
            continue

    return {
        "success": False,
        "error": "Service is temporarily unavailable. Please try again later."
    }
