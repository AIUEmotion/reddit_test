import requests
from flask import Flask, request, jsonify
import traceback
import os

app = Flask(__name__)

# 設定（環境変数から取得、デフォルト値あり）
MAX_COMMENTS = int(os.environ.get("MAX_COMMENTS", 100))
MIN_SCORE = int(os.environ.get("MIN_SCORE", 5))
MAX_COMMENT_LENGTH = int(os.environ.get("MAX_COMMENT_LENGTH", 500))

def extract_comments_recursive(comment_obj, comments_list, depth=0, max_depth=10):
    """再帰的にコメントを抽出"""
    if depth > max_depth:
        return
    
    try:
        if comment_obj.get("kind") == "t1":
            data = comment_obj.get("data", {})
            body = data.get("body")
            score = data.get("score", 0)
            
            # 削除済み、空、長すぎるコメントをスキップ
            if (body and 
                body not in ["[deleted]", "[removed]", ""] and 
                len(body) <= MAX_COMMENT_LENGTH):
                
                comments_list.append({
                    "body": body,
                    "author": data.get("author", "unknown"),
                    "score": score,
                    "created_utc": data.get("created_utc", 0),
                    "id": data.get("id", ""),
                    "permalink": data.get("permalink", "")
                })
            
            # 返信を再帰的に処理
            replies = data.get("replies")
            if replies and isinstance(replies, dict):
                reply_children = replies.get("data", {}).get("children", [])
                for reply in reply_children:
                    extract_comments_recursive(reply, comments_list, depth + 1, max_depth)
                    
    except Exception as e:
        app.logger.error(f"Error extracting comment at depth {depth}: {str(e)}")


@app.route("/fetch-comments", methods=["POST"])
def fetch_comments():
    """
    Redditから人気コメントを取得してMake/スプレッドシート用に整形
    
    リクエストボディ例:
    {
        "reddit_url": "https://www.reddit.com/r/soccer/comments/xxx/title/",
        "max_comments": 100,  // オプション
        "min_score": 5        // オプション
    }
    
    レスポンス例:
    {
        "success": true,
        "post_title": "投稿タイトル",
        "post_url": "https://...",
        "comments": [
            {
                "rank": 1,
                "score": 1500,
                "author": "username",
                "body": "コメント本文",
                "comment_id": "abc123",
                ...
            }
        ]
    }
    """
    try:
        # リクエストデータ取得
        data = request.json
        if not data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        reddit_url = data.get("reddit_url")
        max_comments = data.get("max_comments", MAX_COMMENTS)
        min_score = data.get("min_score", MIN_SCORE)
        
        if not reddit_url:
            return jsonify({"error": "No reddit_url provided"}), 400
        
        if "/comments/" not in reddit_url:
            return jsonify({
                "error": "Invalid URL format",
                "hint": "URL must contain '/comments/' (e.g., https://reddit.com/r/subreddit/comments/post_id/title/)"
            }), 400
        
        app.logger.info(f"Processing URL: {reddit_url}")
        
        # URLをold.reddit.comに変換（403エラー回避）
        original_url = reddit_url
        reddit_url = reddit_url.replace("www.reddit.com", "old.reddit.com")
        if "reddit.com" in reddit_url and "old.reddit.com" not in reddit_url:
            reddit_url = reddit_url.replace("reddit.com", "old.reddit.com")
        
        # .jsonを追加
        reddit_url = reddit_url.rstrip('/')
        if not reddit_url.endswith(".json"):
            reddit_url += ".json"
        
        app.logger.info(f"Fetching from: {reddit_url}")
        
        # Redditにリクエスト
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Accept": "application/json, text/html",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "Referer": "https://www.google.com/",
            "DNT": "1",
            "Connection": "keep-alive"
        }
        
        res = requests.get(reddit_url, headers=headers, timeout=15, allow_redirects=True)
        
        # エラーハンドリング
        if res.status_code == 403:
            return jsonify({
                "error": "Access forbidden by Reddit",
                "status_code": 403,
                "hint": "Reddit is blocking automated requests. This happens sometimes. Try:\n1. Wait a few minutes and retry\n2. Use a different network\n3. Consider using Reddit API with authentication"
            }), 403
        
        if res.status_code == 404:
            return jsonify({
                "error": "Reddit post not found",
                "status_code": 404,
                "url": original_url
            }), 404
        
        if res.status_code != 200:
            return jsonify({
                "error": f"Reddit returned status {res.status_code}",
                "status_code": res.status_code,
                "url": reddit_url
            }), res.status_code
        
        # JSONパース
        try:
            thread_data = res.json()
        except Exception as e:
            return jsonify({
                "error": "Invalid JSON response from Reddit",
                "details": str(e)
            }), 500
        
        # データ検証
        if not isinstance(thread_data, list) or len(thread_data) < 2:
            return jsonify({
                "error": "Unexpected Reddit response format",
                "hint": "The response doesn't match expected Reddit JSON structure"
            }), 500
        
        # 投稿情報取得
        try:
            post_data = thread_data[0]['data']['children'][0]['data']
            post_title = post_data.get('title', '')
            post_author = post_data.get('author', '')
            post_score = post_data.get('score', 0)
            post_created = post_data.get('created_utc', 0)
            post_url = original_url.replace('.json', '')
        except (KeyError, IndexError) as e:
            return jsonify({
                "error": "Failed to extract post information",
                "details": str(e)
            }), 500
        
        app.logger.info(f"Post: '{post_title}' by {post_author}")
        
        # コメント抽出
        all_comments = []
        try:
            comment_children = thread_data[1].get("data", {}).get("children", [])
            
            for child in comment_children:
                extract_comments_recursive(child, all_comments)
                
        except Exception as e:
            return jsonify({
                "error": "Failed to extract comments",
                "details": str(e)
            }), 500
        
        app.logger.info(f"Extracted {len(all_comments)} total comments")
        
        # スコアでフィルタリング＆ソート
        filtered = [c for c in all_comments if c['score'] >= min_score]
        sorted_comments = sorted(filtered, key=lambda x: x['score'], reverse=True)
        top_comments = sorted_comments[:max_comments]
        
        app.logger.info(f"After filtering (score>={min_score}): {len(filtered)} comments")
        app.logger.info(f"Returning top {len(top_comments)} comments")
        
        if len(top_comments) == 0:
            return jsonify({
                "error": "No comments found matching criteria",
                "hint": f"Try lowering min_score (current: {min_score})",
                "total_comments": len(all_comments),
                "filtered_comments": len(filtered)
            }), 400
        
        # Make/スプレッドシート用に整形
        comments_for_sheet = []
        for i, comment in enumerate(top_comments, 1):
            comments_for_sheet.append({
                "rank": i,
                "score": comment['score'],
                "author": comment['author'],
                "body": comment['body'],
                "comment_id": comment['id'],
                "comment_url": f"https://reddit.com{comment['permalink']}" if comment['permalink'] else "",
                "character_count": len(comment['body']),
                "word_count": len(comment['body'].split()),
                "post_title": post_title,
                "post_url": post_url,
                "post_author": post_author
            })
        
        # ChatGPTに渡しやすいテキスト形式も生成
        comments_text = "\n\n---\n\n".join([
            f"【コメント {i+1}】（スコア: {c['score']}）\n"
            f"投稿者: {c['author']}\n"
            f"{c['body']}"
            for i, c in enumerate(top_comments)
        ])
        
        # レスポンス
        return jsonify({
            "success": True,
            "post_info": {
                "title": post_title,
                "author": post_author,
                "score": post_score,
                "url": post_url,
                "created_utc": post_created
            },
            "statistics": {
                "total_comments_found": len(all_comments),
                "comments_after_filter": len(filtered),
                "comments_returned": len(comments_for_sheet),
                "top_score": top_comments[0]['score'] if top_comments else 0,
                "min_score_used": min_score,
                "max_comments_limit": max_comments
            },
            "comments": comments_for_sheet,  # JSON配列形式
            "comments_text": comments_text,   # ChatGPT用のテキスト形式
            "comments_json_string": str(comments_for_sheet)  # スプレッドシート保存用
        }), 200
        
    except requests.exceptions.Timeout:
        return jsonify({
            "error": "Request timed out",
            "hint": "Reddit took too long to respond. Try again."
        }), 504
        
    except requests.exceptions.RequestException as e:
        return jsonify({
            "error": "Network error",
            "details": str(e)
        }), 500
        
    except Exception as e:
        app.logger.error(f"Unexpected error: {str(e)}")
        app.logger.error(traceback.format_exc())
        return jsonify({
            "error": "Internal server error",
            "details": str(e),
            "traceback": traceback.format_exc() if app.debug else None
        }), 500


@app.route("/health", methods=["GET"])
def health_check():
    """ヘルスチェック用エンドポイント"""
    return jsonify({
        "status": "ok",
        "service": "Reddit Comment Fetcher",
        "version": "1.0.0"
    }), 200


@app.route("/", methods=["GET"])
def index():
    """API情報"""
    return jsonify({
        "service": "Reddit Comment Fetcher API",
        "version": "1.0.0",
        "endpoints": {
            "/fetch-comments": {
                "method": "POST",
                "description": "Fetch top comments from a Reddit post",
                "parameters": {
                    "reddit_url": "Required. Full Reddit post URL",
                    "max_comments": "Optional. Max comments to return (default: 100)",
                    "min_score": "Optional. Minimum score filter (default: 5)"
                }
            },
            "/health": {
                "method": "GET",
                "description": "Health check endpoint"
            }
        },
        "example_request": {
            "reddit_url": "https://www.reddit.com/r/soccer/comments/1oizosj/title/",
            "max_comments": 50,
            "min_score": 10
        }
    }), 200


if __name__ == "__main__":
    # 本番環境ではGunicornなどを使用
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)