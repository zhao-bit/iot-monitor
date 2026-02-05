# 部署和使用指南

## 📋 文件说明

### 后端服务器

1. **hv_api_server_real.py** - 控制系统API服务器（端口8000）
   - 基于最新的 `v1.py`
   - 控制Modbus高压电源设备
   - 接收检测系统的TCP连接（端口12345）
   - 提供完整的系统控制、电源控制、电压探索、目标控制等功能

2. **detection_api_server.py** - 检测系统API服务器（端口8001）
   - 基于 `simplified version.py`
   - 提供摄像头视频流（MJPEG）
   - 执行YOLO目标检测
   - 发送检测结果到控制系统
   - 提供图像参数和检测参数调整API

### 前端文件

- **index.html** - 主页面，包含所有功能模块
- **js/modules/controlSystem.js** - 控制系统前端模块
- **js/modules/detectionSystem.js** - 检测系统前端模块（新增）

## 🚀 启动步骤

### 1. 启动控制系统API服务器

```bash
python hv_api_server_real.py
```

服务器将在 `http://localhost:8000` 启动

**要求：**
- `v1.py` 文件必须在同一目录
- Modbus设备已连接（默认COM5）
- 依赖库：`fastapi`, `uvicorn`, `pymodbus`, `scikit-fuzzy`, `numpy`

### 2. 启动检测系统API服务器

```bash
python detection_api_server.py
```

服务器将在 `http://localhost:8001` 启动

**要求：**
- 摄像头已连接
- YOLO模型文件路径正确（默认路径在代码中）
- 依赖库：`fastapi`, `uvicorn`, `opencv-python`, `ultralytics`, `torch`, `numpy`

### 3. 打开前端页面

在浏览器中打开 `index.html`

**前端会自动连接到：**
- 控制系统API: `http://127.0.0.1:8000`
- 检测系统API: `http://127.0.0.1:8001`

## 📡 API接口说明

### 控制系统API（端口8000）

#### 系统控制
- `POST /api/system/init` - 初始化系统
- `POST /api/system/shutdown` - 关闭系统
- `GET /api/system/status` - 获取系统状态（包含GUI中的所有状态字段）

#### 电源控制
- `POST /api/power/set_voltage` - 设置电压
- `POST /api/power/enable` - 开启高压
- `POST /api/power/disable` - 关闭高压
- `GET /api/power/status` - 获取电源状态

#### 控制模式
- `POST /api/control/exploration/start` - 开始电压探索
- `POST /api/control/exploration/stop` - 停止电压探索
- `POST /api/control/target/start` - 开始目标控制
- `POST /api/control/target/stop` - 停止目标控制
- `GET /api/control/modes` - 获取已识别的模式列表

#### 检测连接
- `POST /api/detection/test_connection` - 测试检测连接
- `GET /api/detection/connection_status` - 获取检测连接状态
- `POST /api/detection/diagnose` - 诊断连接问题

#### 紧急控制
- `POST /api/emergency/stop` - 紧急停止

### 检测系统API（端口8001）

#### 摄像头控制
- `POST /api/camera/start` - 启动摄像头和检测
- `POST /api/camera/stop` - 停止摄像头和检测

#### 视频流
- `GET /api/video/stream` - 获取MJPEG视频流
- `GET /api/video/frame` - 获取单帧图像（Base64）

#### 检测结果
- `GET /api/detection/latest` - 获取最新检测结果

#### 参数调整
- `POST /api/image/params` - 更新图像处理参数
- `GET /api/image/params` - 获取图像处理参数
- `POST /api/detection/params` - 更新检测参数
- `GET /api/detection/params` - 获取检测参数

#### 控制系统连接
- `POST /api/control/connect` - 连接到控制系统
- `GET /api/control/status` - 获取连接状态

## 🎯 使用流程

### 1. 初始化系统

1. 打开前端页面，进入"控制系统"模块
2. 点击"初始化系统"按钮
3. 系统将：
   - 连接Modbus设备
   - 启动检测服务器（TCP端口12345）
   - 启动控制循环线程

### 2. 启动检测系统

1. 在检测系统模块（或通过API）启动摄像头
2. 检测系统会自动连接到控制系统的TCP端口12345
3. 视频流将显示在前端页面
4. 检测结果会自动发送到控制系统

### 3. 电压探索

1. 设置探索参数：
   - 最小电压
   - 最大电压
   - 电压步长
   - 等待时间
2. 点击"开始探索"
3. 系统将在指定电压范围内自动探索并识别模式
4. 探索完成后，模式列表会自动更新

### 4. 目标控制

1. 从下拉列表中选择目标模式
2. 点击"开始控制"
3. 系统将通过模糊控制算法自动调整电压以达到目标模式
4. 实时状态会显示在状态面板中

## 🔧 配置说明

### 控制系统配置

在 `hv_api_server_real.py` 中：
- `modbus_port`: Modbus端口（默认COM5）
- `detection_port`: 检测服务器端口（默认12345）

### 检测系统配置

在 `detection_api_server.py` 中：
- `camera_no`: 摄像头编号（默认1）
- `model_path`: YOLO模型文件路径
- `control_system_host`: 控制系统主机（默认localhost）
- `control_system_port`: 控制系统端口（默认12345）

## ⚠️ 注意事项

1. **端口冲突**：
   - 确保端口8000和8001未被占用
   - 确保端口12345未被占用（检测系统TCP连接）

2. **硬件连接**：
   - Modbus设备必须正确连接
   - 摄像头必须正确连接
   - 确保设备驱动已安装

3. **模型文件**：
   - 确保YOLO模型文件路径正确
   - 模型文件必须存在且可访问

4. **网络连接**：
   - 前端需要能够访问localhost:8000和8001
   - 检测系统需要能够连接到控制系统的TCP端口12345

5. **权限问题**：
   - Linux系统可能需要sudo权限访问串口
   - 某些端口可能需要管理员权限

## 🔍 故障排查

### 问题1：无法连接Modbus设备

**解决：**
- 检查串口是否正确
- 检查设备是否连接
- Linux系统检查串口权限：`sudo chmod 666 /dev/ttyUSB0`

### 问题2：检测系统无法连接

**解决：**
- 确保控制系统API服务器已启动
- 检查端口12345是否被占用
- 检查防火墙设置
- 查看服务器日志

### 问题3：视频流无法显示

**解决：**
- 确保检测系统API服务器已启动
- 检查摄像头是否连接
- 检查浏览器是否支持MJPEG流
- 查看浏览器控制台错误信息

### 问题4：前端无法连接后端

**解决：**
- 检查后端服务器是否运行
- 检查端口是否正确
- 检查CORS设置
- 查看浏览器控制台网络请求

## 📚 API文档

启动服务器后，可以访问：

- 控制系统API文档: `http://localhost:8000/docs`
- 检测系统API文档: `http://localhost:8001/docs`

## 🎉 完成

现在您可以在网页上真实调用硬件设备了！

- ✅ 控制系统：控制Modbus高压电源
- ✅ 检测系统：显示摄像头视频流和检测结果
- ✅ 完整集成：两个系统通过TCP socket通信
