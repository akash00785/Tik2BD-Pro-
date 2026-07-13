// =============================================
//  Tik2BD Pro — main.js
// =============================================

const urlInput    = document.getElementById('urlInput');
const clearBtn    = document.getElementById('clearBtn');
const pasteBtn    = document.getElementById('pasteBtn');
const downloadBtn = document.getElementById('downloadBtn');
const downloadBtnText = document.getElementById('downloadBtnText');
const resultArea  = document.getElementById('resultArea');
const inputWrapper = document.getElementById('inputWrapper');

// ===== XSS Protection =====
function escapeHtml(text) {
    const div = document.createElement('div');
    div.appendChild(document.createTextNode(String(text)));
    return div.innerHTML;
}

// ===== Normal (SD) — RapidAPI থেকে পাওয়া CDN লিংক সরাসরি নতুন ট্যাবে
// খোলা হয়, ঠিক HD-এর মতোই — Render সার্ভারের মধ্য দিয়ে ফাইলটা যায় না,
// তাই bandwidth কাটে না। ব্যবহারকারীকে ৩-ডট মেনু থেকে ম্যানুয়ালি
// "Save video" করতে হয় (cross-origin URL-এ <a download> কাজ করে না)।
function openNormalDownload(sdUrl, btn) {
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'খোলা হয়েছে!';
    }
    window.open(sdUrl, '_blank', 'noopener,noreferrer');
    showToast('ভিডিও নতুন ট্যাবে খুলেছে — উপরের ৩-ডট মেনু থেকে "Save video" করুন।', 'info', 5000);
    setTimeout(() => {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Normal Download';
        }
    }, 3000);
}

// ===== Toast Notification System =====
function showToast(message, type = 'info', duration = 3500) {
    const container = document.getElementById('toastContainer');
    const icons = {
        success: `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>`,
        error:   `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="15" y1="9" x2="9" y2="15"/><line x1="9" y1="9" x2="15" y2="15"/></svg>`,
        info:    `<svg class="toast-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>`,
    };
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `${icons[type] || icons.info}<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);
    setTimeout(() => {
        toast.classList.add('hide');
        toast.addEventListener('animationend', () => toast.remove());
    }, duration);
}

// ===== Animated Counter =====
function animateCounter(el, target, duration = 1800) {
    const suffix = el.dataset.suffix || '';
    const isPercent = target <= 100 && el.closest('.stat-item')?.querySelector('.stat-label')?.textContent.includes('%');
    let start = 0;
    const step = target / (duration / 16);
    const timer = setInterval(() => {
        start = Math.min(start + step, target);
        const val = Math.floor(start);
        if (target >= 1000000) {
            el.textContent = (val / 1000000).toFixed(1) + 'M+';
        } else if (target >= 1000) {
            el.textContent = (val / 1000).toFixed(0) + 'K+';
        } else {
            el.textContent = val + (isPercent ? '%' : '');
        }
        if (start >= target) clearInterval(timer);
    }, 16);
}

function startCounters() {
    document.querySelectorAll('.stat-number[data-target]').forEach(el => {
        const target = parseInt(el.dataset.target, 10);
        animateCounter(el, target);
    });
}

// Run counters when hero stats come into view
const observer = new IntersectionObserver(entries => {
    entries.forEach(e => { if (e.isIntersecting) { startCounters(); observer.disconnect(); } });
}, { threshold: 0.3 });
const statsEl = document.querySelector('.hero-stats');
if (statsEl) observer.observe(statsEl);

// ===== Input Validation =====
urlInput.addEventListener('input', () => {
    const val = urlInput.value.trim();
    clearBtn.classList.toggle('hidden', !val);
    if (!val) {
        inputWrapper.className = 'input-wrapper';
    } else if (val.includes('tiktok.com')) {
        inputWrapper.className = 'input-wrapper valid';
    } else {
        inputWrapper.className = 'input-wrapper invalid';
    }
});

// ===== Paste Button =====
async function pasteLink() {
    try {
        const text = await navigator.clipboard.readText();
        urlInput.value = text;
        urlInput.dispatchEvent(new Event('input'));
        showToast('Link pasted!', 'success', 2000);
    } catch {
        showToast('Clipboard access denied — paste manually.', 'error');
    }
}

// ===== Clear Input =====
function clearInput() {
    urlInput.value = '';
    clearBtn.classList.add('hidden');
    inputWrapper.className = 'input-wrapper';
    resultArea.innerHTML = '';
}

// ===== Loading State =====
function setLoading(loading) {
    downloadBtn.disabled = loading;
    if (loading) {
        downloadBtnText.textContent = 'Processing...';
        resultArea.innerHTML = `
            <div class="loading-wrap">
                <div class="spinner"></div>
                <span>Fetching video info...</span>
            </div>`;
    } else {
        downloadBtnText.textContent = 'Download Video';
    }
}

// ===== HD daily-limit UI =====
function renderHdRemainingBadge(hdLimit) {
    // লক না হওয়া অবস্থায় সবসময় "কতটা বাকি" দেখানো হয়, যাতে ব্যবহারকারী
    // বুঝতে পারে একটার পর একটা ডাউনলোড করলে লিমিট কমছে।
    if (!hdLimit || hdLimit.locked) return '';
    return `<span class="hd-remaining-badge">HD বাকি আছে: ${hdLimit.remaining_free}/${hdLimit.limit}</span>`;
}

function renderHdLockBlock(hdLimit) {
    if (!hdLimit || !hdLimit.locked) return '';

    const hours = Math.max(1, Math.ceil((hdLimit.resets_in_seconds || 0) / 3600));

    return `
        <div class="hd-lock-box" id="hdLockBox" data-used="${hdLimit.used}" data-limit="${hdLimit.limit}">
            <p class="hd-lock-msg">
                🔒 আজকের ফ্রি HD লিমিট শেষ (${hdLimit.used}/${hdLimit.limit})। প্রায় ${hours} ঘণ্টা পর আবার পাবেন, অথবা এখনই বিজ্ঞাপন দেখে আনলক করুন।
            </p>
            <div id="hdUnlockArea"></div>
        </div>`;
}

async function initHdUnlockArea() {
    const area = document.getElementById('hdUnlockArea');
    if (!area) return;

    let cfg;
    try {
        cfg = await (await fetch('/ads/config')).json();
    } catch {
        return;
    }

    if (!cfg.enabled) {
        area.innerHTML = `<p class="hd-lock-sub">বিজ্ঞাপন শীঘ্রই আসছে — এখন আনলক করার উপায় নেই।</p>`;
        return;
    }

    area.innerHTML = `<button class="result-btn hd" id="watchAdBtn">বিজ্ঞাপন দেখে আনলক করুন</button>`;
    document.getElementById('watchAdBtn').addEventListener('click', () => startAdUnlockFlow(cfg));
}

async function startAdUnlockFlow(cfg) {
    const area = document.getElementById('hdUnlockArea');
    if (!area) return;

    let startResp;
    try {
        startResp = await (await fetch('/ads/unlock/start', { method: 'POST' })).json();
    } catch {
        showToast('Network error. Please try again.', 'error');
        return;
    }

    const token = startResp.token;
    window.open(cfg.ad_link, '_blank', 'noopener,noreferrer');

    let remaining = cfg.wait_seconds;
    area.innerHTML = `<button class="result-btn sd" id="claimAdBtn" disabled>অপেক্ষা করুন... (${remaining}s)</button>`;
    const claimBtn = document.getElementById('claimAdBtn');

    const timer = setInterval(() => {
        remaining -= 1;
        if (remaining <= 0) {
            clearInterval(timer);
            claimBtn.disabled = false;
            claimBtn.textContent = 'ডাউনলোড আনলক করুন';
        } else {
            claimBtn.textContent = `অপেক্ষা করুন... (${remaining}s)`;
        }
    }, 1000);

    claimBtn.addEventListener('click', async () => {
        claimBtn.disabled = true;
        claimBtn.textContent = 'যাচাই করা হচ্ছে...';
        try {
            const res = await fetch('/ads/unlock/claim', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ token }),
            });
            const result = await res.json();
            if (result.success) {
                showToast('আনলক সফল! এখন আবার HD ডাউনলোড করুন।', 'success');
                area.innerHTML = `<p class="hd-lock-sub">✅ আনলক হয়েছে — উপরের লিংকটা আবার সাবমিট করুন।</p>`;
            } else {
                showToast(result.error || 'আনলক করা যায়নি।', 'error');
                claimBtn.disabled = false;
                claimBtn.textContent = 'আবার চেষ্টা করুন';
            }
        } catch {
            showToast('Network error. Please try again.', 'error');
            claimBtn.disabled = false;
            claimBtn.textContent = 'আবার চেষ্টা করুন';
        }
    });
}

// ===== Render Result =====
function renderVideoResult(data, sourceUrl) {
    const safeTitle  = escapeHtml((data.title  || 'Untitled Video').substring(0, 80));
    const safeAuthor = escapeHtml(data.author   || 'Unknown');
    const safeThumbnail = escapeHtml(data.thumbnail || '');
    // Normal (SD) লিংক RapidAPI থেকে প্রিভিউর সময়ই চলে আসে, তাই বাটনে
    // ক্লিক করলে সরাসরি ওপেন করা যায় — আলাদা resolve কলের দরকার নেই।
    const normalEnabled = Boolean(data.sd_available && data.sd_url);

    const thumbHtml = safeThumbnail
        ? `<img class="result-thumb" src="${safeThumbnail}" alt="Thumbnail" onerror="this.style.display='none'">`
        : '';

    const hdBtn = data.hd_available
        ? `<button type="button" class="result-btn hd" id="hdResolveBtn">
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
               HD Download
           </button>`
        : `<span class="result-btn sd" style="opacity:0.4;cursor:default;">${data.hd_locked ? 'HD Locked' : 'HD Unavailable'}</span>`;

    const hdRemainingBadge = renderHdRemainingBadge(data.hd_limit);

    const sdBtn = normalEnabled
        ? `<button type="button" class="result-btn sd" id="normalResolveBtn">
               <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
               Normal Download
           </button>`
        : '';

    const hdLockHtml = renderHdLockBlock(data.hd_limit);

    resultArea.innerHTML = `
        <div class="result-card">
            <div class="result-meta">
                ${thumbHtml}
                <div class="result-info">
                    <h3>${safeTitle}</h3>
                    <span class="result-author">@${safeAuthor}</span>
                </div>
            </div>
            <div class="result-buttons">
                ${hdBtn}
                ${sdBtn}
            </div>
            ${hdRemainingBadge}
            ${hdLockHtml}
        </div>`;
    showToast('Video found! Choose your quality.', 'success');

    if (data.hd_available) {
        document.getElementById('hdResolveBtn')?.addEventListener('click', () => resolveAndDownloadHd(sourceUrl));
    }
    if (normalEnabled) {
        const normalBtn = document.getElementById('normalResolveBtn');
        normalBtn?.addEventListener('click', () => openNormalDownload(data.sd_url, normalBtn));
    }
    if (data.hd_locked) initHdUnlockArea();
}

// ===== Resolve HD link only when the user actually clicks HD Download =====
// এটাই RapidAPI-কে ডাকার একমাত্র জায়গা — তাই যারা শুধু প্রিভিউ দেখে HD
// ডাউনলোড করে না, তাদের জন্য RapidAPI কোটা খরচ হয় না।

// দ্রুত ডাবল-ট্যাপ/ডাবল-ক্লিক করলে একই ভিডিওর জন্য দুইটা আলাদা HD
// ডাউনলোড রিকোয়েস্ট চলে যেত (প্রতিটাই আলাদা করে ফ্রি লিমিট কোটা কেটে
// নিত) — কারণ বাটন disable হওয়ার আগেই দ্বিতীয় ক্লিকটা রেজিস্টার হয়ে
// যাচ্ছিল, বিশেষ করে মোবাইলে দ্রুত ডাবল-ট্যাপে। এই সিঙ্ক্রোনাস flag-টা
// (btn.disabled-এর উপর নির্ভর না করে) প্রথম লাইনেই সেট হয়, তাই দ্বিতীয়
// ক্লিক ইভেন্ট যতই দ্রুত আসুক, সেটা সাথে সাথে বাতিল হয়ে যায়।
let hdDownloadBusy = false;

async function resolveAndDownloadHd(sourceUrl) {
    if (hdDownloadBusy) {
        showToast('একটা HD ডাউনলোড ইতিমধ্যে চলছে — অপেক্ষা করো।', 'info', 2000);
        return;
    }
    hdDownloadBusy = true;

    const btn = document.getElementById('hdResolveBtn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'খোঁজা হচ্ছে...';
    }
    try {
        const res = await fetch('/hd/resolve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url: sourceUrl }),
        });
        const result = await res.json();

        if (!result.success) {
            hdDownloadBusy = false;
            if (result.error === 'locked') {
                showToast('আজকের ফ্রি HD লিমিট শেষ।', 'error');
                if (btn) {
                    const wrap = document.createElement('span');
                    wrap.innerHTML = renderHdLockBlock(result.hd_limit);
                    btn.replaceWith(...wrap.children);
                    initHdUnlockArea();
                }
            } else {
                showToast(result.error || 'HD লিংক পাওয়া যায়নি।', 'error');
                if (btn) {
                    btn.disabled = false;
                    btn.textContent = 'HD Download';
                }
            }
            return;
        }

        // সরাসরি TikTok CDN-এ নতুন ট্যাবে খোলা হয় — আমাদের সার্ভারের মধ্য
        // দিয়ে ফাইলটা আর যায় না, তাই Render-এর bandwidth কোটা থেকে কিছু
        // কাটে না। ট্রেড-অফ: cross-origin URL-এ <a download> কাজ করে না,
        // তাই ভিডিওটা নতুন ট্যাবে চলতে শুরু করবে — ব্যবহারকারীকে ৩-ডট
        // মেনু থেকে "Save video" করতে হবে।
        window.open(result.hd_url, '_blank', 'noopener,noreferrer');
        showToast('ভিডিও নতুন ট্যাবে খুলেছে — উপরের ৩-ডট মেনু থেকে "Save video" করুন।', 'info', 5000);

        if (btn) {
            btn.textContent = 'খোলা হয়েছে!';
        }
        if (result.hd_limit) {
            const badge = document.querySelector('.hd-remaining-badge');
            if (badge) badge.outerHTML = renderHdRemainingBadge(result.hd_limit);
        }

        // আসল ফাইল ডাউনলোড ব্রাউজারে শুরু হওয়ার পরও কিছু সেকেন্ড বাটন লক
        // রাখা হয়, যাতে ততক্ষণে কেউ আবার ট্যাপ করলেও দ্বিতীয় কোটা না কাটে।
        setTimeout(() => {
            hdDownloadBusy = false;
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'HD Download';
            }
        }, 4000);
    } catch {
        hdDownloadBusy = false;
        showToast('Network error. Please try again.', 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'HD Download';
        }
    }
}

// ছবি ডাউনলোডে ব্যবহারকারী একটাই ক্লিকে ফাইল সেভ হয়ে যাক এটা চান (আগে যেমন
// ছিল), তাই এখানে সরাসরি CDN ওপেনের বদলে ছোট /proxy-download রুট দিয়েই
// আনা হয় — Content-Disposition: attachment হেডার বসানো যায় বলে ব্রাউজার
// নিজে থেকেই ডাউনলোড শুরু করে, নতুন ট্যাব খুলতে হয় না। ছবি ভিডিওর চেয়ে
// অনেক ছোট বলে এই সামান্য bandwidth খরচ গ্রহণযোগ্য (ব্যবহারকারীর সিদ্ধান্ত)।
function proxyUrl(cdnUrl, filename) {
    return `/proxy-download?url=${encodeURIComponent(cdnUrl)}&filename=${encodeURIComponent(filename)}`;
}

function renderPhotoResult(data) {
    const safeTitle  = escapeHtml(data.title  || 'TikTok Photos');
    const safeAuthor = escapeHtml(data.author || 'Unknown');
    const photos = (data.images || []).map((img, i) => `
        <div class="photo-card">
            <div class="photo-preview">
                <img src="${escapeHtml(img)}" alt="Photo ${i + 1}" loading="lazy" onerror="this.closest('.photo-preview').innerHTML='<div class=photo-broken>🖼️</div>'">
            </div>
            <a href="${escapeHtml(proxyUrl(img, 'tiktok_photo_' + (i + 1) + '.jpg'))}" class="photo-dl-btn" download="tiktok_photo_${i + 1}.jpg">
                <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/><polyline points="7 10 12 15 17 10"/><line x1="12" y1="15" x2="12" y2="3"/></svg>
                Download
            </a>
        </div>`).join('');

    resultArea.innerHTML = `
        <div class="result-card">
            <div class="result-meta" style="margin-bottom:1rem">
                <div class="result-info">
                    <h3>${safeTitle}</h3>
                    <span class="result-author">@${safeAuthor}</span>
                </div>
            </div>
            <div class="photo-grid">
                ${photos}
            </div>
        </div>`;
    showToast(`${data.images.length}টি ফটো পাওয়া গেছে!`, 'success');
}

function renderError(message) {
    resultArea.innerHTML = `
        <div class="error-box">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" style="flex-shrink:0;color:#f87171"><circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/></svg>
            <span>${escapeHtml(message)}</span>
        </div>`;
    showToast(message, 'error');
}

// ===== Main Download Process =====
async function processDownload() {
    const url = urlInput.value.trim();
    if (!url) { showToast('Please paste a TikTok link first.', 'info'); return; }
    if (!url.includes('tiktok.com')) {
        renderError('Please enter a valid TikTok URL.');
        return;
    }

    setLoading(true);
    try {
        const response = await fetch('/download', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ url })
        });
        const data = await response.json();

        if (data.success) {
            data.is_photo ? renderPhotoResult(data) : renderVideoResult(data, url);
        } else {
            renderError(data.error || 'Something went wrong. Please try again.');
        }
    } catch {
        renderError('Network error. Please check your connection.');
    } finally {
        setLoading(false);
    }
}

// ===== Enter Key =====
urlInput.addEventListener('keydown', e => {
    if (e.key === 'Enter') processDownload();
});

// ===== FAQ Accordion =====
function toggleFaq(btn) {
    const item = btn.closest('.faq-item');
    const isOpen = item.classList.contains('open');
    document.querySelectorAll('.faq-item.open').forEach(i => i.classList.remove('open'));
    if (!isOpen) item.classList.add('open');
}

// ===== Smooth Scroll for nav links =====
document.querySelectorAll('a[href^="#"]').forEach(a => {
    a.addEventListener('click', e => {
        const target = document.querySelector(a.getAttribute('href'));
        if (target) {
            e.preventDefault();
            target.scrollIntoView({ behavior: 'smooth', block: 'start' });
        }
    });
});
