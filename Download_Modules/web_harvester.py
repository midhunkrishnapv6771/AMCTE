import sys
import os

# Ensure project root and custom module directories are in python search path
_MODULE_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(_MODULE_DIR)

# ── LOAD ENV EARLY ────────────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv as _load_dotenv
    _env_path = os.path.join(PROJECT_ROOT, "Credentials", ".env")
    if os.path.exists(_env_path):
        _load_dotenv(_env_path, override=False)
except Exception:
    pass
# ─────────────────────────────────────────────────────────────────────────────

for folder in [".", "Audio_modules", "video_rendering_modules", "Media_guards", "router", "logs_and_tracker", "Credentials"]:
    path = os.path.abspath(os.path.join(PROJECT_ROOT, folder))
    if path not in sys.path:
        sys.path.insert(0, path)

import logging
# pyrefly: ignore [missing-import]
from flask import Flask, request, jsonify, render_template, send_from_directory
from downloader import download_video

try:
    from trimmer import trim_video
    TRIMMER_AVAILABLE = True
except ImportError:
    TRIMMER_AVAILABLE = False

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("web_harvester")

import hashlib

def _hash_passphrase(p: str) -> str:
    """Zero-knowledge SHA-256 hash of a passphrase. Raw password is never stored or logged."""
    return hashlib.sha256(p.encode("utf-8")).hexdigest() if p else ""

# Initialize Flask, pointing static and templates folders to the current directory
app = Flask(__name__, template_folder='templates', static_folder='static')

@app.route("/")
def index():
    return render_template("index.html")

@app.route("/api/harvest", methods=["POST"])
def harvest():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "Invalid JSON"}), 400
        
    url = data.get("url", "").strip()
    title = data.get("title", "").strip()
    user_id = data.get("user_id", "").strip()
    do_trim = data.get("do_trim", False)
    
    try:
        start_time = float(data.get("start_time", 0))
        end_time = float(data.get("end_time", 10))
    except ValueError:
        start_time = 0
        end_time = 10
    
    if not url:
        return jsonify({"status": "error", "message": "❌ Please provide a URL."}), 400
        
    logger.info(f"🎨 Web Request: {url} | Title: {title} | User: {user_id}")
    
    try:
        result = download_video(
            url, 
            custom_title=title if title else None,
            user_id=user_id if user_id else None
        )
        if result and result[0]:
            v_path, is_cached = result
            final_path = os.path.abspath(v_path)
            status_text = "♻️ DISK CACHE HIT" if is_cached else "✅ HARVEST SUCCESSFUL"
            
            if do_trim:
                if not TRIMMER_AVAILABLE:
                    status_text += " but ❌ TRIM FAILED: Trimmer module not found."
                else:
                    try:
                        final_path = trim_video(final_path, start_time, end_time)
                        status_text += " + ✂️ TRIMMED"
                    except Exception as trim_err:
                        status_text += f" but ❌ TRIM FAILED: {str(trim_err)}"
                        
            downloads_dir = os.path.abspath(os.path.join(PROJECT_ROOT, "downloads"))
            try:
                rel_path = os.path.relpath(final_path, downloads_dir)
                rel_path = rel_path.replace(os.path.sep, "/")
                video_url = f"/api/videos/{rel_path}"
            except Exception:
                video_url = None

            return jsonify({
                "status": "success",
                "message": status_text,
                "video_path": final_path,
                "video_url": video_url
            })
        else:
            return jsonify({"status": "error", "message": "❌ HARVEST FAILED: Site not supported or timeout."}), 500
    except Exception as e:
        logger.error(f"❌ Web Error: {e}")
        return jsonify({"status": "error", "message": f"❌ CRITICAL ERROR: {str(e)}"}), 500

@app.route("/api/credentials/submit", methods=["POST"])
def submit_credentials():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "❌ Invalid JSON."}), 400
        
    user_id = data.get("user_id", "").strip()
    passphrase = data.get("passphrase", "").strip()
    apify_token = data.get("apify_token", "").strip()
    instagram_cookie = data.get("instagram_cookie", "").strip()
    
    if not user_id:
        return jsonify({"status": "error", "message": "❌ User ID is required."}), 400
    if not passphrase:
        return jsonify({"status": "error", "message": "❌ Profile passphrase is required."}), 400
    if not apify_token and not instagram_cookie:
        return jsonify({"status": "error", "message": "❌ Please provide either an Apify Token or Instagram Cookie."}), 400
        
    try:
        from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager
        success, msg = pool_manager.add_user_credentials(user_id, passphrase, apify_token, instagram_cookie)
        if success:
            return jsonify({"status": "success", "message": "🔑 Credentials securely stored & synced!"})
        else:
            return jsonify({"status": "error", "message": f"❌ {msg}"}), 401
    except Exception as e:
        logger.error(f"❌ Credentials Submit Error: {e}")
        return jsonify({"status": "error", "message": f"❌ Server Error: {str(e)}"}), 500

@app.route("/api/credentials/telegram", methods=["POST"])
def submit_telegram_chat_id():
    data = request.get_json()
    if not data:
        return jsonify({"status": "error", "message": "❌ Invalid JSON."}), 400
        
    user_id = data.get("user_id", "").strip()
    passphrase = data.get("passphrase", "").strip()
    telegram_chat_id = data.get("telegram_chat_id", "").strip()
    
    if not user_id:
        return jsonify({"status": "error", "message": "❌ User ID is required."}), 400
    if not passphrase:
        return jsonify({"status": "error", "message": "❌ Profile passphrase is required."}), 400
    if not telegram_chat_id:
        return jsonify({"status": "error", "message": "❌ Telegram Chat ID is required."}), 400
        
    try:
        from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager
        success, msg = pool_manager.add_telegram_chat_id(user_id, passphrase, telegram_chat_id)
        if success:
            return jsonify({"status": "success", "message": "📡 Telegram Vault linked & synced!"})
        else:
            return jsonify({"status": "error", "message": f"❌ {msg}"}), 401
    except Exception as e:
        logger.error(f"❌ Telegram Chat ID Submit Error: {e}")
        return jsonify({"status": "error", "message": f"❌ Server Error: {str(e)}"}), 500

@app.route("/api/oauth/status", methods=["GET"])
def oauth_status():
    user_id = request.args.get("user_id", "").strip()
    if not user_id:
        return jsonify({"status": "error", "message": "❌ User ID is required."}), 400
    try:
        from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager
        creds = pool_manager.get_user_credentials(user_id)
        socials = creds.get("socials", {})
        return jsonify({
            "status": "success",
            "youtube": "youtube" in socials,
            "instagram": "instagram" in socials,
            "github": "github" in socials,
            "telegram_chat_id": creds.get("telegram_chat_id", ""),
            "apify": "apify_token" in creds
        })
    except Exception as e:
        logger.error(f"❌ OAuth Status Error: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

@app.route("/oauth/youtube/start")
def youtube_start():
    user_id = request.args.get("user_id", "").strip()
    passphrase = request.args.get("passphrase", "").strip()
    if not user_id:
        return "❌ User ID is required to start connection.", 400
    if not passphrase:
        return "❌ Profile passphrase is required to link social accounts.", 400

    p_hash = _hash_passphrase(passphrase)
    state = f"{user_id}:{p_hash}"  # Signed session token — never stores raw password

    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_base = os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://127.0.0.1:5000")
    
    if not client_id or not client_secret:
        return f'''
        <html>
        <head>
            <title>Mock Google Consent Screen</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; background: #121214; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: rgba(255,255,255,0.05); padding: 2.5rem; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); max-width: 420px; text-align: center; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37); }}
                h2 {{ color: #ff3333; margin-top: 0; font-family: 'Outfit', sans-serif; }}
                p {{ color: #ccc; font-size: 0.95rem; line-height: 1.5; }}
                .btn {{ display: inline-block; background: #ff3333; color: white; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 1.5rem; cursor: pointer; border: none; }}
                .btn:hover {{ opacity: 0.9; }}
                .footer-text {{ font-size: 0.8rem; color: #777; margin-top: 1.25rem; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>Google YouTube OAuth</h2>
                <p><strong>AMTCE</strong> is requesting permission to manage your YouTube account (Upload Videos).</p>
                <p style="font-size: 0.85rem; color: #ffaa00; background: rgba(255,170,0,0.1); padding: 0.5rem; border-radius: 6px;">⚠️ Client ID/Secret not set. Running in Mock Demo Mode.</p>
                <a href="/oauth/youtube/callback?code=mock_google_code_xyz&state={state}" class="btn">Authorize AMTCE</a>
                <div class="footer-text">Secure OAuth simulation for user: {user_id}</div>
            </div>
        </body>
        </html>
        '''
        
    import urllib.parse
    params = {
        "client_id": client_id,
        "redirect_uri": f"{redirect_base}/oauth/youtube/callback",
        "response_type": "code",
        "scope": "https://www.googleapis.com/auth/youtube.upload",
        "access_type": "offline",
        "prompt": "consent",
        "state": state
    }
    url = "https://accounts.google.com/o/oauth2/v2/auth?" + urllib.parse.urlencode(params)
    from flask import redirect
    return redirect(url)

@app.route("/oauth/youtube/callback")
def youtube_callback():
    code = request.args.get("code")
    state = request.args.get("state", "")
    
    if not code or ":" not in state:
        return "❌ Missing or invalid session token. Please restart the connection.", 400
    user_id, p_hash = state.split(":", 1)
        
    client_id = os.environ.get("GOOGLE_CLIENT_ID")
    client_secret = os.environ.get("GOOGLE_CLIENT_SECRET")
    redirect_base = os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://127.0.0.1:5000")
    
    if not client_id or not client_secret:
        refresh_token = f"mock_google_refresh_token_for_{user_id}_secret_abc123"
    else:
        import requests
        try:
            res = requests.post("https://oauth2.googleapis.com/token", data={
                "code": code,
                "client_id": client_id,
                "client_secret": client_secret,
                "redirect_uri": f"{redirect_base}/oauth/youtube/callback",
                "grant_type": "authorization_code"
            }).json()
            refresh_token = res.get("refresh_token")
            if not refresh_token:
                return f"❌ Failed to exchange code. No refresh token returned. Response: {res}", 400
        except Exception as e:
            return f"❌ Failed to exchange token: {str(e)}", 500
            
    try:
        from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager
        success, msg = pool_manager.add_social_credentials_with_hash(user_id, p_hash, "youtube", refresh_token)
        if not success:
            return f"❌ {msg}", 401
    except Exception as e:
        return f"❌ Failed to call pool manager: {str(e)}", 500
        
    return """
    <html>
    <body style="font-family: sans-serif; background: #121214; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
        <h2 style="color: #4caf50;">✅ YouTube Connected Successfully!</h2>
        <p>This window will close automatically in a moment.</p>
        <script>
            if (window.opener) {
                window.opener.postMessage({ type: "OAUTH_SUCCESS", platform: "youtube" }, "*");
            }
            setTimeout(function() { window.close(); }, 2000);
        </script>
    </body>
    </html>
    """

@app.route("/oauth/instagram/start")
def instagram_start():
    user_id = request.args.get("user_id", "").strip()
    passphrase = request.args.get("passphrase", "").strip()
    if not user_id:
        return "❌ User ID is required to start connection.", 400
    if not passphrase:
        return "❌ Profile passphrase is required to link social accounts.", 400

    p_hash = _hash_passphrase(passphrase)
    state = f"{user_id}:{p_hash}"  # Signed session token — never stores raw password

    client_id = os.environ.get("META_CLIENT_ID")
    client_secret = os.environ.get("META_CLIENT_SECRET")
    redirect_base = os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://127.0.0.1:5000")
    
    if not client_id or not client_secret:
        return f'''
        <html>
        <head>
            <title>Mock Facebook Consent Screen</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; background: #121214; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: rgba(255,255,255,0.05); padding: 2.5rem; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); max-width: 420px; text-align: center; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37); }}
                h2 {{ color: #1877f2; margin-top: 0; font-family: 'Outfit', sans-serif; }}
                p {{ color: #ccc; font-size: 0.95rem; line-height: 1.5; }}
                .btn {{ display: inline-block; background: #1877f2; color: white; padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 1.5rem; cursor: pointer; border: none; }}
                .btn:hover {{ opacity: 0.9; }}
                .footer-text {{ font-size: 0.8rem; color: #777; margin-top: 1.25rem; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>Facebook/Instagram Login</h2>
                <p><strong>AMTCE</strong> is requesting permission to manage your Instagram Professional Account and post content.</p>
                <p style="font-size: 0.85rem; color: #ffaa00; background: rgba(255,170,0,0.1); padding: 0.5rem; border-radius: 6px;">⚠️ Client ID/Secret not set. Running in Mock Demo Mode.</p>
                <a href="/oauth/instagram/callback?code=mock_meta_code_abc&state={state}" class="btn">Log in with Facebook</a>
                <div class="footer-text">Secure OAuth simulation for user: {user_id}</div>
            </div>
        </body>
        </html>
        '''
        
    import urllib.parse
    params = {
        "client_id": client_id,
        "redirect_uri": f"{redirect_base}/oauth/instagram/callback",
        "scope": "instagram_basic,instagram_content_publish,pages_show_list,pages_read_engagement",
        "state": state
    }
    url = "https://www.facebook.com/v18.0/dialog/oauth?" + urllib.parse.urlencode(params)
    from flask import redirect
    return redirect(url)

@app.route("/oauth/instagram/callback")
def instagram_callback():
    code = request.args.get("code")
    state = request.args.get("state", "")
    
    if not code or ":" not in state:
        return "❌ Missing or invalid session token. Please restart the connection.", 400
    user_id, p_hash = state.split(":", 1)
        
    client_id = os.environ.get("META_CLIENT_ID")
    client_secret = os.environ.get("META_CLIENT_SECRET")
    redirect_base = os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://127.0.0.1:5000")
    
    if not client_id or not client_secret:
        access_token = f"mock_meta_long_lived_access_token_for_{user_id}_xyz789"
    else:
        import requests
        try:
            res = requests.get("https://graph.facebook.com/v18.0/oauth/access_token", params={
                "client_id": client_id,
                "redirect_uri": f"{redirect_base}/oauth/instagram/callback",
                "client_secret": client_secret,
                "code": code
            }).json()
            short_token = res.get("access_token")
            if not short_token:
                return f"❌ Failed to get access token. Response: {res}", 400
                
            res_long = requests.get("https://graph.facebook.com/v18.0/oauth/access_token", params={
                "grant_type": "fb_exchange_token",
                "client_id": client_id,
                "client_secret": client_secret,
                "fb_exchange_token": short_token
            }).json()
            access_token = res_long.get("access_token")
            if not access_token:
                return f"❌ Failed to upgrade token. Response: {res_long}", 400
        except Exception as e:
            return f"❌ Failed to exchange Meta token: {str(e)}", 500
            
    try:
        from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager
        success, msg = pool_manager.add_social_credentials_with_hash(user_id, p_hash, "instagram", access_token)
        if not success:
            return f"❌ {msg}", 401
    except Exception as e:
        return f"❌ Failed to call pool manager: {str(e)}", 500
        
    return """
    <html>
    <body style="font-family: sans-serif; background: #121214; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
        <h2 style="color: #4caf50;">✅ Instagram Connected Successfully!</h2>
        <p>This window will close automatically in a moment.</p>
        <script>
            if (window.opener) {
                window.opener.postMessage({ type: "OAUTH_SUCCESS", platform: "instagram" }, "*");
            }
            setTimeout(function() { window.close(); }, 2000);
        </script>
    </body>
    </html>
    """

@app.route("/oauth/github/start")
def github_start():
    user_id = request.args.get("user_id", "").strip()
    passphrase = request.args.get("passphrase", "").strip()
    if not user_id:
        return "❌ User ID is required to start connection.", 400
    if not passphrase:
        return "❌ Profile passphrase is required to link social accounts.", 400

    p_hash = _hash_passphrase(passphrase)
    state = f"{user_id}:{p_hash}"  # Signed session token — never stores raw password

    client_id = os.environ.get("GITHUB_CLIENT_ID")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET")
    redirect_base = os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://127.0.0.1:5000")
    
    if not client_id or not client_secret:
        return f'''
        <html>
        <head>
            <title>Mock GitHub Consent Screen</title>
            <style>
                body {{ font-family: 'Inter', sans-serif; background: #121214; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; }}
                .card {{ background: rgba(255,255,255,0.05); padding: 2.5rem; border-radius: 16px; border: 1px solid rgba(255,255,255,0.1); max-width: 420px; text-align: center; box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.37); }}
                h2 {{ color: #ffffff; margin-top: 0; font-family: 'Outfit', sans-serif; }}
                p {{ color: #ccc; font-size: 0.95rem; line-height: 1.5; }}
                .btn {{ display: inline-block; background: #24292f; color: white; border: 1px solid rgba(255,255,255,0.2); padding: 0.75rem 1.5rem; border-radius: 8px; text-decoration: none; font-weight: bold; margin-top: 1.5rem; cursor: pointer; }}
                .btn:hover {{ background: #2f363d; }}
                .footer-text {{ font-size: 0.8rem; color: #777; margin-top: 1.25rem; }}
            </style>
        </head>
        <body>
            <div class="card">
                <h2>GitHub Connection</h2>
                <p><strong>AMTCE</strong> is requesting permission to access your GitHub repositories to authorize code pushes.</p>
                <p style="font-size: 0.85rem; color: #ffaa00; background: rgba(255,170,0,0.1); padding: 0.5rem; border-radius: 6px;">⚠️ GITHUB_CLIENT_ID/Secret not set. Running in Mock Demo Mode.</p>
                <a href="/oauth/github/callback?code=mock_github_code_abc&state={state}" class="btn">Authorize AMTCE on GitHub</a>
                <div class="footer-text">Secure OAuth simulation for user: {user_id}</div>
            </div>
        </body>
        </html>
        '''
        
    import urllib.parse
    params = {
        "client_id": client_id,
        "redirect_uri": f"{redirect_base}/oauth/github/callback",
        "scope": "repo,user",
        "state": state
    }
    url = "https://github.com/login/oauth/authorize?" + urllib.parse.urlencode(params)
    from flask import redirect
    return redirect(url)

@app.route("/oauth/github/callback")
def github_callback():
    code = request.args.get("code")
    state = request.args.get("state", "")
    
    if not code or ":" not in state:
        return "❌ Missing or invalid session token. Please restart the connection.", 400
    user_id, p_hash = state.split(":", 1)
        
    client_id = os.environ.get("GITHUB_CLIENT_ID")
    client_secret = os.environ.get("GITHUB_CLIENT_SECRET")
    redirect_base = os.environ.get("OAUTH_REDIRECT_BASE_URL", "http://127.0.0.1:5000")
    
    if not client_id or not client_secret:
        access_token = f"mock_github_access_token_for_{user_id}_xyz789"
    else:
        import requests
        try:
            res = requests.post("https://github.com/login/oauth/access_token", 
                                headers={"Accept": "application/json"},
                                data={
                                    "client_id": client_id,
                                    "client_secret": client_secret,
                                    "code": code,
                                    "redirect_uri": f"{redirect_base}/oauth/github/callback"
                                }).json()
            access_token = res.get("access_token")
            if not access_token:
                return f"❌ Failed to get access token. Response: {res}", 400
        except Exception as e:
            return f"❌ Failed to exchange GitHub token: {str(e)}", 500
            
    try:
        from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager
        success, msg = pool_manager.add_social_credentials_with_hash(user_id, p_hash, "github", access_token)
        if not success:
            return f"❌ {msg}", 401
    except Exception as e:
        return f"❌ Failed to call pool manager: {str(e)}", 500
        
    return """
    <html>
    <body style="font-family: sans-serif; background: #121214; color: #fff; display: flex; align-items: center; justify-content: center; height: 100vh; margin: 0; flex-direction: column;">
        <h2 style="color: #4caf50;">✅ GitHub Connected Successfully!</h2>
        <p>This window will close automatically in a moment.</p>
        <script>
            if (window.opener) {
                window.opener.postMessage({ type: "OAUTH_SUCCESS", platform: "github" }, "*");
            }
            setTimeout(function() { window.close(); }, 2000);
        </script>
    </body>
    </html>
    """

@app.route("/api/videos/<path:filename>")
def get_video(filename):
    downloads_dir = os.path.abspath(os.path.join(PROJECT_ROOT, "downloads"))
    return send_from_directory(downloads_dir, filename)

if __name__ == "__main__":
    flask_host = os.environ.get("FLASK_HOST", "127.0.0.1")
    flask_port = int(os.environ.get("FLASK_PORT", 5000))
    flask_debug = os.environ.get("FLASK_DEBUG", "False").strip().lower() in ("true", "1", "yes")
    logger.info(f"🚀 Starting Web Harvester on http://{flask_host}:{flask_port} (debug={flask_debug})")
    app.run(host=flask_host, port=flask_port, debug=flask_debug, use_reloader=False)
