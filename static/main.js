// DOM Elements
const urlInput = document.getElementById('urlInput');
const clearBtn = document.getElementById('clearBtn');
const downloadBtn = document.getElementById('downloadBtn');
const resultArea = document.getElementById('resultArea');

// 1. URL Validation & Auto-Paste
urlInput.addEventListener('input', () => {
    // দেখাও বা লুকাও Clear বাটন
    clearBtn.classList.toggle('hidden', !urlInput.value);
    
    // ভ্যালিডেশন (টিকটক লিঙ্ক চেক)
    const isValid = urlInput.value.includes('tiktok.com');
    urlInput.parentElement.style.borderColor = urlInput.value === '' ? '#374151' : (isValid ? '#06b6d4' : '#ef4444');
});

// 2. Paste Button Logic
async function pasteLink() {
    try {
        const text = await navigator.clipboard.readText();
        urlInput.value = text;
        clearBtn.classList.remove('hidden');
        // ট্রিগার ইনপুট ইভেন্ট যাতে ভ্যালিডেশন চেক হয়
        urlInput.dispatchEvent(new Event('input'));
    } catch (err) {
        console.error('Failed to paste: ', err);
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
    if (!urlInput.value) return;

    // UI State: Loading
    downloadBtn.disabled = true;
    downloadBtn.innerText = 'Processing...';
    resultArea.innerHTML = `<div class="flex justify-center p-10"><div class="spinner"></div></div>`;

    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ url: urlInput.value })
        });

        const data = await response.json();

        if (data.success) {
            // Success State
            resultArea.innerHTML = `
                <div class="glass p-6 mt-6 animate-fade-in">
                    <div class="flex gap-4 items-center">
                        <img src="${data.thumbnail}" class="w-24 h-24 rounded-xl object-cover border border-slate-700">
                        <div>
                            <h3 class="font-bold text-lg">${data.title.substring(0, 50)}...</h3>
                            <p class="text-cyan-400 text-sm">@${data.author}</p>
                        </div>
                    </div>
                    <div class="grid grid-cols-2 gap-4 mt-6">
                        <a href="${data.hd_url}" target="_blank" class="btn-gradient py-3 rounded-xl text-center font-bold">HD Download</a>
                        <a href="${data.sd_url}" target="_blank" class="bg-slate-700 py-3 rounded-xl text-center font-bold hover:bg-slate-600 transition">SD Download</a>
                    </div>
                </div>
            `;
        } else {
            // Error State
            resultArea.innerHTML = `
                <div class="bg-red-500/10 border border-red-500/20 p-4 rounded-xl text-center text-red-400 mt-6">
                    ${data.error}
                </div>
            `;
        }
    } catch (error) {
        resultArea.innerHTML = `<div class="text-red-500 text-center mt-6">Something went wrong. Please try again.</div>`;
    } finally {
        downloadBtn.disabled = false;
        downloadBtn.innerText = 'Download Video';
    }
}

// Auto-Paste on Load (যদি ক্লিপবোর্ডে লিঙ্ক থাকে)
window.onload = async () => {
    try {
        const text = await navigator.clipboard.readText();
        if (text.includes('tiktok.com')) {
            urlInput.value = text;
            clearBtn.classList.remove('hidden');
            urlInput.dispatchEvent(new Event('input'));
        }
    } catch (e) {
        console.log('Permission denied for clipboard');
    }
};

