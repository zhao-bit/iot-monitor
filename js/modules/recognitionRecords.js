/**
 * ============================================
 * 识别记录模块
 * 功能：记录列表、搜索筛选、详情查看、批量操作、CRUD
 * ============================================
 */

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('识别记录模块初始化...');
    
    // 初始化所有功能
    initRecordsList();
    initSearchAndFilter();
    initBatchOperations();
    initRecordDetail();
    
    // 加载并显示记录
    loadAndDisplayRecords();
    
    console.log('识别记录模块初始化完成！');
});

// ========== 全局变量 ==========
let allRecords = []; // 所有记录
let filteredRecords = []; // 筛选后的记录
let selectedRecordIds = new Set(); // 选中的记录ID集合
let currentPage = 1; // 当前页码
const recordsPerPage = 12; // 每页显示记录数

/**
 * 初始化记录列表
 */
function initRecordsList() {
    const refreshBtn = document.getElementById('refreshRecordsBtn');
    
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            loadAndDisplayRecords();
            showMessage('记录已刷新', 'success');
        });
    }
}

/**
 * 加载并显示记录
 */
function loadAndDisplayRecords() {
    // 从localStorage加载记录
    const savedRecords = localStorage.getItem('recognitionRecords');
    if (savedRecords) {
        allRecords = JSON.parse(savedRecords);
        // 按时间倒序排列（最新的在前）
        allRecords.sort((a, b) => {
            const timeA = new Date(a.timestamp || a.id).getTime();
            const timeB = new Date(b.timestamp || b.id).getTime();
            return timeB - timeA;
        });
    } else {
        allRecords = [];
        // 如果没有记录，生成一些模拟数据用于演示
        generateMockRecords();
    }
    
    // 应用筛选
    applyFilters();
}

/**
 * 生成模拟记录（用于演示）
 */
function generateMockRecords() {
    const labels = ['人员', '车辆', '动物', '建筑物', '植物', '设备', '标志牌', '障碍物'];
    const mockRecords = [];
    
    for (let i = 0; i < 5; i++) {
        const label = labels[Math.floor(Math.random() * labels.length)];
        const confidence = (Math.random() * 0.19 + 0.8).toFixed(2);
        const daysAgo = Math.floor(Math.random() * 7);
        const date = new Date();
        date.setDate(date.getDate() - daysAgo);
        
        mockRecords.push({
            id: Date.now() - i * 1000000,
            image: 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2Y1ZjVmNSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjE0IiBmaWxsPSIjOTk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+5Zu+54mH5pyq5Yqg6L29PC90ZXh0Pjwvc3ZnPg==',
            label: label,
            confidence: confidence,
            timestamp: date.toLocaleString('zh-CN'),
            bbox: {
                x: Math.random() * 0.3 + 0.2,
                y: Math.random() * 0.3 + 0.2,
                width: Math.random() * 0.3 + 0.2,
                height: Math.random() * 0.3 + 0.2
            }
        });
    }
    
    localStorage.setItem('recognitionRecords', JSON.stringify(mockRecords));
    allRecords = mockRecords;
}

/**
 * 应用筛选和搜索
 */
function applyFilters() {
    const searchTerm = document.getElementById('searchInput').value.toLowerCase().trim();
    const filterLabel = document.getElementById('filterLabel').value;
    const filterDate = document.getElementById('filterDate').value;
    
    filteredRecords = allRecords.filter(record => {
        // 搜索筛选
        if (searchTerm) {
            const matchSearch = 
                record.label.toLowerCase().includes(searchTerm) ||
                record.timestamp.toLowerCase().includes(searchTerm);
            if (!matchSearch) return false;
        }
        
        // 标签筛选
        if (filterLabel !== 'all' && record.label !== filterLabel) {
            return false;
        }
        
        // 时间筛选
        if (filterDate !== 'all') {
            const recordDate = new Date(record.timestamp || record.id);
            const now = new Date();
            let matchDate = false;
            
            switch (filterDate) {
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
            
            if (!matchDate) return false;
        }
        
        return true;
    });
    
    // 重置分页
    currentPage = 1;
    
    // 显示记录
    displayRecords();
}

/**
 * 显示记录列表
 */
function displayRecords() {
    const recordsList = document.getElementById('recordsList');
    const emptyState = document.getElementById('emptyState');
    
    if (filteredRecords.length === 0) {
        recordsList.innerHTML = `
            <div class="empty-state">
                <i class="fas fa-inbox"></i>
                <p>暂无匹配的记录</p>
                <p class="empty-hint">请尝试调整搜索条件或筛选器</p>
            </div>
        `;
        document.getElementById('recordsPagination').style.display = 'none';
        return;
    }
    
    // 计算分页
    const totalPages = Math.ceil(filteredRecords.length / recordsPerPage);
    const startIndex = (currentPage - 1) * recordsPerPage;
    const endIndex = startIndex + recordsPerPage;
    const pageRecords = filteredRecords.slice(startIndex, endIndex);
    
    // 生成记录卡片HTML
    const recordsHTML = pageRecords.map(record => createRecordCard(record)).join('');
    recordsList.innerHTML = recordsHTML;
    
    // 更新分页
    updatePagination(totalPages);
    
    // 绑定卡片事件
    bindRecordCardEvents();
}

/**
 * 创建记录卡片HTML
 * @param {Object} record - 记录对象
 * @returns {string} 卡片HTML
 */
function createRecordCard(record) {
    const isSelected = selectedRecordIds.has(record.id);
    return `
        <div class="record-card ${isSelected ? 'selected' : ''}" data-record-id="${record.id}">
            <div class="record-checkbox">
                <input type="checkbox" class="record-select-checkbox" data-record-id="${record.id}" ${isSelected ? 'checked' : ''}>
            </div>
            <div class="record-thumbnail" onclick="viewRecordDetail(${record.id})">
                <img src="${record.image}" alt="${record.label}" onerror="this.src='data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMjAwIiBoZWlnaHQ9IjIwMCIgZmlsbD0iI2Y1ZjVmNSIvPjx0ZXh0IHg9IjUwJSIgeT0iNTAlIiBmb250LXNpemU9IjE0IiBmaWxsPSIjOTk5IiB0ZXh0LWFuY2hvcj0ibWlkZGxlIiBkeT0iLjNlbSI+5Zu+54mH5pyq5Yqg6L29PC90ZXh0Pjwvc3ZnPg=='">
            </div>
            <div class="record-info">
                <div class="record-label">
                    <i class="fas fa-tag"></i>
                    <span>${record.label}</span>
                </div>
                <div class="record-confidence">
                    <i class="fas fa-chart-line"></i>
                    <span>${(record.confidence * 100).toFixed(1)}%</span>
                </div>
                <div class="record-time">
                    <i class="fas fa-clock"></i>
                    <span>${record.timestamp}</span>
                </div>
            </div>
            <div class="record-actions">
                <button class="btn-action btn-view" onclick="viewRecordDetail(${record.id})" title="查看详情">
                    <i class="fas fa-eye"></i>
                </button>
                <button class="btn-action btn-delete" onclick="deleteRecord(${record.id})" title="删除">
                    <i class="fas fa-trash"></i>
                </button>
            </div>
        </div>
    `;
}

/**
 * 绑定记录卡片事件
 */
function bindRecordCardEvents() {
    // 复选框点击事件
    const checkboxes = document.querySelectorAll('.record-select-checkbox');
    checkboxes.forEach(checkbox => {
        checkbox.addEventListener('change', function() {
            const recordId = parseInt(this.dataset.recordId);
            if (this.checked) {
                selectedRecordIds.add(recordId);
            } else {
                selectedRecordIds.delete(recordId);
            }
            
            // 更新卡片选中状态
            const card = this.closest('.record-card');
            if (card) {
                card.classList.toggle('selected', this.checked);
            }
            
            updateBatchActions();
        });
    });
    
    // 阻止卡片点击事件冒泡到复选框
    document.querySelectorAll('.record-card').forEach(card => {
        card.addEventListener('click', function(e) {
            if (e.target.closest('.record-select-checkbox') || e.target.closest('.record-actions')) {
                return;
            }
            const recordId = parseInt(this.dataset.recordId);
            viewRecordDetail(recordId);
        });
    });
}

/**
 * 初始化搜索和筛选功能
 */
function initSearchAndFilter() {
    const searchInput = document.getElementById('searchInput');
    const clearSearchBtn = document.getElementById('clearSearchBtn');
    const filterLabel = document.getElementById('filterLabel');
    const filterDate = document.getElementById('filterDate');
    
    // 搜索输入
    if (searchInput) {
        searchInput.addEventListener('input', function() {
            const hasValue = this.value.trim().length > 0;
            if (clearSearchBtn) {
                clearSearchBtn.style.display = hasValue ? 'block' : 'none';
            }
            
            // 防抖处理
            clearTimeout(this.searchTimeout);
            this.searchTimeout = setTimeout(() => {
                applyFilters();
            }, 300);
        });
    }
    
    // 清除搜索
    if (clearSearchBtn) {
        clearSearchBtn.addEventListener('click', function() {
            searchInput.value = '';
            this.style.display = 'none';
            applyFilters();
        });
    }
    
    // 筛选器变化
    if (filterLabel) {
        filterLabel.addEventListener('change', applyFilters);
    }
    
    if (filterDate) {
        filterDate.addEventListener('change', applyFilters);
    }
}

/**
 * 初始化批量操作功能
 */
function initBatchOperations() {
    const toggleSelectAllBtn = document.getElementById('toggleSelectAllBtn');
    const batchDeleteBtn = document.getElementById('batchDeleteBtn');
    
    // 全选/取消全选
    if (toggleSelectAllBtn) {
        toggleSelectAllBtn.addEventListener('click', function() {
            const allSelected = selectedRecordIds.size === filteredRecords.length;
            
            if (allSelected) {
                // 取消全选
                selectedRecordIds.clear();
                document.querySelectorAll('.record-select-checkbox').forEach(cb => {
                    cb.checked = false;
                    cb.closest('.record-card')?.classList.remove('selected');
                });
                this.innerHTML = '<i class="fas fa-check-square"></i> 全选';
            } else {
                // 全选当前页
                filteredRecords.forEach(record => {
                    selectedRecordIds.add(record.id);
                });
                document.querySelectorAll('.record-select-checkbox').forEach(cb => {
                    cb.checked = true;
                    cb.closest('.record-card')?.classList.add('selected');
                });
                this.innerHTML = '<i class="fas fa-square"></i> 取消全选';
            }
            
            updateBatchActions();
        });
    }
    
    // 批量删除
    if (batchDeleteBtn) {
        batchDeleteBtn.addEventListener('click', function() {
            if (selectedRecordIds.size === 0) {
                showMessage('请先选择要删除的记录', 'warning');
                return;
            }
            
            confirmOperation('批量删除', `确定要删除选中的 ${selectedRecordIds.size} 条记录吗？`, () => {
                deleteSelectedRecords();
            });
        });
    }
}

/**
 * 更新批量操作按钮显示
 */
function updateBatchActions() {
    const batchActions = document.getElementById('batchActions');
    const selectedCount = document.getElementById('selectedCount');
    
    if (selectedRecordIds.size > 0) {
        if (batchActions) {
            batchActions.style.display = 'flex';
        }
        if (selectedCount) {
            selectedCount.textContent = `已选择 ${selectedRecordIds.size} 项`;
        }
    } else {
        if (batchActions) {
            batchActions.style.display = 'none';
        }
    }
}

/**
 * 删除选中的记录
 */
function deleteSelectedRecords() {
    // 从所有记录中删除选中的记录
    allRecords = allRecords.filter(record => !selectedRecordIds.has(record.id));
    
    // 保存到localStorage
    localStorage.setItem('recognitionRecords', JSON.stringify(allRecords));
    
    // 清空选中状态
    selectedRecordIds.clear();
    
    // 重新加载显示
    applyFilters();
    
    showMessage(`已删除 ${selectedRecordIds.size} 条记录`, 'success');
}

/**
 * 初始化记录详情功能
 */
function initRecordDetail() {
    const modal = document.getElementById('recordDetailModal');
    const closeBtn = document.getElementById('recordDetailClose');
    const closeDetailBtn = document.getElementById('closeDetailBtn');
    const deleteRecordBtn = document.getElementById('deleteRecordBtn');
    
    // 关闭模态框
    function closeModal() {
        if (modal) {
            modal.style.display = 'none';
        }
    }
    
    if (closeBtn) {
        closeBtn.addEventListener('click', closeModal);
    }
    
    if (closeDetailBtn) {
        closeDetailBtn.addEventListener('click', closeModal);
    }
    
    // 点击背景关闭
    if (modal) {
        modal.addEventListener('click', function(e) {
            if (e.target === modal) {
                closeModal();
            }
        });
    }
    
    // 删除记录
    if (deleteRecordBtn) {
        deleteRecordBtn.addEventListener('click', function() {
            const recordId = parseInt(this.dataset.recordId);
            if (recordId) {
                confirmOperation('删除记录', '确定要删除这条记录吗？', () => {
                    deleteRecord(recordId);
                    closeModal();
                });
            }
        });
    }
}

/**
 * 查看记录详情
 * @param {number} recordId - 记录ID
 */
function viewRecordDetail(recordId) {
    const record = allRecords.find(r => r.id === recordId);
    if (!record) {
        showMessage('记录不存在', 'error');
        return;
    }
    
    const modal = document.getElementById('recordDetailModal');
    const detailImage = document.getElementById('detailImage');
    const detailCanvas = document.getElementById('detailCanvas');
    const detailLabel = document.getElementById('detailLabel');
    const detailConfidence = document.getElementById('detailConfidence');
    const detailTime = document.getElementById('detailTime');
    const detailId = document.getElementById('detailId');
    const deleteRecordBtn = document.getElementById('deleteRecordBtn');
    
    // 显示详情
    detailImage.src = record.image;
    detailLabel.textContent = record.label;
    detailConfidence.textContent = `${(record.confidence * 100).toFixed(1)}%`;
    detailTime.textContent = record.timestamp;
    detailId.textContent = record.id;
    
    // 保存记录ID到删除按钮
    if (deleteRecordBtn) {
        deleteRecordBtn.dataset.recordId = recordId;
    }
    
    // 等待图片加载后绘制边界框
    detailImage.onload = function() {
        if (record.bbox) {
            drawDetailBoundingBox(detailCanvas, detailImage, record.bbox);
        }
    };
    
    // 显示模态框
    if (modal) {
        modal.style.display = 'flex';
    }
}

/**
 * 绘制详情页面的边界框
 * @param {HTMLCanvasElement} canvas - Canvas元素
 * @param {HTMLImageElement} image - 图片元素
 * @param {Object} bbox - 边界框数据
 */
function drawDetailBoundingBox(canvas, image, bbox) {
    canvas.width = image.offsetWidth;
    canvas.height = image.offsetHeight;
    
    const ctx = canvas.getContext('2d');
    const x = bbox.x * canvas.width;
    const y = bbox.y * canvas.height;
    const width = bbox.width * canvas.width;
    const height = bbox.height * canvas.height;
    
    ctx.strokeStyle = '#52c41a';
    ctx.lineWidth = 3;
    ctx.strokeRect(x, y, width, height);
    
    ctx.fillStyle = '#52c41a';
    ctx.fillRect(x, y - 25, width, 25);
    
    ctx.fillStyle = '#ffffff';
    ctx.font = '14px Arial';
    ctx.fillText('检测对象', x + 5, y - 8);
}

/**
 * 删除单条记录
 * @param {number} recordId - 记录ID
 */
function deleteRecord(recordId) {
    // 从所有记录中删除
    allRecords = allRecords.filter(record => record.id !== recordId);
    
    // 从选中集合中移除
    selectedRecordIds.delete(recordId);
    
    // 保存到localStorage
    localStorage.setItem('recognitionRecords', JSON.stringify(allRecords));
    
    // 重新加载显示
    applyFilters();
    
    showMessage('记录已删除', 'success');
}

/**
 * 更新分页
 * @param {number} totalPages - 总页数
 */
function updatePagination(totalPages) {
    const pagination = document.getElementById('recordsPagination');
    const pageInfo = document.getElementById('pageInfo');
    const prevBtn = document.getElementById('prevPageBtn');
    const nextBtn = document.getElementById('nextPageBtn');
    
    if (totalPages <= 1) {
        if (pagination) {
            pagination.style.display = 'none';
        }
        return;
    }
    
    if (pagination) {
        pagination.style.display = 'flex';
    }
    
    if (pageInfo) {
        pageInfo.textContent = `第 ${currentPage} 页，共 ${totalPages} 页`;
    }
    
    if (prevBtn) {
        prevBtn.disabled = currentPage === 1;
        prevBtn.onclick = () => {
            if (currentPage > 1) {
                currentPage--;
                displayRecords();
            }
        };
    }
    
    if (nextBtn) {
        nextBtn.disabled = currentPage === totalPages;
        nextBtn.onclick = () => {
            if (currentPage < totalPages) {
                currentPage++;
                displayRecords();
            }
        };
    }
}

// 全局函数（供HTML中的onclick调用）
window.viewRecordDetail = viewRecordDetail;
window.deleteRecord = function(recordId) {
    confirmOperation('删除记录', '确定要删除这条记录吗？', () => {
        deleteRecord(recordId);
    });
};
