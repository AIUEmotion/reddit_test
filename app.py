import requests
from flask import Flask, request, jsonify
import time
import traceback

app = Flask(__name__)

def extract_comments_recursive(comment_obj, comments_list, depth=0, max_depth=10):
    """再帰的にコメントを抽出する関数"""
    # 無限再帰を防ぐ
    if depth > max_depth:
        return
    
    try:
        # kindが't1'の場合のみコメント
        if comment_obj.get("kind") == "t1":
            data = comment_obj.get("data", {})
            body = data.get("body")
            
            # 削除されたコメントや空のコメントをスキップ
            if body and body not in ["[deleted]", "[removed]", ""]:
                comments_list.append({
                    "body": body,
                    "author": data.get("author", "unknown"),
                    "score": data.get("score", 0),
                    "created_utc": data.get("created_utc", 0)
                })
            
            # 返信がある場合は再帰的に処理
            replies = data.get("replies")
            if replies and isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                for reply in reply_children:
                    extract_comments_recursive(reply, comments_list, depth + 1, max_depth)
                    
    except Exception as e:
        # エラーを記録するが処理は継続
        app.logger.error(f"Error extracting comment at depth {depth}: {str(e)}")


@app.route("/fetch-comments", methods=["POST"])
def fetch_comments():
    debug_mode = False  # デバッグ時はTrueに変更
    
    try:
        # リクエストデータの取得
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        reddit_url = data.get("reddit_url")
        
        if not reddit_url:
            return jsonify({"error": "No reddit_url provided"}), 400
        
        # URLが投稿のURLか検証（/comments/が含まれているか）
        if "/comments/" not in reddit_url:
            return jsonify({
                "error": "Invalid URL format",
                "hint": "URL must be a specific Reddit post URL containing '/comments/'",
                "example": "https://www.reddit.com/r/soccer/comments/1oizosj/title/",
                "provided_url": reddit_url
            }), 400
        
        app.logger.info(f"Fetching comments from: {reddit_url}")
        
        # URLをold.reddit.comに変換（403エラー回避）
        reddit_url = reddit_url.replace("www.reddit.com", "old.reddit.com")
        if "reddit.com" in reddit_url and "old.reddit.com" not in reddit_url:
            reddit_url = reddit_url.replace("reddit.com", "old.reddit.com")
        
        # URLの正規化
        reddit_url = reddit_url.rstrip('/')
        if not reddit_url.endswith(".json"):
            reddit_url += ".json"
        
        app.logger.info(f"Normalized URL: {reddit_url}")
        
        # ブラウザを模倣したヘッダー
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9,ja;q=0.8",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1"
        }
        
        # 少し待機（連続リクエスト回避）
        time.sleep(0.5)
        
        # セッションを使用してクッキーを保持
        session = requests.Session()
        res = session.get(reddit_url, headers=headers, timeout=15, allow_redirects=True)
        
        app.logger.info(f"Response status: {res.status_code}")
        
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
                "hint": "Reddit may be blocking automated requests."
            }), 403
        
        if res.status_code != 200:
            return jsonify({
                "error": f"Failed to fetch data from Reddit",
                "status_code": res.status_code,
                "url": reddit_url,
                "response_preview": res.text[:300] if res.text else "No content"
            }), res.status_code
        
        # JSONパース
        try:
            thread_data = res.json()
            app.logger.info(f"Parsed JSON successfully. Type: {type(thread_data)}")
            
            # デバッグ: 構造を確認
            if isinstance(thread_data, list):
                app.logger.info(f"List length: {len(thread_data)}")
                for i, item in enumerate(thread_data[:3]):  # 最初の3つだけ
                    app.logger.info(f"Item {i} type: {type(item)}, keys: {item.keys() if isinstance(item, dict) else 'N/A'}")
            
        except Exception as e:
            app.logger.error(f"JSON parse error: {str(e)}")
            return jsonify({
                "error": "Invalid JSON response from Reddit",
                "details": str(e),
                "content_preview": res.text[:300] if res.text else "No content"
            }), 500
        
        # データ構造の検証
        if not isinstance(thread_data, list):
            error_info = {
                "error": "Unexpected Reddit response format - not a list",
                "type": str(type(thread_data)),
                "content_preview": str(thread_data)[:500]
            }
            if debug_mode:
                error_info["full_response"] = thread_data
            return jsonify(error_info), 500
        
        if len(thread_data) < 2:
            error_info = {
                "error": "Unexpected Reddit response format - list too short",
                "length": len(thread_data),
                "content_preview": str(thread_data)[:500]
            }
            if debug_mode:
                error_info["full_response"] = thread_data
            return jsonify(error_info), 500
        
        # コメント抽出
        comments = []
        
        # 安全にデータを取得
        if not isinstance(thread_data[1], dict):
            return jsonify({
                "error": "Invalid comment data structure",
                "content_preview": str(thread_data[1])[:300]
            }), 500
        
        comment_data = thread_data[1].get("data")
        if not comment_data or not isinstance(comment_data, dict):
            return jsonify({
                "error": "Missing or invalid 'data' field in comments",
                "content_preview": str(thread_data[1])[:300]
            }), 500
        
        comment_children = comment_data.get("children", [])
        
        app.logger.info(f"Found {len(comment_children)} top-level comments")
        
        for child in comment_children:
            extract_comments_recursive(child, comments)
        
        app.logger.info(f"Extracted {len(comments)} total comments")
        
        return jsonify({
            "success": True,
            "comments": comments,
            "total_count": len(comments),
            "url_used": reddit_url
        }), 200
    
    except requests.exceptions.Timeout:
        app.logger.error("Request timed out")
        return jsonify({"error": "Request timed out"}), 504
    
    except requests.exceptions.RequestException as e:
        app.logger.error(f"Network error: {str(e)}")
        return jsonify({
            "error": "Network error",
            "details": str(e)
        }), 500
    
    except Exception as e:
        # 予期しないエラーをキャッチ
        app.logger.error(f"Unexpected error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "Internal server error",
            "details": str(e),
            "traceback": traceback.format_exc()
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    """ヘルスチェック用エンドポイント"""
    return jsonify({"status": "ok"}), 200


if __name__ == "__main__":
    app.run(debug=True, port=5000)