let currentRecipientId = null;
let currentVolume = 0.5;
let lastMessageCount = 0;
let pollInterval = null;

function updateVolume(val) {
    currentVolume = val / 100;
    document.getElementById('volVal').innerText = val;
}

// Генерация звука через Web Audio API (без внешних аудиофайлов)
function playNotificationSound() {
    if (currentVolume <= 0) return;
    try {
        const audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        const oscillator = audioCtx.createOscillator();
        const gainNode = audioCtx.createGain();
        
        oscillator.type = 'sine';
        oscillator.frequency.setValueAtTime(587.33, audioCtx.currentTime); // нота D5
        gainNode.gain.setValueAtTime(currentVolume * 0.2, audioCtx.currentTime);
        
        oscillator.connect(gainNode);
        gainNode.connect(audioCtx.destination);
        
        oscillator.start();
        oscillator.stop(audioCtx.currentTime + 0.15);
    } catch(e) {
        console.log("AudioContext error:", e);
    }
}

// Периодическое обновление списка пользователей и сообщений
function loadUsers() {
    fetch('/api/users')
        .then(res => res.json())
        .then(users => {
            const listContainer = document.getElementById('userList');
            listContainer.innerHTML = '';
            users.forEach(u => {
                const div = document.createElement('div');
                div.className = 'user-item' + (currentRecipientId == u.id ? ' active' : '');
                div.onclick = () => selectUser(u.id, u.username, u.status, u.last_seen);
                div.innerHTML = `
                    <span class="u-name">${u.username}</span>
                    <span class="u-status">${u.status}</span>
                    <span class="u-seen">Был(а) в сети: ${u.last_seen}</span>
                `;
                listContainer.appendChild(div);
            });
        });
}

function selectUser(userId, username, status, lastSeen) {
    currentRecipientId = userId;
    document.getElementById('chatArea').style.display = 'flex';
    document.getElementById('activeChatName').innerText = username;
    document.getElementById('activeUserStatus').innerText = `Статус: ${status} | Был(а) в сети: ${lastSeen}`;
    
    // Подсветим выбранного в списке
    loadUsers();
    fetchMessages(true);

    if (pollInterval) clearInterval(pollInterval);
    pollInterval = setInterval(() => fetchMessages(false), 2000); // опрос каждые 2 секунды
}

function fetchMessages(scrollToBottomFlag) {
    if (!currentRecipientId) return;
    fetch(`/api/messages/${currentRecipientId}`)
        .then(res => res.json())
        .then(messages => {
            const box = document.getElementById('messagesBox');
            const shouldScroll = scrollToBottomFlag || (box.scrollTop + box.clientHeight >= box.scrollHeight - 30);
            
            // Если пришли новые сообщения от собеседника
            if (messages.length > lastMessageCount && lastMessageCount > 0) {
                const lastMsg = messages[messages.length - 1];
                if (lastMsg.sender_id == currentRecipientId) {
                    playNotificationSound();
                }
            }
            lastMessageCount = messages.length;

            box.innerHTML = '';
            messages.forEach(m => {
                const msgDiv = document.createElement('div');
                msgDiv.className = m.sender_id == currentRecipientId ? 'message incoming' : 'message outgoing';
                msgDiv.innerHTML = `<p style="margin:0;">${escapeHtml(m.content)}</p><span class="time">${m.timestamp}</span>`;
                box.appendChild(msgDiv);
            });

            if (shouldScroll) {
                box.scrollTop = box.scrollHeight;
            }
        });
}

function sendMessage() {
    const input = document.getElementById('messageInput');
    const content = input.value.trim();
    if (!content || !currentRecipientId) return;

    fetch('/api/messages/send', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ recipient_id: currentRecipientId, content: content })
    })
    .then(res => res.json())
    .then(data => {
        if (data.error) {
            alert(data.error);
            return;
        }
        input.value = '';
        fetchMessages(true);
    });
}

function handleKeyPress(e) {
    if (e.key === 'Enter') {
        sendMessage();
    }
}

function toggleBlockUser() {
    if (!currentRecipientId) return;
    if (!confirm('Вы уверены, что хотите заблокировать/разблокировать этого пользователя?')) return;

    fetch(`/api/block/${currentRecipientId}`, { method: 'POST' })
        .then(res => res.json())
        .then(data => {
            alert(data.status === 'blocked' ? 'Пользователь заблокирован' : 'Пользователь разблокирован');
        });
}

function toggleProfileModal() {
    const modal = document.getElementById('profileModal');
    modal.style.display = modal.style.display === 'flex' ? 'none' : 'flex';
}

function saveProfile() {
    const newStatus = document.getElementById('newStatusInput').value;
    fetch('/api/profile/update', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: newStatus })
    })
    .then(res => res.json())
    .then(data => {
        if (data.success) {
            document.getElementById('myStatusText').innerText = newStatus;
            toggleProfileModal();
        }
    });
}

function escapeHtml(text) {
    return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

// Запуск фонового обновления списка пользователей каждые 4 секунды
setInterval(loadUsers, 4000);
loadUsers();
