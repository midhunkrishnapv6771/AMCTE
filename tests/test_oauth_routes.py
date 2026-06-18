import os
import sys
import pytest

# Add paths to sys.path
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, PROJECT_ROOT)
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Download_Modules"))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "Credentials"))

from Telegram_credentials_handler_modules.credential_pool_manager import pool_manager, hash_passphrase
from web_harvester import app

@pytest.fixture
def client(monkeypatch):
    # Clear client credentials to force deterministic mock flow during testing
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "")
    monkeypatch.setenv("GOOGLE_CLIENT_SECRET", "")
    monkeypatch.setenv("META_CLIENT_ID", "")
    monkeypatch.setenv("META_CLIENT_SECRET", "")
    
    app.config["TESTING"] = True
    with app.test_client() as client:
        yield client

def test_pool_manager_new_fields():
    # Test add_telegram_chat_id
    user_id = "test_oauth_user_123"
    chat_id = "-1008888888888"
    test_pass = "test_pool_pass_abc123"
    
    success, msg = pool_manager.add_telegram_chat_id(user_id, test_pass, chat_id)
    assert success
    
    creds = pool_manager.get_user_credentials(user_id)
    assert creds.get("telegram_chat_id") == chat_id
    
    # Test add_social_credentials
    token = "mock_youtube_refresh_token_123"
    success, msg = pool_manager.add_social_credentials(user_id, test_pass, "youtube", token)
    assert success
    
    creds = pool_manager.get_user_credentials(user_id)
    assert creds.get("socials", {}).get("youtube", {}).get("refresh_token") == token
    
    # Prune/Clean up — after clearing fields, the profile row stays (holds passphrase_hash)
    # but all credential values should be absent
    pool_manager.add_telegram_chat_id(user_id, test_pass, "")
    pool_manager.add_social_credentials(user_id, test_pass, "youtube", "")
    creds = pool_manager.get_user_credentials(user_id)
    assert "telegram_chat_id" not in creds
    assert "socials" not in creds

def test_telegram_chat_id_api(client):
    user_id = "test_api_user_456"
    chat_id = "-1009999999999"
    test_pass = "test_api_pass_xyz456"
    
    response = client.post("/api/credentials/telegram", json={
        "user_id": user_id,
        "passphrase": test_pass,
        "telegram_chat_id": chat_id
    })
    assert response.status_code == 200
    res_data = response.get_json()
    assert res_data["status"] == "success"
    
    # Check status endpoint
    response = client.get(f"/api/oauth/status?user_id={user_id}")
    assert response.status_code == 200
    status_data = response.get_json()
    assert status_data["telegram_chat_id"] == chat_id
    assert status_data["youtube"] is False
    assert status_data["instagram"] is False
    
    # Cleanup
    pool_manager.add_telegram_chat_id(user_id, test_pass, "")

def test_oauth_mock_flow(client):
    user_id = "test_oauth_mock_user_789"
    test_pass = "test_oauth_pass_mock789"
    p_hash = hash_passphrase(test_pass)  # Compute expected hash for callback state param
    state = f"{user_id}:{p_hash}"
    
    # 1. Start YouTube OAuth (should render Google mock consent page)
    response = client.get(f"/oauth/youtube/start?user_id={user_id}&passphrase={test_pass}")
    assert response.status_code == 200
    assert b"Mock Google Consent Screen" in response.data
    
    # 2. Complete callback (should save token and render success page)
    response = client.get(f"/oauth/youtube/callback?code=mock_code&state={state}")
    assert response.status_code == 200
    assert b"YouTube Connected Successfully" in response.data
    
    # 3. Check status API
    response = client.get(f"/api/oauth/status?user_id={user_id}")
    assert response.status_code == 200
    status_data = response.get_json()
    assert status_data["youtube"] is True
    
    # 4. Start Instagram OAuth
    response = client.get(f"/oauth/instagram/start?user_id={user_id}&passphrase={test_pass}")
    assert response.status_code == 200
    assert b"Mock Facebook Consent Screen" in response.data
    
    # 5. Complete callback for Instagram
    response = client.get(f"/oauth/instagram/callback?code=mock_code&state={state}")
    assert response.status_code == 200
    assert b"Instagram Connected Successfully" in response.data
    
    # 6. Check status API again
    response = client.get(f"/api/oauth/status?user_id={user_id}")
    status_data = response.get_json()
    assert status_data["instagram"] is True
    
    # 7. Start GitHub OAuth
    response = client.get(f"/oauth/github/start?user_id={user_id}&passphrase={test_pass}")
    assert response.status_code == 200
    assert b"Mock GitHub Consent Screen" in response.data
    
    # 8. Complete callback for GitHub
    response = client.get(f"/oauth/github/callback?code=mock_code&state={state}")
    assert response.status_code == 200
    assert b"GitHub Connected Successfully" in response.data
    
    # 9. Check status API for GitHub
    response = client.get(f"/api/oauth/status?user_id={user_id}")
    status_data = response.get_json()
    assert status_data["github"] is True
    
    # Cleanup
    pool_manager.add_social_credentials(user_id, test_pass, "youtube", "")
    pool_manager.add_social_credentials(user_id, test_pass, "instagram", "")
    pool_manager.add_social_credentials(user_id, test_pass, "github", "")
