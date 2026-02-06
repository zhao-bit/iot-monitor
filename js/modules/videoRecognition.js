/**
 * ============================================
 * 视频识别模块
 * 功能：视频上传、播放、实时识别结果叠加显示
 * ============================================
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('视频识别模块初始化...');
    
    initVideoUpload();
    initVideoPlayer();
    initDetection();
    initResultsPanel();

    // HUD 视觉增强
    initVideoHudEffects();
    
    console.log('视频识别模块初始化完成！');
});

// ========== 全局变量 ==========
let currentVideo = null;
let detectionInterval = null;
let isDetecting = false;
let detectionResults = [];

// ==================== HUD 视觉增强 ====================

function initVideoHudEffects() {
    const section = document.getElementById('video-recognition');
    if (!section) return;

    const leftStream = document.getElementById('videoHexLeft');
    const rightStream = document.getElementById('videoHexRight');
    const frameEl = document.getElementById('videoHudFrame');
    const bitrateEl = document.getElementById('videoHudBitrate');
    const threatFillEl = document.getElementById('videoThreatFill');

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

    const targetSelector = '.video-upload-area, .video-player-wrapper, .recognition-results-panel';

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

/**
 * 初始化视频上传功能
 */
function initVideoUpload() {
    const uploadArea = document.getElementById('videoUploadArea');
    const fileInput = document.getElementById('videoFileInput');
    const uploadBtn = document.getElementById('uploadVideoBtn');
    
    // 点击上传按钮
    uploadBtn.addEventListener('click', () => fileInput.click());
    
    // 文件选择
    fileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) handleVideoFile(file);
    });
    
    // 拖拽上传
    uploadArea.addEventListener('dragover', function(e) {
        e.preventDefault();
        uploadArea.classList.add('dragover');
    });
    
    uploadArea.addEventListener('dragleave', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
    });
    
    uploadArea.addEventListener('drop', function(e) {
        e.preventDefault();
        uploadArea.classList.remove('dragover');
        const file = e.dataTransfer.files[0];
        if (file && file.type.startsWith('video/')) {
            handleVideoFile(file);
        } else {
            showMessage('请上传视频文件！', 'error');
        }
    });
    
    function handleVideoFile(file) {
        if (file.size > 500 * 1024 * 1024) {
            showMessage('文件大小不能超过500MB！', 'error');
            return;
        }
        
        const videoUrl = URL.createObjectURL(file);
        loadVideo(videoUrl);
        showMessage('视频上传成功！', 'success');
    }
}

/**
 * 加载视频
 */
function loadVideo(videoUrl) {
    const videoPlayer = document.getElementById('videoPlayer');
    const uploadArea = document.getElementById('videoUploadArea');
    const playerWrapper = document.getElementById('videoPlayerWrapper');
    
    videoPlayer.src = videoUrl;
    currentVideo = videoUrl;
    
    uploadArea.style.display = 'none';
    playerWrapper.style.display = 'block';
    
    // 设置canvas尺寸
    videoPlayer.addEventListener('loadedmetadata', function() {
        const canvas = document.getElementById('detectionCanvas');
        canvas.width = videoPlayer.videoWidth;
        canvas.height = videoPlayer.videoHeight;
    });
}

/**
 * 初始化视频播放器
 */
function initVideoPlayer() {
    const clearBtn = document.getElementById('clearVideoBtn');
    
    clearBtn.addEventListener('click', function() {
        const videoPlayer = document.getElementById('videoPlayer');
        const uploadArea = document.getElementById('videoUploadArea');
        const playerWrapper = document.getElementById('videoPlayerWrapper');
        
        videoPlayer.pause();
        videoPlayer.src = '';
        URL.revokeObjectURL(currentVideo);
        currentVideo = null;
        
        uploadArea.style.display = 'block';
        playerWrapper.style.display = 'none';
        
        stopDetection();
        clearResults();
    });
}

/**
 * 初始化检测功能
 */
function initDetection() {
    const startBtn = document.getElementById('startDetectionBtn');
    const stopBtn = document.getElementById('stopDetectionBtn');
    const videoPlayer = document.getElementById('videoPlayer');
    
    startBtn.addEventListener('click', function() {
        if (!currentVideo) {
            showMessage('请先上传视频！', 'warning');
            return;
        }
        startDetection();
    });
    
    stopBtn.addEventListener('click', function() {
        stopDetection();
    });
    
    // 视频播放时实时检测
    videoPlayer.addEventListener('play', function() {
        if (isDetecting) {
            startDetectionLoop();
        }
    });
    
    videoPlayer.addEventListener('pause', function() {
        if (detectionInterval) {
            clearInterval(detectionInterval);
            detectionInterval = null;
        }
    });
}

/**
 * 开始检测
 */
function startDetection() {
    isDetecting = true;
    const startBtn = document.getElementById('startDetectionBtn');
    const stopBtn = document.getElementById('stopDetectionBtn');
    const videoPlayer = document.getElementById('videoPlayer');
    
    startBtn.style.display = 'none';
    stopBtn.style.display = 'inline-flex';
    
    if (!videoPlayer.paused) {
        startDetectionLoop();
    }
    
    showMessage('开始识别...', 'info');
}

/**
 * 停止检测
 */
function stopDetection() {
    isDetecting = false;
    const startBtn = document.getElementById('startDetectionBtn');
    const stopBtn = document.getElementById('stopDetectionBtn');
    
    startBtn.style.display = 'inline-flex';
    stopBtn.style.display = 'none';
    
    if (detectionInterval) {
        clearInterval(detectionInterval);
        detectionInterval = null;
    }
    
    showMessage('识别已停止', 'info');
}

/**
 * 检测循环
 */
function startDetectionLoop() {
    const videoPlayer = document.getElementById('videoPlayer');
    const interval = 2000; // 每2秒检测一次
    
    detectionInterval = setInterval(() => {
        if (videoPlayer.paused || !isDetecting) return;
        
        // ========== 未来接API的位置 ==========
        // 这里应该调用真实的视频识别API
        // 示例：
        // fetch('/api/video/detect', {
        //     method: 'POST',
        //     body: getCurrentFrame()
        // }).then(response => response.json())
        //   .then(data => {
        //       displayDetectionResults(data);
        //   });
        // ====================================
        
        // 模拟检测结果
        const mockResults = generateMockDetectionResults();
        displayDetectionResults(mockResults);
    }, interval);
}

/**
 * 生成模拟检测结果
 */
function generateMockDetectionResults() {
    const labels = ['人员', '车辆', '动物', '设备'];
    const label = labels[Math.floor(Math.random() * labels.length)];
    const confidence = (Math.random() * 0.2 + 0.8).toFixed(2);
    
    return {
        label: label,
        confidence: confidence,
        bbox: {
            x: Math.random() * 0.4 + 0.2,
            y: Math.random() * 0.4 + 0.2,
            width: Math.random() * 0.3 + 0.2,
            height: Math.random() * 0.3 + 0.2
        },
        timestamp: new Date().toLocaleTimeString('zh-CN')
    };
}

/**
 * 显示检测结果（在视频上叠加）
 */
function displayDetectionResults(result) {
    const videoPlayer = document.getElementById('videoPlayer');
    const canvas = document.getElementById('detectionCanvas');
    const ctx = canvas.getContext('2d');
    
    // 清空画布
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    
    // 绘制边界框
    const x = result.bbox.x * canvas.width;
    const y = result.bbox.y * canvas.height;
    const width = result.bbox.width * canvas.width;
    const height = result.bbox.height * canvas.height;
    
    ctx.strokeStyle = '#52c41a';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, width, height);
    
    // 绘制标签背景
    ctx.fillStyle = '#52c41a';
    ctx.fillRect(x, y - 30, width, 30);
    
    // 绘制标签文字
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 16px Arial';
    ctx.fillText(`${result.label} ${(result.confidence * 100).toFixed(1)}%`, x + 5, y - 8);
    
    // 添加到结果列表
    addDetectionResult(result);
}

/**
 * 初始化结果面板
 */
function initResultsPanel() {
    const clearBtn = document.getElementById('clearResultsBtn');
    clearBtn.addEventListener('click', clearResults);
}

/**
 * 添加检测结果到列表
 */
function addDetectionResult(result) {
    detectionResults.unshift(result);
    if (detectionResults.length > 100) {
        detectionResults = detectionResults.slice(0, 100);
    }
    
    renderResultsList();
}

/**
 * 渲染结果列表
 */
function renderResultsList() {
    const resultsList = document.getElementById('resultsList');
    
    if (detectionResults.length === 0) {
        resultsList.innerHTML = `
            <div class="empty-results">
                <i class="fas fa-inbox"></i>
                <p>暂无识别结果</p>
                <p class="hint">上传视频并开始识别后，结果将显示在这里</p>
            </div>
        `;
        return;
    }
    
    const resultsHTML = detectionResults.map((result, index) => `
        <div class="result-card">
            <div class="result-header">
                <span class="result-label">${result.label}</span>
                <span class="result-confidence">${(result.confidence * 100).toFixed(1)}%</span>
            </div>
            <div class="result-time">
                <i class="fas fa-clock"></i> ${result.timestamp}
            </div>
        </div>
    `).join('');
    
    resultsList.innerHTML = resultsHTML;
}

/**
 * 清空结果
 */
function clearResults() {
    detectionResults = [];
    renderResultsList();
    
    const canvas = document.getElementById('detectionCanvas');
    const ctx = canvas.getContext('2d');
    ctx.clearRect(0, 0, canvas.width, canvas.height);
}
