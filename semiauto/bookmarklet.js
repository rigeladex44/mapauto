/**
 * =====================================================================
 * 🔥 TOOLS PROSES NIK SEMI-MANUAL PERTAMINA (PRO BOOKMARKLET EDITION)
 * =====================================================================
 * Versi v3.3 - Smart Multi-Type Handling (Utamakan Usaha Mikro -> Fallback Rumah Tangga)
 * - Utamakan memilih "Usaha Mikro" saat modal jenis pelanggan muncul.
 * - Jika Usaha Mikro terdeteksi Limit, otomatis beralih memilih "Rumah Tangga".
 * - Klik presisi pada baris jenis pelanggan & tombol "LANJUTKAN PENJUALAN".
 * - Anti-Logout, Safe Single-Timer & State Lock (tidak ada klik liar bertabrakan).
 * - Di Halaman Sale: Bunyi notifikasi audio + Anda atur kuantitas tabung secara MANUAL.
 * - Setelah Cek Pesanan: Otomatis klik Proses Penjualan -> Transaksi Sukses -> NIK Berikutnya.
 */

(function() {
    // Cegah duplikasi panel jika bookmarklet diklik berulang kali
    const existingPanel = document.getElementById('psa-floating-panel');
    if (existingPanel) {
        existingPanel.style.display = 'block';
        alert('🔔 Panel NIK Semi-Auto sudah aktif di layar Anda!');
        return;
    }

    // State Variables
    let isRunning = false;
    let isPaused = false;
    let isBusy = false; // State lock agar tidak ada eksekusi ganda bersamaan
    let nikQueue = [];
    let nikSukses = [];
    let nikLimit = [];
    let nikGagal = [];
    let currentNik = "";
    let loopTimer = null;
    let salePageBeeped = false;

    // Multi-Type Tracking (Usaha Mikro -> Rumah Tangga fallback)
    let triedCustomerTypes = {}; // { [nik]: ['USAHA MIKRO'] }
    let lastSelectedType = "";   // 'USAHA MIKRO' atau 'RUMAH TANGGA'

    // Single Timer Scheduler yang aman (selalu membersihkan timer sebelumnya)
    function safeSchedule(fn, delayMs) {
        if (loopTimer) {
            clearTimeout(loopTimer);
            loopTimer = null;
        }
        if (!isRunning || isPaused) return;
        loopTimer = setTimeout(() => {
            loopTimer = null;
            if (!isRunning || isPaused) return;
            fn();
        }, delayMs);
    }

    // Local Storage State Key
    const STORAGE_KEY = 'PERTAMINA_SEMIAUTO_DATA_V3';
    function saveState() {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify({
                queue: nikQueue,
                sukses: nikSukses,
                limit: nikLimit,
                gagal: nikGagal
            }));
        } catch(e) {}
    }

    function loadState() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (raw) {
                const data = JSON.parse(raw);
                nikQueue = data.queue || [];
                nikSukses = data.sukses || [];
                nikLimit = data.limit || [];
                nikGagal = data.gagal || [];
            }
        } catch(e) {}
    }
    loadState();

    // Audio Beep Notifikasi saat tiba di halaman Sale
    function playBeep() {
        try {
            const ctx = new (window.AudioContext || window.webkitAudioContext)();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.setValueAtTime(587.33, ctx.currentTime); // D5
            osc.frequency.setValueAtTime(880.00, ctx.currentTime + 0.15); // A5
            gain.gain.setValueAtTime(0.3, ctx.currentTime);
            gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4);
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            osc.stop(ctx.currentTime + 0.4);
        } catch(e) {}
    }

    // =================================================================
    // 1. SAFE DOM CLICKER & REACT INPUT DISPATCHER
    // =================================================================

    // Klik tombol dengan aman dan bersih
    function safeClick(el) {
        if (!el) return false;
        try {
            el.removeAttribute('disabled');
            el.disabled = false;
            el.focus && el.focus();
            el.click();
            return true;
        } catch(e) {
            try {
                el.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
                return true;
            } catch(err) {
                return false;
            }
        }
    }

    // Mengisi input React secara bersih dan memicu event input/change
    function setReactInput(input, value) {
        if (!input) return false;
        try {
            input.focus();

            // Native value setter React 16/17/18
            const descriptor = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value');
            if (descriptor && descriptor.set) {
                descriptor.set.call(input, value);
            } else {
                input.value = value;
            }

            // Dispatch input & change agar React mendeteksi perubahan nilai dan mengaktifkan tombol
            input.dispatchEvent(new Event('input', { bubbles: true }));
            input.dispatchEvent(new Event('change', { bubbles: true }));
            return true;
        } catch(e) {
            input.value = value;
            return false;
        }
    }

    // Mencari elemen input NIK yang sedang terlihat (visible) di layar
    function getNikInputElement() {
        const inputs = Array.from(document.querySelectorAll('input'));
        const pageInputs = inputs.filter(inp => {
            if (inp.closest('#psa-floating-panel')) return false;
            const rect = inp.getBoundingClientRect();
            return inp.offsetParent !== null && rect.width > 30 && rect.height > 10;
        });
        
        // 1. Placeholder memuat 'nik' atau '16'
        let target = pageInputs.find(inp => {
            const ph = (inp.placeholder || '').toLowerCase();
            const aria = (inp.getAttribute('aria-label') || '').toLowerCase();
            const name = (inp.name || '').toLowerCase();
            return ph.includes('nik') || ph.includes('16') || aria.includes('nik') || name.includes('nik');
        });
        if (target) return target;

        // 2. Input di dalam modal yang memuat teks NIK
        const modalContainer = Array.from(document.querySelectorAll('div, form, section')).find(el => {
            if (el.closest('#psa-floating-panel')) return false;
            const txt = (el.innerText || '').toLowerCase();
            return (txt.includes('masukkan nik ktp') || txt.includes('nik pelanggan')) && el.querySelector('input');
        });
        if (modalContainer) {
            const inp = modalContainer.querySelector('input:not([type="hidden"]):not([type="submit"]):not([type="button"])');
            if (inp && inp.offsetParent !== null) return inp;
        }

        // 3. Fallback input visible
        return pageInputs.find(inp => {
            const type = (inp.type || 'text').toLowerCase();
            return ['text', 'tel', 'number'].includes(type) || !inp.type;
        });
    }

    // Cari tombol "LANJUTKAN PENJUALAN"
    function getLanjutkanPenjualanBtn() {
        const candidates = Array.from(document.querySelectorAll('button, a, [role="button"], input[type="submit"]'));
        return candidates.find(b => {
            if (b.closest('#psa-floating-panel')) return false;
            const txt = (b.innerText || b.textContent || '').trim().toUpperCase();
            return (txt.includes('LANJUTKAN PENJUALAN') || txt.includes('CEK NIK')) && b.offsetParent !== null;
        });
    }

    // Cari elemen berdasarkan teks persis
    function findElementByText(text, tag = '*') {
        const all = Array.from(document.querySelectorAll(tag));
        return all.find(el => {
            if (el.closest('#psa-floating-panel')) return false;
            const t = (el.innerText || el.textContent || '').trim();
            return t === text;
        });
    }

    // Cari elemen berdasarkan teks sebagian
    function findElementContainsText(text, tag = '*') {
        const all = Array.from(document.querySelectorAll(tag));
        return all.find(el => {
            if (el.closest('#psa-floating-panel')) return false;
            const t = (el.innerText || el.textContent || '').trim();
            return t.toLowerCase().includes(text.toLowerCase());
        });
    }

    // Klik baris pilihan jenis pelanggan secara presisi (Usaha Mikro / Rumah Tangga)
    function clickCustomerTypeRow(typeName) {
        const elements = Array.from(document.querySelectorAll('div, label, span, p, button, li'));
        const pageElements = elements.filter(el => !el.closest('#psa-floating-panel'));

        // 1. Cari elemen teks spesifik yang pendek memuat nama tipe
        const targetTextEl = pageElements.find(el => {
            const txt = (el.innerText || el.textContent || '').trim().toLowerCase();
            return (txt === typeName.toLowerCase() || txt.includes(typeName.toLowerCase())) && txt.length < 25;
        });

        if (!targetTextEl) return false;

        // 2. Temukan kontainer barisnya
        let row = targetTextEl;
        while (row && row.parentElement && row.parentElement !== document.body) {
            if (row.querySelector('input[type="radio"]') || 
                (row.innerText && row.innerText.includes('Pilih')) ||
                row.classList.contains('flex') ||
                row.tagName === 'LABEL' ||
                row.getAttribute('role') === 'button') {
                break;
            }
            row = row.parentElement;
        }

        const targetRow = row || targetTextEl;

        // Coba centang radio jika ada
        const radio = targetRow.querySelector('input[type="radio"]');
        if (radio) safeClick(radio);

        // Coba klik tombol/badge "Pilih" di baris tersebut jika ada
        const pilihBtn = Array.from(targetRow.querySelectorAll('button, span, div')).find(e => (e.innerText || '').trim().toLowerCase() === 'pilih');
        if (pilihBtn) safeClick(pilihBtn);

        // Klik baris itu sendiri
        safeClick(targetRow);
        return true;
    }

    // Klik Card "Catat Penjualan" di Beranda
    function clickCatatPenjualan() {
        if (getNikInputElement()) return false;

        const catatLeaf = findElementByText('Catat Penjualan');
        if (catatLeaf) {
            let btn = catatLeaf.closest('button') || catatLeaf.closest('a') || catatLeaf;
            return safeClick(btn);
        }
        const btnSale = document.querySelector("[data-testid='btnSale']");
        if (btnSale) {
            return safeClick(btnSale);
        }
        return false;
    }

    // =================================================================
    // 2. MEMBUAT FLOATING UI PANEL
    // =================================================================
    const panel = document.createElement('div');
    panel.id = 'psa-floating-panel';
    panel.style.cssText = `
        position: fixed;
        top: 20px;
        right: 20px;
        width: 330px;
        background: #0f172a;
        color: #f8fafc;
        border: 2px solid #38bdf8;
        border-radius: 14px;
        box-shadow: 0 12px 35px rgba(0, 0, 0, 0.65);
        z-index: 999999999;
        font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
        font-size: 13px;
        line-height: 1.4;
        overflow: hidden;
    `;

    panel.innerHTML = `
        <div id="psa-header" style="background: #1e293b; padding: 10px 14px; font-weight: bold; display: flex; justify-content: space-between; align-items: center; cursor: move; border-bottom: 1px solid #334155; user-select: none;">
            <span style="color: #38bdf8;">🔥 NIK Semi-Auto Pertamina</span>
            <div>
                <button id="psa-min-btn" style="background: none; border: none; color: #94a3b8; font-size: 13px; cursor: pointer; margin-right: 6px;">➖</button>
                <button id="psa-close-btn" style="background: none; border: none; color: #f87171; font-size: 14px; cursor: pointer; font-weight: bold;">✕</button>
            </div>
        </div>
        <div id="psa-body" style="padding: 12px;">
            <div id="psa-status-box" style="background: #1e293b; border-left: 4px solid #38bdf8; padding: 9px 11px; border-radius: 6px; margin-bottom: 10px; font-weight: 600; font-size: 12px;">
                🟢 Siap. Masukkan NIK lalu klik Mulai.
            </div>

            <div style="margin-bottom: 8px;">
                <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                    <label style="font-size: 11px; color: #94a3b8; font-weight: bold; text-transform: uppercase;">Daftar NIK (1 per baris):</label>
                    <span id="psa-count-badge" style="font-size: 11px; color: #38bdf8; font-weight: bold;">0 NIK</span>
                </div>
                <textarea id="psa-nik-input" rows="5" placeholder="Paste 16 digit NIK di sini..." style="width: 100%; box-sizing: border-box; background: #020617; color: #34d399; border: 1px solid #334155; border-radius: 6px; padding: 8px; font-family: monospace; font-size: 12px; resize: vertical; outline: none;"></textarea>
            </div>

            <div style="display: flex; justify-content: space-between; background: #1e293b; padding: 6px 10px; border-radius: 6px; margin-bottom: 10px; font-size: 11px; font-weight: 500;">
                <span id="psa-stat-sisa" style="color: #60a5fa;">Sisa: 0</span>
                <span id="psa-stat-sukses" style="color: #4ade80;">Sukses: 0</span>
                <span id="psa-stat-limit" style="color: #f87171;">Limit: 0</span>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; margin-bottom: 8px;">
                <button id="psa-start-btn" style="background: #0284c7; color: white; border: none; padding: 9px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 12px;">▶️ Mulai</button>
                <button id="psa-pause-btn" style="background: #475569; color: white; border: none; padding: 9px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 12px;">⏸️ Pause</button>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px;">
                <button id="psa-skip-btn" style="background: #334155; color: #cbd5e1; border: none; padding: 7px 10px; border-radius: 6px; font-size: 11px; cursor: pointer;">⏭️ Skip NIK Ini</button>
                <button id="psa-download-btn" style="background: #059669; color: white; border: none; padding: 7px 10px; border-radius: 6px; font-size: 11px; cursor: pointer; font-weight: bold;">💾 Unduh Sukses</button>
            </div>
        </div>
    `;

    document.body.appendChild(panel);

    // DOM Elements Floating Panel
    const statusBox = document.getElementById('psa-status-box');
    const nikInput = document.getElementById('psa-nik-input');
    const countBadge = document.getElementById('psa-count-badge');
    const statSisa = document.getElementById('psa-stat-sisa');
    const statSukses = document.getElementById('psa-stat-sukses');
    const statLimit = document.getElementById('psa-stat-limit');
    const startBtn = document.getElementById('psa-start-btn');
    const pauseBtn = document.getElementById('psa-pause-btn');
    const skipBtn = document.getElementById('psa-skip-btn');
    const downloadBtn = document.getElementById('psa-download-btn');
    const minBtn = document.getElementById('psa-min-btn');
    const closeBtn = document.getElementById('psa-close-btn');
    const psaBody = document.getElementById('psa-body');

    // Restore text NIK jika ada di state
    if (nikQueue.length > 0) {
        nikInput.value = nikQueue.join('\n');
    }
    updateStats();

    function setStatus(text, borderColor = '#38bdf8', bg = '#1e293b') {
        statusBox.innerHTML = text;
        statusBox.style.borderLeftColor = borderColor;
        statusBox.style.background = bg;
        console.log(`[NIK Semi-Auto] ${text.replace(/<[^>]*>?/gm, '')}`);
    }

    function updateStats() {
        const text = nikInput.value.trim();
        const validNiks = text ? text.split('\n').map(s => s.trim().replace(/\D/g, '')).filter(s => s.length === 16) : [];
        countBadge.innerText = `${validNiks.length} NIK`;
        statSisa.innerText = `Sisa: ${validNiks.length}`;
        statSukses.innerText = `Sukses: ${nikSukses.length}`;
        statLimit.innerText = `Limit: ${nikLimit.length}`;
    }

    nikInput.addEventListener('input', updateStats);

    // Draggable Panel
    let isDragging = false, startX, startY, initialLeft, initialTop;
    document.getElementById('psa-header').addEventListener('mousedown', (e) => {
        isDragging = true;
        startX = e.clientX;
        startY = e.clientY;
        const rect = panel.getBoundingClientRect();
        initialLeft = rect.left;
        initialTop = rect.top;
        e.preventDefault();
    });
    document.addEventListener('mousemove', (e) => {
        if (!isDragging) return;
        panel.style.left = (initialLeft + e.clientX - startX) + 'px';
        panel.style.top = (initialTop + e.clientY - startY) + 'px';
        panel.style.right = 'auto';
    });
    document.addEventListener('mouseup', () => { isDragging = false; });

    // Minimize & Close
    minBtn.addEventListener('click', () => {
        if (psaBody.style.display === 'none') {
            psaBody.style.display = 'block';
            minBtn.innerText = '➖';
        } else {
            psaBody.style.display = 'none';
            minBtn.innerText = '➕';
        }
    });

    closeBtn.addEventListener('click', () => {
        if (confirm('Tutup panel tools Semi-Auto?')) {
            isRunning = false;
            isBusy = false;
            if (loopTimer) clearTimeout(loopTimer);
            panel.remove();
        }
    });

    // Unduh NIK Sukses
    downloadBtn.addEventListener('click', () => {
        if (nikSukses.length === 0) {
            alert('Belum ada NIK yang berhasil transaksi!');
            return;
        }
        const blob = new Blob([nikSukses.join('\n')], { type: 'text/plain' });
        const a = document.createElement('a');
        a.href = URL.createObjectURL(blob);
        a.download = `nik_sukses_${new Date().toISOString().slice(0, 10)}.txt`;
        a.click();
    });

    // =================================================================
    // 3. LOGIKA KERJA SEMI-OTOMATIS (SAFE SINGLE-THREADED FLOW)
    // =================================================================

    function parseQueue() {
        const text = nikInput.value.trim();
        return text ? text.split('\n').map(s => s.trim().replace(/\D/g, '')).filter(s => s.length === 16) : [];
    }

    function syncQueue() {
        nikInput.value = nikQueue.join('\n');
        updateStats();
        saveState();
    }

    startBtn.addEventListener('click', () => {
        if (isRunning && !isPaused) return;

        nikQueue = parseQueue();
        if (nikQueue.length === 0) {
            alert('Silakan masukkan minimal satu 16 digit NIK pada kotak textarea!');
            return;
        }

        isRunning = true;
        isPaused = false;
        isBusy = false;
        startBtn.style.background = '#059669';
        startBtn.innerText = '🟢 Berjalan...';
        pauseBtn.style.background = '#475569';
        pauseBtn.innerText = '⏸️ Pause';

        executeLoop();
    });

    pauseBtn.addEventListener('click', () => {
        if (!isRunning) return;
        isPaused = !isPaused;
        if (isPaused) {
            pauseBtn.style.background = '#d97706';
            pauseBtn.innerText = '▶️ Resume';
            setStatus('⏸️ Dipause oleh pengguna.', '#f59e0b');
        } else {
            pauseBtn.style.background = '#475569';
            pauseBtn.innerText = '⏸️ Pause';
            setStatus('▶️ Melanjutkan antrean...', '#38bdf8');
            isBusy = false;
            executeLoop();
        }
    });

    skipBtn.addEventListener('click', () => {
        if (currentNik) {
            nikGagal.push(currentNik);
            setStatus(`⏭️ NIK ${currentNik} dilewati.`, '#64748b');
            advanceToNextNik();
        }
    });

    // Helper untuk klik "Ganti Pelanggan" atau tombol kembali di halaman Penjualan
    function clickGantiPelanggan() {
        // 1. Cari elemen dengan teks persis atau mengandung "Ganti Pelanggan"
        const all = Array.from(document.querySelectorAll('button, a, div, span, p'));
        const gantiBtn = all.find(el => {
            if (el.closest('#psa-floating-panel')) return false;
            const t = (el.innerText || el.textContent || '').trim().toLowerCase();
            return t === 'ganti pelanggan' || t.includes('ganti pelanggan');
        });
        if (gantiBtn) {
            safeClick(gantiBtn);
            return true;
        }

        // 2. Cari tombol panah kembali (back button) di header Penjualan (seperti '← Penjualan')
        const backBtn = document.querySelector('button[aria-label*="kembali" i], button[aria-label*="back" i]');
        if (backBtn && !backBtn.closest('#psa-floating-panel')) {
            safeClick(backBtn);
            return true;
        }

        const headers = Array.from(document.querySelectorAll('header, [class*="header"], nav, div'));
        for (const h of headers) {
            if (h.closest('#psa-floating-panel')) continue;
            const txt = (h.innerText || '').toLowerCase();
            if (txt.includes('penjualan')) {
                const b = h.querySelector('button, svg, [role="button"]');
                if (b && !b.closest('#psa-floating-panel')) {
                    safeClick(b);
                    return true;
                }
            }
        }

        // 3. Fallback jika sudah di beranda
        return clickCatatPenjualan();
    }

    function closePopupTutup() {
        const tutupBtn = findElementByText('TUTUP', 'button') || 
                         findElementContainsText('Tutup', 'button') ||
                         findElementByText('BATAL', 'button') ||
                         findElementContainsText('Batal', 'button') ||
                         findElementByText('OKE', 'button') ||
                         findElementByText('OK', 'button');
        if (tutupBtn) {
            safeClick(tutupBtn);
            return true;
        }
        return false;
    }

    function advanceToNextNik() {
        if (currentNik && triedCustomerTypes[currentNik]) {
            delete triedCustomerTypes[currentNik];
        }
        lastSelectedType = "";
        currentNik = "";
        salePageBeeped = false;
        isBusy = false;
        syncQueue();

        if (nikQueue.length === 0) {
            setStatus('🎉 Semua NIK dalam antrean selesai diproses!', '#4ade80', '#064e3b');
            isRunning = false;
            startBtn.style.background = '#0284c7';
            startBtn.innerText = '▶️ Mulai';
            return;
        }

        // Bersihkan input lama di form jika masih ada
        const nikInp = getNikInputElement();
        if (nikInp) {
            setReactInput(nikInp, '');
        }

        safeSchedule(executeLoop, 3500);
    }

    // MAIN EXECUTION LOOP DENGAN SINGLE TIMER & STATE LOCK
    function executeLoop() {
        if (!isRunning || isPaused) return;

        // Cegah eksekusi jika sedang menunggu proses async
        if (isBusy) return;

        const url = window.location.href;
        const bodyText = (document.body.innerText || '').trim();

        // -------------------------------------------------------------
        // PROTEKSI: Cek apakah sesi login Pertamina habis
        // -------------------------------------------------------------
        if (url.includes('/login') || url.includes('/masuk')) {
            isRunning = false;
            isBusy = false;
            startBtn.style.background = '#0284c7';
            startBtn.innerText = '▶️ Mulai';
            setStatus('⚠️ Sesi login Pertamina habis. Silakan login kembali!', '#f87171', '#450a0a');
            return;
        }

        // -------------------------------------------------------------
        // PRIORITAS 1: HALAMAN SALE / PENJUALAN
        // Didukung deteksi URL, tombol Cek Pesanan, atau Kartu Pelanggan dengan 'Ganti Pelanggan'
        // -------------------------------------------------------------
        const isSalePage = url.includes('/sale') || 
                           bodyText.includes('CEK PESANAN') || 
                           bodyText.includes('PROSES PENJUALAN') || 
                           bodyText.includes('Transaksi Berhasil') ||
                           bodyText.includes('Ganti Pelanggan') ||
                           (bodyText.includes('Penjualan') && bodyText.includes('Informasi Pelanggan'));

        if (isSalePage) {
            handleSaleStep();
            return;
        }

        // -------------------------------------------------------------
        // PRIORITAS 2: MODAL HASIL VERIFIKASI (LIMIT, TIDAK DITEMUKAN, UMKM/RT, NIB)
        // -------------------------------------------------------------
        if (bodyText.includes("melebihi batas kewajaran") || 
            bodyText.includes("kuota") || 
            bodyText.includes("tidak dapat transaksi") ||
            bodyText.includes("tidak ditemukan") || 
            bodyText.includes("tidak terdaftar") || 
            bodyText.includes("jenis pelanggan di bawah ini") || 
            bodyText.includes("Pelanggan Terdaftar") ||
            bodyText.includes("PILIH JENIS PELANGGAN") || 
            bodyText.includes("LENGKAPI NIB") || 
            bodyText.includes("NANTI SAJA")) {
            evaluateVerificationResult();
            return;
        }

        // -------------------------------------------------------------
        // PRIORITAS 3: FORM / MODAL INPUT NIK
        // -------------------------------------------------------------
        const nikInputEl = getNikInputElement();
        const isNikPromptVisible = bodyText.includes('MASUKKAN NIK KTP') || 
                                   bodyText.includes('NIK Pelanggan') || 
                                   url.includes('/verification-nik') || 
                                   (nikInputEl !== null && getLanjutkanPenjualanBtn() !== null);

        if (isNikPromptVisible && nikInputEl) {
            handleInputNikStep(nikInputEl);
            return;
        }

        // -------------------------------------------------------------
        // PRIORITAS 4: BERADA DI BERANDA (Modal belum terbuka)
        // -------------------------------------------------------------
        if (url.includes('/merchant/app')) {
            setStatus('📄 Mengklik Card <b>Catat Penjualan</b>...', '#38bdf8');
            const clicked = clickCatatPenjualan();
            if (clicked) {
                setStatus('⏳ Berhasil klik Catat Penjualan, memuat form input NIK...', '#34d399');
            } else {
                setStatus('⚠️ Mencari tombol Catat Penjualan...', '#f59e0b');
            }
            safeSchedule(executeLoop, 4000);
            return;
        }

        // Fallback untuk halaman lain
        safeSchedule(executeLoop, 2500);
    }

    // PROSES INPUT NIK KE FORM / MODAL (SAFE DISPATCH DENGAN TEMPO 2 DETIK)
    function handleInputNikStep(nikInputEl) {
        if (!currentNik) {
            if (nikQueue.length === 0) {
                nikQueue = parseQueue();
            }
            if (nikQueue.length === 0) {
                setStatus('🎉 Semua NIK dalam antrean selesai diproses!', '#4ade80', '#064e3b');
                isRunning = false;
                startBtn.style.background = '#0284c7';
                startBtn.innerText = '▶️ Mulai';
                return;
            }
            currentNik = nikQueue[0];
        }

        // Aktifkan lock agar loop lain tidak mengklik card di beranda
        isBusy = true;

        setStatus(`📝 Mengisi NIK: <b>${currentNik}</b>`, '#38bdf8');
        setReactInput(nikInputEl, currentNik);

        // Beri tempo 2 detik agar React merender state tombol dan server stabil
        safeSchedule(() => {
            const btnLanjut = getLanjutkanPenjualanBtn() ||
                              document.querySelector("[data-testid='btnCheckNik']") ||
                              findElementContainsText('LANJUTKAN PENJUALAN', 'button') ||
                              findElementContainsText('Cek NIK', 'button');

            if (btnLanjut) {
                setStatus(`🔍 Memeriksa NIK <b>${currentNik}</b>...`, '#f59e0b');
                safeClick(btnLanjut);

                // Tunggu respons server Pertamina selama 4.5 detik (tempo ekstra saat web down)
                safeSchedule(evaluateVerificationResult, 4500);
            } else {
                isBusy = false;
                safeSchedule(executeLoop, 2500);
            }
        }, 2000);
    }

    // Evaluasi Modal / Respon setelah Cek NIK (Dukungan Multi-Type: Usaha Mikro -> Rumah Tangga)
    function evaluateVerificationResult() {
        if (!isRunning || isPaused) return;

        const body = document.body.innerText || '';

        // =============================================================
        // KONDISI 1: CEK LIMIT DI MODAL (FALLBACK DARI USAHA MIKRO KE RUMAH TANGGA)
        // =============================================================
        if (body.includes("melebihi batas kewajaran") || body.includes("kuota") || body.includes("tidak dapat transaksi")) {
            const tried = triedCustomerTypes[currentNik] || [];

            // JIKA TADI MEMILIH USAHA MIKRO DAN LIMIT, COBA BERALIH KE RUMAH TANGGA!
            if (lastSelectedType === "USAHA MIKRO" && !tried.includes("RUMAH TANGGA")) {
                setStatus(`⚠️ Usaha Mikro LIMIT untuk NIK <b>${currentNik}</b>. Beralih ke <b>Rumah Tangga</b>...`, '#f59e0b');

                closePopupTutup();

                // Jeda 2 detik lalu pilih Rumah Tangga jika opsi masih ada di modal
                safeSchedule(() => {
                    const rowSelected = clickCustomerTypeRow("Rumah Tangga");
                    lastSelectedType = "RUMAH TANGGA";
                    tried.push("RUMAH TANGGA");
                    triedCustomerTypes[currentNik] = tried;

                    if (rowSelected) {
                        // Jeda 1.8 detik lalu klik tombol submit
                        safeSchedule(() => {
                            const btnLanjut = getLanjutkanPenjualanBtn() ||
                                              findElementContainsText('LANJUTKAN PENJUALAN', 'button') ||
                                              findElementContainsText('LANJUTKAN TRANSAKSI', 'button') ||
                                              findElementContainsText('Lanjutkan', 'button');
                            if (btnLanjut) safeClick(btnLanjut);
                            safeSchedule(evaluateVerificationResult, 4500);
                        }, 1800);
                    } else {
                        // Jika modal tertutup setelah klik TUTUP, klik Ganti Pelanggan / Catat Penjualan untuk input ulang
                        clickGantiPelanggan();
                        isBusy = false;
                        safeSchedule(executeLoop, 3000);
                    }
                }, 2000);
                return;
            }

            // Jika Rumah Tangga juga limit, atau hanya ada 1 tipe: BENAR-BENAR LIMIT
            setStatus(`❌ NIK <b>${currentNik}</b> LIMIT (${lastSelectedType || 'Semua Opsi'})!`, '#f87171', '#450a0a');
            if (currentNik && !nikLimit.includes(currentNik)) {
                nikLimit.push(currentNik);
            }
            if (nikQueue[0] === currentNik) {
                nikQueue.shift();
            }
            syncQueue();

            closePopupTutup();
            clickGantiPelanggan();

            safeSchedule(advanceToNextNik, 3800);
            return;
        }

        // =============================================================
        // KONDISI 2: CEK TIDAK TERDAFTAR / TIDAK DITEMUKAN
        // =============================================================
        if (body.includes("tidak ditemukan") || body.includes("tidak terdaftar")) {
            setStatus(`❓ NIK <b>${currentNik}</b> Tidak Ditemukan!`, '#f87171', '#450a0a');
            if (currentNik && !nikGagal.includes(currentNik)) {
                nikGagal.push(currentNik);
            }
            if (nikQueue[0] === currentNik) {
                nikQueue.shift();
            }
            syncQueue();

            closePopupTutup();
            clickGantiPelanggan();

            safeSchedule(advanceToNextNik, 3800);
            return;
        }

        // =============================================================
        // KONDISI 3: MODAL PILIHAN JENIS PELANGGAN (USAHA MIKRO DULU, LALU RUMAH TANGGA)
        // =============================================================
        if (body.includes("jenis pelanggan di bawah ini") || 
            body.includes("PILIH JENIS PELANGGAN") || 
            (body.includes("Pelanggan Terdaftar") && (body.includes("Usaha Mikro") || body.includes("Rumah Tangga")))) {

            const tried = triedCustomerTypes[currentNik] || [];
            const hasUsahaMikro = body.toLowerCase().includes('usaha mikro');
            const hasRumahTangga = body.toLowerCase().includes('rumah tangga');

            // Prioritas: 1. Usaha Mikro (jika belum dicoba) | 2. Rumah Tangga (jika Usaha Mikro sudah dicoba/limit)
            let targetType = "";
            if (hasUsahaMikro && !tried.includes("USAHA MIKRO")) {
                targetType = "USAHA MIKRO";
            } else if (hasRumahTangga && !tried.includes("RUMAH TANGGA")) {
                targetType = "RUMAH TANGGA";
            } else if (hasRumahTangga) {
                targetType = "RUMAH TANGGA";
            } else if (hasUsahaMikro) {
                targetType = "USAHA MIKRO";
            }

            if (targetType) {
                lastSelectedType = targetType;
                if (!tried.includes(targetType)) {
                    tried.push(targetType);
                    triedCustomerTypes[currentNik] = tried;
                }

                const labelName = targetType === "USAHA MIKRO" ? "Usaha Mikro" : "Rumah Tangga";
                setStatus(`🏢 Memilih opsi <b>${labelName}</b> untuk NIK ${currentNik}...`, '#38bdf8');
                
                // Klik opsi radio / baris pilihan
                clickCustomerTypeRow(labelName);

                // Jeda 2 detik (tempo server) lalu klik tombol hijau LANJUTKAN PENJUALAN
                safeSchedule(() => {
                    const btnLanjut = getLanjutkanPenjualanBtn() ||
                                      findElementContainsText('LANJUTKAN PENJUALAN', 'button') ||
                                      findElementContainsText('LANJUTKAN TRANSAKSI', 'button') ||
                                      findElementContainsText('Lanjutkan', 'button');

                    if (btnLanjut) {
                        safeClick(btnLanjut);
                        // Tunggu 4.5 detik untuk memeriksa apakah muncul Limit atau lanjut ke Sale
                        safeSchedule(evaluateVerificationResult, 4500);
                    } else {
                        isBusy = false;
                        safeSchedule(executeLoop, 2500);
                    }
                }, 2000);
                return;
            }
        }

        // =============================================================
        // KONDISI 4: POPUP NIB (LENGKAPI NIB / NANTI SAJA)
        // =============================================================
        if (body.includes("NIB") || body.includes("LENGKAPI NIB") || body.includes("NANTI SAJA")) {
            const nantiNib = findElementContainsText('NANTI SAJA', 'button') || findElementContainsText('Nanti Saja', 'button');
            if (nantiNib) {
                safeClick(nantiNib);
                isBusy = false;
                safeSchedule(executeLoop, 2500);
                return;
            }
            const lengkapiNib = findElementContainsText('LENGKAPI NIB', 'button');
            if (lengkapiNib) {
                safeClick(lengkapiNib);
                isBusy = false;
                safeSchedule(executeLoop, 2500);
                return;
            }
        }

        // =============================================================
        // KONDISI 5: TOMBOL LANJUT TRANSAKSI LANGSUNG
        // =============================================================
        const btnLanjut = findElementByText('Lanjut Transaksi', 'button') || findElementContainsText('LANJUT TRANSAKSI', 'button');
        if (btnLanjut) {
            safeClick(btnLanjut);
            isBusy = false;
            safeSchedule(executeLoop, 3000);
            return;
        }

        // Buka lock jika sudah selesai evaluasi
        isBusy = false;
        safeSchedule(executeLoop, 2000);
    }

    // -------------------------------------------------------------
    // LOGIKA DI HALAMAN SALE (LIMIT HANDLING + SEMI-MANUAL & AUTO-PAY)
    // -------------------------------------------------------------
    function handleSaleStep() {
        if (!isRunning || isPaused) return;

        const body = document.body.innerText || '';

        // =============================================================
        // CEK 1: APAKAH HALAMAN SALE MENAMPILKAN ALERT LIMIT
        // =============================================================
        const isLimitSale = body.includes("melebihi batas kewajaran") || 
                            body.includes("tidak dapat transaksi") || 
                            body.includes("kuota pembelian") ||
                            body.includes("batas kewajaran pembelian");

        if (isLimitSale) {
            isBusy = true;
            const tried = triedCustomerTypes[currentNik] || [];

            // A. JIKA NIK TADI MEMILIH USAHA MIKRO DAN LIMIT, COBA BERALIH KE RUMAH TANGGA!
            if (lastSelectedType === "USAHA MIKRO" && !tried.includes("RUMAH TANGGA")) {
                setStatus(`⚠️ Usaha Mikro LIMIT untuk NIK <b>${currentNik}</b>! Mengklik 'Ganti Pelanggan' untuk mencoba <b>Rumah Tangga</b>...`, '#f59e0b');

                // Klik tombol 'Ganti Pelanggan' agar kembali ke input NIK
                clickGantiPelanggan();

                // Tandai bahwa USAHA MIKRO sudah dicoba, dan statusnya LIMIT
                if (!tried.includes("USAHA MIKRO")) tried.push("USAHA MIKRO");
                triedCustomerTypes[currentNik] = tried;
                lastSelectedType = "USAHA MIKRO_LIMIT";

                // Jeda 3 detik agar halaman input NIK/beranda terbuka kembali
                safeSchedule(() => {
                    isBusy = false;
                    executeLoop();
                }, 3000);
                return;
            }

            // B. JIKA RUMAH TANGGA JUGA LIMIT (ATAU NIK BUKAN MULTI-TYPE): BENAR-BENAR LIMIT!
            setStatus(`❌ NIK <b>${currentNik}</b> LIMIT TOTAL (${lastSelectedType || 'Semua Opsi'})!`, '#f87171', '#450a0a');
            if (currentNik && !nikLimit.includes(currentNik)) {
                nikLimit.push(currentNik);
            }
            if (nikQueue[0] === currentNik) {
                nikQueue.shift();
            }
            syncQueue();

            // Klik Ganti Pelanggan agar siap input NIK berikutnya
            clickGantiPelanggan();

            // Jeda tempo sebelum memproses NIK berikutnya
            safeSchedule(advanceToNextNik, 3500);
            return;
        }

        // =============================================================
        // CEK 2: APAKAH TRANSAKSI SUDAH BERHASIL
        // =============================================================
        const keBeranda = findElementByText('KE BERANDA', 'a, button') || findElementContainsText('Ke Beranda', 'a, button');
        if (keBeranda || body.includes('Transaksi Berhasil') || body.includes('Pembayaran Berhasil')) {
            salePageBeeped = false;
            setStatus(`🎉 NIK <b>${currentNik}</b> BERHASIL TRANSAKSI!`, '#4ade80', '#064e3b');
            if (currentNik && !nikSukses.includes(currentNik)) {
                nikSukses.push(currentNik);
            }
            if (nikQueue[0] === currentNik) {
                nikQueue.shift();
            }
            syncQueue();

            if (keBeranda) {
                safeClick(keBeranda);
            } else {
                clickCatatPenjualan();
            }

            // Jeda 4.5 detik sebelum memproses NIK berikutnya
            safeSchedule(advanceToNextNik, 4500);
            return;
        }

        // =============================================================
        // CEK 3: APAKAH TOMBOL "PROSES PENJUALAN" SUDAH MUNCUL (AUTO-PAY)
        // =============================================================
        const btnPay = document.querySelector("[data-testid='btnPay']") ||
                       findElementContainsText('PROSES PENJUALAN', 'button');

        if (btnPay && btnPay.offsetParent !== null) {
            setStatus(`🤖 <b>Otomatis</b> klik 'PROSES PENJUALAN'...`, '#a855f7');
            safeClick(btnPay);

            safeSchedule(() => {
                setStatus(`🧩 Selesaikan Captcha Slider jika muncul...`, '#f59e0b');
                safeSchedule(handleSaleStep, 3000);
            }, 2000);
            return;
        }

        // =============================================================
        // CEK 4: POSISI DI PILIHAN KUANTITAS: MANUAL INPUT USER
        // =============================================================
        const btnCheckOrder = document.querySelector("[data-testid='btnCheckOrder']") ||
                              findElementContainsText('CEK PESANAN', 'button');

        if (btnCheckOrder && btnCheckOrder.offsetParent !== null) {
            if (!salePageBeeped) {
                playBeep();
                salePageBeeped = true;
            }
            setStatus(`✋ <b>MANUAL:</b> Atur kuantitas tabung gas, lalu klik <b>'CEK PESANAN'</b>!`, '#f59e0b', '#451a03');
            safeSchedule(handleSaleStep, 1500);
            return;
        }

        // =============================================================
        // CEK 5: CAPTCHA SLIDER TERDETEKSI
        // =============================================================
        if (document.querySelector('.rc-slider-captcha') || body.includes('Geser')) {
            setStatus(`🧩 Silakan geser Slider Captcha di layar!`, '#f59e0b');
            safeSchedule(handleSaleStep, 1500);
            return;
        }

        isBusy = false;
        safeSchedule(handleSaleStep, 2000);
    }

    console.log("🔥 [NIK Semi-Auto Bookmarklet Pro v3.5 - Smart Limit & Dual-Type Handling] Berhasil diinisialisasi!");
})();

