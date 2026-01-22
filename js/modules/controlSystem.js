/**
 * ============================================
 * 控制系统模块
 * 功能：设备管理、远程控制、参数设置、操作日志
 * ============================================
 */

// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('控制系统模块初始化...');
    
    // 初始化所有功能
    initDeviceData();
    initDeviceTree();
    initDeviceControl();
    initDeviceSettings();
    initOperationLogs();
    initStatusOverview();
    initConfirmDialog();
    
    // 启动状态自动更新
    startStatusUpdate();
    
    console.log('控制系统模块初始化完成！');
});

// ========== 全局变量 ==========
let devices = []; // 设备列表
let selectedDevice = null; // 当前选中的设备
let statusUpdateInterval = null; // 状态更新定时器
let operationLogs = []; // 操作日志列表

// 模拟设备数据（实际项目中应从后端API获取）
const mockDevices = [
    {
        id: 'DEV001',
        name: '监控摄像头-01',
        group: '监控设备',
        status: 'online',
        runStatus: 'running',
        lastOnline: '2024-01-22 18:30:15',
        settings: {
            power: 75,
            speed: 'medium',
            mode: 'auto',
            interval: 10,
            autoRestart: true
        }
    },
    {
        id: 'DEV002',
        name: '智能传感器-01',
        group: '传感器设备',
        status: 'online',
        runStatus: 'stopped',
        lastOnline: '2024-01-22 18:29:45',
        settings: {
            power: 50,
            speed: 'low',
            mode: 'manual',
            interval: 5,
            autoRestart: false
        }
    },
    {
        id: 'DEV003',
        name: '环境监测器-01',
        group: '监测设备',
        status: 'offline',
        runStatus: 'stopped',
        lastOnline: '2024-01-22 17:15:30',
        settings: {
            power: 60,
            speed: 'medium',
            mode: 'auto',
            interval: 15,
            autoRestart: true
        }
    },
    {
        id: 'DEV004',
        name: '门禁控制器-01',
        group: '安防设备',
        status: 'online',
        runStatus: 'running',
        lastOnline: '2024-01-22 18:31:00',
        settings: {
            power: 80,
            speed: 'high',
            mode: 'scheduled',
            interval: 30,
            autoRestart: true
        }
    },
    {
        id: 'DEV005',
        name: '温湿度传感器-01',
        group: '传感器设备',
        status: 'online',
        runStatus: 'running',
        lastOnline: '2024-01-22 18:30:50',
        settings: {
            power: 40,
            speed: 'low',
            mode: 'auto',
            interval: 20,
            autoRestart: false
        }
    }
];

// 设备分组结构
const deviceGroups = [
    {
        name: '监控设备',
        devices: ['DEV001']
    },
    {
        name: '传感器设备',
        devices: ['DEV002', 'DEV005']
    },
    {
        name: '监测设备',
        devices: ['DEV003']
    },
    {
        name: '安防设备',
        devices: ['DEV004']
    }
];

/**
 * 初始化设备数据
 */
function initDeviceData() {
    // 从本地存储加载设备数据，如果没有则使用模拟数据
    const savedDevices = localStorage.getItem('controlSystemDevices');
    if (savedDevices) {
        devices = JSON.parse(savedDevices);
    } else {
        devices = JSON.parse(JSON.stringify(mockDevices)); // 深拷贝
        saveDevicesToStorage();
    }
    
    // 加载操作日志
    const savedLogs = localStorage.getItem('controlSystemLogs');
    if (savedLogs) {
        operationLogs = JSON.parse(savedLogs);
    }
}

/**
 * 保存设备数据到本地存储
 */
function saveDevicesToStorage() {
    localStorage.setItem('controlSystemDevices', JSON.stringify(devices));
}

/**
 * 初始化设备树形结构
 */
function initDeviceTree() {
    const deviceTree = document.getElementById('deviceTree');
    const addGroupBtn = document.getElementById('addGroupBtn');
    
    // 渲染设备树
    renderDeviceTree();
    
    // 添加分组按钮
    addGroupBtn.addEventListener('click', function() {
        const groupName = prompt('请输入分组名称：');
        if (groupName && groupName.trim()) {
            addDeviceGroup(groupName.trim());
        }
    });
}

/**
 * 渲染设备树
 */
function renderDeviceTree() {
    const deviceTree = document.getElementById('deviceTree');
    deviceTree.innerHTML = '';
    
    // 按分组组织设备
    const groupedDevices = {};
    devices.forEach(device => {
        if (!groupedDevices[device.group]) {
            groupedDevices[device.group] = [];
        }
        groupedDevices[device.group].push(device);
    });
    
    // 渲染每个分组
    Object.keys(groupedDevices).forEach(groupName => {
        const groupEl = createGroupElement(groupName, groupedDevices[groupName]);
        deviceTree.appendChild(groupEl);
    });
}

/**
 * 创建分组元素
 * @param {string} groupName - 分组名称
 * @param {Array} groupDevices - 该分组的设备列表
 * @returns {HTMLElement} 分组元素
 */
function createGroupElement(groupName, groupDevices) {
    const groupDiv = document.createElement('div');
    groupDiv.className = 'tree-group';
    
    // 分组标题
    const groupHeader = document.createElement('div');
    groupHeader.className = 'tree-group-header';
    groupHeader.innerHTML = `
        <i class="fas fa-folder"></i>
        <span class="group-name">${groupName}</span>
        <span class="group-count">(${groupDevices.length})</span>
    `;
    
    // 分组内容（设备列表）
    const groupContent = document.createElement('div');
    groupContent.className = 'tree-group-content';
    
    groupDevices.forEach(device => {
        const deviceEl = createDeviceElement(device);
        groupContent.appendChild(deviceEl);
    });
    
    // 点击分组标题展开/折叠
    groupHeader.addEventListener('click', function() {
        groupContent.classList.toggle('collapsed');
        const icon = groupHeader.querySelector('i');
        icon.classList.toggle('fa-folder');
        icon.classList.toggle('fa-folder-open');
    });
    
    groupDiv.appendChild(groupHeader);
    groupDiv.appendChild(groupContent);
    
    return groupDiv;
}

/**
 * 创建设备元素
 * @param {Object} device - 设备对象
 * @returns {HTMLElement} 设备元素
 */
function createDeviceElement(device) {
    const deviceDiv = document.createElement('div');
    deviceDiv.className = `tree-device ${device.status === 'online' ? 'online' : 'offline'}`;
    deviceDiv.dataset.deviceId = device.id;
    
    deviceDiv.innerHTML = `
        <i class="fas fa-circle status-indicator"></i>
        <span class="device-name">${device.name}</span>
        <span class="device-status">${device.runStatus === 'running' ? '运行中' : '已停止'}</span>
    `;
    
    // 点击设备选中
    deviceDiv.addEventListener('click', function() {
        selectDevice(device.id);
    });
    
    return deviceDiv;
}

/**
 * 选中设备
 * @param {string} deviceId - 设备ID
 */
function selectDevice(deviceId) {
    // 更新选中状态
    document.querySelectorAll('.tree-device').forEach(el => {
        el.classList.remove('selected');
    });
    const deviceEl = document.querySelector(`[data-device-id="${deviceId}"]`);
    if (deviceEl) {
        deviceEl.classList.add('selected');
    }
    
    // 查找设备对象
    selectedDevice = devices.find(d => d.id === deviceId);
    
    if (selectedDevice) {
        // 显示设备详情
        displayDeviceDetail(selectedDevice);
    }
}

/**
 * 显示设备详情
 * @param {Object} device - 设备对象
 */
function displayDeviceDetail(device) {
    const noSelection = document.getElementById('noDeviceSelected');
    const deviceDetail = document.getElementById('deviceDetail');
    
    noSelection.style.display = 'none';
    deviceDetail.style.display = 'block';
    
    // 更新设备基本信息
    document.getElementById('deviceName').textContent = device.name;
    document.getElementById('deviceId').textContent = device.id;
    document.getElementById('deviceGroup').textContent = device.group;
    document.getElementById('deviceLastOnline').textContent = device.lastOnline;
    
    // 更新状态徽章
    const statusBadge = document.getElementById('deviceStatusBadge');
    statusBadge.className = `device-status-badge ${device.status}`;
    statusBadge.innerHTML = `
        <i class="fas fa-circle"></i> ${device.status === 'online' ? '在线' : '离线'}
    `;
    
    // 更新运行状态
    const runStatus = document.getElementById('deviceRunStatus');
    runStatus.textContent = device.runStatus === 'running' ? '运行中' : '已停止';
    runStatus.className = device.runStatus === 'running' ? 'status-running' : 'status-stopped';
    
    // 更新参数设置表单
    updateSettingsForm(device.settings);
    
    // 更新控制按钮状态
    updateControlButtons(device);
}

/**
 * 更新设置表单
 * @param {Object} settings - 设备设置
 */
function updateSettingsForm(settings) {
    document.getElementById('devicePower').value = settings.power;
    document.getElementById('powerValue').textContent = `${settings.power}%`;
    document.getElementById('deviceSpeed').value = settings.speed;
    document.getElementById('deviceMode').value = settings.mode;
    document.getElementById('deviceInterval').value = settings.interval;
    document.getElementById('deviceAutoRestart').checked = settings.autoRestart;
}

/**
 * 更新控制按钮状态
 * @param {Object} device - 设备对象
 */
function updateControlButtons(device) {
    const startBtn = document.getElementById('startDeviceBtn');
    const stopBtn = document.getElementById('stopDeviceBtn');
    const restartBtn = document.getElementById('restartDeviceBtn');
    
    // 根据设备状态和在线状态启用/禁用按钮
    const isOnline = device.status === 'online';
    const isRunning = device.runStatus === 'running';
    
    startBtn.disabled = !isOnline || isRunning;
    stopBtn.disabled = !isOnline || !isRunning;
    restartBtn.disabled = !isOnline;
}

/**
 * 初始化设备控制功能
 */
function initDeviceControl() {
    const startBtn = document.getElementById('startDeviceBtn');
    const stopBtn = document.getElementById('stopDeviceBtn');
    const restartBtn = document.getElementById('restartDeviceBtn');
    
    startBtn.addEventListener('click', function() {
        if (selectedDevice) {
            confirmOperation('启动设备', `确定要启动设备 "${selectedDevice.name}" 吗？`, () => {
                controlDevice(selectedDevice.id, 'start');
            });
        }
    });
    
    stopBtn.addEventListener('click', function() {
        if (selectedDevice) {
            confirmOperation('停止设备', `确定要停止设备 "${selectedDevice.name}" 吗？`, () => {
                controlDevice(selectedDevice.id, 'stop');
            });
        }
    });
    
    restartBtn.addEventListener('click', function() {
        if (selectedDevice) {
            confirmOperation('重启设备', `确定要重启设备 "${selectedDevice.name}" 吗？`, () => {
                controlDevice(selectedDevice.id, 'restart');
            });
        }
    });
}

/**
 * 控制设备
 * @param {string} deviceId - 设备ID
 * @param {string} action - 操作类型：start, stop, restart
 */
function controlDevice(deviceId, action) {
    const device = devices.find(d => d.id === deviceId);
    if (!device) return;
    
    // 模拟操作延迟
    showMessage(`正在${getActionName(action)}设备...`, 'info');
    
    setTimeout(() => {
        // 更新设备状态
        if (action === 'start') {
            device.runStatus = 'running';
        } else if (action === 'stop') {
            device.runStatus = 'stopped';
        } else if (action === 'restart') {
            device.runStatus = 'stopped';
            setTimeout(() => {
                device.runStatus = 'running';
                updateDeviceStatus();
            }, 1000);
        }
        
        // 保存设备数据
        saveDevicesToStorage();
        
        // 更新UI
        updateDeviceStatus();
        if (selectedDevice && selectedDevice.id === deviceId) {
            displayDeviceDetail(device);
        }
        
        // 记录操作日志
        addOperationLog(deviceId, device.name, action, 'success');
        
        showMessage(`设备${getActionName(action)}成功！`, 'success');
    }, 1000);
}

/**
 * 获取操作名称
 * @param {string} action - 操作类型
 * @returns {string} 操作名称
 */
function getActionName(action) {
    const names = {
        start: '启动',
        stop: '停止',
        restart: '重启'
    };
    return names[action] || action;
}

/**
 * 初始化设备设置功能
 */
function initDeviceSettings() {
    const settingsForm = document.getElementById('deviceSettingsForm');
    const resetBtn = document.getElementById('resetSettingsBtn');
    const powerSlider = document.getElementById('devicePower');
    
    // 功率滑块实时显示
    powerSlider.addEventListener('input', function() {
        document.getElementById('powerValue').textContent = `${this.value}%`;
    });
    
    // 表单提交
    settingsForm.addEventListener('submit', function(e) {
        e.preventDefault();
        
        if (!selectedDevice) {
            showMessage('请先选择一个设备！', 'warning');
            return;
        }
        
        // 获取表单数据
        const settings = {
            power: parseInt(document.getElementById('devicePower').value),
            speed: document.getElementById('deviceSpeed').value,
            mode: document.getElementById('deviceMode').value,
            interval: parseInt(document.getElementById('deviceInterval').value),
            autoRestart: document.getElementById('deviceAutoRestart').checked
        };
        
        // 更新设备设置
        selectedDevice.settings = settings;
        saveDevicesToStorage();
        
        // 记录操作日志
        addOperationLog(selectedDevice.id, selectedDevice.name, 'settings', 'success', '更新设备参数');
        
        showMessage('设备参数已保存！', 'success');
    });
    
    // 重置按钮
    resetBtn.addEventListener('click', function() {
        if (selectedDevice) {
            if (confirm('确定要重置为默认设置吗？')) {
                updateSettingsForm(selectedDevice.settings);
            }
        }
    });
}

/**
 * 初始化操作日志功能
 */
function initOperationLogs() {
    const clearLogsBtn = document.getElementById('clearLogsBtn');
    const exportLogsBtn = document.getElementById('exportLogsBtn');
    const filterType = document.getElementById('logFilterType');
    const filterDevice = document.getElementById('logFilterDevice');
    
    // 初始化设备筛选下拉框
    updateDeviceFilter();
    
    // 清空日志
    clearLogsBtn.addEventListener('click', function() {
        if (confirm('确定要清空所有日志吗？')) {
            operationLogs = [];
            localStorage.removeItem('controlSystemLogs');
            renderLogs();
            showMessage('日志已清空', 'success');
        }
    });
    
    // 导出日志
    exportLogsBtn.addEventListener('click', function() {
        exportLogs();
    });
    
    // 筛选日志
    filterType.addEventListener('change', renderLogs);
    filterDevice.addEventListener('change', renderLogs);
    
    // 初始渲染日志
    renderLogs();
}

/**
 * 渲染操作日志
 */
function renderLogs() {
    const logsContainer = document.getElementById('logsContainer');
    const filterType = document.getElementById('logFilterType').value;
    const filterDevice = document.getElementById('logFilterDevice').value;
    
    // 筛选日志
    let filteredLogs = operationLogs;
    
    if (filterType !== 'all') {
        filteredLogs = filteredLogs.filter(log => log.action === filterType);
    }
    
    if (filterDevice !== 'all') {
        filteredLogs = filteredLogs.filter(log => log.deviceId === filterDevice);
    }
    
    // 如果没有日志
    if (filteredLogs.length === 0) {
        logsContainer.innerHTML = '<div class="no-logs">暂无操作日志</div>';
        return;
    }
    
    // 渲染日志列表
    logsContainer.innerHTML = filteredLogs.map(log => `
        <div class="log-item ${log.status}">
            <div class="log-icon">
                <i class="fas ${getLogIcon(log.action)}"></i>
            </div>
            <div class="log-content">
                <div class="log-header">
                    <span class="log-action">${getActionName(log.action)}</span>
                    <span class="log-device">${log.deviceName}</span>
                </div>
                <div class="log-message">${log.message || ''}</div>
                <div class="log-time">${log.timestamp}</div>
            </div>
            <div class="log-status">
                <i class="fas ${log.status === 'success' ? 'fa-check-circle' : 'fa-times-circle'}"></i>
            </div>
        </div>
    `).join('');
}

/**
 * 获取日志图标
 * @param {string} action - 操作类型
 * @returns {string} 图标类名
 */
function getLogIcon(action) {
    const icons = {
        start: 'fa-play-circle',
        stop: 'fa-stop-circle',
        restart: 'fa-redo',
        settings: 'fa-cog'
    };
    return icons[action] || 'fa-info-circle';
}

/**
 * 添加操作日志
 * @param {string} deviceId - 设备ID
 * @param {string} deviceName - 设备名称
 * @param {string} action - 操作类型
 * @param {string} status - 状态：success, error
 * @param {string} message - 日志消息
 */
function addOperationLog(deviceId, deviceName, action, status, message) {
    const log = {
        id: Date.now(),
        deviceId,
        deviceName,
        action,
        status,
        message: message || `${getActionName(action)}设备 "${deviceName}"`,
        timestamp: new Date().toLocaleString('zh-CN')
    };
    
    operationLogs.unshift(log);
    
    // 限制日志数量（最多500条）
    if (operationLogs.length > 500) {
        operationLogs = operationLogs.slice(0, 500);
    }
    
    // 保存到本地存储
    localStorage.setItem('controlSystemLogs', JSON.stringify(operationLogs));
    
    // 更新设备筛选下拉框
    updateDeviceFilter();
    
    // 重新渲染日志
    renderLogs();
}

/**
 * 更新设备筛选下拉框
 */
function updateDeviceFilter() {
    const filterDevice = document.getElementById('logFilterDevice');
    const currentValue = filterDevice.value;
    
    // 获取所有唯一的设备ID和名称
    const deviceMap = new Map();
    operationLogs.forEach(log => {
        if (!deviceMap.has(log.deviceId)) {
            deviceMap.set(log.deviceId, log.deviceName);
        }
    });
    
    // 更新下拉框选项
    filterDevice.innerHTML = '<option value="all">全部设备</option>';
    deviceMap.forEach((name, id) => {
        const option = document.createElement('option');
        option.value = id;
        option.textContent = name;
        filterDevice.appendChild(option);
    });
    
    // 恢复之前的选择
    filterDevice.value = currentValue;
}

/**
 * 导出日志
 */
function exportLogs() {
    if (operationLogs.length === 0) {
        showMessage('没有可导出的日志', 'warning');
        return;
    }
    
    // 转换为CSV格式
    const csv = [
        ['时间', '设备ID', '设备名称', '操作', '状态', '消息'].join(','),
        ...operationLogs.map(log => [
            log.timestamp,
            log.deviceId,
            log.deviceName,
            getActionName(log.action),
            log.status === 'success' ? '成功' : '失败',
            log.message || ''
        ].join(','))
    ].join('\n');
    
    // 创建下载链接
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    const url = URL.createObjectURL(blob);
    link.setAttribute('href', url);
    link.setAttribute('download', `操作日志_${new Date().toISOString().split('T')[0]}.csv`);
    link.style.visibility = 'hidden';
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    
    showMessage('日志导出成功！', 'success');
}

/**
 * 初始化状态概览
 */
function initStatusOverview() {
    const refreshBtn = document.getElementById('refreshStatusBtn');
    
    refreshBtn.addEventListener('click', function() {
        updateDeviceStatus();
        showMessage('状态已刷新', 'success');
    });
    
    // 初始更新
    updateDeviceStatus();
}

/**
 * 更新设备状态统计
 */
function updateDeviceStatus() {
    const onlineCount = devices.filter(d => d.status === 'online').length;
    const offlineCount = devices.filter(d => d.status === 'offline').length;
    const runningCount = devices.filter(d => d.runStatus === 'running').length;
    const stoppedCount = devices.filter(d => d.runStatus === 'stopped').length;
    
    document.getElementById('onlineCount').textContent = onlineCount;
    document.getElementById('offlineCount').textContent = offlineCount;
    document.getElementById('runningCount').textContent = runningCount;
    document.getElementById('stoppedCount').textContent = stoppedCount;
    
    // 更新最后更新时间
    document.getElementById('lastUpdateTime').textContent = 
        `最后更新：${new Date().toLocaleTimeString('zh-CN')}`;
    
    // 重新渲染设备树（更新状态显示）
    renderDeviceTree();
}

/**
 * 启动状态自动更新
 */
function startStatusUpdate() {
    // 每30秒自动更新一次状态
    statusUpdateInterval = setInterval(() => {
        // 模拟设备状态随机变化（实际项目中应从服务器获取）
        simulateStatusChange();
        updateDeviceStatus();
    }, 30000);
}

/**
 * 模拟设备状态变化（用于演示）
 */
function simulateStatusChange() {
    // 随机改变一些设备的在线状态（5%概率）
    devices.forEach(device => {
        if (Math.random() < 0.05) {
            device.status = device.status === 'online' ? 'offline' : 'online';
            device.lastOnline = new Date().toLocaleString('zh-CN');
        }
    });
}

/**
 * 添加设备分组
 * @param {string} groupName - 分组名称
 */
function addDeviceGroup(groupName) {
    // 检查分组是否已存在
    const existingGroup = deviceGroups.find(g => g.name === groupName);
    if (existingGroup) {
        showMessage('分组已存在！', 'warning');
        return;
    }
    
    // 添加新分组
    deviceGroups.push({
        name: groupName,
        devices: []
    });
    
    // 重新渲染设备树
    renderDeviceTree();
    
    showMessage(`分组 "${groupName}" 已添加`, 'success');
}

/**
 * 初始化确认对话框
 */
function initConfirmDialog() {
    const dialog = document.getElementById('confirmDialog');
    const closeBtn = document.getElementById('confirmDialogClose');
    const cancelBtn = document.getElementById('confirmDialogCancel');
    const confirmBtn = document.getElementById('confirmDialogConfirm');
    
    // 关闭对话框
    function closeDialog() {
        dialog.style.display = 'none';
    }
    
    closeBtn.addEventListener('click', closeDialog);
    cancelBtn.addEventListener('click', closeDialog);
    
    // 点击背景关闭
    dialog.addEventListener('click', function(e) {
        if (e.target === dialog) {
            closeDialog();
        }
    });
}

/**
 * 显示确认对话框
 * @param {string} title - 对话框标题
 * @param {string} message - 对话框消息
 * @param {Function} onConfirm - 确认回调函数
 */
function confirmOperation(title, message, onConfirm) {
    const dialog = document.getElementById('confirmDialog');
    const titleEl = document.getElementById('confirmDialogTitle');
    const messageEl = document.getElementById('confirmDialogMessage');
    const confirmBtn = document.getElementById('confirmDialogConfirm');
    
    titleEl.textContent = title;
    messageEl.textContent = message;
    
    // 移除之前的监听器
    const newConfirmBtn = confirmBtn.cloneNode(true);
    confirmBtn.parentNode.replaceChild(newConfirmBtn, confirmBtn);
    
    // 添加新的确认监听器
    newConfirmBtn.addEventListener('click', function() {
        dialog.style.display = 'none';
        if (onConfirm) {
            onConfirm();
        }
    });
    
    dialog.style.display = 'flex';
}
