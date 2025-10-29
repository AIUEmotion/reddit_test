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
            reddit_url = reddit_url + ".json"
        else:
            reddit_url = reddit_url + "/.json"

    # Reddit API呼び出し（User-Agentを明示）
    headers = {"User-Agent": "Mozilla/5.0 (compatible; RedditFetcher/1.0)"}
    res = requests.get(reddit_url, headers=headers)

    # 応答チェック
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
            "text": res.text[:500]  # デバッグ用に先頭500文字を返す
        }), 500

    # コメント抽出（サンプル）
    comments = []
    for child in thread_data[1]["data"]["children"]:
        body = child["data"].get("body")
        if body:
            comments.append(body)

    return jsonify({"comments": comments})