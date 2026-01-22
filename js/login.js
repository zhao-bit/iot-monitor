/**
 * ============================================
 * 登录页面功能
 * 功能：粒子背景、表单验证、登录处理
 * ============================================
 */

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('登录页面初始化...');
    
    // 初始化粒子背景
    initParticleBackground();
    
    // 初始化表单验证
    initFormValidation();
    
    // 初始化登录功能
    initLogin();
    
    console.log('登录页面初始化完成！');
});

/**
 * 初始化粒子背景效果
 */
function initParticleBackground() {
    const canvas = document.getElementById('particleCanvas');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    let particles = [];
    const particleCount = 50;
    
    // 设置画布尺寸
    function resizeCanvas() {
        canvas.width = window.innerWidth;
        canvas.height = window.innerHeight;
    }
    resizeCanvas();
    window.addEventListener('resize', resizeCanvas);
    
    // 创建粒子类
    class Particle {
        constructor() {
            this.x = Math.random() * canvas.width;
            this.y = Math.random() * canvas.height;
            this.size = Math.random() * 2 + 1;
            this.speedX = Math.random() * 0.5 - 0.25;
            this.speedY = Math.random() * 0.5 - 0.25;
            this.opacity = Math.random() * 0.5 + 0.2;
        }
        
        update() {
            this.x += this.speedX;
            this.y += this.speedY;
            
            // 边界检测
            if (this.x > canvas.width) this.x = 0;
            if (this.x < 0) this.x = canvas.width;
            if (this.y > canvas.height) this.y = 0;
            if (this.y < 0) this.y = canvas.height;
        }
        
        draw() {
            ctx.fillStyle = `rgba(59, 130, 246, ${this.opacity})`;
            ctx.beginPath();
            ctx.arc(this.x, this.y, this.size, 0, Math.PI * 2);
            ctx.fill();
        }
    }
    
    // 创建粒子
    for (let i = 0; i < particleCount; i++) {
        particles.push(new Particle());
    }
    
    // 绘制连接线
    function drawConnections() {
        for (let i = 0; i < particles.length; i++) {
            for (let j = i + 1; j < particles.length; j++) {
                const dx = particles[i].x - particles[j].x;
                const dy = particles[i].y - particles[j].y;
                const distance = Math.sqrt(dx * dx + dy * dy);
                
                if (distance < 150) {
                    ctx.strokeStyle = `rgba(59, 130, 246, ${0.2 * (1 - distance / 150)})`;
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    ctx.moveTo(particles[i].x, particles[i].y);
                    ctx.lineTo(particles[j].x, particles[j].y);
                    ctx.stroke();
                }
            }
        }
    }
    
    // 动画循环
    function animate() {
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        
        particles.forEach(particle => {
            particle.update();
            particle.draw();
        });
        
        drawConnections();
        
        requestAnimationFrame(animate);
    }
    
    animate();
}

/**
 * 初始化表单验证
 */
function initFormValidation() {
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const usernameError = document.getElementById('usernameError');
    const passwordError = document.getElementById('passwordError');
    const togglePasswordBtn = document.getElementById('togglePassword');
    
    // 用户名验证
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
    
    // 密码显示/隐藏
    if (togglePasswordBtn && passwordInput) {
        togglePasswordBtn.addEventListener('click', function() {
            const type = passwordInput.type === 'password' ? 'text' : 'password';
            passwordInput.type = type;
            const icon = this.querySelector('i');
            icon.classList.toggle('fa-eye');
            icon.classList.toggle('fa-eye-slash');
        });
    }
    
    // 密码验证
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
    
    /**
     * 验证用户名
     */
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
    
    /**
     * 验证密码
     */
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
    
    /**
     * 显示错误
     */
    function showError(input, errorEl, message) {
        input.classList.add('error');
        if (errorEl) {
            errorEl.textContent = message;
        }
    }
    
    /**
     * 清除错误
     */
    function clearError(input, errorEl) {
        input.classList.remove('error');
        if (errorEl) {
            errorEl.textContent = '';
        }
    }
    
    // 导出验证函数供登录使用
    window.validateForm = function() {
        const usernameValid = validateUsername();
        const passwordValid = validatePassword();
        return usernameValid && passwordValid;
    };
}

/**
 * 初始化登录功能
 */
function initLogin() {
    const loginForm = document.getElementById('loginForm');
    const loginBtn = document.getElementById('loginBtn');
    
    if (loginForm) {
        loginForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            
            // 验证表单
            if (!window.validateForm()) {
                return;
            }
            
            // 显示加载状态
            const btnText = loginBtn.querySelector('.btn-text');
            const btnLoader = loginBtn.querySelector('.btn-loader');
            btnText.style.display = 'none';
            btnLoader.style.display = 'inline-block';
            loginBtn.disabled = true;
            
            // 获取表单数据
            const formData = {
                username: document.getElementById('username').value.trim(),
                password: document.getElementById('password').value,
                rememberMe: document.getElementById('rememberMe').checked
            };
            
            // ========== 未来接API的位置 ==========
            // 这里应该调用真实的登录API
            // 示例：
            // try {
            //     const response = await fetch('/api/login', {
            //         method: 'POST',
            //         headers: { 'Content-Type': 'application/json' },
            //         body: JSON.stringify(formData)
            //     });
            //     const data = await response.json();
            //     if (data.success) {
            //         localStorage.setItem('token', data.token);
            //         window.location.href = 'index.html';
            //     } else {
            //         showLoginError(data.message);
            //     }
            // } catch (error) {
            //     showLoginError('登录失败，请稍后重试');
            // }
            // ====================================
            
            // 模拟登录请求（用于演示）
            setTimeout(() => {
                // 模拟成功登录
                if (formData.username && formData.password) {
                    // 保存登录状态
                    if (formData.rememberMe) {
                        localStorage.setItem('rememberUsername', formData.username);
                    }
                    
                    // 跳转到主页面
                    window.location.href = 'index.html';
                } else {
                    // 显示错误
                    showLoginError('用户名或密码错误');
                    btnText.style.display = 'inline-block';
                    btnLoader.style.display = 'none';
                    loginBtn.disabled = false;
                }
            }, 1500);
        });
    }
    
    // 加载记住的用户名
    const rememberedUsername = localStorage.getItem('rememberUsername');
    if (rememberedUsername) {
        const usernameInput = document.getElementById('username');
        if (usernameInput) {
            usernameInput.value = rememberedUsername;
            document.getElementById('rememberMe').checked = true;
        }
    }
}

/**
 * 显示登录错误
 */
function showLoginError(message) {
    const passwordError = document.getElementById('passwordError');
    if (passwordError) {
        passwordError.textContent = message;
        passwordError.style.display = 'block';
        
        // 添加错误动画
        const loginBox = document.querySelector('.login-box');
        loginBox.style.animation = 'shake 0.5s';
        setTimeout(() => {
            loginBox.style.animation = '';
        }, 500);
    }
}
