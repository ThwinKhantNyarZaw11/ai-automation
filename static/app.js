// WebSocket chat client for AI Automation System

let ws = null;
let sessionId = null;

const messagesEl = document.getElementById('messages');
const messageInput = document.getElementById('messageInput');
const sendBtn = document.getElementById('sendBtn');
const statusEl = document.getElementById('status');
const uploadBtn = document.getElementById('uploadBtn');
const fileInput = document.getElementById('fileInput');

function connect() {
    const protocol = location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${location.host}/ws`);

    ws.onopen = () => {
        statusEl.textContent = 'Connected';
        statusEl.classList.add('connected');
    };

    ws.onclose = () => {
        statusEl.textContent = 'Disconnected';
        statusEl.classList.remove('connected');
        // Reconnect after 3 seconds
        setTimeout(connect, 3000);
    };

    ws.onerror = () => {
        statusEl.textContent = 'Connection error';
        statusEl.classList.remove('connected');
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleServerMessage(data);
    };
}

function handleServerMessage(data) {
    switch (data.type) {
        case 'session':
            sessionId = data.session_id;
            break;

        case 'message':
            addMessage(data.text, 'bot');
            break;

        case 'status':
            addMessage(data.text || data.detail, 'status');
            break;

        case 'sources':
            addSources(data.data);
            break;

        case 'images':
            addImages(data.urls);
            break;

        case 'prompt':
            addPrompt(data.text, data.options);
            break;

        case 'file_ready':
            addFileReady(data.filename, data.drive_url);
            break;

        case 'error':
            addMessage(data.text, 'error');
            break;
    }

    scrollToBottom();
}

function addMessage(text, type = 'bot') {
    const div = document.createElement('div');
    div.className = `message ${type}`;
    div.textContent = text;
    messagesEl.appendChild(div);
}

function addSources(sources) {
    if (!sources || sources.length === 0) return;

    const container = document.createElement('div');
    container.className = 'message bot';

    let html = '<div class="sources-list"><strong>Sources found:</strong>';
    sources.forEach((s, i) => {
        html += `<div class="source-item">
            ${i + 1}. <a href="${s.link}" target="_blank">${s.title}</a>
            <div class="snippet">${s.snippet || ''}</div>
        </div>`;
    });
    html += '</div>';

    container.innerHTML = html;
    messagesEl.appendChild(container);
}

function addImages(urls) {
    if (!urls || urls.length === 0) return;

    const container = document.createElement('div');
    container.className = 'message bot';

    let html = '<div class="images-grid">';
    urls.forEach(url => {
        if (url) {
            html += `<img src="${url}" alt="Related image" onerror="this.style.display='none'" loading="lazy">`;
        }
    });
    html += '</div>';

    container.innerHTML = html;
    messagesEl.appendChild(container);
}

function addPrompt(text, options) {
    const container = document.createElement('div');
    container.className = 'message bot';

    let html = `<div>${text}</div>`;
    if (options && options.length > 0) {
        html += '<div class="options">';
        options.forEach(opt => {
            html += `<button class="option-btn" onclick="sendOption('${opt}')">${opt}</button>`;
        });
        html += '</div>';
    }

    container.innerHTML = html;
    messagesEl.appendChild(container);
}

function addFileReady(filename, driveUrl) {
    const div = document.createElement('div');
    div.className = 'file-ready';
    div.innerHTML = `Saved to Google Drive: <a href="${driveUrl}" target="_blank">${filename}</a>`;
    messagesEl.appendChild(div);
}

function sendMessage(text) {
    if (!text.trim() || !ws || ws.readyState !== WebSocket.OPEN) return;

    addMessage(text, 'user');
    ws.send(JSON.stringify({ type: 'message', text: text }));
    messageInput.value = '';
}

function sendOption(option) {
    sendMessage(option);
}

async function uploadFiles(files) {
    if (!sessionId) return;

    for (const file of files) {
        const formData = new FormData();
        formData.append('file', file);

        addMessage(`Uploading: ${file.name}...`, 'status');

        try {
            const response = await fetch(`/upload/${sessionId}`, {
                method: 'POST',
                body: formData,
            });

            if (response.ok) {
                ws.send(JSON.stringify({
                    type: 'upload_complete',
                    filename: file.name,
                }));
            } else {
                addMessage(`Failed to upload: ${file.name}`, 'error');
            }
        } catch (err) {
            addMessage(`Upload error: ${err.message}`, 'error');
        }
    }

    // After all files uploaded, send a message to trigger processing
    ws.send(JSON.stringify({ type: 'message', text: 'Files uploaded' }));
}

function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
}

// Event listeners
sendBtn.addEventListener('click', () => sendMessage(messageInput.value));

messageInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage(messageInput.value);
    }
});

uploadBtn.addEventListener('click', () => fileInput.click());

fileInput.addEventListener('change', (e) => {
    if (e.target.files.length > 0) {
        uploadFiles(e.target.files);
        fileInput.value = '';
    }
});

// Drag and drop
messagesEl.addEventListener('dragover', (e) => {
    e.preventDefault();
    messagesEl.style.background = '#252525';
});

messagesEl.addEventListener('dragleave', () => {
    messagesEl.style.background = '';
});

messagesEl.addEventListener('drop', (e) => {
    e.preventDefault();
    messagesEl.style.background = '';
    if (e.dataTransfer.files.length > 0) {
        uploadFiles(e.dataTransfer.files);
    }
});

// Start connection
connect();
