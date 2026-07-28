document.addEventListener('DOMContentLoaded', () => {
    // --- TAB SWITCHING LOGIC ---
    const tabBtns = document.querySelectorAll('.tab-btn');
    const viewSections = document.querySelectorAll('.view-section');

    tabBtns.forEach(btn => {
        btn.addEventListener('click', () => {
            // Remove active classes
            tabBtns.forEach(b => b.classList.remove('active'));
            viewSections.forEach(v => v.classList.remove('active'));

            // Add active class to clicked
            btn.classList.add('active');
            const targetId = btn.getAttribute('data-target');
            document.getElementById(targetId).classList.add('active');
        });
    });

    // --- MATCHES API LOGIC ---
    const matchForm = document.getElementById('match-form');
    const btnFindMatches = document.getElementById('btn-find-matches');
    const loadingSpinner = document.getElementById('loading-spinner');
    const matchesContainer = document.getElementById('matches-container');
    const matchesStatus = document.getElementById('matches-status');
    const matchCardTemplate = document.getElementById('match-card-template');

    matchForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        // Lấy dữ liệu từ form
        const payload = {
            user_id: document.getElementById('m_user_id').value,
            age: parseInt(document.getElementById('m_age').value),
            location: document.getElementById('m_location').value,
            relationship_intent: document.getElementById('m_intent').value,
            interests: document.getElementById('m_interests').value.split(',').map(s => s.trim()).filter(Boolean),
            values: document.getElementById('m_values').value.split(',').map(s => s.trim()).filter(Boolean),
            limit: 3
        };

        // Giao diện: Loading state
        matchesStatus.classList.add('hidden');
        matchesContainer.innerHTML = '';
        loadingSpinner.classList.remove('hidden');
        btnFindMatches.disabled = true;
        btnFindMatches.innerHTML = '<i data-lucide="loader" class="spin"></i> Đang Phân Tích...';
        lucide.createIcons();

        try {
            const response = await fetch('/api/matches', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || 'Có lỗi xảy ra khi gọi API Backend!');
            }

            const data = await response.json();
            renderMatches(data);
        } catch (error) {
            console.error(error);
            matchesStatus.classList.remove('hidden');
            matchesStatus.textContent = '❌ Lỗi: ' + error.message;
        } finally {
            loadingSpinner.classList.add('hidden');
            btnFindMatches.disabled = false;
            btnFindMatches.innerHTML = '<i data-lucide="search"></i> Tìm Ứng Viên Bằng AI';
            lucide.createIcons();
        }
    });

    function renderMatches(data) {
        if (!data.matches || data.matches.length === 0) {
            matchesStatus.classList.remove('hidden');
            matchesStatus.textContent = 'Không tìm thấy ứng viên phù hợp trong cơ sở dữ liệu.';
            return;
        }

        data.matches.forEach((match, index) => {
            // Clone template
            const card = matchCardTemplate.content.cloneNode(true);
            
            // Fill data
            card.querySelector('.name').textContent = match.name + ', ' + match.age;
            card.querySelector('.location').innerHTML = '<i data-lucide="map-pin"></i> ' + (match.location || 'Bí ẩn');
            card.querySelector('.percentage').textContent = match.score;
            
            // Circle progress (100 = full circle dasharray)
            const circle = card.querySelector('.circle');
            circle.setAttribute('stroke-dasharray', `${match.score}, 100`);

            // AI Report
            const report = data.reports[index];
            if (report) {
                card.querySelector('.strengths span').textContent = (report.strengths || []).join(', ') || 'Chưa rõ';
                card.querySelector('.differences span').textContent = (report.differences || []).join(', ') || 'Chưa rõ';
            }

            matchesContainer.appendChild(card);
        });

        lucide.createIcons();
    }


    // --- COMPARE API LOGIC ---
    const compareForm = document.getElementById('compare-form');
    const compareLoading = document.getElementById('compare-loading');
    const compareResult = document.getElementById('compare-result');
    const btnCompare = document.getElementById('btn-compare');

    compareForm.addEventListener('submit', async (e) => {
        e.preventDefault();

        const payload = {
            person1: {
                name: document.getElementById('c1_name').value,
                age: parseInt(document.getElementById('c1_age').value),
                location: document.getElementById('c1_location').value,
                interests: document.getElementById('c1_interests').value.split(',').map(s => s.trim()).filter(Boolean),
                values: document.getElementById('c1_values').value.split(',').map(s => s.trim()).filter(Boolean),
            },
            person2: {
                name: document.getElementById('c2_name').value,
                age: parseInt(document.getElementById('c2_age').value),
                location: document.getElementById('c2_location').value,
                interests: document.getElementById('c2_interests').value.split(',').map(s => s.trim()).filter(Boolean),
                values: document.getElementById('c2_values').value.split(',').map(s => s.trim()).filter(Boolean),
            }
        };

        // Giao diện loading
        compareResult.classList.add('hidden');
        compareLoading.classList.remove('hidden');
        btnCompare.style.pointerEvents = 'none';

        try {
            const response = await fetch('/api/compare', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });

            if (!response.ok) {
                const errData = await response.json().catch(() => ({}));
                throw new Error(errData.error || 'API Lỗi.');
            }

            const data = await response.json();
            renderCompareReport(data, payload.person1.name, payload.person2.name);
        } catch (error) {
            compareResult.classList.remove('hidden');
            compareResult.innerHTML = `<p style="color:red">Lỗi: ${error.message}</p>`;
        } finally {
            compareLoading.classList.add('hidden');
            btnCompare.style.pointerEvents = 'auto';
        }
    });

    function renderCompareReport(data, name1, name2) {
        compareResult.classList.remove('hidden');
        const report = data.report;
        
        if (!report) {
            compareResult.innerHTML = `<p>Không có dữ liệu trả về.</p>`;
            return;
        }

        const score = report.score || 0;
        const label = report.score_label || 'Khá';
        const strengths = (report.strengths || []).map(s => `<li>${s}</li>`).join('');
        const diffs = (report.differences || []).map(s => `<li>${s}</li>`).join('');

        let html = `
            <h3><i data-lucide="award"></i> Điểm Tương Thích: ${score}/100 (${label})</h3>
            <div style="margin-top: 1rem;">
                <p><strong><i data-lucide="check-circle" style="color:var(--accent-neon); width: 16px;"></i> Điểm Chung Mạnh Nhất:</strong></p>
                <ul style="padding-left: 2rem; margin-top: 0.5rem; color: var(--text-secondary); line-height: 1.6;">
                    ${strengths || '<li>Chưa có nhiều điểm chung nổi bật</li>'}
                </ul>
            </div>
            <div style="margin-top: 1.5rem;">
                <p><strong><i data-lucide="alert-triangle" style="color: #f39c12; width: 16px;"></i> Sự Khác Biệt Cần Lưu Ý:</strong></p>
                <ul style="padding-left: 2rem; margin-top: 0.5rem; color: var(--text-secondary); line-height: 1.6;">
                    ${diffs || '<li>Chưa phát hiện khác biệt lớn</li>'}
                </ul>
            </div>
            <p style="margin-top: 2rem; font-size: 0.85rem; color: #aaa; font-style: italic;">${data.disclaimer}</p>
        `;

        compareResult.innerHTML = html;
        lucide.createIcons();
    }

    // --- CHATBOT API LOGIC ---
    const chatForm = document.getElementById('chat-form');
    const chatInput = document.getElementById('chat-input');
    const chatMessages = document.getElementById('chat-messages');
    const btnSend = document.getElementById('btn-send');

    function appendMessage(sender, text) {
        const msgDiv = document.createElement('div');
        msgDiv.className = `message ${sender}`;
        
        let avatarIcon = sender === 'bot' ? 'bot' : 'user';
        let html = `
            <div class="msg-avatar"><i data-lucide="${avatarIcon}"></i></div>
            <div class="msg-bubble">${escapeHTML(text)}</div>
        `;
        msgDiv.innerHTML = html;
        chatMessages.appendChild(msgDiv);
        lucide.createIcons();
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    function showTypingIndicator() {
        const msgDiv = document.createElement('div');
        msgDiv.className = 'message bot typing-msg';
        msgDiv.innerHTML = `
            <div class="msg-avatar"><i data-lucide="bot"></i></div>
            <div class="msg-bubble">
                <div class="typing-indicator">
                    <span></span><span></span><span></span>
                </div>
            </div>
        `;
        chatMessages.appendChild(msgDiv);
        lucide.createIcons();
        chatMessages.scrollTop = chatMessages.scrollHeight;
        return msgDiv;
    }

    function escapeHTML(str) {
        return str.replace(/[&<>'"]/g, 
            tag => ({
                '&': '&amp;',
                '<': '&lt;',
                '>': '&gt;',
                "'": '&#39;',
                '"': '&quot;'
            }[tag])
        );
    }

    if(chatForm) {
        chatForm.addEventListener('submit', async (e) => {
            e.preventDefault();
            const message = chatInput.value.trim();
            if (!message) return;

            // 1. Render User Message
            appendMessage('user', message);
            chatInput.value = '';
            
            // 2. Show Typing Indicator and Disable Input
            const typingDiv = showTypingIndicator();
            chatInput.disabled = true;
            btnSend.disabled = true;

            try {
                // 3. Call API
                const response = await fetch('/api/chat', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ message: message })
                });

                if (!response.ok) {
                    const errData = await response.json().catch(() => ({}));
                    throw new Error(errData.error || 'Có lỗi khi gọi API Chat.');
                }

                const data = await response.json();
                
                // 4. Remove Typing and Show Bot Reply
                typingDiv.remove();
                appendMessage('bot', data.reply);
                
            } catch (error) {
                typingDiv.remove();
                appendMessage('bot', `❌ Lỗi: ${error.message}`);
            } finally {
                chatInput.disabled = false;
                btnSend.disabled = false;
                chatInput.focus();
            }
        });
    }

});
