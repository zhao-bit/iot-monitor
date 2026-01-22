/**
 * ============================================
 * 实时检测模块
 * 功能：多摄像头画面、实时检测、报警通知
 * ============================================
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('实时检测模块初始化...');
    
    initDetectionControls();
    initCameraViews();
    initStatistics();
    initAlerts();
    
    console.log('实时检测模块初始化完成！');
});

// ========== 全局变量 ==========
let isDetecting = false;
let detectionIntervals = {};
let cameraData = [
    { id: 1, name: '摄像头 01', status: 'online', count: 0 },
    { id: 2, name: '摄像头 02', status: 'online', count: 0 },
    { id: 3, name: '摄像头 03', status: 'offline', count: 0 },
    { id: 4, name: '摄像头 04', status: 'online', count: 0 }
];
let totalDetections = 0;
let totalAlerts = 0;

/**
 * 初始化检测控制
 */
function initDetectionControls() {
    const startBtn = document.getElementById('startDetectionBtn');
    const stopBtn = document.getElementById('stopDetectionBtn');
    const refreshBtn = document.getElementById('refreshCamerasBtn');
    const sensitivitySlider = document.getElementById('detectionSensitivity');
    const sensitivityValue = document.getElementById('sensitivityValue');
    
    startBtn.addEventListener('click', startAllDetection);
    stopBtn.addEventListener('click', stopAllDetection);
    refreshBtn.addEventListener('click', refreshCameras);
    
    sensitivitySlider.addEventListener('input', function() {
        sensitivityValue.textContent = this.value;
    });
}

/**
 * 开始所有检测
 */
function startAllDetection() {
    isDetecting = true;
    const startBtn = document.getElementById('startDetectionBtn');
    const stopBtn = document.getElementById('stopDetectionBtn');
    
    startBtn.disabled = true;
    stopBtn.disabled = false;
    
    // 启动所有在线摄像头
    cameraData.forEach(camera => {
        if (camera.status === 'online') {
            startCameraDetection(camera.id);
        }
    });
    
    showMessage('开始实时检测', 'success');
}

/**
 * 停止所有检测
 */
function stopAllDetection() {
    isDetecting = false;
    const startBtn = document.getElementById('startDetectionBtn');
    const stopBtn = document.getElementById('stopDetectionBtn');
    
    startBtn.disabled = false;
    stopBtn.disabled = true;
    
    // 停止所有检测
    Object.keys(detectionIntervals).forEach(id => {
        clearInterval(detectionIntervals[id]);
        delete detectionIntervals[id];
    });
    
    showMessage('停止实时检测', 'info');
}

/**
 * 启动单个摄像头检测
 */
function startCameraDetection(cameraId) {
    const camera = cameraData.find(c => c.id === cameraId);
    if (!camera || camera.status !== 'online') return;
    
    const canvas = document.getElementById(`cameraCanvas${cameraId}`);
    const overlay = document.getElementById(`overlay${cameraId}`);
    const placeholder = canvas.parentElement.querySelector('.camera-placeholder');
    
    // 隐藏占位符
    if (placeholder) placeholder.style.display = 'none';
    
    // 绘制模拟视频流（静态图片轮播）
    drawMockVideoStream(canvas, cameraId);
    
    // 开始检测循环
    const interval = parseInt(document.getElementById('detectionInterval').value) * 1000;
    
    detectionIntervals[cameraId] = setInterval(() => {
        if (!isDetecting) return;
        
        // ========== 未来接API的位置 ==========
        // 这里应该调用真实的实时检测API
        // 示例：
        // fetch(`/api/detection/realtime/${cameraId}`)
        //     .then(response => response.json())
        //     .then(data => {
        //         displayDetectionOnCamera(cameraId, data);
        //     });
        // ====================================
        
        // 模拟检测结果
        const result = generateMockDetection();
        displayDetectionOnCamera(cameraId, result);
        
        camera.count++;
        totalDetections++;
        updateCameraInfo(cameraId);
        updateStatistics();
        
        // 检查是否需要报警
        if (result.alert) {
            addAlert(camera, result);
        }
    }, interval);
}

/**
 * 绘制模拟视频流
 */
function drawMockVideoStream(canvas, cameraId) {
    const ctx = canvas.getContext('2d');
    const images = [
        'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgZmlsbD0iIzFhMWUyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjI0IiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+6L+Z5piv5LiK5Lyg5Zu+54mHPC90ZXh0Pjwvc3ZnPg==',
        'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iNjQwIiBoZWlnaHQ9IjQ4MCIgZmlsbD0iIzI2M2I1MCIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjI0IiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+6L+Z5piv5LiK5Lyg5Zu+54mHPC90ZXh0Pjwvc3ZnPg=='
    ];
    
    canvas.width = 640;
    canvas.height = 480;
    
    let currentImage = 0;
    const img = new Image();
    
    function drawFrame() {
        img.onload = function() {
            ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        };
        img.src = images[currentImage];
        currentImage = (currentImage + 1) % images.length;
    }
    
    drawFrame();
    setInterval(drawFrame, 1000); // 每秒切换一次
}

/**
 * 生成模拟检测结果
 */
function generateMockDetection() {
    const labels = ['人员', '车辆', '动物'];
    const label = labels[Math.floor(Math.random() * labels.length)];
    const confidence = Math.random() * 0.2 + 0.8;
    const alert = Math.random() > 0.7; // 30%概率报警
    
    return {
        label: label,
        confidence: confidence,
        bbox: {
            x: Math.random() * 0.4 + 0.2,
            y: Math.random() * 0.4 + 0.2,
            width: Math.random() * 0.3 + 0.2,
            height: Math.random() * 0.3 + 0.2
        },
        alert: alert,
        timestamp: new Date().toLocaleTimeString('zh-CN')
    };
}

/**
 * 在摄像头上显示检测结果
 */
function displayDetectionOnCamera(cameraId, result) {
    const canvas = document.getElementById(`cameraCanvas${cameraId}`);
    const ctx = canvas.getContext('2d');
    const overlay = document.getElementById(`overlay${cameraId}`);
    
    // 绘制边界框
    const x = result.bbox.x * canvas.width;
    const y = result.bbox.y * canvas.height;
    const width = result.bbox.width * canvas.width;
    const height = result.bbox.height * canvas.height;
    
    ctx.strokeStyle = result.alert ? '#ef4444' : '#52c41a';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, width, height);
    
    // 绘制标签
    ctx.fillStyle = result.alert ? '#ef4444' : '#52c41a';
    ctx.fillRect(x, y - 30, width, 30);
    
    ctx.fillStyle = '#ffffff';
    ctx.font = 'bold 16px Arial';
    ctx.fillText(`${result.label} ${(result.confidence * 100).toFixed(1)}%`, x + 5, y - 8);
    
    // 添加闪烁动画（如果是报警）
    if (result.alert) {
        overlay.classList.add('alert-flash');
        setTimeout(() => {
            overlay.classList.remove('alert-flash');
        }, 1000);
    }
}

/**
 * 更新摄像头信息
 */
function updateCameraInfo(cameraId) {
    const camera = cameraData.find(c => c.id === cameraId);
    if (!camera) return;
    
    const countEl = document.getElementById(`count${cameraId}`);
    const lastEl = document.getElementById(`last${cameraId}`);
    
    if (countEl) countEl.textContent = `检测: ${camera.count}`;
    if (lastEl) lastEl.textContent = new Date().toLocaleTimeString('zh-CN');
}

/**
 * 刷新摄像头
 */
function refreshCameras() {
    showMessage('刷新摄像头状态...', 'info');
    
    // ========== 未来接API的位置 ==========
    // 这里应该从服务器获取摄像头状态
    // fetch('/api/cameras/status')
    //     .then(response => response.json())
    //     .then(data => {
    //         cameraData = data;
    //         updateCameraViews();
    //     });
    // ====================================
    
    setTimeout(() => {
        updateCameraViews();
        showMessage('摄像头状态已更新', 'success');
    }, 1000);
}

/**
 * 更新摄像头视图
 */
function updateCameraViews() {
    cameraData.forEach(camera => {
        const statusEl = document.querySelector(`#cameraView${camera.id} .camera-status`);
        if (statusEl) {
            statusEl.className = `camera-status ${camera.status}`;
            statusEl.innerHTML = `<i class="fas fa-circle"></i> ${camera.status === 'online' ? '在线' : '离线'}`;
        }
    });
    
    updateStatistics();
}

/**
 * 初始化摄像头视图
 */
function initCameraViews() {
    updateCameraViews();
}

/**
 * 初始化统计信息
 */
function initStatistics() {
    updateStatistics();
}

/**
 * 更新统计信息
 */
function updateStatistics() {
    const activeCount = cameraData.filter(c => c.status === 'online').length;
    const totalCount = cameraData.reduce((sum, c) => sum + c.count, 0);
    const objectCount = totalDetections;
    
    document.getElementById('totalDetections').textContent = totalCount;
    document.getElementById('activeCameras').textContent = activeCount;
    document.getElementById('totalAlerts').textContent = totalAlerts;
    document.getElementById('detectedObjects').textContent = objectCount;
}

/**
 * 初始化报警
 */
function initAlerts() {
    const clearBtn = document.getElementById('clearAlertsBtn');
    clearBtn.addEventListener('click', clearAlerts);
}

/**
 * 添加报警
 */
function addAlert(camera, result) {
    if (!document.getElementById('enableAlerts').checked) return;
    
    totalAlerts++;
    updateStatistics();
    
    const alertsList = document.getElementById('alertsList');
    const emptyAlerts = alertsList.querySelector('.empty-alerts');
    if (emptyAlerts) emptyAlerts.remove();
    
    const alertEl = document.createElement('div');
    alertEl.className = 'alert-item';
    alertEl.innerHTML = `
        <div class="alert-icon">
            <i class="fas fa-exclamation-triangle"></i>
        </div>
        <div class="alert-content">
            <div class="alert-title">${camera.name} - ${result.label}检测</div>
            <div class="alert-time">${result.timestamp}</div>
        </div>
    `;
    
    alertsList.insertBefore(alertEl, alertsList.firstChild);
    
    // 限制报警数量
    while (alertsList.children.length > 20) {
        alertsList.removeChild(alertsList.lastChild);
    }
    
    // 声音提示
    if (document.getElementById('enableSound').checked) {
        // 可以添加声音提示
    }
}

/**
 * 清空报警
 */
function clearAlerts() {
    const alertsList = document.getElementById('alertsList');
    alertsList.innerHTML = `
        <div class="empty-alerts">
            <i class="fas fa-bell-slash"></i>
            <p>暂无报警信息</p>
        </div>
    `;
    totalAlerts = 0;
    updateStatistics();
}
