import requests
from flask import Flask, request, jsonify

app = Flask(__name__)

@app.route("/fetch-comments", methods=["POST"])
def fetch_comments():
    data = request.json
    reddit_url = data.get("reddit_url")

    if not reddit_url:
        return jsonify({"error": "No reddit_url provided"}), 400

    # RedditのURLに .json を強制的に追加
    if not reddit_url.endswith(".json"):
        if reddit_url.endswith("/"):
            reddit_url += ".json"
        else:
            reddit_url += "/.json"

    headers = {"User-Agent": "Mozilla/5.0 (compatible; RedditFetcher/1.0)"}
    res = requests.get(reddit_url, headers=headers)

    if res.status_code != 200:
        return jsonify({
            "error": f"Failed to fetch data from Reddit (status {res.status_code})",
            "url": reddit_url
        }), 500

    try:
        thread_data = res.json()
    except Exception as e:
        return jsonify({
            "error": "Invalid JSON response from Reddit",
            "details": str(e),
            "text": res.text[:500]
        }), 500

    # 構造チェック
    if not isinstance(thread_data, list) or len(thread_data) < 2:
        return jsonify({
            "error": "Unexpected Reddit response format",
            "type": str(type(thread_data)),
            "keys": list(thread_data.keys()) if isinstance(thread_data, dict) else "N/A",
            "sample": str(thread_data)[:500]
        }), 500

    # コメント抽出
    comments = []
    try:
        for child in thread_data[1]["data"]["children"]:
            body = child["data"].get("body")
            if body:
                comments.append(body)
    except Exception as e:
        return jsonify({
            "error": "Failed to parse comments",
            "details": str(e),
            "sample": str(thread_data[1])[:500]
        }), 500

    return jsonify({"comments": comments})
