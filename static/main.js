// DOM Elements
const urlInput = document.getElementById('urlInput');
const clearBtn = document.getElementById('clearBtn');
const downloadBtn = document.getElementById('downloadBtn');
const resultArea = document.getElementById('resultArea');

// Helper: XSS থেকে বাঁচার জন্য text safe করা
function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(text));
    return div.innerHTML;
}

// 1. URL Validation
urlInput.addEventListener('input', () => {
    clearBtn.classList.toggle('hidden', !urlInput.value);
    const isValid = urlInput.value.includes('tiktok.com');
    urlInput.parentElement.style.borderColor = urlInput.value === '' ? '#374151' : (isValid ? '#06b6d4' : '#ef4444');
});

// 2. Paste Button Logic
async function pasteLink() {
    try {
        const text = await navigator.clipboard.readText();
        urlInput.value = text;
        clearBtn.classList.remove('hidden');
        urlInput.dispatchEvent(new Event('input'));
    } catch (err) {
        alert('Clipboard access denied. Please paste manually.');
    }
}

// 3. Clear Button Logic
function clearInput() {
    urlInput.value = '';
    clearBtn.classList.add('hidden');
    resultArea.innerHTML = '';
    urlInput.parentElement.style.borderColor = '#374151';
}

// 4. Download Process
async function processDownload() {
    const url = urlInput.value.trim();
    if (!url) return;

    // সহজ ক্লায়েন্ট-সাইড চেক
    if (!url.includes('tiktok.com')) {
        resultArea.innerHTML = `<div class="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-center text-red-400 mt-6">Please enter a valid TikTok URL.</div>`;
        return;
    }

    // UI State: Loading
    downloadBtn.disabled = true;
    downloadBtn.innerText = 'Processing...';
    resultArea.innerHTML = `<div class="flex justify-center p-10"><div class="spinner"></div></div>`;

    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ url: url })
        });

        const data = await response.json();

        if (data.success) {
            let html = '';

            // FIX: escapeHtml দিয়ে XSS রোধ করা হয়েছে
            if (data.is_photo) {
                const safeTitle = escapeHtml(data.title || 'TikTok Photos');
                const safeAuthor = escapeHtml(data.author || 'Unknown');
                html = `
                    <div class="glass p-6 mt-6 animate-fade-in">
                        <h3 class="font-bold text-lg mb-2">${safeTitle}</h3>
                        <p class="text-cyan-400 text-sm mb-6">Author: @${safeAuthor}</p>
                        <div class="grid grid-cols-2 gap-4">
                            ${data.images.map((img, index) => `
                                <a href="${escapeHtml(img)}" download="tiktok_photo_${index + 1}.jpg" target="_blank" rel="noopener noreferrer" class="bg-slate-700 py-3 px-2 rounded-xl text-center font-bold hover:bg-cyan-600 transition truncate">
                                    📥 Photo ${index + 1}
                                </a>
                            `).join('')}
                        </div>
                    </div>
                `;
            } else {
                const safeTitle = escapeHtml((data.title || 'Untitled Video').substring(0, 60));
                const safeAuthor = escapeHtml(data.author || 'Unknown');
                const safeThumbnail = escapeHtml(data.thumbnail || '');
                const safeHdUrl = escapeHtml(data.hd_url || '');
                const safeSdUrl = escapeHtml(data.sd_url || '');

                html = `
                    <div class="glass p-6 mt-6 animate-fade-in">
                        <div class="flex gap-4 items-center">
                            ${safeThumbnail ? `<img src="${safeThumbnail}" class="w-24 h-24 rounded-xl object-cover border border-slate-700" alt="Thumbnail" onerror="this.style.display='none'">` : ''}
                            <div>
                                <h3 class="font-bold text-lg">${safeTitle}</h3>
                                <p class="text-cyan-400 text-sm">@${safeAuthor}</p>
                            </div>
                        </div>
                        <!-- FIX: download attribute যোগ করা হয়েছে — নতুন ট্যাব না খুলে এখন সরাসরি ডাউনলোড হবে -->
                        <div class="grid grid-cols-2 gap-4 mt-6">
                            <a href="${safeHdUrl}" download="tiktok_hd.mp4" target="_blank" rel="noopener noreferrer" class="btn-gradient py-3 rounded-xl text-center font-bold">📥 HD Download</a>
                            <a href="${safeSdUrl}" download="tiktok_sd.mp4" target="_blank" rel="noopener noreferrer" class="bg-slate-700 py-3 rounded-xl text-center font-bold hover:bg-slate-600 transition">📥 SD Download</a>
                        </div>
                    </div>
                `;
            }
            resultArea.innerHTML = html;
        } else {
            resultArea.innerHTML = `<div class="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-center text-red-400 mt-6">${escapeHtml(data.error || 'Something went wrong.')}</div>`;
        }
    } catch (error) {
        resultArea.innerHTML = `<div class="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-center text-red-400 mt-6">Network error. Please check your connection and try again.</div>`;
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.innerText = 'Download Video';
    }
}

// Enter key দিয়েও ডাউনলোড করা যাবে
urlInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') processDownload();
});
