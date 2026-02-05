# 高压控制系统 API 服务器使用说明

## 📋 文件说明

### 1. hv_api_server_mock.py（模拟版）
- **用途**：前端开发和测试，无需真实硬件
- **特点**：返回模拟数据，不连接真实设备
- **适用场景**：前端开发、功能测试、演示

### 2. hv_api_server_real.py（真实版）⭐
- **用途**：生产环境，连接真实硬件设备
- **特点**：集成 v1控制.py 的所有功能，控制真实Modbus设备
- **适用场景**：实际生产使用

## 🚀 快速开始

### 启动模拟服务器（开发测试）
```bash
python hv_api_server_mock.py
```

### 启动真实服务器（生产环境）
```bash
python hv_api_server_real.py
```

服务器将在 `http://localhost:8000` 启动

## 📡 API接口列表

### 系统控制

#### POST `/api/system/init`
初始化系统
- **请求体**：
  ```json
  {
    "modbus_port": "COM5",
    "detection_port": 12345,
    "model_path": "best.pt",
    "camera_id": 1
  }
  ```
- **功能**：
  - 创建控制系统实例
  - 连接Modbus设备
  - 启动检测服务器（TCP端口12345）
  - 启动控制循环线程

#### POST `/api/system/shutdown`
关闭系统
- **功能**：
  - 停止所有控制
  - 断开Modbus连接
  - 关闭检测服务器
  - 清理资源

#### GET `/api/system/status`
获取系统状态
- **返回**：
  ```json
  {
    "system": {
      "running": true,
      "control_enabled": false,
      "exploration_active": false
    },
    "power": {
      "connected": true,
      "voltage_kv": 5.0,
      "current_ma": 0.5,
      "port": "COM5"
    },
    "detection": {
      "active": true,
      "clients": 1,
      "latest_detection": {
        "detected_mode": "normal",
        "confidence": 0.85,
        "timestamp": 1234567890
      }
    },
    "control": {
      "target_mode": "1",
      "current_voltage_kv": 5.0,
      "mode_count": 3
    },
    "timestamp": 1234567890
  }
  ```

### 电源控制

#### POST `/api/power/set_voltage`
设置电压
- **请求体**：
  ```json
  {
    "voltage_kv": 5.0
  }
  ```
- **范围**：0.0 - 30.0 kV

#### POST `/api/power/enable`
开启高压电源

#### POST `/api/power/disable`
关闭高压电源

#### GET `/api/power/status`
获取电源状态

### 控制模式

#### POST `/api/control/exploration/start`
开始电压探索
- **请求体**：
  ```json
  {
    "min_voltage": 0.0,
    "max_voltage": 20.0,
    "voltage_step": 0.5,
    "wait_time": 1.0,
    "confidence_threshold": 0.7
  }
  ```
- **功能**：
  - 在指定电压范围内自动探索
  - 识别不同模式（normal/spark/arc等）
  - 建立模式与电压的映射关系

#### POST `/api/control/exploration/stop`
停止电压探索

#### POST `/api/control/target/start`
开始目标控制
- **请求体**：
  ```json
  {
    "target_mode": "1"
  }
  ```
- **功能**：
  - 启动模糊控制算法
  - 自动调整电压以达到目标模式
  - 实时监控和反馈

#### POST `/api/control/target/stop`
停止目标控制

#### GET `/api/control/modes`
获取已识别的模式列表
- **返回**：
  ```json
  {
    "success": true,
    "modes": [
      {
        "id": "1",
        "name": "normal",
        "voltage": 5.0,
        "count": 10
      },
      {
        "id": "2",
        "name": "spark",
        "voltage": 12.0,
        "count": 6
      }
    ],
    "count": 2
  }
  ```

### 紧急控制

#### POST `/api/emergency/stop`
紧急停止
- **功能**：
  - 立即设置电压为0
  - 关闭高压电源
  - 停止所有控制

## 🔧 真实服务器配置要求

### 1. 依赖库
```bash
pip install fastapi uvicorn pymodbus scikit-fuzzy numpy
```

### 2. 文件要求
- `v1控制.py` 必须在同一目录下
- Modbus设备已连接并配置正确端口

### 3. 系统要求
- Python 3.7+
- Windows/Linux（Modbus串口支持）
- 串口权限（Linux可能需要sudo）

## 📝 使用流程

### 1. 初始化系统
```bash
POST /api/system/init
{
  "modbus_port": "COM5",
  "detection_port": 12345
}
```

### 2. 电压探索（识别模式）
```bash
POST /api/control/exploration/start
{
  "min_voltage": 0.0,
  "max_voltage": 20.0,
  "voltage_step": 0.5,
  "wait_time": 1.0,
  "confidence_threshold": 0.7
}
```

### 3. 查看识别的模式
```bash
GET /api/control/modes
```

### 4. 启动目标控制
```bash
POST /api/control/target/start
{
  "target_mode": "1"
}
```

### 5. 监控系统状态
```bash
GET /api/system/status
```

## ⚠️ 注意事项

1. **真实服务器**：
   - 确保Modbus设备已连接
   - 检查串口权限
   - 确保检测模块已连接到TCP端口12345

2. **电压探索**：
   - 需要检测模块连接才能识别模式
   - 探索过程可能需要较长时间
   - 可以通过状态接口查看进度

3. **目标控制**：
   - 必须先完成电压探索
   - 需要检测模块实时反馈
   - 控制算法会自动调整电压

4. **安全**：
   - 紧急停止功能随时可用
   - 电压范围限制在0-30kV
   - 所有操作都有错误处理

## 🔍 故障排查

### 问题1：无法导入v1控制模块
**解决**：确保 `v1控制.py` 在同一目录下

### 问题2：Modbus连接失败
**解决**：
- 检查串口是否正确
- 检查设备是否连接
- Linux系统检查串口权限

### 问题3：检测服务器启动失败
**解决**：
- 检查端口12345是否被占用
- Linux系统可能需要sudo权限

### 问题4：电压探索无结果
**解决**：
- 确保检测模块已连接
- 检查检测模块是否发送数据
- 调整置信度阈值

## 📚 API文档

启动服务器后，访问 `http://localhost:8000/docs` 查看完整的API文档（Swagger UI）

## 🔄 前端集成

前端代码已自动连接到 `http://127.0.0.1:8000`，所有按钮都已连接：

- ✅ 系统初始化
- ✅ 系统关闭
- ✅ 紧急停止
- ✅ 设置电压
- ✅ 开启/关闭高压
- ✅ 电压探索
- ✅ 目标控制
- ✅ 状态监控

只需启动对应的API服务器即可使用！
