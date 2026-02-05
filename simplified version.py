# 就这个管用
import cv2
import torch
import numpy as np
from ultralytics import YOLO
import time
import os
from datetime import datetime
import socket
import json

# 摄像头编号
camera_no = 1

# 图像调整参数
bar_brightness = 256
bar_contrast = 0
bar_sharpness = 0
bar_gamma = 65
bar_denoise = 0
bar_denoise_param1 = 5
bar_denoise_param2 = 10
bar_hist_eq = 0
bar_clahe_clip = 20
bar_clahe_grid = 8
bar_edge = 0
bar_threshold = 0
bar_thresh_value = 127
target_fps = 30
save_count = 0
save_dir = "不同针头/15ml的流量-21g-无水乙醇-5cm-1218下午测试/25g"
auto_save_enabled = False
auto_save_interval = 0.1
last_save_time = time.time()
bar_noise_removal = 0
bar_noise_kernel = 3
bar_noise_iter = 1
bar_noise_min_area = 50
max_quality_mode = False

# 通信配置
CONTROL_SYSTEM_HOST = 'localhost'
CONTROL_SYSTEM_PORT = 12345
sock = None

""""
#这个是老的
def connect_to_control_system():
    #连接到控制系统 
    global sock
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((CONTROL_SYSTEM_HOST, CONTROL_SYSTEM_PORT))
        print(f"成功连接到控制系统: {CONTROL_SYSTEM_HOST}:{CONTROL_SYSTEM_PORT}")
        return True
    except Exception as e:
        print(f"连接控制系统失败: {e}")
        return False
        #下面的是新的
"""""


def connect_to_control_system():
    """连接到控制系统"""
    global sock
    try:
        # 先关闭现有连接（如果有）
        if sock is not None:
            try:
                sock.close()
            except:
                pass

        # 创建新的socket连接
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        # 设置超时，避免长时间阻塞
        sock.settimeout(5.0)

        sock.connect((CONTROL_SYSTEM_HOST, CONTROL_SYSTEM_PORT))

        # 设置发送/接收超时
        sock.settimeout(2.0)

        print(f"成功连接到控制系统: {CONTROL_SYSTEM_HOST}:{CONTROL_SYSTEM_PORT}")
        return True
    except Exception as e:
        print(f"连接控制系统失败: {e}")
        # 确保失败时 sock 为 None
        sock = None
        return False


def send_detection_result(detection_data):
    """发送检测结果到控制系统"""
    global sock
    try:
        if sock is None:
            if not connect_to_control_system():
                return False

        # 将检测数据转换为JSON格式
        message = json.dumps(detection_data)
        sock.send((message + '\n').encode())
        return True
    except Exception as e:
        print(f"发送检测结果失败: {e}")
        sock = None
        return False


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
    if bar_denoise == 0:
        return img
    if bar_denoise == 1:
        kernel_size = max(3, bar_denoise_param1 * 2 + 1)
        return cv2.GaussianBlur(img, (kernel_size, kernel_size), max(1, bar_denoise_param2))
    if bar_denoise == 2:
        kernel_size = max(3, bar_denoise_param1 * 2 + 1)
        return cv2.medianBlur(img, kernel_size)
    if bar_denoise == 3:
        d = max(1, bar_denoise_param1)
        sigma_color = max(1, bar_denoise_param2)
        return cv2.bilateralFilter(img, d, sigma_color, sigma_color)
    if bar_denoise == 4:
        h = max(1, bar_denoise_param1)
        template_size = max(3, bar_denoise_param2)
        search_size = min(21, template_size * 3)
        return cv2.fastNlMeansDenoising(img, None, h, template_size, search_size)
    return img


def apply_hist_equalization(img):
    """应用直方图均衡化"""
    if bar_hist_eq == 0:
        return img
    if bar_hist_eq == 1:
        return cv2.equalizeHist(img)
    if bar_hist_eq == 2:
        clip_limit = bar_clahe_clip / 100.0
        grid_size = max(4, bar_clahe_grid)
        if max_quality_mode:
            grid_size = max(8, grid_size)
        clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(grid_size, grid_size))
        return clahe.apply(img)
    return img


def apply_brightness_contrast_gamma(img):
    """应用亮度、对比度和伽马校正"""
    adj_brightness = (bar_brightness - 256) / 2.0
    adj_contrast = bar_contrast / 200.0 + 1.0
    adj_gamma = max(bar_gamma / 100.0, 0.01)

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
    if bar_sharpness > 0:
        adj_sharpness = bar_sharpness / 200.0
        if max_quality_mode:
            kernel = np.array([[-1, -1, -1, -1, -1],
                               [-1, 2, 2, 2, -1],
                               [-1, 2, 8 + adj_sharpness, 2, -1],
                               [-1, 2, 2, 2, -1],
                               [-1, -1, -1, -1, -1]]) / 8.0
        else:
            kernel = np.array([[-1, -1, -1],
                               [-1, 9 + adj_sharpness, -1],
                               [-1, -1, -1]])
        img = cv2.filter2D(img, -1, kernel)

    if bar_edge > 0:
        adj_edge = bar_edge / 200.0
        laplacian = cv2.Laplacian(img, cv2.CV_16S, ksize=5)
        img = cv2.convertScaleAbs(img + adj_edge * laplacian)

    return img


def apply_threshold(img):
    """应用阈值处理"""
    if bar_threshold == 0:
        return img
    if bar_threshold == 1:
        _, thresh = cv2.threshold(img, bar_thresh_value, 255, cv2.THRESH_BINARY)
        return thresh
    if bar_threshold == 2:
        block_size = max(3, bar_denoise_param1 * 2 + 1)
        return cv2.adaptiveThreshold(
            img, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY, block_size, max(1, bar_denoise_param2)
        )
    if bar_threshold == 3:
        _, thresh = cv2.threshold(img, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh
    return img


def apply_noise_removal(img):
    """应用噪点去除"""
    if bar_noise_removal == 0:
        return img

    if img.dtype != np.uint8:
        img = img.astype(np.uint8)

    kernel_size = max(1, bar_noise_kernel)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (kernel_size, kernel_size))

    if bar_noise_removal == 1:
        cleaned = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=bar_noise_iter)
    elif bar_noise_removal == 2:
        cleaned = cv2.morphologyEx(img, cv2.MORPH_CLOSE, kernel, iterations=bar_noise_iter)
    elif bar_noise_removal == 3:
        cleaned = cv2.morphologyEx(img, cv2.MORPH_OPEN, kernel, iterations=bar_noise_iter)
        cleaned = cv2.morphologyEx(cleaned, cv2.MORPH_CLOSE, kernel, iterations=bar_noise_iter)
    elif bar_noise_removal == 4:
        contours, _ = cv2.findContours(img, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        mask = np.zeros_like(img)
        min_area = max(1, bar_noise_min_area)
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area >= min_area:
                cv2.drawContours(mask, [cnt], -1, 255, -1)
        cleaned = mask

    return cleaned


def process_detection_results(results, model):
    """处理检测结果并发送到控制系统"""
    if results[0].boxes is not None and len(results[0].boxes) > 0:
        boxes = results[0].boxes.xyxy.cpu().numpy()
        confidences = results[0].boxes.conf.cpu().numpy()
        class_ids = results[0].boxes.cls.cpu().numpy().astype(int)

        # 获取最高置信度的检测结果
        max_conf_idx = np.argmax(confidences)
        best_class_id = class_ids[max_conf_idx]
        best_confidence = confidences[max_conf_idx]
        best_class_name = model.names[best_class_id]

        # 构建检测数据
        detection_data = {
            'timestamp': time.time(),
            'detected_mode': best_class_name,
            'confidence': float(best_confidence),
            'all_detections': []
        }

        # 添加所有检测结果
        for box, conf, cls_id in zip(boxes, confidences, class_ids):
            detection_data['all_detections'].append({
                'class_name': model.names[cls_id],
                'confidence': float(conf),
                'bbox': box.tolist()
            })

        # 发送到控制系统
        if send_detection_result(detection_data):
            print(f"检测结果已发送: {best_class_name} (置信度: {best_confidence:.2f})")
        else:
            print(f"检测结果发送失败: {best_class_name}")

        return best_class_name, best_confidence
    else:
        # 没有检测到任何目标
        detection_data = {
            'timestamp': time.time(),
            'detected_mode': 'none',
            'confidence': 0.0,
            'all_detections': []
        }
        send_detection_result(detection_data)
        return None, 0.0

def save_image(adjusted, auto=False):
    """只保存纯净的调整后图像（不带任何文字）"""
    global save_count
    save_count += 1

    # 确保保存目录存在
    if not os.path.exists(save_dir):
        os.makedirs(save_dir)

    # 生成带时间戳的文件名
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")[:-3]  # 精确到毫秒
    prefix = "auto" if auto else "manual"
    filename = os.path.join(save_dir, f"{prefix}_adjusted_{timestamp}.jpg")

    # 保存纯净图像 - 使用最高质量JPEG压缩
    cv2.imwrite(filename, adjusted, [int(cv2.IMWRITE_JPEG_QUALITY), 100])

    print(f"已保存纯净图像: {filename}")


def main():
    global bar_brightness, bar_contrast, bar_sharpness, bar_gamma
    global bar_denoise, bar_denoise_param1, bar_denoise_param2
    global bar_hist_eq, bar_clahe_clip, bar_clahe_grid
    global bar_edge, bar_threshold, bar_thresh_value, target_fps
    global bar_noise_removal, bar_noise_kernel, bar_noise_iter, bar_noise_min_area
    global auto_save_enabled, auto_save_interval, last_save_time, max_quality_mode

    # 连接到控制系统
    print("正在连接到控制系统...")
    connect_to_control_system()

    # 准备YOLOv8模型
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    print(f"使用设备: {device}")

    # 加载训练好的模型
    model = YOLO(
        r'D:\pycharmdededework\yolov11v12v13\eight\runs\V11train\twowan\wan_yolov11n.yaml2\weights\best.pt').to(device)
    model.conf = 0.5

    # 设置USB摄像头
    cap = cv2.VideoCapture(camera_no, cv2.CAP_DSHOW)
    if not cap.isOpened():
        print("无法打开摄像头，尝试其他方式...")
        for i in range(0, 3):
            cap = cv2.VideoCapture(i, cv2.CAP_DSHOW)
            if cap.isOpened():
                print(f"成功打开索引 {i} 的摄像头")
                break
        if not cap.isOpened():
            raise IOError("无法打开任何USB摄像头")

    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

    actual_width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    actual_height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
    print(f"摄像头分辨率: {actual_width}x{actual_height}")

    # 创建调整窗口
    cv2.namedWindow("Basic Adjustment", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Advanced Adjustment", cv2.WINDOW_NORMAL)
    cv2.namedWindow("Noise Removal", cv2.WINDOW_NORMAL)

    cv2.resizeWindow("Basic Adjustment", 600, 300)
    cv2.resizeWindow("Advanced Adjustment", 600, 350)
    cv2.resizeWindow("Noise Removal", 600, 250)

    # 创建滑动条
    cv2.createTrackbar("Brightness", "Basic Adjustment", bar_brightness, 512, lambda x: None)
    cv2.createTrackbar("Contrast", "Basic Adjustment", bar_contrast, 300, lambda x: None)
    cv2.createTrackbar("Sharpness", "Basic Adjustment", bar_sharpness, 200, lambda x: None)
    cv2.createTrackbar("Gamma", "Basic Adjustment", bar_gamma, 300, lambda x: None)
    cv2.createTrackbar("Target FPS", "Basic Adjustment", target_fps, 120, lambda x: None)

    cv2.createTrackbar("Denoise Method", "Advanced Adjustment", bar_denoise, 4, lambda x: None)
    cv2.createTrackbar("Denoise Param1", "Advanced Adjustment", bar_denoise_param1, 20, lambda x: None)
    cv2.createTrackbar("Denoise Param2", "Advanced Adjustment", bar_denoise_param2, 50, lambda x: None)
    cv2.createTrackbar("Hist Equalize", "Advanced Adjustment", bar_hist_eq, 2, lambda x: None)
    cv2.createTrackbar("CLAHE Clip", "Advanced Adjustment", bar_clahe_clip, 100, lambda x: None)
    cv2.createTrackbar("CLAHE Grid", "Advanced Adjustment", bar_clahe_grid, 16, lambda x: None)
    cv2.createTrackbar("Edge Enhance", "Advanced Adjustment", bar_edge, 200, lambda x: None)
    cv2.createTrackbar("Threshold", "Advanced Adjustment", bar_threshold, 3, lambda x: None)

    cv2.createTrackbar("Noise Removal", "Noise Removal", bar_noise_removal, 4, lambda x: None)
    cv2.createTrackbar("Kernel Size", "Noise Removal", bar_noise_kernel, 15, lambda x: None)
    cv2.createTrackbar("Iterations", "Noise Removal", bar_noise_iter, 5, lambda x: None)
    cv2.createTrackbar("Min Area", "Noise Removal", bar_noise_min_area, 200, lambda x: None)

    # 实时推理循环
    prev_time = 0
    last_frame_time = time.time()
    print("开始实时目标检测 (按 'q' 退出)...")
    print("按 's' 保存当前帧")
    print("按 'd' 手动发送检测结果")

    clean_adjusted_frame = None

    while True:
        target_fps = cv2.getTrackbarPos("Target FPS", "Basic Adjustment")

        if target_fps == 0:
            key = cv2.waitKey(100)
            if key & 0xFF == ord('q'):
                break
            elif key & 0xFF == ord('s'):
                if clean_adjusted_frame is not None:
                    save_image(clean_adjusted_frame, auto=False)
            elif key & 0xFF == ord('d'):
                # 手动发送检测结果
                if clean_adjusted_frame is not None:
                    frame_rgb = cv2.cvtColor(clean_adjusted_frame, cv2.COLOR_BGR2RGB)
                    results = model(frame_rgb, verbose=False, imgsz=640)
                    process_detection_results(results, model)
            continue

        target_frame_time = 1.0 / target_fps
        current_time = time.time()
        elapsed = current_time - last_frame_time
        if elapsed < target_frame_time:
            time.sleep(max(0, target_frame_time - elapsed))
        last_frame_time = time.time()

        ret, frame = cap.read()
        if not ret:
            print("捕获帧失败")
            break

        if frame.size == 0 or frame.shape[0] == 0 or frame.shape[1] == 0:
            print("图像尺寸无效，跳过")
            continue

        # 更新参数
        bar_brightness = cv2.getTrackbarPos("Brightness", "Basic Adjustment")
        bar_contrast = cv2.getTrackbarPos("Contrast", "Basic Adjustment")
        bar_sharpness = cv2.getTrackbarPos("Sharpness", "Basic Adjustment")
        bar_gamma = max(1, cv2.getTrackbarPos("Gamma", "Basic Adjustment"))
        bar_denoise = cv2.getTrackbarPos("Denoise Method", "Advanced Adjustment")
#        bar_denoise_param1 = max(1, cv2.getTrackbarPos("Denoise Param1", "Advanced Adjustment"))
#        bar_denoise_param2 = max(1, cv2.getTrackbarPos("Denoise Param2", "Advanced Adjustment"))
#        bar_hist_eq = cv2.getTrackbarPos("Hist Equalize", "Advanced Adjustment")
        bar_clahe_clip = max(1, cv2.getTrackbarPos("CLAHE Clip", "Advanced Adjustment"))
        bar_clahe_grid = max(4, cv2.getTrackbarPos("CLAHE Grid", "Advanced Adjustment"))
        bar_edge = cv2.getTrackbarPos("Edge Enhance", "Advanced Adjustment")
        bar_threshold = cv2.getTrackbarPos("Threshold", "Advanced Adjustment")
        bar_noise_removal = cv2.getTrackbarPos("Noise Removal", "Noise Removal")
        bar_noise_kernel = max(1, cv2.getTrackbarPos("Kernel Size", "Noise Removal"))
        bar_noise_iter = max(1, cv2.getTrackbarPos("Iterations", "Noise Removal"))
        bar_noise_min_area = max(1, cv2.getTrackbarPos("Min Area", "Noise Removal"))

        # 应用图像调整
        clean_adjusted_frame = apply_adjustment(frame)
        frame_rgb = cv2.cvtColor(clean_adjusted_frame, cv2.COLOR_BGR2RGB)

        # 执行推理
        try:
            if target_fps <= 5:
                results = model(frame_rgb, verbose=False, imgsz=640, conf=0.3)
            else:
                results = model(frame_rgb, verbose=False, imgsz=640)
        except Exception as e:
            print(f"推理错误: {e}")
            continue

        # 处理检测结果并发送到控制系统
        detected_mode, confidence = process_detection_results(results, model)

        # 创建带注释的帧用于显示
        annotated_frame = clean_adjusted_frame.copy()

        # 绘制检测结果
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

        # 计算和显示FPS
        current_time = time.time()
        fps = 1 / (current_time - prev_time) if current_time != prev_time else 0
        prev_time = current_time

        fps_info = f"FPS: {fps:.1f} (Target: {target_fps})"
        cv2.putText(annotated_frame, fps_info, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

        # 显示检测结果
        if detected_mode:
            detection_info = f"Detected: {detected_mode} ({confidence:.2f})"
            cv2.putText(annotated_frame, detection_info, (10, 60),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)

        # 显示连接状态
        connection_status = "Connected" if sock else "Disconnected"
        color = (0, 255, 0) if sock else (0, 0, 255)
        cv2.putText(annotated_frame, f"Control: {connection_status}", (10, 90),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)

        # 显示窗口
        cv2.imshow("Adjusted Image (with annotations)", annotated_frame)

        # 退出条件
        key = cv2.waitKey(1)
        if key & 0xFF == ord('q'):
            break
        elif key & 0xFF == ord('s'):
            if clean_adjusted_frame is not None:
                save_image(clean_adjusted_frame, auto=False)
        elif key & 0xFF == ord('d'):
            # 手动发送检测结果
            frame_rgb = cv2.cvtColor(clean_adjusted_frame, cv2.COLOR_BGR2RGB)
            results = model(frame_rgb, verbose=False, imgsz=640)
            process_detection_results(results, model)

    # 释放资源
    cap.release()
    cv2.destroyAllWindows()
    if sock:
        sock.close()
    print("程序退出")


if __name__ == "__main__":
    main()
