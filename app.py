import requests
from flask import Flask, request, jsonify
import time

app = Flask(__name__)

def extract_comments_recursive(comment_obj, comments_list):
    """再帰的にコメントを抽出する関数"""
    try:
        # kindが't1'の場合のみコメント
        if comment_obj.get("kind") == "t1":
            data = comment_obj.get("data", {})
            body = data.get("body")
            
            # 削除されたコメントや空のコメントをスキップ
            if body and body not in ["[deleted]", "[removed]"]:
                comments_list.append({
                    "body": body,
                    "author": data.get("author"),
                    "score": data.get("score"),
                    "created_utc": data.get("created_utc")
                })
            
            # 返信がある場合は再帰的に処理
            replies = data.get("replies")
            if replies and isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                for reply in reply_children:
                    extract_comments_recursive(reply, comments_list)
                    
    except Exception as e:
        print(f"Error extracting comment: {e}")
        pass


@app.route("/fetch-comments", methods=["POST"])
def fetch_comments():
    data = request.json
    reddit_url = data.get("reddit_url")
    
    if not reddit_url:
        return jsonify({"error": "No reddit_url provided"}), 400
    
    # URLをold.reddit.comに変換（403エラー回避）
    reddit_url = reddit_url.replace("www.reddit.com", "old.reddit.com")
    reddit_url = reddit_url.replace("reddit.com", "old.reddit.com")
    
    # URLの正規化
    reddit_url = reddit_url.rstrip('/')
    if not reddit_url.endswith(".json"):
        reddit_url += ".json"
    
    # ブラウザを模倣したヘッダー
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "DNT": "1",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
        "Sec-Fetch-Dest": "document",
        "Sec-Fetch-Mode": "navigate",
        "Sec-Fetch-Site": "none",
        "Cache-Control": "max-age=0"
    }
    
    try:
        # 少し待機（連続リクエスト回避）
        time.sleep(0.5)
        
        # セッションを使用してクッキーを保持
        session = requests.Session()
        res = session.get(reddit_url, headers=headers, timeout=15, allow_redirects=True)
        
        # レート制限のチェック
        if res.status_code == 429:
            return jsonify({
                "error": "Rate limit exceeded. Please try again later.",
                "status_code": 429
            }), 429
        
        if res.status_code == 403:
            return jsonify({
                "error": "Access forbidden by Reddit. Try using old.reddit.com URL or wait before retrying.",
                "status_code": 403,
                "url": reddit_url,
                "hint": "Reddit may be blocking automated requests. Consider using Reddit's official API."
            }), 403
        
        if res.status_code != 200:
            return jsonify({
                "error": f"Failed to fetch data from Reddit",
                "status_code": res.status_code,
                "url": reddit_url
            }), res.status_code
            
    except requests.exceptions.Timeout:
        return jsonify({"error": "Request timed out"}), 504
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Network error",
            "details": str(e)
        }), 500
    
    # JSONパース
    try:
        thread_data = res.json()
    except Exception as e:
        return jsonify({
            "error": "Invalid JSON response from Reddit",
            "details": str(e),
            "content_preview": res.text[:200]
        }), 500
    
    # データ構造の検証
    if not isinstance(thread_data, list) or len(thread_data) < 2:
        return jsonify({
            "error": "Unexpected Reddit response format",
            "hint": "Make sure the URL is a valid Reddit post URL"
        }), 500
    
    # コメント抽出
    comments = []
    try:
        comment_children = thread_data[1].get("data", {}).get("children", [])
        
        for child in comment_children:
            extract_comments_recursive(child, comments)
            
    except Exception as e:
        return jsonify({
            "error": "Failed to parse comments",
            "details": str(e)
        }), 500
    
    return jsonify({
        "comments": comments,
        "total_count": len(comments),
        "url_used": reddit_url
    })


if __name__ == "__main__":
    app.run(debug=True, port=5000)