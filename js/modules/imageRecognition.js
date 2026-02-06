/**
 * ============================================
 * 图片识别模块
 * 功能：图片上传、摄像头拍摄、AI识别（模拟）
 * ============================================
 */

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('图片识别模块初始化...');
    
    // 初始化图片上传功能
    initImageUpload();
    
    // 初始化摄像头功能
    initCamera();
    
    // 初始化识别按钮功能
    initRecognitionButton();
    
    // 初始化识别结果功能
    initRecognitionResults();

    // HUD 视觉增强
    initImageHudEffects();
    
    console.log('图片识别模块初始化完成！');
});

// ========== 全局变量 ==========
let currentImage = null; // 当前处理的图片
let cameraStream = null; // 摄像头流对象
let recognitionData = null; // 识别结果数据

// ==================== HUD 视觉增强 ====================

function initImageHudEffects() {
    const section = document.getElementById('image-recognition');
    if (!section) return;

    const leftStream = document.getElementById('imageHexLeft');
    const rightStream = document.getElementById('imageHexRight');
    const frameEl = document.getElementById('imageHudFrame');
    const bitrateEl = document.getElementById('imageHudBitrate');
    const threatFillEl = document.getElementById('imageThreatFill');

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

    const targetSelector = '.upload-area, .camera-section, .recognition-actions, .recognition-results';

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
 * 初始化图片上传功能
 */
function initImageUpload() {
    const uploadArea = document.getElementById('uploadArea');
    const fileInput = document.getElementById('fileInput');
    const uploadBtn = document.getElementById('uploadBtn');
    const uploadPreview = document.getElementById('uploadPreview');
    const previewImage = document.getElementById('previewImage');
    const removeImageBtn = document.getElementById('removeImage');
    
    // 点击上传按钮
    uploadBtn.addEventListener('click', function() {
        fileInput.click();
    });
    
    // 文件选择事件
    fileInput.addEventListener('change', function(e) {
        const file = e.target.files[0];
        if (file) {
            handleFileSelect(file);
        }
    });
    
    // 拖拽上传功能
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
        if (file && file.type.startsWith('image/')) {
            handleFileSelect(file);
        } else {
            showMessage('请上传图片文件！', 'error');
        }
    });
    
    // 移除图片
    removeImageBtn.addEventListener('click', function() {
        resetUploadArea();
    });
    
    /**
     * 处理文件选择
     * @param {File} file - 选择的文件
     */
    function handleFileSelect(file) {
        // 验证文件类型
        if (!file.type.startsWith('image/')) {
            showMessage('请选择图片文件！', 'error');
            return;
        }
        
        // 验证文件大小（10MB）
        if (file.size > 10 * 1024 * 1024) {
            showMessage('文件大小不能超过10MB！', 'error');
            return;
        }
        
        // 读取文件并显示预览
        const reader = new FileReader();
        reader.onload = function(e) {
            const imageUrl = e.target.result;
            displayImagePreview(imageUrl);
            currentImage = imageUrl;
            
            // 不自动识别，等待用户点击识别按钮
            showMessage('图片上传成功，请点击"开始识别"按钮进行识别', 'success');
        };
        reader.readAsDataURL(file);
    }
    
    /**
     * 显示图片预览
     * @param {string} imageUrl - 图片URL
     */
    function displayImagePreview(imageUrl) {
        const uploadContent = uploadArea.querySelector('.upload-content');
        uploadContent.style.display = 'none';
        uploadPreview.style.display = 'block';
        previewImage.src = imageUrl;
        
        // 显示识别按钮区域
        const recognitionActions = document.getElementById('recognitionActions');
        if (recognitionActions) {
            recognitionActions.style.display = 'flex';
        }
    }
    
    /**
     * 重置上传区域
     */
    function resetUploadArea() {
        const uploadContent = uploadArea.querySelector('.upload-content');
        uploadContent.style.display = 'block';
        uploadPreview.style.display = 'none';
        fileInput.value = '';
        currentImage = null;
        
        // 隐藏识别按钮和结果
        const recognitionActions = document.getElementById('recognitionActions');
        const recognitionResults = document.getElementById('recognitionResults');
        if (recognitionActions) {
            recognitionActions.style.display = 'none';
        }
        if (recognitionResults) {
            recognitionResults.style.display = 'none';
        }
    }
}

/**
 * 初始化摄像头功能
 */
function initCamera() {
    const startCameraBtn = document.getElementById('startCameraBtn');
    const captureBtn = document.getElementById('captureBtn');
    const stopCameraBtn = document.getElementById('stopCameraBtn');
    const cameraVideo = document.getElementById('cameraVideo');
    const cameraCanvas = document.getElementById('cameraCanvas');
    const cameraPlaceholder = document.getElementById('cameraPlaceholder');
    
    // 启动摄像头
    startCameraBtn.addEventListener('click', async function() {
        try {
            // 请求摄像头权限
            cameraStream = await navigator.mediaDevices.getUserMedia({
                video: {
                    width: { ideal: 1280 },
                    height: { ideal: 720 },
                    facingMode: 'environment' // 优先使用后置摄像头
                }
            });
            
            // 显示视频流
            cameraVideo.srcObject = cameraStream;
            cameraVideo.style.display = 'block';
            cameraPlaceholder.style.display = 'none';
            
            // 更新按钮状态
            startCameraBtn.disabled = true;
            captureBtn.disabled = false;
            stopCameraBtn.disabled = false;
            
            showMessage('摄像头启动成功！', 'success');
        } catch (error) {
            console.error('摄像头启动失败：', error);
            showMessage('摄像头启动失败，请检查权限设置！', 'error');
        }
    });
    
    // 拍摄照片
    captureBtn.addEventListener('click', function() {
        if (!cameraStream) {
            showMessage('请先启动摄像头！', 'warning');
            return;
        }
        
        // 设置canvas尺寸
        const video = cameraVideo;
        cameraCanvas.width = video.videoWidth;
        cameraCanvas.height = video.videoHeight;
        
        // 绘制当前帧到canvas
        const ctx = cameraCanvas.getContext('2d');
        ctx.drawImage(video, 0, 0);
        
        // 获取图片数据
        const imageData = cameraCanvas.toDataURL('image/jpeg', 0.9);
        currentImage = imageData;
        
        // 显示预览（不自动识别，等待用户点击识别按钮）
        displayImagePreview(imageData);
        
        showMessage('照片拍摄成功，请点击"开始识别"按钮进行识别', 'success');
    });
    
    // 停止摄像头
    stopCameraBtn.addEventListener('click', function() {
        stopCamera();
    });
    
    /**
     * 停止摄像头
     */
    function stopCamera() {
        if (cameraStream) {
            // 停止所有视频轨道
            cameraStream.getTracks().forEach(track => track.stop());
            cameraStream = null;
            
            // 隐藏视频
            cameraVideo.srcObject = null;
            cameraVideo.style.display = 'none';
            cameraPlaceholder.style.display = 'block';
            
            // 更新按钮状态
            startCameraBtn.disabled = false;
            captureBtn.disabled = true;
            stopCameraBtn.disabled = true;
            
            showMessage('摄像头已关闭', 'info');
        }
    }
    
    // 页面卸载时关闭摄像头
    window.addEventListener('beforeunload', function() {
        stopCamera();
    });
}

/**
 * 初始化识别按钮功能
 */
function initRecognitionButton() {
    const recognizeBtn = document.getElementById('recognizeBtn');
    const clearImageBtn = document.getElementById('clearImageBtn');
    
    // 识别按钮点击事件
    if (recognizeBtn) {
        recognizeBtn.addEventListener('click', function() {
            if (!currentImage) {
                showMessage('请先上传或拍摄图片！', 'warning');
                return;
            }
            performRecognition(currentImage);
        });
    }
    
    // 清除图片按钮
    if (clearImageBtn) {
        clearImageBtn.addEventListener('click', function() {
            resetUploadArea();
            // 同时重置摄像头区域（如果正在使用）
            const uploadArea = document.getElementById('uploadArea');
            const uploadContent = uploadArea.querySelector('.upload-content');
            uploadContent.style.display = 'block';
        });
    }
}

/**
 * 初始化识别结果功能
 */
function initRecognitionResults() {
    const saveResultBtn = document.getElementById('saveResultBtn');
    const newRecognitionBtn = document.getElementById('newRecognitionBtn');
    
    // 保存结果
    saveResultBtn.addEventListener('click', function() {
        if (!recognitionData) {
            showMessage('没有可保存的识别结果！', 'warning');
            return;
        }
        
        // 保存到本地存储（模拟）
        saveRecognitionRecord(recognitionData);
        showMessage('识别结果已保存！', 'success');
    });
    
    // 重新识别
    newRecognitionBtn.addEventListener('click', function() {
        // 重置上传区域
        const uploadArea = document.getElementById('uploadArea');
        const uploadContent = uploadArea.querySelector('.upload-content');
        const uploadPreview = document.getElementById('uploadPreview');
        uploadContent.style.display = 'block';
        uploadPreview.style.display = 'none';
        
        // 隐藏识别结果
        const recognitionResults = document.getElementById('recognitionResults');
        recognitionResults.style.display = 'none';
        
        // 清空文件输入
        document.getElementById('fileInput').value = '';
        currentImage = null;
        recognitionData = null;
    });
}

/**
 * 执行图片识别（模拟AI识别）
 * @param {string} imageUrl - 图片URL
 */
function performRecognition(imageUrl) {
    showMessage('正在识别中...', 'info');
    
    // 模拟AI识别过程（实际项目中这里应该调用后端API）
    setTimeout(() => {
        // 生成模拟识别结果
        const mockResults = generateMockRecognitionResult();
        recognitionData = {
            image: imageUrl,
            label: mockResults.label,
            confidence: mockResults.confidence,
            bbox: mockResults.bbox,
            timestamp: new Date().toLocaleString('zh-CN')
        };
        
        // 显示识别结果
        displayRecognitionResults(recognitionData);
        
        showMessage('识别完成！', 'success');
    }, 1500); // 模拟1.5秒的识别时间
}

/**
 * 生成模拟识别结果
 * @returns {Object} 识别结果对象
 */
function generateMockRecognitionResult() {
    // 模拟的识别标签列表
    const labels = [
        '人员', '车辆', '动物', '建筑物', '植物',
        '设备', '标志牌', '障碍物', '其他物体'
    ];
    
    // 随机选择一个标签
    const label = labels[Math.floor(Math.random() * labels.length)];
    
    // 生成随机置信度（80%-99%）
    const confidence = (Math.random() * 0.19 + 0.8).toFixed(2);
    
    // 生成随机边界框（模拟物体位置）
    const bbox = {
        x: Math.random() * 0.3 + 0.2, // x坐标（20%-50%）
        y: Math.random() * 0.3 + 0.2, // y坐标（20%-50%）
        width: Math.random() * 0.3 + 0.2, // 宽度（20%-50%）
        height: Math.random() * 0.3 + 0.2 // 高度（20%-50%）
    };
    
    return { label, confidence, bbox };
}

/**
 * 显示识别结果
 * @param {Object} data - 识别结果数据
 */
function displayRecognitionResults(data) {
    const resultsSection = document.getElementById('recognitionResults');
    const resultImage = document.getElementById('resultImage');
    const resultCanvas = document.getElementById('resultCanvas');
    const resultLabel = document.getElementById('resultLabel');
    const resultConfidence = document.getElementById('resultConfidence');
    const resultTime = document.getElementById('resultTime');
    
    // 显示结果区域
    resultsSection.style.display = 'block';
    
    // 显示图片
    resultImage.src = data.image;
    
    // 等待图片加载后绘制边界框
    resultImage.onload = function() {
        drawBoundingBox(resultCanvas, resultImage, data.bbox);
    };
    
    // 显示识别信息
    resultLabel.textContent = data.label;
    resultConfidence.textContent = `${(data.confidence * 100).toFixed(1)}%`;
    resultTime.textContent = data.timestamp;
    
    // 滚动到结果区域
    resultsSection.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

/**
 * 绘制边界框
 * @param {HTMLCanvasElement} canvas - Canvas元素
 * @param {HTMLImageElement} image - 图片元素
 * @param {Object} bbox - 边界框数据 {x, y, width, height}
 */
function drawBoundingBox(canvas, image, bbox) {
    // 设置canvas尺寸与图片一致
    canvas.width = image.offsetWidth;
    canvas.height = image.offsetHeight;
    
    const ctx = canvas.getContext('2d');
    
    // 计算实际像素坐标
    const x = bbox.x * canvas.width;
    const y = bbox.y * canvas.height;
    const width = bbox.width * canvas.width;
    const height = bbox.height * canvas.height;
    
    // 绘制边界框
    ctx.strokeStyle = '#52c41a';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, width, height);
    
    // 绘制标签背景
    ctx.fillStyle = '#52c41a';
    ctx.fillRect(x, y - 25, width, 25);
    
    // 绘制标签文字
    ctx.fillStyle = '#ffffff';
    ctx.font = '14px Arial';
    ctx.fillText('检测对象', x + 5, y - 8);
}

/**
 * 保存识别记录到本地存储
 * @param {Object} data - 识别结果数据
 */
function saveRecognitionRecord(data) {
    try {
        // 从本地存储获取现有记录
        let records = JSON.parse(localStorage.getItem('recognitionRecords') || '[]');
        
        // 添加新记录
        records.unshift({
            id: Date.now(),
            ...data
        });
        
        // 限制最多保存100条记录
        if (records.length > 100) {
            records = records.slice(0, 100);
        }
        
        // 保存到本地存储
        localStorage.setItem('recognitionRecords', JSON.stringify(records));
        
        console.log('识别记录已保存，当前共有', records.length, '条记录');
    } catch (error) {
        console.error('保存识别记录失败：', error);
        showMessage('保存失败，请检查浏览器存储权限！', 'error');
    }
}
