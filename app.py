from flask import Flask, request, jsonify
import requests

app = Flask(__name__)

@app.route('/')
def home():
    return {"message": "Reddit fetch service running!"}

@app.route('/fetch-comments', methods=['POST'])
def fetch_comments():
    data = request.get_json()
    reddit_url = data.get('reddit_url')

    if not reddit_url:
        return jsonify({"error": "Missing reddit_url"}), 400

    # Reddit APIからコメント取得（簡易例）
    api_url = reddit_url + ".json"
    res = requests.get(api_url, headers={'User-agent': 'Mozilla/5.0'})
    thread_data = res.json()

    comments = []
    for c in thread_data[1]["data"]["children"]:
        body = c["data"].get("body")
        if body and len(body) < 400:
            comments.append(body)

    return jsonify({"comments": comments})
