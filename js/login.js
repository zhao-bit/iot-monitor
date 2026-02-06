/**
 * ============================================
 * 登录页面功能
 * 功能：HUD背景、表单验证、登录处理
 * ============================================
 */

document.addEventListener('DOMContentLoaded', function() {
    initHudBackground();
    initHexStreams();
    initWaveform();
    initHudCounters();
    initFormValidation();
    initLogin();
    initGlowFollow();
});

function initHudBackground() {
    const canvas = document.getElementById('hudCanvas');
    if (!canvas) return;

    const ctx = canvas.getContext('2d');
    const particles = [];
    const linksDistance = 120;
    const maxParticles = 45;
    const boxes = [];
    let frame = 0;
    let width = 0;
    let height = 0;
    let dpr = window.devicePixelRatio || 1;

    function resize() {
        dpr = window.devicePixelRatio || 1;
        width = window.innerWidth;
        height = window.innerHeight;
        canvas.width = Math.floor(width * dpr);
        canvas.height = Math.floor(height * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    function rand(min, max) {
        return Math.random() * (max - min) + min;
    }

    function createParticle() {
        return {
            x: rand(0, width),
            y: rand(0, height),
            vx: rand(-0.25, 0.25),
            vy: rand(-0.25, 0.25),
            r: rand(1, 2.2),
            o: rand(0.2, 0.6)
        };
    }

    for (let i = 0; i < maxParticles; i++) {
        particles.push(createParticle());
    }

    function spawnBox() {
        const w = rand(80, 180);
        const h = rand(60, 140);
        const x = rand(40, width - w - 40);
        const y = rand(40, height - h - 40);
        boxes.push({
            x,
            y,
            w,
            h,
            confidence: Math.floor(rand(72, 99)),
            life: rand(120, 260)
        });
    }

    function drawGrid() {
        ctx.strokeStyle = 'rgba(0, 200, 255, 0.03)';
        ctx.lineWidth = 1;
        const gap = 40;
        for (let x = 0; x <= width; x += gap) {
            ctx.beginPath();
            ctx.moveTo(x, 0);
            ctx.lineTo(x, height);
            ctx.stroke();
        }
        for (let y = 0; y <= height; y += gap) {
            ctx.beginPath();
            ctx.moveTo(0, y);
            ctx.lineTo(width, y);
            ctx.stroke();
        }
    }

    function drawHexMesh() {
        const size = 26;
        const heightStep = Math.sqrt(3) * size;
        const pulse = 0.04 + 0.03 * Math.sin(frame * 0.02);
        ctx.strokeStyle = `rgba(0, 200, 255, ${pulse})`;
        ctx.lineWidth = 1;
        for (let y = -heightStep; y < height + heightStep; y += heightStep) {
            for (let x = 0; x < width + size * 2; x += size * 1.5) {
                const offsetY = (x / (size * 1.5)) % 2 === 0 ? 0 : heightStep / 2;
                drawHexagon(x, y + offsetY, size);
            }
        }
    }

    function drawHexagon(cx, cy, r) {
        ctx.beginPath();
        for (let i = 0; i < 6; i++) {
            const angle = (Math.PI / 3) * i + Math.PI / 6;
            const px = cx + r * Math.cos(angle);
            const py = cy + r * Math.sin(angle);
            if (i === 0) ctx.moveTo(px, py);
            else ctx.lineTo(px, py);
        }
        ctx.closePath();
        ctx.stroke();
    }

    function drawParticles() {
        particles.forEach(p => {
            p.x += p.vx;
            p.y += p.vy;

            if (p.x < 0) p.x = width;
            if (p.x > width) p.x = 0;
            if (p.y < 0) p.y = height;
            if (p.y > height) p.y = 0;

            ctx.fillStyle = `rgba(0, 200, 255, ${p.o})`;
            ctx.beginPath();
            ctx.arc(p.x, p.y, p.r, 0, Math.PI * 2);
            ctx.fill();
        });

        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const dist = Math.sqrt(dx * dx + dy * dy);
                if (dist < linksDistance) {
                    const alpha = 0.18 * (1 - dist / linksDistance);
                    ctx.strokeStyle = `rgba(0, 200, 255, ${alpha})`;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }
    }

    function drawScanlines() {
        const lineGap = 4;
        ctx.strokeStyle = 'rgba(0, 200, 255, 0.02)';
        ctx.lineWidth = 1;
        for (let y = 0; y < height; y += lineGap) {
            ctx.beginPath();
            ctx.moveTo(0, y + (frame % lineGap));
            ctx.lineTo(width, y + (frame % lineGap));
            ctx.stroke();
        }
    }

    function drawCornerBrackets() {
        const size = 28;
        const offset = 20;
        ctx.strokeStyle = 'rgba(0, 200, 255, 0.4)';
        ctx.lineWidth = 2;
        // top-left
        ctx.beginPath();
        ctx.moveTo(offset, offset + size);
        ctx.lineTo(offset, offset);
        ctx.lineTo(offset + size, offset);
        ctx.stroke();
        // top-right
        ctx.beginPath();
        ctx.moveTo(width - offset - size, offset);
        ctx.lineTo(width - offset, offset);
        ctx.lineTo(width - offset, offset + size);
        ctx.stroke();
        // bottom-left
        ctx.beginPath();
        ctx.moveTo(offset, height - offset - size);
        ctx.lineTo(offset, height - offset);
        ctx.lineTo(offset + size, height - offset);
        ctx.stroke();
        // bottom-right
        ctx.beginPath();
        ctx.moveTo(width - offset - size, height - offset);
        ctx.lineTo(width - offset, height - offset);
        ctx.lineTo(width - offset, height - offset - size);
        ctx.stroke();
    }

    function drawScanBar() {
        const y = (frame * 0.6) % height;
        const gradient = ctx.createLinearGradient(0, y - 10, 0, y + 10);
        gradient.addColorStop(0, 'rgba(0, 200, 255, 0)');
        gradient.addColorStop(0.5, 'rgba(0, 200, 255, 0.18)');
        gradient.addColorStop(1, 'rgba(0, 200, 255, 0)');
        ctx.fillStyle = gradient;
        ctx.fillRect(0, y - 10, width, 20);
    }

    function drawDetectionBoxes() {
        if (boxes.length < 3 && Math.random() > 0.985) {
            spawnBox();
        }

        boxes.forEach(box => {
            box.life -= 1;
            ctx.strokeStyle = 'rgba(0, 200, 255, 0.7)';
            ctx.lineWidth = 1.5;
            ctx.strokeRect(box.x, box.y, box.w, box.h);

            ctx.fillStyle = 'rgba(0, 200, 255, 0.15)';
            ctx.fillRect(box.x, box.y, box.w, box.h);

            ctx.fillStyle = 'rgba(0, 200, 255, 0.85)';
            ctx.font = '12px "JetBrains Mono", monospace';
            ctx.fillText(`CONF ${box.confidence}%`, box.x + 6, box.y - 8);

            const cx = box.x + box.w / 2;
            const cy = box.y + box.h / 2;
            ctx.beginPath();
            ctx.moveTo(cx - 10, cy);
            ctx.lineTo(cx + 10, cy);
            ctx.moveTo(cx, cy - 10);
            ctx.lineTo(cx, cy + 10);
            ctx.stroke();
        });

        for (let i = boxes.length - 1; i >= 0; i--) {
            if (boxes[i].life <= 0) boxes.splice(i, 1);
        }
    }

    function animate() {
        frame++;
        ctx.clearRect(0, 0, width, height);

        drawGrid();
        drawHexMesh();
        drawParticles();
        drawScanlines();
        drawScanBar();
        drawDetectionBoxes();
        drawCornerBrackets();

        requestAnimationFrame(animate);
    }

    animate();
}

function initHexStreams() {
    const left = document.getElementById('hexStreamLeft');
    const right = document.getElementById('hexStreamRight');
    if (!left || !right) return;

    function generateLine() {
        const parts = [];
        for (let i = 0; i < 8; i++) {
            parts.push(Math.floor(Math.random() * 256).toString(16).padStart(2, '0'));
        }
        return parts.join(' ');
    }

    function updateStream(el) {
        const lines = [];
        for (let i = 0; i < 36; i++) {
            lines.push(generateLine());
        }
        el.innerHTML = lines.join('<br>');
    }

    updateStream(left);
    updateStream(right);
    setInterval(() => {
        updateStream(left);
        updateStream(right);
    }, 1200);
}

function initWaveform() {
    const canvas = document.getElementById('waveformCanvas');
    if (!canvas) return;
    const ctx = canvas.getContext('2d');

    function resize() {
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.offsetWidth;
        const h = canvas.offsetHeight;
        canvas.width = Math.floor(w * dpr);
        canvas.height = Math.floor(h * dpr);
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();
    window.addEventListener('resize', resize);

    let t = 0;
    function draw() {
        t += 0.02;
        const w = canvas.offsetWidth;
        const h = canvas.offsetHeight;
        ctx.clearRect(0, 0, w, h);
        ctx.strokeStyle = 'rgba(0, 200, 255, 0.8)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        const mid = h / 2;
        for (let x = 0; x < w; x++) {
            const y = mid + Math.sin((x * 0.04) + t) * 16 + Math.sin((x * 0.12) - t) * 6;
            if (x === 0) ctx.moveTo(x, y);
            else ctx.lineTo(x, y);
        }
        ctx.stroke();

        ctx.strokeStyle = 'rgba(0, 200, 255, 0.2)';
        ctx.lineWidth = 1;
        ctx.beginPath();
        ctx.moveTo(0, mid);
        ctx.lineTo(w, mid);
        ctx.stroke();

        requestAnimationFrame(draw);
    }

    draw();
}

function initHudCounters() {
    const frameEl = document.getElementById('hudFrame');
    const bitrateEl = document.getElementById('hudBitrate');
    const threatFill = document.getElementById('threatFill');
    let frame = 0;

    setInterval(() => {
        frame += Math.floor(Math.random() * 6) + 1;
        if (frameEl) frameEl.textContent = frame.toString().padStart(5, '0');
        if (bitrateEl) bitrateEl.textContent = `${(Math.random() * 2 + 1.5).toFixed(2)} MB/s`;
        if (threatFill) threatFill.style.width = `${Math.floor(Math.random() * 40) + 20}%`;
    }, 600);
}

function initGlowFollow() {
    const loginBox = document.getElementById('loginBox');
    if (!loginBox) return;

    loginBox.addEventListener('mousemove', (event) => {
        const rect = loginBox.getBoundingClientRect();
        const x = ((event.clientX - rect.left) / rect.width) * 100;
        const y = ((event.clientY - rect.top) / rect.height) * 100;
        loginBox.style.setProperty('--glow-x', `${x}%`);
        loginBox.style.setProperty('--glow-y', `${y}%`);
    });
}

function initFormValidation() {
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const usernameError = document.getElementById('usernameError');
    const passwordError = document.getElementById('passwordError');
    const togglePasswordBtn = document.getElementById('togglePassword');

    if (usernameInput) {
        usernameInput.addEventListener('blur', function() {
            validateUsername();
        });
        usernameInput.addEventListener('input', function() {
            if (this.value.trim()) {
                clearError(usernameInput, usernameError);
            }
        });
    }

    if (togglePasswordBtn && passwordInput) {
        togglePasswordBtn.addEventListener('click', function() {
            const type = passwordInput.type === 'password' ? 'text' : 'password';
            passwordInput.type = type;
            const icon = this.querySelector('i');
            icon.classList.toggle('fa-eye');
            icon.classList.toggle('fa-eye-slash');
        });
    }

    if (passwordInput) {
        passwordInput.addEventListener('blur', function() {
            validatePassword();
        });
        passwordInput.addEventListener('input', function() {
            if (this.value.trim()) {
                clearError(passwordInput, passwordError);
            }
        });
    }

    function validateUsername() {
        const value = usernameInput.value.trim();
        if (!value) {
            showError(usernameInput, usernameError, '请输入用户名');
            return false;
        }
        if (value.length < 3) {
            showError(usernameInput, usernameError, '用户名至少3个字符');
            return false;
        }
        clearError(usernameInput, usernameError);
        return true;
    }

    function validatePassword() {
        const value = passwordInput.value;
        if (!value) {
            showError(passwordInput, passwordError, '请输入密码');
            return false;
        }
        if (value.length < 6) {
            showError(passwordInput, passwordError, '密码至少6个字符');
            return false;
        }
        clearError(passwordInput, passwordError);
        return true;
    }

    function showError(input, errorEl, message) {
        input.classList.add('error');
        if (errorEl) {
            errorEl.textContent = message;
        }
    }

    function clearError(input, errorEl) {
        input.classList.remove('error');
        if (errorEl) {
            errorEl.textContent = '';
        }
    }

    window.validateForm = function() {
        const usernameValid = validateUsername();
        const passwordValid = validatePassword();
        return usernameValid && passwordValid;
    };
}

function initLogin() {
    const loginForm = document.getElementById('loginForm');
    const loginBtn = document.getElementById('loginBtn');
    const statusText = document.getElementById('loginStatusText');

    if (loginForm) {
        loginForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            if (!window.validateForm()) {
                if (statusText) statusText.textContent = 'VALIDATION ERROR';
                return;
            }

            const btnText = loginBtn.querySelector('.btn-text');
            const btnLoader = loginBtn.querySelector('.btn-loader');
            btnText.style.display = 'none';
            btnLoader.style.display = 'inline-block';
            loginBtn.disabled = true;

            const formData = {
                username: document.getElementById('username').value.trim(),
                password: document.getElementById('password').value,
                rememberMe: document.getElementById('rememberMe').checked
            };

            const stages = [
                'AUTHENTICATING',
                'VERIFYING CREDENTIALS',
                'ESTABLISHING SECURE TUNNEL',
                'ACCESS GRANTED'
            ];

            await runStatusSequence(statusText, stages, 650);

            setTimeout(() => {
                if (formData.username && formData.password) {
                    localStorage.setItem('isLoggedIn', 'true');
                    localStorage.setItem('username', formData.username);
                    if (formData.rememberMe) {
                        localStorage.setItem('rememberUsername', formData.username);
                    }
                    window.location.href = 'index.html';
                } else {
                    showLoginError('用户名或密码错误');
                    if (statusText) statusText.textContent = 'ACCESS DENIED';
                    btnText.style.display = 'inline-block';
                    btnLoader.style.display = 'none';
                    loginBtn.disabled = false;
                }
            }, 300);
        });
    }

    const rememberedUsername = localStorage.getItem('rememberUsername');
    if (rememberedUsername) {
        const usernameInput = document.getElementById('username');
        if (usernameInput) {
            usernameInput.value = rememberedUsername;
            document.getElementById('rememberMe').checked = true;
        }
    }
}

function runStatusSequence(el, stages, stepMs) {
    if (!el) return Promise.resolve();
    return new Promise(resolve => {
        let index = 0;
        el.textContent = stages[index];
        const timer = setInterval(() => {
            index += 1;
            if (index >= stages.length) {
                clearInterval(timer);
                resolve();
                return;
            }
            el.textContent = stages[index];
        }, stepMs);
    });
}

function showLoginError(message) {
    const passwordError = document.getElementById('passwordError');
    if (passwordError) {
        passwordError.textContent = message;
        passwordError.style.display = 'block';

        const loginBox = document.querySelector('.login-box');
        loginBox.style.animation = 'shake 0.5s';
        setTimeout(() => {
            loginBox.style.animation = '';
        }, 500);
    }
}
