// Multi-chat WebSocket client for AI Automation System

const WORKFLOW_NAMES = {
    '1': 'Source Finder',
    '2': 'Video + Audio',
    '3': 'Video Changer',
    '4': 'Script Changer',
    '5': 'Image + Audio',
    '6': 'Script to Voice',
};

// State: multiple chats, each with its own WebSocket
const chats = {}; // { chatId: { ws, sessionId, workflow, el, messages } }
let activeChatId = null;
let chatCounter = 0;

// DOM refs
const sidebar = document.getElementById('sidebar');
const sidebarToggle = document.getElementById('sidebarToggle');
const chatTabs = document.getElementById('chatTabs');
const emptyChats = document.getElementById('emptyChats');
const chatPanels = document.getElementById('chatPanels');
const welcomeScreen = document.getElementById('welcomeScreen');
const inputArea = document.getElementById('inputArea');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('fileInput');
const chatTitle = document.getElementById('chatTitle');
const chatSubtitle = document.getElementById('chatSubtitle');
const closeChatBtn = document.getElementById('closeChatBtn');
const connectionStatus = document.getElementById('connectionStatus');
const statusEl = document.getElementById('status');
const dropOverlay = document.getElementById('dropOverlay');

// ─── Chat Management ───

function createChat(workflowNum) {
    chatCounter++;
    const chatId = 'chat_' + chatCounter;
    const name = WORKFLOW_NAMES[workflowNum] || 'Chat';

    // Create message panel
    const panel = document.createElement('div');
    panel.className = 'chat-panel';
    panel.id = 'panel_' + chatId;
    chatPanels.appendChild(panel);

    // Create sidebar tab
    const tab = document.createElement('div');
    tab.className = 'chat-tab';
    tab.dataset.chatId = chatId;
    tab.innerHTML = `
        <span class="tab-dot wf-color-${workflowNum}"></span>
        <span class="tab-name">${name}</span>
        <button class="tab-close" title="Close">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                <line x1="18" y1="6" x2="6" y2="18"/><line x1="6" y1="6" x2="18" y2="18"/>
            </svg>
        </button>
    `;

    tab.addEventListener('click', (e) => {
        if (!e.target.closest('.tab-close')) {
            switchChat(chatId);
        }
    });

    tab.querySelector('.tab-close').addEventListener('click', (e) => {
        e.stopPropagation();
        closeChat(chatId);
    });

    chatTabs.appendChild(tab);
    emptyChats.style.display = 'none';

    // Open WebSocket
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    const ws = new WebSocket(`${protocol}//${location.host}/ws?workflow=${workflowNum}`);

    const chat = {
        id: chatId,
        ws: ws,
        sessionId: null,
        workflow: workflowNum,
        name: name,
        panel: panel,
        tab: tab,
    };

    ws.onopen = () => updateConnectionStatus(true);

    ws.onclose = () => {
        // Check if any chat is still connected
        const anyOpen = Object.values(chats).some(c => c.ws && c.ws.readyState === WebSocket.OPEN);
        if (!anyOpen) updateConnectionStatus(false);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(chatId, data);
    };

    chats[chatId] = chat;
    switchChat(chatId);
    return chatId;
}

function switchChat(chatId) {
    if (!chats[chatId]) return;

    activeChatId = chatId;
    const chat = chats[chatId];

    // Update panels visibility
    welcomeScreen.style.display = 'none';
    chatPanels.classList.add('active');
    inputArea.style.display = '';
    closeChatBtn.style.display = '';

    document.querySelectorAll('.chat-panel').forEach(p => p.classList.remove('active'));
    chat.panel.classList.add('active');

    document.querySelectorAll('.chat-tab').forEach(t => t.classList.remove('active'));
    chat.tab.classList.add('active');

    // Update header
    chatTitle.textContent = chat.name;
    chatSubtitle.textContent = 'Workflow ' + chat.workflow;

    messageInput.focus();
    scrollToBottom(chat.panel);
}

function closeChat(chatId) {
    const chat = chats[chatId];
    if (!chat) return;

    // Close WebSocket
    if (chat.ws && chat.ws.readyState === WebSocket.OPEN) {
        chat.ws.close();
    }

    // Remove DOM elements
    chat.panel.remove();
    chat.tab.remove();

    delete chats[chatId];

    // Switch to another chat or show welcome
    const remaining = Object.keys(chats);
    if (remaining.length > 0) {
        switchChat(remaining[remaining.length - 1]);
    } else {
        activeChatId = null;
        welcomeScreen.style.display = '';
        chatPanels.classList.remove('active');
        inputArea.style.display = 'none';
        closeChatBtn.style.display = 'none';
        chatTitle.textContent = 'AI Automation';
        chatSubtitle.textContent = 'Select a workflow to start';
        emptyChats.style.display = '';
    }
}

function updateConnectionStatus(connected) {
    if (connected) {
        connectionStatus.classList.add('connected');
        statusEl.textContent = 'Connected';
    } else {
        connectionStatus.classList.remove('connected');
        statusEl.textContent = 'Disconnected';
    }
}

// ─── Message Handling ───

function handleServerMessage(chatId, data) {
    const chat = chats[chatId];
    if (!chat) return;

    // Remove typing indicator if present
    const typing = chat.panel.querySelector('.typing-row');
    if (typing) typing.remove();

    switch (data.type) {
        case 'session':
            chat.sessionId = data.session_id;
            break;
        case 'workflow_started':
            // Already handled by tab name
            break;
        case 'message':
            appendMessage(chat.panel, data.text, 'bot');
            break;
        case 'status':
            appendMessage(chat.panel, data.text || data.detail, 'status');
            break;
        case 'sources':
            appendSources(chat.panel, data.data);
            break;
        case 'images':
            appendImages(chat.panel, data.urls);
            break;
        case 'prompt':
            appendPrompt(chatId, chat.panel, data.text, data.options);
            break;
        case 'file_ready':
            appendFileReady(chat.panel, data.filename, data.drive_url);
            break;
        case 'error':
            appendMessage(chat.panel, data.text, 'error');
            break;
    }

    if (chatId === activeChatId) {
        scrollToBottom(chat.panel);
    }
}

function appendMessage(panel, text, type) {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.textContent = text;
    panel.appendChild(div);
}

function appendSources(panel, sources) {
    if (!sources || !sources.length) return;
    const container = document.createElement('div');
    container.className = 'message bot';
    let html = '<div class="sources-list"><strong>Sources found:</strong>';
    sources.forEach((s, i) => {
        html += `<div class="source-item">${i+1}. <a href="${esc(s.link)}" target="_blank" rel="noopener">${esc(s.title)}</a><div class="snippet">${esc(s.snippet||'')}</div></div>`;
    });
    html += '</div>';
    container.innerHTML = html;
    panel.appendChild(container);
}

function appendImages(panel, urls) {
    if (!urls || !urls.length) return;
    const container = document.createElement('div');
    container.className = 'message bot';
    let html = '<div class="images-grid">';
    urls.forEach(url => {
        if (url) html += `<img src="${esc(url)}" alt="" onerror="this.style.display='none'" loading="lazy">`;
    });
    html += '</div>';
    container.innerHTML = html;
    panel.appendChild(container);
}

function appendPrompt(chatId, panel, text, options) {
    const container = document.createElement('div');
    container.className = 'message bot';
    let html = `<div>${esc(text)}</div>`;
    if (options && options.length) {
        html += '<div class="options">';
        options.forEach(opt => {
            html += `<button class="option-btn" data-option="${esc(opt)}">${esc(opt)}</button>`;
        });
        html += '</div>';
    }
    container.innerHTML = html;
    panel.appendChild(container);

    container.querySelectorAll('.option-btn').forEach(btn => {
        btn.addEventListener('click', () => sendToChat(chatId, btn.dataset.option));
    });
}

function appendFileReady(panel, filename, driveUrl) {
    const div = document.createElement('div');
    div.className = 'file-ready';
    div.innerHTML = `Saved to Google Drive: <a href="${esc(driveUrl)}" target="_blank" rel="noopener">${esc(filename)}</a>`;
    panel.appendChild(div);
}

function showTyping(panel) {
    // Don't duplicate
    if (panel.querySelector('.typing-row')) return;
    const row = document.createElement('div');
    row.className = 'typing-row';
    row.innerHTML = '<div class="dot"></div><div class="dot"></div><div class="dot"></div>';
    panel.appendChild(row);
    scrollToBottom(panel);
}

// ─── Sending Messages ───

function sendToChat(chatId, text) {
    const chat = chats[chatId];
    if (!chat || !text || !text.trim()) return;
    if (chat.ws.readyState !== WebSocket.OPEN) return;

    appendMessage(chat.panel, text, 'user');
    chat.ws.send(JSON.stringify({ type: 'message', text: text }));
    showTyping(chat.panel);
    scrollToBottom(chat.panel);
}

function sendMessage(text) {
    if (!activeChatId) return;
    sendToChat(activeChatId, text);
    messageInput.value = '';
}

async function uploadFiles(files) {
    if (!activeChatId) return;
    const chat = chats[activeChatId];
    if (!chat || !chat.sessionId) return;

    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);
        appendMessage(chat.panel, `Uploading: ${file.name}...`, 'status');

        try {
            const resp = await fetch(`/upload/${chat.sessionId}`, { method: 'POST', body: formData });
            if (resp.ok) {
                chat.ws.send(JSON.stringify({ type: 'upload_complete', filename: file.name }));
            } else {
                appendMessage(chat.panel, `Failed to upload: ${file.name}`, 'error');
            }
        } catch (err) {
            appendMessage(chat.panel, `Upload error: ${err.message}`, 'error');
        }
    }

    showTyping(chat.panel);
    chat.ws.send(JSON.stringify({ type: 'message', text: 'Files uploaded' }));
    scrollToBottom(chat.panel);
}

// ─── Helpers ───

function scrollToBottom(panel) {
    requestAnimationFrame(() => { panel.scrollTop = panel.scrollHeight; });
}

function esc(str) {
    const d = document.createElement('div');
    d.textContent = str;
    return d.innerHTML;
}

// ─── Event Listeners ───

// Send
sendBtn.addEventListener('click', () => sendMessage(messageInput.value));
messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(messageInput.value);
    }
});

// Upload
uploadBtn.addEventListener('click', () => fileInput.click());
fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        // Snapshot the FileList to a plain Array BEFORE clearing the input,
        // otherwise `fileInput.value = ''` empties the live FileList mid-upload
        // and only the first file gets sent.
        const filesCopy = Array.from(e.target.files);
        fileInput.value = '';
        uploadFiles(filesCopy);
    }
});

// Sidebar toggle
sidebarToggle.addEventListener('click', () => sidebar.classList.toggle('collapsed'));

// Close active chat
closeChatBtn.addEventListener('click', () => { if (activeChatId) closeChat(activeChatId); });

// New chat buttons (sidebar)
document.querySelectorAll('.new-chat-btn').forEach(btn => {
    btn.addEventListener('click', () => createChat(btn.dataset.workflow));
});

// Quick action buttons (welcome screen)
document.querySelectorAll('.quick-btn').forEach(btn => {
    btn.addEventListener('click', () => createChat(btn.dataset.workflow));
});

// Drag and drop
const chatMain = document.querySelector('.chat-main');
chatMain.addEventListener('dragenter', (e) => { e.preventDefault(); dropOverlay.classList.add('active'); });
dropOverlay.addEventListener('dragleave', (e) => { if (e.target === dropOverlay) dropOverlay.classList.remove('active'); });
dropOverlay.addEventListener('dragover', (e) => e.preventDefault());
dropOverlay.addEventListener('drop', (e) => {
    e.preventDefault();
    dropOverlay.classList.remove('active');
    if (e.dataTransfer.files.length > 0) uploadFiles(Array.from(e.dataTransfer.files));
});
