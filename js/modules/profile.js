/**
 * ============================================
 * 个人中心模块
 * 功能：用户信息、系统设置、使用统计
 * ============================================
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('个人中心模块初始化...');
    
    initUserInfo();
    initSettings();
    initStatistics();
    initLoginHistory();

    // HUD 视觉增强
    initProfileHudEffects();
    
    console.log('个人中心模块初始化完成！');
});

/**
 * 初始化用户信息
 */
function initUserInfo() {
    // ========== 未来接API的位置 ==========
    // 这里应该从服务器获取用户信息
    // fetch('/api/user/info')
    //     .then(response => response.json())
    //     .then(data => {
    //         document.getElementById('userName').textContent = data.name;
    //         document.getElementById('userEmail').textContent = data.email;
    //         document.getElementById('userAvatar').src = data.avatar;
    //     });
    // ====================================
    
    // 使用模拟数据
    const userName = localStorage.getItem('username') || '管理员';
    document.getElementById('userName').textContent = userName;
}

/**
 * 初始化系统设置
 */
function initSettings() {
    const themeToggle = document.getElementById('themeToggle');
    const notificationToggle = document.getElementById('notificationToggle');
    const languageSelect = document.getElementById('languageSelect');
    
    // 加载保存的设置
    const savedTheme = localStorage.getItem('theme');
    const savedNotification = localStorage.getItem('notifications');
    const savedLanguage = localStorage.getItem('language');
    
    if (savedTheme) themeToggle.checked = savedTheme === 'dark';
    if (savedNotification) notificationToggle.checked = savedNotification === 'true';
    if (savedLanguage) languageSelect.value = savedLanguage;
    
    // 主题切换
    themeToggle.addEventListener('change', function() {
        const theme = this.checked ? 'dark' : 'light';
        localStorage.setItem('theme', theme);
        // 这里可以添加主题切换逻辑
        showMessage('主题已切换', 'success');
    });
    
    // 通知设置
    notificationToggle.addEventListener('change', function() {
        localStorage.setItem('notifications', this.checked);
        showMessage('通知设置已更新', 'success');
    });
    
    // 语言选择
    languageSelect.addEventListener('change', function() {
        localStorage.setItem('language', this.value);
        showMessage('语言设置已更新', 'success');
    });
}

/**
 * 初始化使用统计
 */
function initStatistics() {
    // ========== 未来接API的位置 ==========
    // 这里应该从服务器获取使用统计
    // fetch('/api/user/statistics')
    //     .then(response => response.json())
    //     .then(data => {
    //         document.getElementById('totalVideos').textContent = data.totalVideos;
    //         document.getElementById('totalDetections').textContent = data.totalDetections;
    //         document.getElementById('totalTime').textContent = data.totalTime + 'h';
    //         drawChart(data);
    //     });
    // ====================================
    
    // 使用模拟数据
    const stats = {
        totalVideos: 156,
        totalDetections: 2847,
        totalTime: 342
    };
    
    document.getElementById('totalVideos').textContent = stats.totalVideos;
    document.getElementById('totalDetections').textContent = stats.totalDetections;
    document.getElementById('totalTime').textContent = stats.totalTime + 'h';
    
    // 绘制图表占位
    drawChartPlaceholder();
}

/**
 * 绘制图表占位
 */
function drawChartPlaceholder() {
    const canvas = document.getElementById('usageChart');
    if (!canvas) return;
    
    const ctx = canvas.getContext('2d');
    canvas.width = 400;
    canvas.height = 200;
    
    // 绘制简单的占位图表
    ctx.fillStyle = 'rgba(59, 130, 246, 0.1)';
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    
    ctx.fillStyle = '#3b82f6';
    ctx.font = '14px Arial';
    ctx.textAlign = 'center';
    ctx.fillText('未来接入真实统计图表API', canvas.width / 2, canvas.height / 2);
}

/**
 * 初始化登录历史
 */
function initLoginHistory() {
    // ========== 未来接API的位置 ==========
    // 这里应该从服务器获取登录历史
    // fetch('/api/user/login-history')
    //     .then(response => response.json())
    //     .then(data => {
    //         renderLoginHistory(data);
    //     });
    // ====================================
    
    // 使用模拟数据
    const history = [];
    for (let i = 0; i < 10; i++) {
        const date = new Date();
        date.setDate(date.getDate() - i);
        history.push({
            time: date.toLocaleString('zh-CN'),
            location: ['北京', '上海', '广州', '深圳'][Math.floor(Math.random() * 4)],
            ip: `192.168.1.${Math.floor(Math.random() * 255)}`,
            device: ['Windows', 'Mac', 'Linux', 'Mobile'][Math.floor(Math.random() * 4)]
        });
    }
    
    renderLoginHistory(history);
}

/**
 * 渲染登录历史
 */
function renderLoginHistory(history) {
    const list = document.getElementById('loginHistoryList');
    
    if (history.length === 0) {
        list.innerHTML = '<div class="empty-state">暂无登录历史</div>';
        return;
    }
    
    const historyHTML = history.map(item => `
        <div class="login-history-item">
            <div class="history-icon">
                <i class="fas fa-sign-in-alt"></i>
            </div>
            <div class="history-content">
                <div class="history-time">${item.time}</div>
                <div class="history-meta">
                    <span><i class="fas fa-map-marker-alt"></i> ${item.location}</span>
                    <span><i class="fas fa-network-wired"></i> ${item.ip}</span>
                    <span><i class="fas fa-desktop"></i> ${item.device}</span>
                </div>
            </div>
        </div>
    `).join('');
    
    list.innerHTML = historyHTML;
}

// ==================== HUD 视觉增强 ====================

function initProfileHudEffects() {
    const section = document.getElementById('profile');
    if (!section) return;

    const leftStream = document.getElementById('profileHexLeft');
    const rightStream = document.getElementById('profileHexRight');
    const frameEl = document.getElementById('profileHudFrame');
    const bitrateEl = document.getElementById('profileHudBitrate');
    const threatFillEl = document.getElementById('profileThreatFill');

    const makeHexLine = () => {
        const len = 8 + Math.floor(Math.random() * 8);
        let out = '';
        for (let i = 0; i < len; i += 1) {
            out += Math.floor(Math.random() * 16).toString(16).toUpperCase();
        }
        return out;
    };

    const initStream = (count = 48) => {
        const lines = [];
        for (let i = 0; i < count; i += 1) {
            lines.push(makeHexLine());
        }
        return lines;
    };

    if (leftStream && rightStream) {
        let leftLines = initStream();
        let rightLines = initStream();
        leftStream.innerHTML = leftLines.join('<br>');
        rightStream.innerHTML = rightLines.join('<br>');

        setInterval(() => {
            leftLines.shift();
            rightLines.shift();
            leftLines.push(makeHexLine());
            rightLines.push(makeHexLine());
            leftStream.innerHTML = leftLines.join('<br>');
            rightStream.innerHTML = rightLines.join('<br>');
        }, 700);
    }

    if (frameEl || bitrateEl || threatFillEl) {
        let frame = 0;
        setInterval(() => {
            frame += Math.floor(8 + Math.random() * 6);
            if (frameEl) {
                frameEl.textContent = frame.toString().padStart(5, '0');
            }
        }, 120);

        setInterval(() => {
            if (bitrateEl) {
                const bitrate = (2 + Math.random() * 8).toFixed(1);
                bitrateEl.textContent = `${bitrate} MB/s`;
            }
            if (threatFillEl) {
                const level = 20 + Math.random() * 60;
                threatFillEl.style.width = `${level}%`;
            }
        }, 900);
    }

    let rafId = null;
    let latestEvent = null;

    const targetSelector = '.profile-card, .chart-placeholder';

    const updateGlow = () => {
        rafId = null;
        if (!latestEvent) return;
        const target = latestEvent.target.closest(targetSelector);
        if (!target || !section.contains(target)) return;
        const rect = target.getBoundingClientRect();
        const x = ((latestEvent.clientX - rect.left) / rect.width) * 100;
        const y = ((latestEvent.clientY - rect.top) / rect.height) * 100;
        target.style.setProperty('--glow-x', `${x}%`);
        target.style.setProperty('--glow-y', `${y}%`);
    };

    section.addEventListener('mousemove', (event) => {
        latestEvent = event;
        if (rafId) return;
        rafId = requestAnimationFrame(updateGlow);
    });

    section.addEventListener('mouseleave', () => {
        latestEvent = null;
        const targets = section.querySelectorAll(targetSelector);
        targets.forEach((el) => {
            el.style.setProperty('--glow-x', '50%');
            el.style.setProperty('--glow-y', '50%');
        });
    });
}
