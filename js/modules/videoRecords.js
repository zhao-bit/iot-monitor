/**
 * ============================================
 * 视频记录模块
 * 功能：历史视频记录列表、搜索、筛选、详情查看
 * ============================================
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('视频记录模块初始化...');
    
    initVideoRecords();
    initSearchAndFilter();
    initVideoDetail();

    // HUD 视觉增强
    initVideoRecordsHudEffects();
    
    console.log('视频记录模块初始化完成！');
});

// ========== 全局变量 ==========
let videoRecords = [];
let filteredRecords = [];
let currentPage = 1;
const recordsPerPage = 12;

// ==================== HUD 视觉增强 ====================

function initVideoRecordsHudEffects() {
    const section = document.getElementById('video-records');
    if (!section) return;

    const leftStream = document.getElementById('videoRecordsHexLeft');
    const rightStream = document.getElementById('videoRecordsHexRight');
    const frameEl = document.getElementById('videoRecordsHudFrame');
    const bitrateEl = document.getElementById('videoRecordsHudBitrate');
    const threatFillEl = document.getElementById('videoRecordsThreatFill');

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

    const targetSelector = '.video-records-toolbar, .video-record-card, .video-pagination';

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
 * 初始化视频记录
 */
function initVideoRecords() {
    loadVideoRecords();
    renderVideoRecords();
    
    const refreshBtn = document.getElementById('refreshVideoRecordsBtn');
    refreshBtn.addEventListener('click', function() {
        loadVideoRecords();
        renderVideoRecords();
        showMessage('记录已刷新', 'success');
    });
}

/**
 * 加载视频记录
 */
function loadVideoRecords() {
    // ========== 未来接API的位置 ==========
    // 这里应该从服务器获取视频记录
    // 示例：
    // fetch('/api/video/records')
    //     .then(response => response.json())
    //     .then(data => {
    //         videoRecords = data.records;
    //         renderVideoRecords();
    //     });
    // ====================================
    
    // 从localStorage加载或生成模拟数据
    const saved = localStorage.getItem('videoRecords');
    if (saved) {
        videoRecords = JSON.parse(saved);
    } else {
        generateMockVideoRecords();
    }
}

/**
 * 生成模拟视频记录
 */
function generateMockVideoRecords() {
    const statuses = ['completed', 'processing', 'failed'];
    const mockRecords = [];
    
    for (let i = 0; i < 15; i++) {
        const date = new Date();
        date.setDate(date.getDate() - Math.floor(Math.random() * 30));
        
        mockRecords.push({
            id: Date.now() - i * 1000000,
            name: `监控视频_${String(i + 1).padStart(3, '0')}`,
            thumbnail: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMzIwIiBoZWlnaHQ9IjE4MCIgZmlsbD0iIzFhMWUyZSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjE0IiBmaWxsPSIjNjY2IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+6L+Z5piv5LiK5Lyg5Zu+54mHPC90ZXh0Pjwvc3ZnPg==',
            duration: `${Math.floor(Math.random() * 60) + 1}:${String(Math.floor(Math.random() * 60)).padStart(2, '0')}`,
            status: statuses[Math.floor(Math.random() * statuses.length)],
            detectionCount: Math.floor(Math.random() * 50),
            timestamp: date.toLocaleString('zh-CN'),
            fileSize: (Math.random() * 100 + 10).toFixed(1) + 'MB'
        });
    }
    
    videoRecords = mockRecords;
    localStorage.setItem('videoRecords', JSON.stringify(mockRecords));
}

/**
 * 初始化搜索和筛选
 */
function initSearchAndFilter() {
    const searchInput = document.getElementById('videoSearchInput');
    const clearBtn = document.getElementById('clearVideoSearchBtn');
    const statusFilter = document.getElementById('videoFilterStatus');
    
    searchInput.addEventListener('input', function() {
        clearBtn.style.display = this.value ? 'block' : 'none';
        applyFilters();
    });
    
    clearBtn.addEventListener('click', function() {
        searchInput.value = '';
        this.style.display = 'none';
        applyFilters();
    });
    
    statusFilter.addEventListener('change', applyFilters);
}

/**
 * 应用筛选
 */
function applyFilters() {
    const searchTerm = document.getElementById('videoSearchInput').value.toLowerCase();
    const status = document.getElementById('videoFilterStatus').value;
    
    filteredRecords = videoRecords.filter(record => {
        const matchSearch = !searchTerm || 
            record.name.toLowerCase().includes(searchTerm) ||
            record.timestamp.toLowerCase().includes(searchTerm);
        
        const matchStatus = status === 'all' || record.status === status;
        
        return matchSearch && matchStatus;
    });
    
    currentPage = 1;
    renderVideoRecords();
}

/**
 * 渲染视频记录列表
 */
function renderVideoRecords() {
    const grid = document.getElementById('videoRecordsGrid');
    
    if (filteredRecords.length === 0) {
        grid.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <p>暂无视频记录</p>
            </div>
        `;
        return;
    }
    
    const totalPages = Math.ceil(filteredRecords.length / recordsPerPage);
    const start = (currentPage - 1) * recordsPerPage;
    const end = start + recordsPerPage;
    const pageRecords = filteredRecords.slice(start, end);
    
    const recordsHTML = pageRecords.map(record => createVideoRecordCard(record)).join('');
    grid.innerHTML = recordsHTML;
    
    renderPagination(totalPages);
}

/**
 * 创建视频记录卡片
 */
function createVideoRecordCard(record) {
    const statusClass = {
        completed: 'success',
        processing: 'warning',
        failed: 'danger'
    }[record.status] || 'secondary';
    
    const statusText = {
        completed: '已完成',
        processing: '处理中',
        failed: '失败'
    }[record.status] || '未知';
    
    return `
        <div class="video-record-card" onclick="viewVideoDetail(${record.id})">
            <div class="video-thumbnail">
                <img src="${record.thumbnail}" alt="${record.name}">
                <div class="video-duration">${record.duration}</div>
                <div class="video-status-badge ${statusClass}">${statusText}</div>
            </div>
            <div class="video-info">
                <h4 class="video-name">${record.name}</h4>
                <div class="video-meta">
                    <span><i class="fas fa-eye"></i> ${record.detectionCount} 次检测</span>
                    <span><i class="fas fa-clock"></i> ${record.timestamp}</span>
                </div>
                <div class="video-size">${record.fileSize}</div>
            </div>
        </div>
    `;
}

/**
 * 初始化视频详情
 */
function initVideoDetail() {
    const modal = document.getElementById('videoDetailModal');
    const closeBtn = document.getElementById('closeVideoDetailBtn');
    
    closeBtn.addEventListener('click', () => {
        modal.style.display = 'none';
    });
    
    modal.addEventListener('click', function(e) {
        if (e.target === modal) {
            modal.style.display = 'none';
        }
    });
}

/**
 * 查看视频详情
 */
function viewVideoDetail(recordId) {
    const record = videoRecords.find(r => r.id === recordId);
    if (!record) return;
    
    const modal = document.getElementById('videoDetailModal');
    const content = document.getElementById('videoDetailContent');
    
    content.innerHTML = `
        <div class="video-detail-content">
            <div class="detail-thumbnail">
                <img src="${record.thumbnail}" alt="${record.name}">
            </div>
            <div class="detail-info">
                <h4>${record.name}</h4>
                <div class="detail-item">
                    <label>状态：</label>
                    <span class="status-${record.status}">${record.status === 'completed' ? '已完成' : record.status === 'processing' ? '处理中' : '失败'}</span>
                </div>
                <div class="detail-item">
                    <label>时长：</label>
                    <span>${record.duration}</span>
                </div>
                <div class="detail-item">
                    <label>文件大小：</label>
                    <span>${record.fileSize}</span>
                </div>
                <div class="detail-item">
                    <label>检测次数：</label>
                    <span>${record.detectionCount}</span>
                </div>
                <div class="detail-item">
                    <label>处理时间：</label>
                    <span>${record.timestamp}</span>
                </div>
            </div>
        </div>
    `;
    
    modal.style.display = 'flex';
}

/**
 * 渲染分页
 */
function renderPagination(totalPages) {
    const pagination = document.getElementById('videoPagination');
    
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    
    html += `<button class="btn btn-sm btn-secondary" ${currentPage === 1 ? 'disabled' : ''} onclick="changeVideoPage(${currentPage - 1})">
        <i class="fas fa-chevron-left"></i> 上一页
    </button>`;
    
    html += `<span class="page-info">第 ${currentPage} 页，共 ${totalPages} 页</span>`;
    
    html += `<button class="btn btn-sm btn-secondary" ${currentPage === totalPages ? 'disabled' : ''} onclick="changeVideoPage(${currentPage + 1})">
        下一页 <i class="fas fa-chevron-right"></i>
    </button>`;
    
    html += '</div>';
    pagination.innerHTML = html;
}

/**
 * 切换页面
 */
function changeVideoPage(page) {
    const totalPages = Math.ceil(filteredRecords.length / recordsPerPage);
    if (page < 1 || page > totalPages) return;
    
    currentPage = page;
    renderVideoRecords();
}

// 全局函数
window.viewVideoDetail = viewVideoDetail;
window.changeVideoPage = changeVideoPage;
