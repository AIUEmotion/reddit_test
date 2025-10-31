import requests
from flask import Flask, request, jsonify
import traceback
import random
import time

app = Flask(__name__)

# 無料プロキシリスト（定期的に更新が必要）
FREE_PROXIES = [
    # これらは例です。実際には https://free-proxy-list.net/ などから取得
    # "http://proxy1:port",
    # "http://proxy2:port",
]

def extract_comments_recursive(comment_obj, comments_list, depth=0, max_depth=10):
    """再帰的にコメントを抽出"""
    if depth > max_depth:
        return
    
    try:
        if comment_obj.get("kind") == "t1":
            data = comment_obj.get("data", {})
            body = data.get("body")
            
            if body and body not in ["[deleted]", "[removed]", ""]:
                comments_list.append({
                    "body": body,
                    "author": data.get("author", "unknown"),
                    "score": data.get("score", 0),
                    "created_utc": data.get("created_utc", 0)
                })
            
            replies = data.get("replies")
            if replies and isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                for reply in reply_children:
                    extract_comments_recursive(reply, comments_list, depth + 1, max_depth)
                    
    except Exception as e:
        app.logger.error(f"Error extracting comment: {str(e)}")


def fetch_with_fallback(reddit_url):
    """複数の方法でフォールバック取得"""
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
        "Accept": "application/json",
        "Accept-Language": "en-US,en;q=0.9",
    }
    
    # 方法1: old.reddit.com で直接試行
    try:
        app.logger.info("Trying old.reddit.com...")
        res = requests.get(reddit_url, headers=headers, timeout=10)
        if res.status_code == 200:
            return res.json()
    except Exception as e:
        app.logger.error(f"old.reddit.com failed: {str(e)}")
    
    # 方法2: User-Agentをランダム化して再試行
    user_agents = [
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
        "Mozilla/5.0 (iPhone; CPU iPhone OS 14_0 like Mac OS X) AppleWebKit/605.1.15",
    ]
    
    for ua in user_agents:
        try:
            time.sleep(1)  # レート制限回避
            app.logger.info(f"Trying with different UA: {ua[:50]}...")
            headers["User-Agent"] = ua
            res = requests.get(reddit_url, headers=headers, timeout=10)
            if res.status_code == 200:
                return res.json()
        except Exception as e:
            continue
    
    # 方法3: 無料プロキシ経由（設定されている場合）
    if FREE_PROXIES:
        for proxy_url in random.sample(FREE_PROXIES, min(3, len(FREE_PROXIES))):
            try:
                time.sleep(1)
                app.logger.info(f"Trying with proxy: {proxy_url}")
                proxies = {"http": proxy_url, "https": proxy_url}
                res = requests.get(reddit_url, headers=headers, proxies=proxies, timeout=10)
                if res.status_code == 200:
                    return res.json()
            except Exception as e:
                continue
    
    # 全て失敗
    raise Exception("All fetch methods failed")


@app.route("/fetch-comments", methods=["POST"])
def fetch_comments():
    try:
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        reddit_url = data.get("reddit_url")
        
        if not reddit_url:
            return jsonify({"error": "No reddit_url provided"}), 400
        
        if "/comments/" not in reddit_url:
            return jsonify({
                "error": "Invalid URL format",
                "hint": "URL must contain '/comments/'"
            }), 400
        
        # URLをold.reddit.comに変換
        reddit_url = reddit_url.replace("www.reddit.com", "old.reddit.com")
        if "reddit.com" in reddit_url and "old.reddit.com" not in reddit_url:
            reddit_url = reddit_url.replace("reddit.com", "old.reddit.com")
        
        reddit_url = reddit_url.rstrip('/')
        if not reddit_url.endswith(".json"):
            reddit_url += ".json"
        
        app.logger.info(f"Fetching: {reddit_url}")
        
        # フォールバック取得
        thread_data = fetch_with_fallback(reddit_url)
        
        # データ検証
        if not isinstance(thread_data, list) or len(thread_data) < 2:
            return jsonify({
                "error": "Invalid Reddit response format"
            }), 500
        
        # コメント抽出
        comments = []
        comment_children = thread_data[1].get("data", {}).get("children", [])
        
        for child in comment_children:
            extract_comments_recursive(child, comments)
        
        return jsonify({
            "success": True,
            "comments": comments,
            "total_count": len(comments)
        }), 200
        
    except Exception as e:
        app.logger.error(f"Error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "Failed to fetch comments",
            "details": str(e),
            "hint": "All methods failed. Consider using Reddit API or waiting."
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)