/**
 * ============================================
 * 检测系统模块（摄像头视频流）
 * 功能：显示视频流、检测结果、图像参数调整
 * ============================================
 */

const DETECTION_API_BASE = "http://ynlu100202514.vicp.fun:26987"; // 检测系统API地址

// 全局变量
let videoStreamUrl = null;
let detectionStatusInterval = null;
let imageParams = {};
let detectionParams = {};
let detectionAutoPolling = true;

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('检测系统模块初始化...');
    
    // 检查是否在检测系统页面
    const detectionSection = document.getElementById('detection-system-section');
    if (!detectionSection) {
        console.log('检测系统页面未找到，跳过初始化');
        return;
    }
    
    // 启用摄像头视频面板（显示 simplified version.py 的画面）
    const videoPanel = detectionSection.querySelector('.detection-video-panel');
    if (videoPanel) {
        videoPanel.style.display = 'block';
    }
    
    // 初始化视频流显示
    initVideoStream();
    
    // 初始化检测结果监控按钮（刷新 / 开关自动轮询）
    initDetectionMonitorControls();
    
    // 启动状态自动更新（从后端获取最新检测结果和检测状态）
    startDetectionStatusUpdate();
    startDetectionSystemStatusUpdate();
    
    // 页面打开时自动确保检测系统运行（向控制系统推送信息）
    ensureDetectionSystemRunning();
    
    console.log('检测系统模块初始化完成（摄像头画面 + 检测信息）！');
});

// ==================== 视频流（显示 simplified version.py 的画面） ====================

/**
 * 初始化视频流显示
 */
function initVideoStream() {
    const videoImg = document.getElementById('detectionVideo');
    if (!videoImg) return;
    
    // 设置 MJPEG 流地址（来自 detection_api_server.py）
    const streamUrl = `${DETECTION_API_BASE}/api/video/stream`;
    videoImg.src = streamUrl;
    videoImg.onerror = function() {
        console.warn('视频流加载失败，请确保 detection_api_server.py 正在运行');
        videoImg.alt = '视频流加载失败';
    };
    
    // 刷新按钮
    const refreshBtn = document.getElementById('refreshVideoStreamBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            videoImg.src = '';
            setTimeout(() => {
                videoImg.src = streamUrl;
            }, 100);
        });
    }
    
    // 连接控制系统按钮
    const connectBtn = document.getElementById('connectControlSystemBtn');
    if (connectBtn) {
        connectBtn.addEventListener('click', async function() {
            try {
                const res = await fetch(`${DETECTION_API_BASE}/api/control/connect`, {
                    method: 'POST'
                });
                const data = await res.json();
                if (data.success) {
                    alert('✅ 已连接到控制系统');
                } else {
                    alert('⚠️ ' + data.message);
                }
            } catch (e) {
                alert('❌ 连接失败: ' + e.message);
            }
        });
    }
    
    console.log('视频流已初始化:', streamUrl);
}

// ==================== 检测控制 ====================

// 检测控制：摄像头由 simplified version.py 管理，此处不再启动/停止摄像头，
// 后续可在这里扩展与后端的健康检查等简单控制。

// ==================== 图像参数 ====================

/**
 * 更新图像参数
 */
async function updateImageParams() {
    const params = {
        brightness: parseInt(document.getElementById('brightnessSlider')?.value) || 256,
        contrast: parseInt(document.getElementById('contrastSlider')?.value) || 0,
        sharpness: parseInt(document.getElementById('sharpnessSlider')?.value) || 0,
        gamma: parseInt(document.getElementById('gammaSlider')?.value) || 65,
        denoise: parseInt(document.getElementById('denoiseSelect')?.value) || 0,
        hist_eq: parseInt(document.getElementById('histEqSelect')?.value) || 0,
        threshold: parseInt(document.getElementById('thresholdSelect')?.value) || 0
    };
    
    const url = `${DETECTION_API_BASE}/api/image/params`;
    
    try {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(params)
        });
        
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        imageParams = data.params;
        console.log('图像参数已更新', imageParams);
        
    } catch (e) {
        console.error("更新图像参数失败", e);
    }
}

/**
 * 初始化图像参数
 */
function initImageParams() {
    // 绑定滑块和选择框的变化事件
    const sliders = ['brightnessSlider', 'contrastSlider', 'sharpnessSlider', 'gammaSlider'];
    const selects = ['denoiseSelect', 'histEqSelect', 'thresholdSelect'];
    
    sliders.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('input', updateImageParams);
        }
    });
    
    selects.forEach(id => {
        const element = document.getElementById(id);
        if (element) {
            element.addEventListener('change', updateImageParams);
        }
    });
    
    // 加载当前参数
    loadImageParams();
}

// ==================== 检测监控控制 ====================

/**
 * 初始化检测监控控制按钮（刷新 / 开关自动轮询）
 */
function initDetectionMonitorControls() {
    const infoPanel = document.querySelector('#detection-system-section .detection-info-panel');
    if (!infoPanel) return;

    // 创建控制按钮区域
    const controlsBar = document.createElement('div');
    controlsBar.style.display = 'flex';
    controlsBar.style.gap = '8px';
    controlsBar.style.marginTop = '8px';

    const refreshBtn = document.createElement('button');
    refreshBtn.textContent = '立即刷新检测';
    refreshBtn.className = 'btn btn-secondary btn-sm';
    refreshBtn.addEventListener('click', fetchLatestDetection);

    const toggleBtn = document.createElement('button');
    toggleBtn.textContent = '暂停自动刷新';
    toggleBtn.className = 'btn btn-secondary btn-sm';
    toggleBtn.addEventListener('click', () => {
        detectionAutoPolling = !detectionAutoPolling;
        if (!detectionAutoPolling) {
            stopDetectionStatusUpdate();
            toggleBtn.textContent = '恢复自动刷新';
        } else {
            startDetectionStatusUpdate();
            toggleBtn.textContent = '暂停自动刷新';
        }
    });

    controlsBar.appendChild(refreshBtn);
    controlsBar.appendChild(toggleBtn);

    // 插入到面板底部
    infoPanel.appendChild(controlsBar);
}

/**
 * 加载图像参数
 */
async function loadImageParams() {
    const url = `${DETECTION_API_BASE}/api/image/params`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        imageParams = data.params;
        
        // 更新UI
        updateImageParamsUI(data.params);
        
    } catch (e) {
        console.error("加载图像参数失败", e);
    }
}

/**
 * 更新图像参数UI
 */
function updateImageParamsUI(params) {
    if (document.getElementById('brightnessSlider')) {
        document.getElementById('brightnessSlider').value = params.brightness || 256;
    }
    if (document.getElementById('contrastSlider')) {
        document.getElementById('contrastSlider').value = params.contrast || 0;
    }
    if (document.getElementById('sharpnessSlider')) {
        document.getElementById('sharpnessSlider').value = params.sharpness || 0;
    }
    if (document.getElementById('gammaSlider')) {
        document.getElementById('gammaSlider').value = params.gamma || 65;
    }
}

// ==================== 检测参数 ====================

/**
 * 更新检测参数
 */
async function updateDetectionParams() {
    const params = {
        target_fps: parseInt(document.getElementById('targetFpsSlider')?.value) || 30,
        confidence_threshold: parseFloat(document.getElementById('confidenceSlider')?.value) || 0.5
    };
    
    const url = `${DETECTION_API_BASE}/api/detection/params`;
    
    try {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(params)
        });
        
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        detectionParams = data.params;
        console.log('检测参数已更新', detectionParams);
        
    } catch (e) {
        console.error("更新检测参数失败", e);
    }
}

/**
 * 初始化检测参数
 */
function initDetectionParams() {
    const fpsSlider = document.getElementById('targetFpsSlider');
    const confidenceSlider = document.getElementById('confidenceSlider');
    
    if (fpsSlider) {
        fpsSlider.addEventListener('input', updateDetectionParams);
    }
    
    if (confidenceSlider) {
        confidenceSlider.addEventListener('input', updateDetectionParams);
    }
    
    // 加载当前参数
    loadDetectionParams();
}

/**
 * 加载检测参数
 */
async function loadDetectionParams() {
    const url = `${DETECTION_API_BASE}/api/detection/params`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        detectionParams = data.params;
        
        // 更新UI
        if (document.getElementById('targetFpsSlider')) {
            document.getElementById('targetFpsSlider').value = detectionParams.target_fps || 30;
        }
        if (document.getElementById('confidenceSlider')) {
            document.getElementById('confidenceSlider').value = detectionParams.confidence_threshold || 0.5;
        }
        
    } catch (e) {
        console.error("加载检测参数失败", e);
    }
}

// ==================== 状态更新 ====================

/**
 * 获取最新检测结果
 */
async function fetchLatestDetection() {
    const url = `${DETECTION_API_BASE}/api/detection/latest`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        if (data.success && data.detection) {
            updateDetectionDisplay(data.detection);
        }
        
    } catch (e) {
        console.error("获取检测结果失败", e);
    }
}

/**
 * 更新检测结果显示
 */
function updateDetectionDisplay(detection) {
    const modeEl = document.getElementById('detectedMode');
    const confidenceEl = document.getElementById('detectionConfidence');
    const timestampEl = document.getElementById('detectionTimestamp');
    
    if (modeEl) {
        modeEl.textContent = detection.detected_mode || "none";
    }
    
    if (confidenceEl) {
        confidenceEl.textContent = detection.confidence 
            ? (detection.confidence * 100).toFixed(1) + '%'
            : '0%';
    }
    
    if (timestampEl && detection.timestamp) {
        const date = new Date(detection.timestamp * 1000);
        timestampEl.textContent = date.toLocaleTimeString("zh-CN");
    }
}

/**
 * 启动状态更新
 */
function startDetectionStatusUpdate() {
    if (detectionStatusInterval) {
        return;
    }
    // 每2秒更新一次检测结果
    detectionStatusInterval = setInterval(() => {
        if (detectionAutoPolling) {
            fetchLatestDetection();
        }
    }, 2000);
}

/**
 * 停止状态更新
 */
function stopDetectionStatusUpdate() {
    if (detectionStatusInterval) {
        clearInterval(detectionStatusInterval);
        detectionStatusInterval = null;
    }
}

// ==================== 检测系统状态更新 ====================

let detectionSystemStatusInterval = null;

/**
 * 启动检测系统状态更新（FPS、运行状态等）
 */
function startDetectionSystemStatusUpdate() {
    if (detectionSystemStatusInterval) {
        return;
    }
    // 每3秒更新一次检测系统状态
    detectionSystemStatusInterval = setInterval(() => {
        fetchDetectionSystemStatus();
    }, 3000);
    // 立即执行一次
    fetchDetectionSystemStatus();
}

/**
 * 停止检测系统状态更新
 */
function stopDetectionSystemStatusUpdate() {
    if (detectionSystemStatusInterval) {
        clearInterval(detectionSystemStatusInterval);
        detectionSystemStatusInterval = null;
    }
}

/**
 * 获取检测系统状态
 */
async function fetchDetectionSystemStatus() {
    const url = `${DETECTION_API_BASE}/api/detection/status`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        // 更新运行状态
        const statusEl = document.getElementById('detectionRunningStatus');
        if (statusEl) {
            if (data.running) {
                statusEl.textContent = '运行中';
                statusEl.style.color = '#28a745';
            } else {
                statusEl.textContent = '未运行';
                statusEl.style.color = '#dc3545';
            }
        }
        
        // 更新FPS
        const fpsEl = document.getElementById('detectionFps');
        if (fpsEl && data.fps) {
            fpsEl.textContent = data.fps.toFixed(1) + ' fps';
        }
        
        // 更新帧数
        const framesEl = document.getElementById('detectionFramesReceived');
        if (framesEl && data.frames_received !== undefined) {
            framesEl.textContent = data.frames_received.toLocaleString();
        }
        
    } catch (e) {
        console.error("获取检测系统状态失败", e);
        const statusEl = document.getElementById('detectionRunningStatus');
        if (statusEl) {
            statusEl.textContent = '连接失败';
            statusEl.style.color = '#dc3545';
        }
    }
}

// ==================== 确保检测系统运行 ====================

/**
 * 确保检测系统正在运行（页面打开时自动启动）
 * 说明：detection_api_server.py 启动时会自动拉起 simplified version.py，
 *       这里只是检查状态，确保检测系统正常工作并向控制系统推送信息
 */
async function ensureDetectionSystemRunning() {
    try {
        // 检查检测系统状态
        const statusRes = await fetch(`${DETECTION_API_BASE}/api/detection/status`);
        if (statusRes.ok) {
            const statusData = await statusRes.json();
            if (statusData.running) {
                console.log('✅ 检测系统正在运行，已自动向控制系统推送信息');
                return;
            }
        }
        
        // 如果未运行，尝试连接控制系统（确保通信链路正常）
        const connectRes = await fetch(`${DETECTION_API_BASE}/api/control/connect`, {
            method: 'POST'
        });
        if (connectRes.ok) {
            const connectData = await connectRes.json();
            if (connectData.success) {
                console.log('✅ 已连接到控制系统，检测结果将自动推送');
            } else {
                console.warn('⚠️ 控制系统连接失败:', connectData.message);
            }
        }
        
    } catch (e) {
        console.warn('⚠️ 检测系统状态检查失败:', e.message);
        console.warn('   请确保 detection_api_server.py 正在运行（端口8001）');
    }
}
