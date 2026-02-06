/**
 * ============================================
 * 实时记录模块
 * 功能：记录管理、搜索筛选、统计分析
 * ============================================
 */

document.addEventListener('DOMContentLoaded', function() {
    console.log('实时记录模块初始化...');
    
    initRecords();
    initSearchAndFilter();
    initStatistics();

    // HUD 视觉增强
    initRealtimeRecordsHudEffects();
    
    console.log('实时记录模块初始化完成！');
});

// ========== 全局变量 ==========
let allRecords = [];
let filteredRecords = [];
let currentPage = 1;
const recordsPerPage = 20;

// ==================== HUD 视觉增强 ====================

function initRealtimeRecordsHudEffects() {
    const section = document.getElementById('realtime-records');
    if (!section) return;

    const leftStream = document.getElementById('realtimeRecordsHexLeft');
    const rightStream = document.getElementById('realtimeRecordsHexRight');
    const frameEl = document.getElementById('realtimeRecordsHudFrame');
    const bitrateEl = document.getElementById('realtimeRecordsHudBitrate');
    const threatFillEl = document.getElementById('realtimeRecordsThreatFill');

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

    const targetSelector = '.records-toolbar, .records-stats-grid, .realtime-record-item, .records-pagination';

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
 * 初始化记录
 */
function initRecords() {
    loadRecords();
    renderRecords();
    
    const refreshBtn = document.getElementById('refreshRealtimeRecordsBtn');
    refreshBtn.addEventListener('click', function() {
        loadRecords();
        renderRecords();
        showMessage('记录已刷新', 'success');
    });
    
    const exportBtn = document.getElementById('exportRecordsBtn');
    exportBtn.addEventListener('click', exportRecords);
}

/**
 * 加载记录
 */
function loadRecords() {
    // ========== 未来接API的位置 ==========
    // 这里应该从服务器获取实时记录
    // fetch('/api/realtime/records')
    //     .then(response => response.json())
    //     .then(data => {
    //         allRecords = data.records;
    //         renderRecords();
    //     });
    // ====================================
    
    const saved = localStorage.getItem('realtimeRecords');
    if (saved) {
        allRecords = JSON.parse(saved);
    } else {
        generateMockRecords();
    }
    
    allRecords.sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));
}

/**
 * 生成模拟记录
 */
function generateMockRecords() {
    const types = ['detection', 'alert', 'control', 'status'];
    const labels = ['人员', '车辆', '动物', '设备'];
    const devices = ['摄像头 01', '摄像头 02', '摄像头 03', '摄像头 04'];
    const severities = ['low', 'medium', 'high'];
    
    const mockRecords = [];
    for (let i = 0; i < 50; i++) {
        const type = types[Math.floor(Math.random() * types.length)];
        const date = new Date();
        date.setHours(date.getHours() - Math.floor(Math.random() * 168)); // 过去一周
        
        mockRecords.push({
            id: Date.now() - i * 1000000,
            type: type,
            label: labels[Math.floor(Math.random() * labels.length)],
            device: devices[Math.floor(Math.random() * devices.length)],
            severity: severities[Math.floor(Math.random() * severities.length)],
            timestamp: date.toLocaleString('zh-CN'),
            description: `${type === 'detection' ? '检测到' : type === 'alert' ? '报警：' : type === 'control' ? '控制：' : '状态：'}${labels[Math.floor(Math.random() * labels.length)]}`,
            confidence: (Math.random() * 0.2 + 0.8).toFixed(2)
        });
    }
    
    allRecords = mockRecords;
    localStorage.setItem('realtimeRecords', JSON.stringify(mockRecords));
}

/**
 * 初始化搜索和筛选
 */
function initSearchAndFilter() {
    const searchInput = document.getElementById('realtimeSearchInput');
    const clearBtn = document.getElementById('clearRealtimeSearchBtn');
    const typeFilter = document.getElementById('realtimeFilterType');
    const dateFilter = document.getElementById('realtimeFilterDate');
    
    searchInput.addEventListener('input', function() {
        clearBtn.style.display = this.value ? 'block' : 'none';
        applyFilters();
    });
    
    clearBtn.addEventListener('click', function() {
        searchInput.value = '';
        this.style.display = 'none';
        applyFilters();
    });
    
    typeFilter.addEventListener('change', applyFilters);
    dateFilter.addEventListener('change', applyFilters);
}

/**
 * 应用筛选
 */
function applyFilters() {
    const searchTerm = document.getElementById('realtimeSearchInput').value.toLowerCase();
    const type = document.getElementById('realtimeFilterType').value;
    const date = document.getElementById('realtimeFilterDate').value;
    
    filteredRecords = allRecords.filter(record => {
        const matchSearch = !searchTerm ||
            record.label.toLowerCase().includes(searchTerm) ||
            record.device.toLowerCase().includes(searchTerm) ||
            record.timestamp.toLowerCase().includes(searchTerm);
        
        const matchType = type === 'all' || record.type === type;
        
        let matchDate = true;
        if (date !== 'all') {
            const recordDate = new Date(record.timestamp);
            const now = new Date();
            switch (date) {
                case 'today':
                    matchDate = recordDate.toDateString() === now.toDateString();
                    break;
                case 'week':
                    const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);
                    matchDate = recordDate >= weekAgo;
                    break;
                case 'month':
                    const monthAgo = new Date(now.getTime() - 30 * 24 * 60 * 60 * 1000);
                    matchDate = recordDate >= monthAgo;
                    break;
            }
        }
        
        return matchSearch && matchType && matchDate;
    });
    
    currentPage = 1;
    renderRecords();
    updateStatistics();
}

/**
 * 渲染记录列表
 */
function renderRecords() {
    const list = document.getElementById('realtimeRecordsList');
    
    if (filteredRecords.length === 0) {
        list.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <p>暂无记录</p>
            </div>
        `;
        return;
    }
    
    const totalPages = Math.ceil(filteredRecords.length / recordsPerPage);
    const start = (currentPage - 1) * recordsPerPage;
    const end = start + recordsPerPage;
    const pageRecords = filteredRecords.slice(start, end);
    
    const recordsHTML = pageRecords.map(record => createRecordItem(record)).join('');
    list.innerHTML = recordsHTML;
    
    renderPagination(totalPages);
}

/**
 * 创建记录项
 */
function createRecordItem(record) {
    const typeIcons = {
        detection: 'fa-eye',
        alert: 'fa-exclamation-triangle',
        control: 'fa-sliders-h',
        status: 'fa-info-circle'
    };
    
    const severityColors = {
        low: '#52c41a',
        medium: '#faad14',
        high: '#ef4444'
    };
    
    return `
        <div class="realtime-record-item" data-severity="${record.severity}">
            <div class="record-icon ${record.type}">
                <i class="fas ${typeIcons[record.type]}"></i>
            </div>
            <div class="record-content">
                <div class="record-header">
                    <span class="record-label">${record.label}</span>
                    <span class="record-severity" style="color: ${severityColors[record.severity]}">
                        ${record.severity === 'high' ? '高' : record.severity === 'medium' ? '中' : '低'}
                    </span>
                </div>
                <div class="record-description">${record.description}</div>
                <div class="record-meta">
                    <span><i class="fas fa-video"></i> ${record.device}</span>
                    <span><i class="fas fa-clock"></i> ${record.timestamp}</span>
                </div>
            </div>
        </div>
    `;
}

/**
 * 初始化统计
 */
function initStatistics() {
    updateStatistics();
}

/**
 * 更新统计
 */
function updateStatistics() {
    const total = filteredRecords.length;
    const alerts = filteredRecords.filter(r => r.type === 'alert').length;
    const today = filteredRecords.filter(r => {
        const date = new Date(r.timestamp);
        return date.toDateString() === new Date().toDateString();
    }).length;
    
    document.getElementById('totalRecords').textContent = total;
    document.getElementById('alertRecords').textContent = alerts;
    document.getElementById('todayRecords').textContent = today;
}

/**
 * 渲染分页
 */
function renderPagination(totalPages) {
    const pagination = document.getElementById('realtimePagination');
    
    if (totalPages <= 1) {
        pagination.innerHTML = '';
        return;
    }
    
    let html = '<div class="pagination-controls">';
    html += `<button class="btn btn-sm btn-secondary" ${currentPage === 1 ? 'disabled' : ''} onclick="changeRealtimePage(${currentPage - 1})">
        <i class="fas fa-chevron-left"></i> 上一页
    </button>`;
    html += `<span class="page-info">第 ${currentPage} 页，共 ${totalPages} 页</span>`;
    html += `<button class="btn btn-sm btn-secondary" ${currentPage === totalPages ? 'disabled' : ''} onclick="changeRealtimePage(${currentPage + 1})">
        下一页 <i class="fas fa-chevron-right"></i>
    </button>`;
    html += '</div>';
    
    pagination.innerHTML = html;
}

/**
 * 切换页面
 */
function changeRealtimePage(page) {
    const totalPages = Math.ceil(filteredRecords.length / recordsPerPage);
    if (page < 1 || page > totalPages) return;
    
    currentPage = page;
    renderRecords();
}

/**
 * 导出记录
 */
function exportRecords() {
    if (filteredRecords.length === 0) {
        showMessage('没有可导出的记录', 'warning');
        return;
    }
    
    const csv = [
        ['时间', '类型', '标签', '设备', '严重程度', '描述'].join(','),
        ...filteredRecords.map(r => [
            r.timestamp,
            r.type,
            r.label,
            r.device,
            r.severity,
            r.description
        ].join(','))
    ].join('\n');
    
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `实时记录_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    
    showMessage('记录导出成功', 'success');
}

window.changeRealtimePage = changeRealtimePage;
