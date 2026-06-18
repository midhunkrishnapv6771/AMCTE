document.addEventListener('DOMContentLoaded', () => {
    // Accordion Logic
    const trimToggleBtn = document.getElementById('trimToggleBtn');
    const accordion = trimToggleBtn.parentElement;
    
    trimToggleBtn.addEventListener('click', () => {
        accordion.classList.toggle('active');
    });

    // Checkbox Logic for Time Inputs
    const doTrimCheckbox = document.getElementById('doTrim');
    const timeInputsGroup = document.getElementById('timeInputsGroup');

    doTrimCheckbox.addEventListener('change', (e) => {
        if (e.target.checked) {
            timeInputsGroup.classList.add('enabled');
        } else {
            timeInputsGroup.classList.remove('enabled');
        }
    });

    // Form Submission
    const harvestForm = document.getElementById('harvest-form');
    const submitBtn = document.getElementById('submitBtn');
    const statusOutput = document.getElementById('statusOutput');
    const videoContainer = document.getElementById('videoContainer');
    const videoPathLabel = document.getElementById('videoPathLabel');

    function appendLog(message, type = 'normal') {
        const p = document.createElement('p');
        p.className = `log-line ${type}`;
        
        const timestamp = new Date().toLocaleTimeString();
        p.textContent = `[${timestamp}] ${message}`;
        
        statusOutput.appendChild(p);
        statusOutput.scrollTop = statusOutput.scrollHeight;
    }

    harvestForm.addEventListener('submit', async (e) => {
        e.preventDefault();
        
        const url = document.getElementById('urlInput').value.trim();
        const title = document.getElementById('titleInput').value.trim();
        const userId = document.getElementById('harvestUserIdInput').value.trim();
        const doTrim = doTrimCheckbox.checked;
        const startTime = parseFloat(document.getElementById('startTime').value) || 0;
        const endTime = parseFloat(document.getElementById('endTime').value) || 10;

        if (!url) return;

        // UI State: Loading
        submitBtn.classList.add('loading');
        submitBtn.disabled = true;
        videoContainer.style.display = 'none';
        
        statusOutput.innerHTML = ''; // Clear previous logs
        appendLog(`Initiating harvest sequence for: ${url}`, 'normal');

        try {
            const response = await fetch('/api/harvest', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    url,
                    title,
                    user_id: userId,
                    do_trim: doTrim,
                    start_time: startTime,
                    end_time: endTime
                })
            });

            const data = await response.json();

            if (response.ok) {
                appendLog(data.message, 'success');
                appendLog(`Asset saved to local disk.`, 'success');
                videoPathLabel.textContent = `File Path: ${data.video_path}`;
                
                // Load and stream the downloaded video file in the player
                const videoPlayer = document.getElementById('videoPlayer');
                if (videoPlayer && data.video_url) {
                    videoPlayer.src = data.video_url;
                    videoPlayer.load();
                    videoPlayer.play().catch(err => console.log('Play triggered after user interaction:', err));
                }
                
                videoContainer.style.display = 'block';
            } else {
                appendLog(data.message || 'Server returned an error.', 'error');
            }

        } catch (error) {
            appendLog(`Network or critical error: ${error.message}`, 'error');
        } finally {
            // UI State: Reset
            submitBtn.classList.remove('loading');
            submitBtn.disabled = false;
        }
    });

    // OAuth & Credentials UI logic
    const userIdInput = document.getElementById('userIdInput');
    const connectYoutubeBtn = document.getElementById('connectYoutubeBtn');
    const connectInstagramBtn = document.getElementById('connectInstagramBtn');
    const connectGithubBtn = document.getElementById('connectGithubBtn');
    const youtubeStatus = document.getElementById('youtubeStatus');
    const instagramStatus = document.getElementById('instagramStatus');
    const githubStatus = document.getElementById('githubStatus');
    const oauthUnlockHint = document.getElementById('oauthUnlockHint');
    const telegramForm = document.getElementById('telegram-form');
    const telegramChatIdInput = document.getElementById('telegramChatIdInput');
    const telegramSubmitBtn = document.getElementById('telegramSubmitBtn');
    const telegramBtnLoader = document.getElementById('telegramBtnLoader');
    const profilePassphraseInput = document.getElementById('profilePassphraseInput');

    let activeUserId = '';
    let activePassphrase = '';

    // Check connection status for a user
    async function checkConnectionStatus(userId) {
        if (!userId) return;
        try {
            const response = await fetch(`/api/oauth/status?user_id=${encodeURIComponent(userId)}`);
            if (response.ok) {
                const data = await response.json();
                
                // Update YouTube Badge
                if (data.youtube) {
                    youtubeStatus.textContent = 'Connected';
                    youtubeStatus.className = 'connection-status badge-connected';
                } else {
                    youtubeStatus.textContent = 'Disconnected';
                    youtubeStatus.className = 'connection-status badge-disconnected';
                }

                // Update Instagram Badge
                if (data.instagram) {
                    instagramStatus.textContent = 'Connected';
                    instagramStatus.className = 'connection-status badge-connected';
                } else {
                    instagramStatus.textContent = 'Disconnected';
                    instagramStatus.className = 'connection-status badge-disconnected';
                }

                // Update GitHub Badge
                if (data.github) {
                    githubStatus.textContent = 'Connected';
                    githubStatus.className = 'connection-status badge-connected';
                } else {
                    githubStatus.textContent = 'Disconnected';
                    githubStatus.className = 'connection-status badge-disconnected';
                }

                // Update Telegram Input if it has a value stored
                if (data.telegram_chat_id) {
                    telegramChatIdInput.value = data.telegram_chat_id;
                } else {
                    telegramChatIdInput.value = '';
                }

                // Update Apify input indicator (placeholder only)
                const apifyTokenInput = document.getElementById('apifyTokenInput');
                if (data.apify) {
                    apifyTokenInput.placeholder = '•••••••• (Token Configured)';
                } else {
                    apifyTokenInput.placeholder = 'apify_api_...';
                }
            }
        } catch (error) {
            console.error('Failed to check OAuth status:', error);
        }
    }

    // Toggle Buttons based on User ID and Passphrase input
    function handleProfileFieldsChange() {
        const userId = userIdInput.value.trim();
        const passphrase = profilePassphraseInput ? profilePassphraseInput.value.trim() : '';
        activeUserId = userId;
        activePassphrase = passphrase;
        
        // Auto-fill the User ID on the harvest form for convenience
        const harvestUserField = document.getElementById('harvestUserIdInput');
        if (harvestUserField) {
            harvestUserField.value = userId;
        }

        const canEnable = userId.length > 0 && passphrase.length > 0;
        if (canEnable) {
            connectYoutubeBtn.disabled = false;
            connectInstagramBtn.disabled = false;
            connectGithubBtn.disabled = false;
            oauthUnlockHint.style.display = 'none';
            checkConnectionStatus(userId);
        } else {
            connectYoutubeBtn.disabled = true;
            connectInstagramBtn.disabled = true;
            connectGithubBtn.disabled = true;
            oauthUnlockHint.style.display = 'block';
            oauthUnlockHint.textContent = userId.length === 0
                ? '\u26a0\ufe0f Enter a User Identifier above to enable connection buttons.'
                : '\u26a0\ufe0f Set a Profile Passphrase above to enable connection buttons.';

            // Reset Badges only when user ID is cleared
            if (userId.length === 0) {
                youtubeStatus.textContent = 'Disconnected';
                youtubeStatus.className = 'connection-status badge-disconnected';
                instagramStatus.textContent = 'Disconnected';
                instagramStatus.className = 'connection-status badge-disconnected';
                githubStatus.textContent = 'Disconnected';
                githubStatus.className = 'connection-status badge-disconnected';
                telegramChatIdInput.value = '';
                document.getElementById('apifyTokenInput').placeholder = 'apify_api_...';
            }
        }
    }

    userIdInput.addEventListener('input', handleProfileFieldsChange);
    userIdInput.addEventListener('change', handleProfileFieldsChange);
    if (profilePassphraseInput) {
        profilePassphraseInput.addEventListener('input', handleProfileFieldsChange);
    }

    // OAuth Trigger Popups
    function openOAuthPopup(url) {
        const width = 500;
        const height = 600;
        const left = (window.innerWidth - width) / 2;
        const top = (window.innerHeight - height) / 2;
        return window.open(
            url,
            'OAuth Connection',
            `width=${width},height=${height},top=${top},left=${left},resizable=yes,scrollbars=yes`
        );
    }

    connectYoutubeBtn.addEventListener('click', () => {
        if (!activeUserId || !activePassphrase) {
            appendLog('\u274c User Identifier and Profile Passphrase are required to link accounts.', 'error');
            return;
        }
        openOAuthPopup(`/oauth/youtube/start?user_id=${encodeURIComponent(activeUserId)}&passphrase=${encodeURIComponent(activePassphrase)}`);
    });

    connectInstagramBtn.addEventListener('click', () => {
        if (!activeUserId || !activePassphrase) {
            appendLog('\u274c User Identifier and Profile Passphrase are required to link accounts.', 'error');
            return;
        }
        openOAuthPopup(`/oauth/instagram/start?user_id=${encodeURIComponent(activeUserId)}&passphrase=${encodeURIComponent(activePassphrase)}`);
    });

    connectGithubBtn.addEventListener('click', () => {
        if (!activeUserId || !activePassphrase) {
            appendLog('\u274c User Identifier and Profile Passphrase are required to link accounts.', 'error');
            return;
        }
        openOAuthPopup(`/oauth/github/start?user_id=${encodeURIComponent(activeUserId)}&passphrase=${encodeURIComponent(activePassphrase)}`);
    });

    // Listen for OAuth connection success messages from callback pages
    window.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'OAUTH_SUCCESS') {
            appendLog(`🔑 Social account connected successfully for platform: ${event.data.platform.toUpperCase()}`, 'success');
            if (activeUserId) {
                checkConnectionStatus(activeUserId);
            }
        }
    });

    // Telegram Chat ID submission
    if (telegramForm) {
        telegramForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            if (!activeUserId) {
                appendLog('\u274c User Identifier is required to save Telegram Chat ID.', 'error');
                return;
            }
            if (!activePassphrase) {
                appendLog('\u274c Profile Passphrase is required to save Telegram Chat ID.', 'error');
                return;
            }
            const telegramChatId = telegramChatIdInput.value.trim();
            if (!telegramChatId) {
                appendLog('❌ Please provide a Telegram Chat ID.', 'error');
                return;
            }

            telegramSubmitBtn.classList.add('loading');
            telegramSubmitBtn.disabled = true;

            appendLog(`Vault: Saving isolated Telegram Chat ID for '${activeUserId}'...`, 'normal');

            try {
                const response = await fetch('/api/credentials/telegram', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        user_id: activeUserId,
                        passphrase: activePassphrase,
                        telegram_chat_id: telegramChatId
                    })
                });

                const data = await response.json();
                if (response.ok) {
                    appendLog(data.message, 'success');
                    checkConnectionStatus(activeUserId);
                } else {
                    appendLog(data.message || 'Failed to save Telegram Chat ID.', 'error');
                }
            } catch (error) {
                appendLog(`Telegram Config Error: ${error.message}`, 'error');
            } finally {
                telegramSubmitBtn.classList.remove('loading');
                telegramSubmitBtn.disabled = false;
            }
        });
    }

    // Credentials Form Submission (Apify Scraper Token only)
    const credentialsForm = document.getElementById('credentials-form');
    const credSubmitBtn = document.getElementById('credSubmitBtn');

    if (credentialsForm) {
        credentialsForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            
            const userId = userIdInput.value.trim();
            const apifyToken = document.getElementById('apifyTokenInput').value.trim();

            if (!userId) {
                appendLog('\u274c User Identifier is required to register credentials.', 'error');
                return;
            }
            if (!activePassphrase) {
                appendLog('\u274c Profile Passphrase is required to save credentials.', 'error');
                return;
            }
            if (!apifyToken) {
                appendLog('\u274c Provide an Apify Token to register.', 'error');
                return;
            }

            // UI State: Loading
            credSubmitBtn.classList.add('loading');
            credSubmitBtn.disabled = true;

            appendLog(`Vault: Encrypting and syncing Apify credentials for '${userId}'...`, 'normal');

            try {
                const response = await fetch('/api/credentials/submit', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({
                        user_id: userId,
                        passphrase: activePassphrase,
                        apify_token: apifyToken,
                        instagram_cookie: '' // Removed manual cookie input in favor of OAuth
                    })
                });

                const data = await response.json();

                if (response.ok) {
                    appendLog(data.message, 'success');
                    document.getElementById('apifyTokenInput').value = '';
                    checkConnectionStatus(userId);
                } else {
                    appendLog(data.message || 'Credentials vault sync failed.', 'error');
                }
            } catch (error) {
                appendLog(`Vault Sync Error: ${error.message}`, 'error');
            } finally {
                credSubmitBtn.classList.remove('loading');
                credSubmitBtn.disabled = false;
            }
        });
    }
});
