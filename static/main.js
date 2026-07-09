// DOM Elements
const urlInput = document.getElementById('urlInput');
const clearBtn = document.getElementById('clearBtn');
const downloadBtn = document.getElementById('downloadBtn');
const resultArea = document.getElementById('resultArea');
const loadingOverlay = document.getElementById('loadingOverlay');
const inputWrapper = document.getElementById('inputWrapper');

// 1. Live URL Validation
urlInput.addEventListener('input', () => {
    const value = urlInput.value;
    clearBtn.classList.toggle('hidden', !value);
    
    if (value === '') {
        inputWrapper.classList.remove('valid', 'invalid');
    } else {
        const isValid = value.includes('tiktok.com');
        inputWrapper.classList.toggle('valid', isValid);
        inputWrapper.classList.toggle('invalid', !isValid);
    }
});

// 2. Paste Button Logic
async function pasteLink() {
    try {
        const text = await navigator.clipboard.readText();
        urlInput.value = text;
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
    inputWrapper.classList.remove('valid', 'invalid');
}

// 4. Process Download
async function processDownload() {
    if (!urlInput.value || !urlInput.value.includes('tiktok.com')) {
        alert("Please enter a valid TikTok URL");
        return;
    }

    // UI State: Show Loading
    loadingOverlay.style.display = 'flex';
    downloadBtn.disabled = true;

    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ url: urlInput.value })
        });

        const data = await response.json();
        resultArea.innerHTML = ''; // Clear previous

        if (data.success) {
            let html = '';
            
            // Photo Mode
            if (data.is_photo) {
                html = `
                    <div class="glass p-6 mt-6 animate-fade-in">
                        <h3 class="font-bold text-xl mb-2">${data.title}</h3>
                        <p class="text-cyan-400 mb-6">Author: @${data.author}</p>
                        <div class="grid grid-cols-2 gap-4">
                            ${data.images.map((img, index) => `
                                <a href="${img}" download="tiktok_photo_${index + 1}.jpg" target="_blank" class="bg-slate-800 hover:bg-cyan-600 py-3 rounded-xl text-center font-bold transition">Photo ${index + 1}</a>
                            `).join('')}
                        </div>
                    </div>
                `;
            } 
            // Video Mode
            else {
                html = `
                    <div class="glass p-6 mt-6 animate-fade-in">
                        <div class="flex gap-4 items-center mb-6">
                            <img src="${data.thumbnail}" loading="lazy" class="w-20 h-20 rounded-xl object-cover border border-slate-700">
                            <div>
                                <h3 class="font-bold text-lg">${data.title.substring(0, 40)}...</h3>
                                <p class="text-cyan-400 text-sm">@${data.author}</p>
                            </div>
                        </div>
                        <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                            <a href="${data.hd_url}" target="_blank" class="btn-gradient py-3 rounded-xl text-center font-bold">HD Download</a>
                            <a href="${data.sd_url}" target="_blank" class="bg-slate-800 hover:bg-slate-700 py-3 rounded-xl text-center font-bold transition">SD Download</a>
                        </div>
                    </div>
                `;
            }
            resultArea.innerHTML = html;
        } else {
            resultArea.innerHTML = `
                <div class="glass border-red-500/20 p-6 mt-6 text-center animate-fade-in">
                    <p class="text-red-400 font-bold">Error</p>
                    <p class="text-slate-300 mt-2">${data.error}</p>
                </div>
            `;
        }
    } catch (error) {
        resultArea.innerHTML = `<div class="text-red-500 text-center mt-6">System error. Please try again later.</div>`;
    } finally {
        loadingOverlay.style.display = 'none';
        downloadBtn.disabled = false;
    }
}
