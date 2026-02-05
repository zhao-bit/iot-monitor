/**
 * ============================================
 * 控制系统模块（已对接后端 API）
 * 功能：系统控制、电源控制、电压探索、目标控制
 * ============================================
 */

const API_BASE = "http://ynlu100202514.vicp.fun"; // FastAPI 后端地址

// ========== 全局变量 ==========
let systemStatus = null;
let statusUpdateInterval = null;
let operationLogs = [];
let lastExplorationActive = false; // 用于检测探索结束并自动刷新模式列表
let prevModeCount = 0;
// 等待DOM加载完成
document.addEventListener('DOMContentLoaded', function() {
    console.log('控制系统模块初始化...');
    
    // 初始化所有功能
    initHvPowerConnection();
    initDetectionConnection();
    initSystemControls();
    initPowerControls();
    initControlModes();
    initStatusOverview();
    initOperationLogs();
    
    // 启动状态自动更新
    startStatusUpdate();
    
    console.log('控制系统模块初始化完成！');
});

// ==================== 后端通信 ====================

/**
 * 获取系统状态
 * 逻辑：每5秒获取一次状态，实时检测探索进度，并在模式增加或探索结束时自动刷新下拉列表
 */
async function fetchSystemStatus() {
    const url = `${API_BASE}/api/system/status`;
    // 调试时可以开启下面这行，生产环境如果觉得烦可以注释掉
    // showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        systemStatus = data;

        // --- 核心同步逻辑开始 ---
        const exploring = data.system?.exploration_active || false;
        const currentModeCount = data.control?.mode_count || 0;

        // 判定条件：
        // 1. 探索状态从“运行中”变成了“已停止”（lastExplorationActive 为 true，exploring 为 false）
        // 2. 或者在探索过程中，后端发现新模式了（currentModeCount 大于 prevModeCount）
        if ((lastExplorationActive && !exploring) || (currentModeCount > prevModeCount)) {
            console.log(`[同步] 检测到模式更新 (数量: ${currentModeCount})，正在刷新下拉框...`);
            loadModesList(); // 触发你刚才修改好的 loadModesList 刷新 UI
        }

        // 更新持久化状态供下次对比
        lastExplorationActive = exploring;
        prevModeCount = currentModeCount;
        // --- 核心同步逻辑结束 ---

        updateStatusUI(data);
        
        // 只有请求成功才显示，如果觉得太频繁可以去掉
        // showRequestStatus(`系统在线`, 'success');

        console.log("系统状态:", data);
    } catch (e) {
        console.error("获取系统状态失败", e);
        showRequestStatus(`连接失败: 请检查后端 API 是否运行`, 'error');
        // 不要在这里使用 confirm 否则会卡死自动刷新
    }
}
/**
 * 初始化系统
 */
async function initSystem() {
    const url = `${API_BASE}/api/system/init`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                modbus_port: "COM5",
                detection_port: 12345,
                model_path: "best.pt",
                camera_id: 1
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        console.log("初始化系统返回:", data);
        showRequestStatus(`初始化成功: ${url}`, 'success');
        showMessage(data.message || "系统初始化成功", "success");
        
        addOperationLog('system', 'init', '系统初始化', 'success');
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("初始化系统失败", e);
        showRequestStatus(`初始化失败: ${url}`, 'error');
        showMessage("系统初始化失败: " + e.message, "error");
        addOperationLog('system', 'init', '系统初始化失败', 'error');
    }
}

/**
 * 关闭系统
 */
async function shutdownSystem() {
    if (!confirm('确定要关闭系统吗？')) return;
    
    const url = `${API_BASE}/api/system/shutdown`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`关闭成功: ${url}`, 'success');
        showMessage(data.message || "系统已关闭", "success");
        
        addOperationLog('system', 'shutdown', '系统关闭', 'success');
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("关闭系统失败", e);
        showRequestStatus(`关闭失败: ${url}`, 'error');
        showMessage("关闭系统失败: " + e.message, "error");
        addOperationLog('system', 'shutdown', '系统关闭失败', 'error');
    }
}

/**
 * 紧急停止
 */
async function emergencyStop() {
    if (!confirm('确定要执行紧急停止吗？这将立即关闭所有电源！')) return;
    
    const url = `${API_BASE}/api/emergency/stop`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`急停成功: ${url}`, 'success');
        showMessage(data.message || "已发送急停指令", "warning");
        
        addOperationLog('system', 'emergency', '紧急停止', 'warning');
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("急停失败", e);
        showRequestStatus(`急停失败: ${url}`, 'error');
        showMessage("急停失败: " + e.message, "error");
        addOperationLog('system', 'emergency', '紧急停止失败', 'error');
    }
}

/**
 * 设置电压
 */
async function setVoltage(voltage) {
    const url = `${API_BASE}/api/power/set_voltage`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ voltage_kv: voltage })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`电压设置成功: ${url}`, 'success');
        showMessage(data.message || `电压已设置为 ${voltage} kV`, "success");
        
        addOperationLog('power', 'set_voltage', `设置电压: ${voltage} kV`, 'success');
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("设置电压失败", e);
        showRequestStatus(`电压设置失败: ${url}`, 'error');
        showMessage("设置电压失败: " + e.message, "error");
        addOperationLog('power', 'set_voltage', `设置电压失败: ${voltage} kV`, 'error');
    }
}

/**
 * 开启高压
 */
async function enablePower() {
    const url = `${API_BASE}/api/power/enable`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`开启成功: ${url}`, 'success');
        showMessage(data.message || "高压已开启", "success");
        
        addOperationLog('power', 'enable', '开启高压', 'success');
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("开启高压失败", e);
        showRequestStatus(`开启失败: ${url}`, 'error');
        showMessage("开启高压失败: " + e.message, "error");
        addOperationLog('power', 'enable', '开启高压失败', 'error');
    }
}

/**
 * 关闭高压
 */
async function disablePower() {
    const url = `${API_BASE}/api/power/disable`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`关闭成功: ${url}`, 'success');
        showMessage(data.message || "高压已关闭", "success");
        
        addOperationLog('power', 'disable', '关闭高压', 'success');
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("关闭高压失败", e);
        showRequestStatus(`关闭失败: ${url}`, 'error');
        showMessage("关闭高压失败: " + e.message, "error");
        addOperationLog('power', 'disable', '关闭高压失败', 'error');
    }
}

/**
 * 开始电压探索
 */
async function startExploration() {
    const minVoltage = parseFloat(document.getElementById('minVoltage').value);
    const maxVoltage = parseFloat(document.getElementById('maxVoltage').value);
    const voltageStep = parseFloat(document.getElementById('voltageStep').value);
    const waitTime = parseFloat(document.getElementById('waitTime').value);

    if (isNaN(minVoltage) || isNaN(maxVoltage) || isNaN(voltageStep) || isNaN(waitTime)) {
        showMessage('请填写有效的电压与时间参数', 'error');
        return;
    }
    if (minVoltage >= maxVoltage) {
        showMessage('最小电压必须小于最大电压', 'error');
        return;
    }
    if (voltageStep <= 0) {
        showMessage('电压步长必须大于 0', 'error');
        return;
    }
    if (waitTime < 0.15 || waitTime > 10) {
        showMessage('等待时间建议在 0.15～10 秒之间', 'error');
        return;
    }
    
    const url = `${API_BASE}/api/control/exploration/start`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                min_voltage: minVoltage,
                max_voltage: maxVoltage,
                voltage_step: voltageStep,
                wait_time: waitTime,
                confidence_threshold: 0.1
            })
        });

        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`探索启动成功: ${url}`, 'success');
        showMessage(data.message || "电压探索已启动", "success");
        
        addOperationLog('control', 'exploration_start', `开始电压探索: ${minVoltage}-${maxVoltage}kV`, 'success');
        
        // 更新按钮状态
        document.getElementById('startExplorationBtn').disabled = true;
        document.getElementById('stopExplorationBtn').disabled = false;
        
        // 刷新状态和模式列表
        setTimeout(() => {
            fetchSystemStatus();
            loadModesList();
        }, 500);
    } catch (e) {
        console.error("启动探索失败", e);
        showRequestStatus(`探索启动失败: ${url}`, 'error');
        showMessage("启动探索失败: " + e.message, "error");
        addOperationLog('control', 'exploration_start', '启动探索失败', 'error');
    }
}

/**
 * 停止电压探索
 */
async function stopExploration() {
    const url = `${API_BASE}/api/control/exploration/stop`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`探索停止成功: ${url}`, 'success');
        showMessage(data.message || "电压探索已停止", "success");
        
        addOperationLog('control', 'exploration_stop', '停止电压探索', 'success');
        
        // 更新按钮状态
        document.getElementById('startExplorationBtn').disabled = false;
        document.getElementById('stopExplorationBtn').disabled = true;
        
        // 刷新状态和模式列表
        setTimeout(() => {
            fetchSystemStatus();
            loadModesList();
        }, 500);
    } catch (e) {
        console.error("停止探索失败", e);
        showRequestStatus(`探索停止失败: ${url}`, 'error');
        showMessage("停止探索失败: " + e.message, "error");
        addOperationLog('control', 'exploration_stop', '停止探索失败', 'error');
        // 失败时恢复按钮状态，避免界面卡死
        const startBtn = document.getElementById('startExplorationBtn');
        const stopBtn = document.getElementById('stopExplorationBtn');
        if (startBtn) startBtn.disabled = false;
        if (stopBtn) stopBtn.disabled = true;
    }
}

/**
 * 开始目标控制
 */
async function startTargetControl() {
    const targetMode = (document.getElementById('targetModeSelect').value || '').trim();
    if (!targetMode) {
        showMessage('请先选择目标模式（完成电压探索后刷新模式列表）', 'error');
        return;
    }

    const url = `${API_BASE}/api/control/target/start`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                target_mode: targetMode
            })
        });

        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
            const msg = data.detail || data.message || `HTTP ${res.status}`;
            throw new Error(msg);
        }

        showRequestStatus(`目标控制启动成功: ${url}`, 'success');
        showMessage(data.message || `目标控制已启动: ${targetMode}`, "success");
        
        addOperationLog('control', 'target_start', `开始目标控制: ${targetMode}`, 'success');
        
        // 更新按钮状态
        document.getElementById('startTargetControlBtn').disabled = true;
        document.getElementById('stopTargetControlBtn').disabled = false;
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("启动目标控制失败", e);
        showRequestStatus(`目标控制启动失败: ${url}`, 'error');
        showMessage("启动目标控制失败: " + (e.message || String(e)), "error");
        addOperationLog('control', 'target_start', '启动目标控制失败: ' + (e.message || ''), 'error');
    }
}

/**
 * 停止目标控制
 */
async function stopTargetControl() {
    const url = `${API_BASE}/api/control/target/stop`;
    showRequestStatus(`请求: ${url} ...`, 'info');

    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showRequestStatus(`目标控制停止成功: ${url}`, 'success');
        showMessage(data.message || "目标控制已停止", "success");
        
        addOperationLog('control', 'target_stop', '停止目标控制', 'success');
        
        // 更新按钮状态
        document.getElementById('startTargetControlBtn').disabled = false;
        document.getElementById('stopTargetControlBtn').disabled = true;
        
        // 刷新状态
        setTimeout(fetchSystemStatus, 500);
    } catch (e) {
        console.error("停止目标控制失败", e);
        showRequestStatus(`目标控制停止失败: ${url}`, 'error');
        showMessage("停止目标控制失败: " + e.message, "error");
        addOperationLog('control', 'target_stop', '停止目标控制失败', 'error');
    }
}

// ==================== UI 更新 ====================

/**
 * 更新状态UI - 包含GUI中的所有状态字段
 */
function updateStatusUI(data) {
    // 系统状态
    const systemRunning = data.system?.running || false;
    const onlineCountEl = document.getElementById("onlineCount");
    if (onlineCountEl) {
        onlineCountEl.textContent = systemRunning ? "运行中" : "未运行";
    }
    
    // 电压值
    const voltage = data.power?.voltage_kv || 0.0;
    const voltageValueEl = document.getElementById("voltageValue");
    if (voltageValueEl) {
        voltageValueEl.textContent = voltage.toFixed(1);
    }
    
    // 电源状态
    const powerEnabled = data.power?.connected || false;
    const powerStatusEl = document.getElementById("powerStatus");
    if (powerStatusEl) {
        powerStatusEl.textContent = powerEnabled ? "已开启" : "已关闭";
    }
    
    // 检测状态
    const detectionActive = data.detection?.active || false;
    const detectionStatusEl = document.getElementById("detectionStatus");
    if (detectionStatusEl) {
        detectionStatusEl.textContent = detectionActive ? "激活" : "未激活";
    }
    
    // 更新时间
    const lastUpdateEl = document.getElementById("lastUpdateTime");
    if (lastUpdateEl) {
        lastUpdateEl.textContent = `最后更新：${new Date().toLocaleTimeString("zh-CN")}`;
    }
    
    // 更新详细状态（如果存在对应的DOM元素）
    updateDetailedStatus(data);
    
    // 更新控制按钮状态
    updateControlButtons(data);
}

/**
 * 更新详细状态信息（GUI中的所有状态字段）
 */
function updateDetailedStatus(data) {
    // 连接状态
    const connected = data.power?.connected ? "已连接" : "未连接";
    updateStatusField("connectionStatus", connected);
    
    // 控制权状态
    const controlAcquired = data.power?.control_acquired ? "已获取" : "未获取";
    updateStatusField("controlAuthorityStatus", controlAcquired);
    
    // 当前电压
    const voltage = (data.power?.voltage_kv || 0.0).toFixed(1);
    updateStatusField("currentVoltage", `${voltage} kV`);
    
    // 当前电流
    const current = (data.power?.current_ma || 0.0).toFixed(3);
    updateStatusField("currentCurrent", `${current} mA`);
    
    // 最后成功时间
    const lastSuccess = data.power?.last_successful_command 
        ? new Date(data.power.last_successful_command * 1000).toLocaleTimeString("zh-CN")
        : "无";
    updateStatusField("lastSuccessTime", lastSuccess);
    
    // 检测连接数
    const detectionClients = data.detection?.clients || 0;
    updateStatusField("detectionConnections", detectionClients.toString());
    
    // 当前阶段
    const currentStage = data.phase?.current_stage || "待开始";
    updateStatusField("currentStage", currentStage);
    
    // 系统模式
    const systemMode = data.phase?.system_mode || "空闲";
    updateStatusField("systemMode", systemMode);
    
    // 目标模式
    const targetMode = data.control?.target_mode || "None";
    updateStatusField("targetMode", targetMode);
    
    // 当前模式
    const currentMode = data.control?.current_mode || "---";
    updateStatusField("currentMode", currentMode);
    
    // 目标电压
    const targetVoltage = data.control?.target_voltage 
        ? `${data.control.target_voltage.toFixed(1)} kV`
        : "---";
    updateStatusField("targetVoltage", targetVoltage);
    
    // 模式误差
    const modeError = data.control?.mode_error !== null && data.control?.mode_error !== undefined
        ? data.control.mode_error.toFixed(2)
        : "---";
    updateStatusField("modeError", modeError);
    
    // 调整量
    const adjustment = data.control?.adjustment !== null && data.control?.adjustment !== undefined
        ? `${data.control.adjustment.toFixed(3)} kV`
        : "---";
    updateStatusField("adjustment", adjustment);
    
    // 控制迭代
    const controlIteration = data.control?.control_iteration || 0;
    updateStatusField("controlIteration", controlIteration.toString());
    
    // 已识别模式数
    const modeCount = data.control?.mode_count || 0;
    updateStatusField("recognizedModeCount", modeCount.toString());
    
    // 稳定性计数
    const stabilityCount = data.control?.stability_count !== null && data.control?.stability_count !== undefined
        ? data.control.stability_count.toString()
        : "---";
    updateStatusField("stabilityCount", stabilityCount);
    
    // 高压电源输出
    const outputVoltage = (data.power?.voltage_kv || 0.0).toFixed(2);
    updateStatusField("outputVoltage", `${outputVoltage} kV`);
    
    const outputCurrent = (data.power?.current_ma || 0.0).toFixed(3);
    updateStatusField("outputCurrent", `${outputCurrent} mA`);
    
    // 检测结果
    if (data.detection?.latest_detection) {
        const detection = data.detection.latest_detection;
        updateStatusField("modeName", detection.detected_mode || "---");
        updateStatusField("confidence", detection.confidence 
            ? detection.confidence.toFixed(2) 
            : "---");
        
        if (detection.timestamp) {
            const detectionTime = new Date(detection.timestamp * 1000).toLocaleTimeString("zh-CN");
            updateStatusField("detectionTime", detectionTime);
        } else {
            updateStatusField("detectionTime", "---");
        }
    } else {
        updateStatusField("modeName", "---");
        updateStatusField("confidence", "---");
        updateStatusField("detectionTime", "---");
    }
}

/**
 * 更新状态字段（辅助函数）
 */
function updateStatusField(fieldId, value) {
    const element = document.getElementById(fieldId);
    if (element) {
        element.textContent = value;
    }
}

/**
 * 更新控制按钮状态
 */
function updateControlButtons(data) {
    const systemRunning = data.system?.running || false;
    const exploring = data.system?.exploration_active || false;
    const controlling = data.system?.control_enabled || false;
    
    // 探索按钮
    const startExplorationBtn = document.getElementById('startExplorationBtn');
    const stopExplorationBtn = document.getElementById('stopExplorationBtn');
    if (startExplorationBtn && stopExplorationBtn) {
        startExplorationBtn.disabled = exploring;
        stopExplorationBtn.disabled = !exploring;
    }
    
    // 目标控制按钮
    const startTargetControlBtn = document.getElementById('startTargetControlBtn');
    const stopTargetControlBtn = document.getElementById('stopTargetControlBtn');
    if (startTargetControlBtn && stopTargetControlBtn) {
        startTargetControlBtn.disabled = controlling;
        stopTargetControlBtn.disabled = !controlling;
    }
}

// ==================== 高压电源连接 ====================

/**
 * 连接高压电源
 */
async function connectHvPower() {
    // 通过初始化系统来连接
    await initSystem();
}

/**
 * 断开高压电源
 */
async function disconnectHvPower() {
    await shutdownSystem();
}

/**
 * 测试连接
 */
async function testConnection() {
    const url = `${API_BASE}/api/system/status`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        const connected = data.power?.connected || false;
        
        if (connected) {
            showMessage("连接测试成功：高压电源已连接", "success");
        } else {
            showMessage("连接测试失败：高压电源未连接", "error");
        }
    } catch (e) {
        console.error("测试连接失败", e);
        showMessage("测试连接失败: " + e.message, "error");
    }
}

/**
 * 初始化高压电源连接
 */
function initHvPowerConnection() {
    const connectBtn = document.getElementById('connectHvPowerBtn');
    const disconnectBtn = document.getElementById('disconnectHvPowerBtn');
    const testBtn = document.getElementById('testConnectionBtn');
    
    if (connectBtn) {
        connectBtn.addEventListener('click', connectHvPower);
    }
    
    if (disconnectBtn) {
        disconnectBtn.addEventListener('click', disconnectHvPower);
    }
    
    if (testBtn) {
        testBtn.addEventListener('click', testConnection);
    }
}

// ==================== 检测连接 ====================

/**
 * 测试检测连接
 */
async function testDetectionConnection() {
    const url = `${API_BASE}/api/detection/test_connection`;
    
    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        if (data.success) {
            showMessage(`检测连接测试成功：${data.clients}个客户端已连接`, "success");
        } else {
            showMessage("检测连接测试失败：没有活动的检测连接", "error");
        }
    } catch (e) {
        console.error("测试检测连接失败", e);
        showMessage("测试检测连接失败: " + e.message, "error");
    }
}

/**
 * 显示连接状态
 */
async function showConnectionStatus() {
    const url = `${API_BASE}/api/detection/connection_status`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        
        let message = `检测服务器状态: ${data.server_running ? '运行中' : '未运行'}\n`;
        message += `检测连接数: ${data.clients}\n`;
        
        if (data.client_info && data.client_info.length > 0) {
            message += "\n连接详情:\n";
            data.client_info.forEach((client, index) => {
                message += `  连接${index + 1}: ${client.address} (连接时间: ${client.connected_time})\n`;
            });
        }
        
        alert(message);
    } catch (e) {
        console.error("获取连接状态失败", e);
        showMessage("获取连接状态失败: " + e.message, "error");
    }
}

/**
 * 诊断连接问题
 */
async function diagnoseConnection() {
    const url = `${API_BASE}/api/detection/diagnose`;
    
    try {
        const res = await fetch(url, { method: "POST" });
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        showMessage("诊断完成，请查看服务器日志", "info");
    } catch (e) {
        console.error("诊断连接失败", e);
        showMessage("诊断连接失败: " + e.message, "error");
    }
}

/**
 * 初始化检测连接
 */
function initDetectionConnection() {
    const testBtn = document.getElementById('testDetectionConnectionBtn');
    const showStatusBtn = document.getElementById('showConnectionStatusBtn');
    const diagnoseBtn = document.getElementById('diagnoseConnectionBtn');
    
    if (testBtn) {
        testBtn.addEventListener('click', testDetectionConnection);
    }
    
    if (showStatusBtn) {
        showStatusBtn.addEventListener('click', showConnectionStatus);
    }
    
    if (diagnoseBtn) {
        diagnoseBtn.addEventListener('click', diagnoseConnection);
    }
}

// ==================== 初始化功能 ====================

/**
 * 初始化系统控制
 */
function initSystemControls() {
    const initBtn = document.getElementById('initSystemBtn');
    const shutdownBtn = document.getElementById('shutdownSystemBtn');
    const emergencyBtn = document.getElementById('emergencyStopBtn');
    
    if (initBtn) {
        initBtn.addEventListener('click', initSystem);
    }
    
    if (shutdownBtn) {
        shutdownBtn.addEventListener('click', shutdownSystem);
    }
    
    if (emergencyBtn) {
        emergencyBtn.addEventListener('click', emergencyStop);
    }
}

/**
 * 初始化电源控制
 */
function initPowerControls() {
    const setVoltageBtn = document.getElementById('setVoltageBtn');
    const enablePowerBtn = document.getElementById('enablePowerBtn');
    const disablePowerBtn = document.getElementById('disablePowerBtn');
    
    if (setVoltageBtn) {
        setVoltageBtn.addEventListener('click', function() {
            const inputEl = document.getElementById('voltageInput');
            if (!inputEl) return;
            const voltage = parseFloat(inputEl.value);
            if (isNaN(voltage) || voltage < 0 || voltage > 30) {
                showMessage('请输入0-30之间的电压值', 'error');
                return;
            }
            setVoltage(voltage);
        });
    }
    
    if (enablePowerBtn) {
        enablePowerBtn.addEventListener('click', enablePower);
    }
    
    if (disablePowerBtn) {
        disablePowerBtn.addEventListener('click', disablePower);
    }
}

/**
 * 初始化控制模式
 */
function initControlModes() {
    const startExplorationBtn = document.getElementById('startExplorationBtn');
    const stopExplorationBtn = document.getElementById('stopExplorationBtn');
    const startTargetControlBtn = document.getElementById('startTargetControlBtn');
    const stopTargetControlBtn = document.getElementById('stopTargetControlBtn');
    const refreshModesBtn = document.getElementById('refreshModesBtn');
    
    if (startExplorationBtn) {
        startExplorationBtn.addEventListener('click', startExploration);
    }
    
    if (stopExplorationBtn) {
        stopExplorationBtn.disabled = true;
        stopExplorationBtn.addEventListener('click', stopExploration);
    }
    
    if (startTargetControlBtn) {
        startTargetControlBtn.addEventListener('click', startTargetControl);
    }
    
    if (stopTargetControlBtn) {
        stopTargetControlBtn.disabled = true;
        stopTargetControlBtn.addEventListener('click', stopTargetControl);
    }
    
    if (refreshModesBtn) {
        refreshModesBtn.addEventListener('click', loadModesList);
    }
    
    // 初始加载模式列表
    loadModesList();
    
    // 定期刷新模式列表（每10秒）
    setInterval(loadModesList, 10000);
}

/**
 * 加载模式列表
 */
async function loadModesList() {
    const url = `${API_BASE}/api/control/modes`;
    
    try {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        
        const data = await res.json();
        const targetModeSelect = document.getElementById('targetModeSelect');
        if (!targetModeSelect) return;

        // 无论 success 与否都更新下拉框，避免接口失败时残留旧数据
        const currentValue = targetModeSelect.value;
        targetModeSelect.innerHTML = '';

        if (data.success && data.modes && data.modes.length > 0) {
            // 与后端“已识别模式”一致：模式X: 名称, 电压:X.XkV (N次)
            data.modes.forEach((mode) => {
                const option = document.createElement('option');
                option.value = mode.id;
                const vol = (typeof mode.voltage === 'number' ? mode.voltage : Number(mode.voltage) || 0).toFixed(1);
                const count = mode.count != null ? mode.count : 0;
                const name = mode.name || '';
                option.textContent = `模式${mode.id}: ${name}, 电压:${vol}kV (${count}次)`;
                targetModeSelect.appendChild(option);
            });
            if (currentValue && Array.from(targetModeSelect.options).some(opt => opt.value === currentValue)) {
                targetModeSelect.value = currentValue;
            }
        } else {
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '请先完成电压探索';
            targetModeSelect.appendChild(option);
        }
    } catch (e) {
        console.error('加载模式列表失败:', e);
        const targetModeSelect = document.getElementById('targetModeSelect');
        if (targetModeSelect) {
            targetModeSelect.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.textContent = '请先完成电压探索';
            targetModeSelect.appendChild(option);
        }
    }
}

/**
 * 初始化状态概览
 */
function initStatusOverview() {
    const refreshBtn = document.getElementById('refreshStatusBtn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', function() {
            fetchSystemStatus();
            showMessage('已从服务器刷新状态', 'success');
        });
    }

    // 初始获取
    fetchSystemStatus();
}

/**
 * 启动状态自动更新
 */
function startStatusUpdate() {
    // 每5秒自动更新一次状态
    statusUpdateInterval = setInterval(fetchSystemStatus, 5000);
}

/**
 * 初始化操作日志
 */
function initOperationLogs() {
    const clearLogsBtn = document.getElementById('clearLogsBtn');
    const exportLogsBtn = document.getElementById('exportLogsBtn');
    const filterType = document.getElementById('logFilterType');
    
    if (clearLogsBtn) {
        clearLogsBtn.addEventListener('click', function() {
            if (confirm('确定要清空所有日志吗？')) {
                operationLogs = [];
                renderLogs();
                showMessage('日志已清空', 'success');
            }
        });
    }
    
    if (exportLogsBtn) {
        exportLogsBtn.addEventListener('click', exportLogs);
    }
    
    if (filterType) {
        filterType.addEventListener('change', renderLogs);
    }
    
    // 初始渲染
    renderLogs();
}

/**
 * 添加操作日志
 */
function addOperationLog(category, action, message, status) {
    const log = {
        id: Date.now(),
        category: category,
        action: action,
        message: message,
        status: status,
        timestamp: new Date().toLocaleString('zh-CN')
    };
    
    operationLogs.unshift(log);
    
    // 限制日志数量
    if (operationLogs.length > 100) {
        operationLogs = operationLogs.slice(0, 100);
    }
    
    renderLogs();
}

/**
 * 渲染日志列表
 */
function renderLogs() {
    const logsContainer = document.getElementById('logsContainer');
    if (!logsContainer) return;
    
    const filterType = document.getElementById('logFilterType')?.value || 'all';
    
    // 筛选日志
    let filteredLogs = operationLogs;
    if (filterType !== 'all') {
        filteredLogs = operationLogs.filter(log => log.action === filterType);
    }
    
    if (filteredLogs.length === 0) {
        logsContainer.innerHTML = '<div class="no-logs">暂无操作日志</div>';
        return;
    }
    
    const logsHTML = filteredLogs.map(log => `
        <div class="log-item ${log.status}">
            <div class="log-icon">
                <i class="fas ${getLogIcon(log.action)}"></i>
            </div>
            <div class="log-content">
                <div class="log-header">
                    <span class="log-action">${log.message}</span>
                </div>
                <div class="log-time">${log.timestamp}</div>
            </div>
            <div class="log-status">
                <i class="fas ${log.status === 'success' ? 'fa-check-circle' : log.status === 'error' ? 'fa-times-circle' : 'fa-exclamation-circle'}"></i>
            </div>
        </div>
    `).join('');
    
    logsContainer.innerHTML = logsHTML;
}

/**
 * 获取日志图标
 */
function getLogIcon(action) {
    const icons = {
        init: 'fa-power-off',
        shutdown: 'fa-stop',
        emergency: 'fa-exclamation-triangle',
        set_voltage: 'fa-bolt',
        enable: 'fa-toggle-on',
        disable: 'fa-toggle-off',
        exploration_start: 'fa-play',
        exploration_stop: 'fa-stop',
        target_start: 'fa-play-circle',
        target_stop: 'fa-stop-circle'
    };
    return icons[action] || 'fa-info-circle';
}

/**
 * 导出日志
 */
function exportLogs() {
    if (operationLogs.length === 0) {
        showMessage('没有可导出的日志', 'warning');
        return;
    }
    
    const csv = [
        ['时间', '类别', '操作', '消息', '状态'].join(','),
        ...operationLogs.map(log => [
            log.timestamp,
            log.category,
            log.action,
            log.message,
            log.status
        ].join(','))
    ].join('\n');
    
    const blob = new Blob(['\ufeff' + csv], { type: 'text/csv;charset=utf-8;' });
    const link = document.createElement('a');
    link.href = URL.createObjectURL(blob);
    link.download = `操作日志_${new Date().toISOString().split('T')[0]}.csv`;
    link.click();
    URL.revokeObjectURL(link.href);
    showMessage('日志导出成功！', 'success');
}

// ==================== UI 提示 ====================

/**
 * 显示消息提示
 */
function showMessage(msg, type) {
    // 使用全局的showMessage函数（如果存在）
    if (typeof window.showMessage === 'function') {
        window.showMessage(msg, type);
    } else {
        // 简单的alert提示
        alert(`[${type.toUpperCase()}] ${msg}`);
    }
}

/**
 * 显示请求状态
 */
function showRequestStatus(msg, type) {
    let statusEl = document.getElementById("requestStatus");
    if (!statusEl) {
        statusEl = document.createElement("div");
        statusEl.id = "requestStatus";
        statusEl.style.cssText = `
            position: fixed;
            top: 10px;
            right: 10px;
            background: rgba(0,0,0,0.8);
            color: #fff;
            padding: 8px 16px;
            border-radius: 6px;
            font-size: 12px;
            z-index: 9999;
            max-width: 300px;
            word-break: break-all;
        `;
        document.body.appendChild(statusEl);
    }

    statusEl.textContent = msg;

    if (type === "error") {
        statusEl.style.background = "rgba(239, 68, 68, 0.9)";
    } else if (type === "success") {
        statusEl.style.background = "rgba(82, 196, 26, 0.9)";
    } else {
        statusEl.style.background = "rgba(59, 130, 246, 0.9)";
    }
    
    // 3秒后自动隐藏
    setTimeout(() => {
        if (statusEl && statusEl.parentNode) {
            statusEl.style.opacity = '0';
            statusEl.style.transition = 'opacity 0.3s';
            setTimeout(() => {
                if (statusEl && statusEl.parentNode) {
                    statusEl.parentNode.removeChild(statusEl);
                }
            }, 300);
        }
    }, 3000);
}
