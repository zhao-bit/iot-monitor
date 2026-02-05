# detection_api_server.py - 检测系统（摄像头）HTTP API服务器
# 基于 simplified version.py，提供视频流和检测API

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
import uvicorn
import cv2
import torch
import numpy as np
from ultralytics import YOLO
import time
import os
import socket
import json
import threading
from datetime import datetime
import io
import base64
import requests  # 用于从控制系统API读取检测结果
import importlib.util

app = FastAPI(
    title="检测系统API（摄像头）",
    description="提供摄像头视频流和检测结果API",
    version="1.0.0"
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== 全局变量 ==========

# 摄像头和模型
camera = None
model = None
device = None
camera_no = 1
# 模型路径
# 默认使用当前目录下的 best.pt，如果不存在，可以通过 API 启动时传入完整路径
model_path = "best.pt"

# 图像调整参数
image_params = {
    'brightness': 256,
    'contrast': 0,
    'sharpness': 0,
    'gamma': 65,
    'denoise': 0,
    'denoise_param1': 5,
    'denoise_param2': 10,
    'hist_eq': 0,
    'clahe_clip': 20,
    'clahe_grid': 8,
    'edge': 0,
    'threshold': 0,
    'thresh_value': 127,
    'noise_removal': 0,
    'noise_kernel': 3,
    'noise_iter': 1,
    'noise_min_area': 50,
    'max_quality_mode': False
}

# 检测参数
detection_params = {
    'target_fps': 30,
    'confidence_threshold': 0.5
}

# 控制系统连接
control_system_host = 'localhost'
control_system_port = 12345
control_sock = None
control_sock_lock = threading.Lock()

# 运行状态
running = False
capture_thread = None
latest_detection = None
latest_frame = None
frame_lock = threading.Lock()

# ========== 新增：后台启动 simplified version.py（不改脚本本体）==========
# 方案：
# - 以"线程方式"在本进程后台运行 simplified version.py 的 main()
# - 通过 monkeypatch 拦截 cv2.imshow(name, frame) 来拿到已标注帧（latest_frame）
# - 不接管其 VideoCapture 打开逻辑，因此仍按你脚本里的 USB 摄像头策略工作

SIMPLIFIED_SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "simplified version.py")
_simplified_thread = None
_simplified_stop_event = threading.Event()
_stream_last_frame_ts = None
_stream_fps_ema = 0.0
_stream_frames_received = 0


def _load_simplified_module():
    if not os.path.exists(SIMPLIFIED_SCRIPT):
        raise FileNotFoundError(f"找不到脚本: {SIMPLIFIED_SCRIPT}")
    spec = importlib.util.spec_from_file_location("simplified_version_module", SIMPLIFIED_SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _start_simplified_in_thread():
    global _simplified_thread, running
    if _simplified_thread is not None and _simplified_thread.is_alive():
        return

    try:
        simplified = _load_simplified_module()
    except Exception as e:
        print(f"❌ 无法加载 simplified version.py: {e}")
        return

    # monkeypatch: 拦截 imshow / waitKey，实现"取帧 + 可退出"
    original_imshow = cv2.imshow
    original_waitKey = cv2.waitKey

    def patched_imshow(winname, mat):
        global latest_frame, _stream_last_frame_ts, _stream_fps_ema, _stream_frames_received, running
        try:
            if isinstance(mat, np.ndarray) and mat.size > 0:
                now = time.time()
                if _stream_last_frame_ts is not None:
                    dt = max(1e-6, now - _stream_last_frame_ts)
                    fps_inst = 1.0 / dt
                    _stream_fps_ema = fps_inst if _stream_fps_ema <= 0 else (_stream_fps_ema * 0.9 + fps_inst * 0.1)
                _stream_last_frame_ts = now
                _stream_frames_received += 1
                with frame_lock:
                    latest_frame = mat.copy()
                running = True
        except Exception:
            pass
        return original_imshow(winname, mat)

    def patched_waitKey(delay=0):
        if _simplified_stop_event.is_set():
            # 返回 'q' 触发 simplified version.py 的退出逻辑
            return ord('q')
        return original_waitKey(delay)

    cv2.imshow = patched_imshow
    cv2.waitKey = patched_waitKey

    def runner():
        try:
            simplified.main()
        except Exception as e:
            print(f"❌ simplified version.py 运行异常: {e}")
            import traceback
            traceback.print_exc()
        finally:
            # 尽量恢复（避免影响别的OpenCV逻辑）
            try:
                cv2.imshow = original_imshow
                cv2.waitKey = original_waitKey
            except Exception:
                pass

    _simplified_stop_event.clear()
    _simplified_thread = threading.Thread(target=runner, name="SimplifiedRunner", daemon=True)
    _simplified_thread.start()
    print("🚀 已后台启动 simplified version.py（线程方式）")


@app.on_event("startup")
def _on_startup():
    _start_simplified_in_thread()


@app.on_event("shutdown")
def _on_shutdown():
    _simplified_stop_event.set()


# 保存设置
save_dir = "不同针头/15ml的流量-21g-无水乙醇-5cm-1218下午测试/25g"
auto_save_enabled = False
auto_save_interval = 0.1
last_save_time = time.time()
save_count = 0


# ========== 图像处理函数（从simplified version.py）==========

def apply_adjustment(frame):
    """应用所有图像调整参数"""
    try:
        gray_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        denoised_frame = apply_denoise(gray_frame)
        equalized_frame = apply_hist_equalization(denoised_frame)
        adjusted_frame = apply_brightness_contrast_gamma(equalized_frame)
        enhanced_frame = apply_sharpness_edge(adjusted_frame)
        thresholded_frame = apply_threshold(enhanced_frame)
        cleaned_frame = apply_noise_removal(thresholded_frame)
        return cv2.cvtColor(cleaned_frame, cv2.COLOR_GRAY2BGR)
    except Exception as e:
        print(f"图像处理错误: {e}")
        return frame.copy()


def apply_denoise(img):
    """应用降噪处理"""
    method = image_params['denoise']
    if method == 0:
        return img
    if method == 1:
        kernel_size = max(3, image_params['denoise_param1'] * 2 + 1)
        return cv2.GaussianBlur(img, (kernel_size, kernel_size), max(1, image_params['denoise_param2']))
    if method == 2:
        kernel_size = max(3, image_params['denoise_param1'] * 2 + 1)
        return cv2.medianBlur(img, kernel_size)
    if method == 3:
        d = max(1, image_params['denoise_param1'])
        sigma_color = max(1, image_params['denoise_param2'])
        return cv2.bilateralFilter(img, d, sigma_color, sigma_color)
    if method == 4:
        h = max(1, image_params['denoise_param1'])
        template_size = max(3, image_params['denoise_param2'])
        search_size = min(21, template_size * 3)
        return cv2.fastNlMeansDenoising(img, None, h, template_size, search_size)
    return img


def apply_hist_equalization(img):
    """应用直方图均衡化"""
    method = image_params['hist_eq']
    if method == 0:
        return img
    if method == 1:
        return cv2.equalizeHist(img)
    if method == 2:
        clip_limit = image_params['clahe_clip'] / 100.0
        grid_size = max(4, image_params['clahe_grid'])
        if image_params['max_quality_mode']:
            grid_size = max(8, grid_size)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
        return clahe.apply(img)
    return img


def apply_brightness_contrast_gamma(img):
    """应用亮度、对比度和伽马校正"""
    adj_brightness = (image_params['brightness'] - 256) / 2.0
    adj_contrast = image_params['contrast'] / 200.0 + 1.0
    adj_gamma = max(image_params['gamma'] / 100.0, 0.01)

    img_adj = img.astype(np.float32)
    img_adj = img_adj + adj_brightness

    if adj_contrast != 1.0:
        mean_val = np.mean(img_adj)
        img_adj = (img_adj - mean_val) * adj_contrast + mean_val

    if abs(adj_gamma - 1.0) > 0.01:
        inv_gamma = 1.0 / adj_gamma
        table = np.array([((i / 255.0) ** inv_gamma) * 255 for i in range(256)]).astype("uint8")
        img_adj = cv2.LUT(np.clip(img_adj, 0, 255).astype(np.uint8), table)

    img_adj = np.clip(img_adj, 0, 255)
    return img_adj.astype(np.uint8)


def apply_sharpness_edge(img):
    """应用锐化和边缘增强"""
    if image_params['sharpness'] > 0:
        adj_sharpness = image_params['sharpness'] / 200.0
        if image_params['max_quality_mode']:
            kernel = np.array([[-1, -1, -1, -1, -1],
                               [-1, 2, 2, 2, -1],
                               [-1, 2, 8 + adj_sharpness, 2, -1],
                               [-1, 2, 2, 2, -1],
                               [-1, -1, -1, -1, -1]]) / 8.0
        else:
            kernel = np.array([[-1, -1, -1],
                               [-1, 9 + adj_sharpness, -1],
                               [-1, -1, -1]])
        return cv2.filter2D(img, -1, kernel)

    if image_params['edge'] > 0:
        adj_edge = image_params['edge'] / 200.0
        kernel = np.array([[-1, -1, -1],
                           [-1, 8 + adj_edge, -1],
                           [-1, -1, -1]])
        return cv2.filter2D(img, -1, kernel)

    return img


def apply_threshold(img):
    """应用阈值处理"""
    method = image_params['threshold']
    if method == 0:
        return img
    if method == 1:
        _, thresh = cv2.threshold(img, image_params['thresh_value'], 255, cv2.THRESH_BINARY)
        return thresh
    if method == 2:
        _, thresh = cv2.threshold(img, image_params['thresh_value'], 255, cv2.THRESH_BINARY_INV)
        return thresh
    if method == 3:
        thresh = cv2.adaptiveThreshold(img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
        return thresh
    return img


def apply_noise_removal(img):
    """应用噪声去除"""
    method = image_params['noise_removal']
    if method == 0:
        return img
    if method == 1:
        kernel_size = max(1, image_params['noise_kernel'])
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        return cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=image_params['noise_iter'])
    if method == 2:
        kernel_size = max(1, image_params['noise_kernel'])
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        return cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=image_params['noise_iter'])
    if method == 3:
        kernel_size = max(1, image_params['noise_kernel'])
        kernel = np.ones((kernel_size, kernel_size), np.uint8)
        opened = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=image_params['noise_iter'])
        return cv2.morphologyEx(opened, cv2.MORPH_CLOSE, kernel, iterations=image_params['noise_iter'])
    if method == 4:
        # 连通域分析去除小区域
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(img, connectivity=8)
        result = np.zeros_like(img)
        for i in range(1, num_labels):
            if stats[i, cv2.CC_STAT_AREA] >= image_params['noise_min_area']:
                result[labels == i] = 255
        return result
    return img


# ========== 控制系统连接函数 ==========

def connect_to_control_system(silent=False):
    """连接到控制系统"""
    global control_sock

    with control_sock_lock:
        try:
            if control_sock is not None:
                try:
                    control_sock.close()
                except:
                    pass

            control_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            control_sock.settimeout(2.0)  # 缩短超时时间，避免长时间阻塞
            control_sock.connect((control_system_host, control_system_port))
            control_sock.settimeout(2.0)

            if not silent:
                print(f"✅ 成功连接到控制系统: {control_system_host}:{control_system_port}")
            return True
        except Exception as e:
            if not silent:
                print(f"⚠️ 连接控制系统失败: {e} (控制系统可能未启动，检测系统将继续独立运行)")
            control_sock = None
            return False


def send_detection_result(detection_data, silent=True):
    """发送检测结果到控制系统（静默模式，失败不影响主流程）"""
    global control_sock

    with control_sock_lock:
        try:
            if control_sock is None:
                # 静默尝试连接，失败也不影响
                if not connect_to_control_system(silent=True):
                    return False

            message = json.dumps(detection_data)
            control_sock.send((message + '\n').encode())
            return True
        except Exception as e:
            # 连接断开，静默处理
            if control_sock:
                try:
                    control_sock.close()
                except:
                    pass
            control_sock = None
            # 只在非静默模式下打印错误
            if not silent:
                print(f"⚠️ 发送检测结果失败: {e}")
            return False


def process_detection_results(results, model, silent=False):
    """处理检测结果并发送到控制系统"""
    global latest_detection

    if results[0].boxes is not None and len(results[0].boxes) > 0:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        confidences = results[0].boxes.conf.cpu().numpy()
        class_ids = results[0].boxes.cls.cpu().numpy().astype(int)

        max_conf_idx = np.argmax(confidences)
        best_class_id = class_ids[max_conf_idx]
        best_confidence = confidences[max_conf_idx]
        best_class_name = model.names[best_class_id]

        detection_data = {
            'timestamp': time.time(),
            'detected_mode': best_class_name,
            'confidence': float(best_confidence),
            'all_detections': []
        }

        for box, conf, cls_id in zip(boxes, confidences, class_ids):
            detection_data['all_detections'].append({
                'class_name': model.names[cls_id],
                'confidence': float(conf),
                'bbox': box.tolist()
            })

        # 静默发送，失败不影响主流程
        send_success = send_detection_result(detection_data, silent=True)
        if send_success and not silent:
            print(f"✅ 检测结果已发送: {best_class_name} (置信度: {best_confidence:.2f})")

        latest_detection = detection_data
        return best_class_name, best_confidence
    else:
        detection_data = {
            'timestamp': time.time(),
            'detected_mode': 'none',
            'confidence': 0.0,
            'all_detections': []
        }
        send_detection_result(detection_data, silent=True)
        latest_detection = detection_data
        return None, 0.0


# ========== 后台重连线程 ==========

def background_reconnect_worker():
    """后台重连工作线程（定期尝试连接控制系统）"""
    global control_sock, running

    reconnect_interval = 10.0  # 每10秒尝试一次

    while running:
        time.sleep(reconnect_interval)

        # 如果未连接，尝试重连
        with control_sock_lock:
            if control_sock is None and running:
                try:
                    # 静默尝试连接
                    if connect_to_control_system(silent=True):
                        print("✅ 后台重连成功：已连接到控制系统")
                except:
                    pass  # 静默失败，继续等待下次重试


# ========== 视频捕获线程 ==========

def capture_loop():
    """视频捕获和处理循环"""
    global camera, model, running, latest_frame

    prev_time = time.time()
    last_frame_time = time.time()

    while running:
        try:
            target_frame_time = 1.0 / detection_params['target_fps']
            current_time = time.time()
            elapsed = current_time - last_frame_time

            if elapsed < target_frame_time:
                time.sleep(max(0, target_frame_time - elapsed))

            last_frame_time = time.time()

            ret, frame = camera.read()
            if not ret:
                print("⚠️ 捕获帧失败")
                time.sleep(0.1)
                continue

            if frame.size == 0 or frame.shape[0] == 0 or frame.shape[1] == 0:
                continue

            # 应用图像调整
            adjusted_frame = apply_adjustment(frame)
            frame_rgb = cv2.cvtColor(adjusted_frame, cv2.COLOR_BGR2RGB)

            detected_mode = None
            confidence = 0.0

            # 如果模型已加载，则执行推理；否则仅推送原始画面
            if model is not None:
                try:
                    if detection_params['target_fps'] <= 5:
                        results = model(frame_rgb, verbose=False, imgsz=640, conf=0.3)
                    else:
                        results = model(frame_rgb, verbose=False, imgsz=640,
                                        conf=detection_params['confidence_threshold'])
                except Exception as e:
                    print(f"⚠️ 推理错误: {e}")
                    results = None

                if results is not None:
                    # 处理检测结果（静默发送，失败不影响视频流）
                    detected_mode, confidence = process_detection_results(results, model, silent=True)

                    # 创建带注释的帧
                    annotated_frame = adjusted_frame.copy()

                    if results[0].boxes is not None:
                        boxes = results[0].boxes.xyxy.cpu().numpy()
                        confidences = results[0].boxes.conf.cpu().numpy()
                        class_ids = results[0].boxes.cls.cpu().numpy().astype(int)

                        for box, conf, cls_id in zip(boxes, confidences, class_ids):
                            x1, y1, x2, y2 = map(int, box)
                            color = (0, 0, 255)
                            if cls_id < len(model.names):
                                color = (
                                    int(255 * (cls_id % 3 == 0)),
                                    int(255 * (cls_id % 3 == 1)),
                                    int(255 * (cls_id % 3 == 2))
                                )

                            cv2.rectangle(annotated_frame, (x1, y1), (x2, y2), color, 2)
                            label = f"{model.names[cls_id]} {conf:.2f}"
                            cv2.putText(annotated_frame, label, (x1, max(20, y1 - 10)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)
                else:
                    annotated_frame = adjusted_frame.copy()
            else:
                # 未加载模型时，仅显示经过预处理的原始画面
                annotated_frame = adjusted_frame.copy()

            # 显示FPS和检测信息
            current_time = time.time()
            fps = 1 / (current_time - prev_time) if current_time != prev_time else 0
            prev_time = current_time

            fps_info = f"FPS: {fps:.1f} (Target: {detection_params['target_fps']})"
            cv2.putText(annotated_frame, fps_info, (10, 30),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

            if detected_mode:
                detection_info = f"Detected: {detected_mode} ({confidence:.2f})"
                cv2.putText(annotated_frame, detection_info, (10, 60),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

            connection_status = "Connected" if control_sock else "Disconnected"
            color = (0, 255, 0) if control_sock else (0, 0, 255)
            cv2.putText(annotated_frame, f"Control: {connection_status}", (10, 90),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

            # 更新最新帧
            with frame_lock:
                latest_frame = annotated_frame.copy()

        except Exception as e:
            print(f"❌ 捕获循环错误: {e}")
            import traceback
            traceback.print_exc()
            time.sleep(0.1)

    print("📹 视频捕获循环已停止")


# ========== 请求模型 ==========

class ImageParamsRequest(BaseModel):
    brightness: int = Field(None, ge=0, le=512)
    contrast: int = Field(None, ge=0, le=300)
    sharpness: int = Field(None, ge=0, le=200)
    gamma: int = Field(None, ge=1, le=300)
    denoise: int = Field(None, ge=0, le=4)
    denoise_param1: int = Field(None, ge=1, le=20)
    denoise_param2: int = Field(None, ge=1, le=50)
    hist_eq: int = Field(None, ge=0, le=2)
    clahe_clip: int = Field(None, ge=1, le=100)
    clahe_grid: int = Field(None, ge=4, le=16)
    edge: int = Field(None, ge=0, le=200)
    threshold: int = Field(None, ge=0, le=3)
    thresh_value: int = Field(None, ge=0, le=255)
    noise_removal: int = Field(None, ge=0, le=4)
    noise_kernel: int = Field(None, ge=1, le=15)
    noise_iter: int = Field(None, ge=1, le=5)
    noise_min_area: int = Field(None, ge=1, le=200)
    max_quality_mode: bool = None


class DetectionParamsRequest(BaseModel):
    target_fps: int = Field(None, ge=1, le=120)
    confidence_threshold: float = Field(None, ge=0.0, le=1.0)


class CameraConfigRequest(BaseModel):
    camera_no: int = Field(None, ge=0, le=10)
    model_path: str = None
    control_host: str = None
    control_port: int = Field(None, ge=1, le=65535)


# ========== API接口 ==========

@app.get("/")
def root():
    return {
        "service": "检测系统API（摄像头）",
        "version": "1.0.0",
        "docs": "/docs",
        "status": "running" if running else "stopped",
        "camera_connected": camera is not None and camera.isOpened() if camera else False
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "running": running,
        "camera_connected": camera is not None and camera.isOpened() if camera else False,
        "model_loaded": model is not None,
        "control_connected": control_sock is not None
    }


@app.post("/api/camera/start")
def start_camera(config: CameraConfigRequest = None):
    """
    启动摄像头和检测（已禁用本服务的摄像头控制）

    说明：
    - 实际摄像头由 `simplified version.py` 进程通过 OpenCV 管理并采集外接硬件画面。
    - 本 HTTP 服务不再直接打开摄像头或加载模型，避免与 simplified version.py 抢占设备。
    - 前端如需启动/停止摄像头，请在后端电脑上单独运行/停止 simplified version.py。
    """
    raise HTTPException(
        status_code=400,
        detail="摄像头由 simplified version.py 管理，本检测API不再直接控制摄像头，请在后端电脑上启动/停止 simplified version.py"
    )


@app.post("/api/camera/stop")
def stop_camera():
    """
    停止摄像头和检测（占位接口）

    实际摄像头由 simplified version.py 管理，这里仅返回占位响应，避免前端报错。
    """
    return {"success": True, "message": "摄像头由 simplified version.py 管理，本接口不执行实际停止操作"}


@app.get("/api/video/stream")
def video_stream():
    """
    获取MJPEG视频流（来自 simplified version.py 的已标注帧）
    """

    def generate():
        boundary = b"--frame\r\n"
        while True:
            with frame_lock:
                frame = latest_frame.copy() if latest_frame is not None else None

            if frame is None:
                # 没有帧时返回占位图像
                placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
                cv2.putText(placeholder, "Waiting for camera...", (50, 240),
                            cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
                frame = placeholder

            ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
            if not ok:
                time.sleep(0.01)
                continue

            jpg = buf.tobytes()
            yield boundary
            yield b"Content-Type: image/jpeg\r\n"
            yield f"Content-Length: {len(jpg)}\r\n\r\n".encode("utf-8")
            yield jpg
            yield b"\r\n"

            # 控制推送频率（避免无限占用CPU）
            time.sleep(0.033)  # 约30fps

    return StreamingResponse(generate(), media_type="multipart/x-mixed-replace; boundary=frame")


@app.get("/api/video/frame")
def get_frame():
    """获取单帧图像（Base64编码）"""
    global latest_frame, running, camera

    # 如果摄像头未运行，返回占位图像
    if not running or camera is None:
        placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.putText(placeholder, "Camera Not Started", (50, 240),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
        ret, buffer = cv2.imencode('.jpg', placeholder, [cv2.IMWRITE_JPEG_QUALITY, 90])
        if ret:
            frame_base64 = base64.b64encode(buffer).decode('utf-8')
            return {
                "success": False,
                "frame": f"data:image/jpeg;base64,{frame_base64}",
                "timestamp": time.time(),
                "message": "摄像头未启动"
            }
        else:
            raise HTTPException(status_code=500, detail="图像编码失败")

    with frame_lock:
        if latest_frame is None:
            # 没有帧数据，返回占位图像
            placeholder = np.zeros((480, 640, 3), dtype=np.uint8)
            cv2.putText(placeholder, "Waiting for frame...", (50, 240),
                        cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)
            frame = placeholder
        else:
            frame = latest_frame.copy()

    ret, buffer = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if ret:
        frame_base64 = base64.b64encode(buffer).decode('utf-8')
        return {
            "success": True,
            "frame": f"data:image/jpeg;base64,{frame_base64}",
            "timestamp": time.time()
        }
    else:
        raise HTTPException(status_code=500, detail="图像编码失败")


HV_API_BASE = "http://127.0.0.1:8000"  # 控制系统 Real API 基地址


@app.get("/api/detection/latest")
def get_latest_detection():
    """
    获取最新检测结果

    数据来源：
    - simplified version.py 通过 TCP 把检测结果发送给控制系统 (v1.py)；
    - 控制系统通过 hv_api_server_real.py 的 `/api/system/status` 暴露 `latest_detection` 字段；
    - 本接口只是从控制系统 API 读取并转发给前端使用。
    """
    try:
        resp = requests.get(f"{HV_API_BASE}/api/system/status", timeout=1.0)
        if resp.status_code != 200:
            raise HTTPException(status_code=resp.status_code, detail="无法从控制系统获取检测结果")

        data = resp.json()
        detection_block = data.get("detection", {}) if isinstance(data, dict) else {}
        latest = detection_block.get("latest_detection")

        if not latest:
            return {
                "success": False,
                "detection": None,
                "message": "暂无检测结果"
            }

        return {
            "success": True,
            "detection": latest,
            "timestamp": time.time()
        }
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 从控制系统获取检测结果失败: {e}")
        raise HTTPException(status_code=500, detail=f"获取检测结果失败: {str(e)}")


@app.post("/api/image/params")
def update_image_params(req: ImageParamsRequest):
    """更新图像处理参数"""
    global image_params

    try:
        params_dict = req.dict(exclude_unset=True)
        for key, value in params_dict.items():
            if key in image_params:
                image_params[key] = value

        return {
            "success": True,
            "message": "图像参数已更新",
            "params": image_params
        }
    except Exception as e:
        print(f"❌ 更新图像参数失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新图像参数失败: {str(e)}")


@app.get("/api/image/params")
def get_image_params():
    """获取当前图像处理参数"""
    return {
        "success": True,
        "params": image_params
    }


@app.post("/api/detection/params")
def update_detection_params(req: DetectionParamsRequest):
    """更新检测参数"""
    global detection_params

    try:
        params_dict = req.dict(exclude_unset=True)
        for key, value in params_dict.items():
            if key in detection_params:
                detection_params[key] = value

        # 更新模型置信度阈值
        if 'confidence_threshold' in params_dict and model:
            model.conf = detection_params['confidence_threshold']

        return {
            "success": True,
            "message": "检测参数已更新",
            "params": detection_params
        }
    except Exception as e:
        print(f"❌ 更新检测参数失败: {e}")
        raise HTTPException(status_code=500, detail=f"更新检测参数失败: {str(e)}")


@app.get("/api/detection/params")
def get_detection_params():
    """获取当前检测参数"""
    return {
        "success": True,
        "params": detection_params
    }


@app.post("/api/control/connect")
def connect_control_system():
    """连接到控制系统"""
    try:
        success = connect_to_control_system(silent=False)
        return {
            "success": success,
            "message": "连接成功" if success else f"连接失败：控制系统可能未启动（{control_system_host}:{control_system_port}）",
            "host": control_system_host,
            "port": control_system_port,
            "note": "检测系统可以独立运行，即使控制系统未连接也能正常工作"
        }
    except Exception as e:
        print(f"⚠️ 连接控制系统失败: {e}")
        return {
            "success": False,
            "message": f"连接失败: {str(e)}",
            "host": control_system_host,
            "port": control_system_port,
            "note": "检测系统可以独立运行，即使控制系统未连接也能正常工作"
        }


@app.get("/api/control/status")
def get_control_status():
    """获取控制系统连接状态"""
    return {
        "success": True,
        "connected": control_sock is not None,
        "host": control_system_host,
        "port": control_system_port
    }


# ========== 新增：检测状态接口（不修改已有接口，仅新增）==========
@app.get("/api/detection/status")
def detection_status():
    """返回检测状态：是否运行、当前FPS、最近处理时间。"""
    return {
        "success": True,
        "running": _simplified_thread is not None and _simplified_thread.is_alive(),
        "frames_received": _stream_frames_received,
        "fps": float(_stream_fps_ema),
        "last_frame_time": _stream_last_frame_ts,
        "timestamp": time.time()
    }


# ========== 启动 ==========

if __name__ == "__main__":
    print("=" * 60)
    print("检测系统 API 服务器（摄像头）")
    print("接口地址: http://localhost:8001")
    print("文档地址: http://localhost:8001/docs")
    print("视频流地址: http://localhost:8001/api/video/stream")
    print("=" * 60)
    print("⚠️  注意：请确保：")
    print("   1. 摄像头已连接")
    print("   2. YOLO模型文件路径正确")
    print("   3. 控制系统API服务器在运行（端口8000）")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8001)
