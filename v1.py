"""

"""

import socket
import json
import threading
import time
import numpy as np
from collections import defaultdict, deque
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
from datetime import datetime
import traceback
# 兼容pymodbus 2.x和3.x版本导入，支持模拟模式
try:
    # pymodbus 3.x版本
    from pymodbus.client import ModbusSerialClient
    from pymodbus.exceptions import ModbusException, ConnectionException
    PYMODBUS_AVAILABLE = True
    print("pymodbus模块已加载")
except ImportError:
    try:
        # pymodbus 2.x版本
        from pymodbus.client.sync import ModbusSerialClient
        from pymodbus.exceptions import ModbusException, ConnectionException
        PYMODBUS_AVAILABLE = True
        print("pymodbus 2.x版本模块已加载")
    except ImportError:
        # pymodbus未安装，创建模拟类
        PYMODBUS_AVAILABLE = False
        print("警告: pymodbus模块未安装，使用模拟模式")

        class MockModbusSerialClient:
            def __init__(self, method='rtu', port='COM1', baudrate=9600, parity='N',
                         stopbits=1, bytesize=8, timeout=1):
                self.method = method
                self.port = port
                self.baudrate = baudrate
                self.parity = parity
                self.stopbits = stopbits
                self.bytesize = bytesize
                self.timeout = timeout
                self.connected = False
                print(f"模拟ModbusSerialClient创建: port={port}")

            def connect(self):
                self.connected = True
                print("模拟Modbus连接成功")
                return True

            def close(self):
                self.connected = False
                print("模拟Modbus连接关闭")

            def read_input_registers(self, address=0, count=1, unit=1):
                class MockResponse:
                    def __init__(self):
                        self.registers = [0] * count
                        self.isError = lambda: False
                return MockResponse()

            def write_register(self, address=0, value=0, unit=1):
                class MockResponse:
                    def __init__(self):
                        self.isError = lambda: False
                return MockResponse()

            def write_coil(self, address=0, value=False, unit=1):
                class MockResponse:
                    def __init__(self):
                        self.isError = lambda: False
                return MockResponse()

            def read_discrete_inputs(self, address=0, count=8, unit=1):
                class MockResponse:
                    def __init__(self):
                        self.bits = [False] * count
                        self.isError = lambda: False
                return MockResponse()

        # 创建模拟类
        ModbusSerialClient = MockModbusSerialClient

        # 创建模拟异常类
        class ModbusException(Exception):
            pass

        class ConnectionException(Exception):
            pass


# ==================== 高压电源控制器 ====================
class RobustTCM6000iController:
    def __init__(self, port='COM5', baudrate=9600, parity='N', stopbits=1, bytesize=8, timeout=1, slave_id=1,
                 rated_voltage=30000):
        self.port = port
        self.client = None
        self.slave_id = slave_id
        self.rated_voltage = rated_voltage
        self.rated_current = 1.0

        # 连接参数
        self.baudrate = baudrate
        self.parity = parity
        self.stopbits = stopbits
        self.bytesize = bytesize
        self.timeout = timeout

        # 重连参数
        self.keep_alive_active = False
        self.keep_alive_thread = None
        self.reconnect_thread = None
        self.reconnect_active = False
        self.max_reconnect_attempts = 10
        self.reconnect_delay = 1  # 重连延迟（秒）

        # 状态变量
        self.current_voltage = 0
        self.current_current = 0
        self.control_acquired = False
        self.voltage_lock = threading.Lock()
        self.status_history = []

        # 连接状态监控
        self.connection_lost = False
        self.last_successful_command = 0
        self.command_timeout = 1.0  # 命令超时时间（秒），必须小于2秒

        # 初始化Modbus客户端
        self._init_client()

    def _init_client(self):
        """初始化Modbus客户端"""
        try:
            self.client = ModbusSerialClient(
                method='rtu',
                port=self.port,
                baudrate=self.baudrate,
                parity=self.parity,
                stopbits=self.stopbits,
                bytesize=self.bytesize,
                timeout=self.timeout
            )
            print(f"Modbus客户端已初始化 (端口: {self.port})")
            return True
        except Exception as e:
            print(f"Modbus客户端初始化失败: {e}")
            return False

    def connect(self):
        """连接到高压电源"""
        try:
            if not self.client:
                if not self._init_client():
                    return False

            if self.client.connect():
                print(f"已连接到高压电源 {self.port}")
                self._start_connection_monitoring()
                return True
            else:
                print(f"连接失败 (端口: {self.port})")
                return False
        except Exception as e:
            print(f"连接过程中发生错误: {e}")
            return False

    def _start_connection_monitoring(self):
        """启动连接监控"""
        self.keep_alive_active = True
        self.keep_alive_thread = threading.Thread(target=self._keep_alive_worker, name="KeepAliveThread")
        self.keep_alive_thread.daemon = True
        self.keep_alive_thread.start()

        # 启动重连线程
        self.reconnect_active = True
        self.reconnect_thread = threading.Thread(target=self._reconnect_worker, name="ReconnectThread")
        self.reconnect_thread.daemon = True
        self.reconnect_thread.start()

        print("连接监控已启动")

    def _keep_alive_worker(self):
        """保持连接的工作线程 - 定期检查连接状态"""
        check_interval = 1.0  # 每秒检查一次

        while self.keep_alive_active:
            try:
                # 检查最后成功命令的时间
                current_time = time.time()
                if current_time - self.last_successful_command > self.command_timeout:
                    print(f"命令超时 ({current_time - self.last_successful_command:.1f}秒)，检查连接...")
                    self._check_connection()

                time.sleep(check_interval)
            except Exception as e:
                print(f"心跳线程错误: {e}")
                time.sleep(1)

    def _check_connection(self):
        """检查连接状态"""
        try:
            # 尝试读取一个寄存器来验证连接
            response = self.client.read_input_registers(address=0, count=1, unit=self.slave_id)
            if response.isError():
                print("连接检查失败 (Modbus错误)")
                self.connection_lost = True
            else:
                self.last_successful_command = time.time()
                if self.connection_lost:
                    print("连接已恢复")
                    self.connection_lost = False
        except Exception as e:
            print(f"连接检查异常: {e}")
            self.connection_lost = True

    def _reconnect_worker(self):
        """重连工作线程"""
        while self.reconnect_active:
            if self.connection_lost:
                print("连接断开，尝试重新连接...")
                self._reconnect()

            time.sleep(2)  # 每2秒检查一次

    def _reconnect(self):
        """重新连接高压电源"""
        attempts = 0

        while attempts < self.max_reconnect_attempts and self.connection_lost:
            attempts += 1
            print(f"尝试重新连接 ({attempts}/{self.max_reconnect_attempts})...")

            try:
                # 关闭当前连接
                if self.client:
                    self.client.close()

                # 重新初始化客户端
                time.sleep(0.5)
                if not self._init_client():
                    continue

                # 尝试连接
                if self.client.connect():
                    print("重新连接成功")
                    self.connection_lost = False
                    self.last_successful_command = time.time()
                    return True

            except Exception as e:
                print(f"重新连接失败: {e}")

            # 等待后重试
            if attempts < self.max_reconnect_attempts:
                time.sleep(self.reconnect_delay)

        print(f"重新连接失败，达到最大尝试次数 ({self.max_reconnect_attempts})")
        return False

    def disconnect(self):
        """断开连接"""
        self.keep_alive_active = False
        self.reconnect_active = False

        if self.keep_alive_thread:
            self.keep_alive_thread.join(timeout=2)

        if self.reconnect_thread:
            self.reconnect_thread.join(timeout=2)

        self._safe_shutdown()

        if self.client:
            self.client.close()

        print("连接已关闭")

    def _safe_shutdown(self):
        """安全关闭高压"""
        try:
            if self.client:
                self.client.write_coil(address=0, value=False, unit=self.slave_id)
                self.client.write_coil(address=10, value=False, unit=self.slave_id)
                time.sleep(0.5)
        except:
            pass

    def _read_status_silent(self):
        """静默读取状态"""
        try:
            response = self.client.read_discrete_inputs(address=0, count=8, unit=self.slave_id)
            if not response.isError():
                bits = response.bits
                if len(bits) > 4:
                    self.control_acquired = bits[4]
                return bits
        except:
            pass
        return None

    def _send_command_with_retry(self, command_func, max_retries=3, command_name=""):
        """带重试的命令发送"""
        for attempt in range(max_retries):
            try:
                # 检查连接状态
                if self.connection_lost:
                    print(f"连接断开，尝试重新发送命令 '{command_name}' ({attempt + 1}/{max_retries})...")
                    if not self._reconnect():
                        continue

                # 执行命令
                result = command_func()

                # 更新最后成功命令时间
                self.last_successful_command = time.time()

                return result

            except ConnectionException as e:
                print(f"连接异常 ({command_name}): {e}")
                self.connection_lost = True

            except ModbusException as e:
                print(f"Modbus错误 ({command_name}): {e}")

            except Exception as e:
                print(f"未知错误 ({command_name}): {e}")

            # 重试前等待
            if attempt < max_retries - 1:
                time.sleep(0.5)

        print(f"命令 '{command_name}' 失败，达到最大重试次数")
        return False

    def ensure_control(self, max_retries=3):
        """获取控制权（带重试）"""

        def _acquire_control():
            response = self.client.write_coil(address=10, value=True, unit=self.slave_id)
            if response.isError():
                return False

            time.sleep(0.5)
            status_bits = self._read_status_silent()
            if status_bits and len(status_bits) > 4:
                if status_bits[4]:
                    self.control_acquired = True
                    return True

            return False

        return self._send_command_with_retry(
            _acquire_control,
            max_retries,
            "获取控制权"
        )

    def smart_set_voltage(self, voltage, current=1.0, auto_enable_hv=True):
        """智能设置电压（带重试）"""
        print(f"\n智能设置电压: {voltage}V")

        with self.voltage_lock:
            # 确保控制权
            if not self.ensure_control():
                return False

            # 设置电流
            if not self._set_current_internal(current):
                return False

            # 设置电压
            if not self._set_voltage_internal(voltage):
                return False

            # 开启高压
            if auto_enable_hv:
                if not self._enable_high_voltage_internal():
                    return False

            print(f"智能设置完成: 电压{voltage}V, 电流{current}mA")
            if auto_enable_hv:
                print("高压已自动开启")

            return True

    def _set_voltage_internal(self, voltage):
        """内部设置电压（带重试）"""
        register_value = int((voltage / self.rated_voltage) * 4095)
        register_value = max(0, min(4095, register_value))

        def _set_voltage():
            response = self.client.write_register(address=0, value=register_value, unit=self.slave_id)
            if response.isError():
                return False

            self.current_voltage = voltage
            print(f"电压设置: {voltage}V (寄存器值: {register_value:04X}h)")

            # 读取输出验证
            time.sleep(0.3)
            output = self.read_output_silent()
            if output:
                print(f"   当前输出: {output['voltage']:.1f}V")

            return True

        return self._send_command_with_retry(
            _set_voltage,
            3,
            "设置电压"
        )

    def _set_current_internal(self, current):
        """内部设置电流（带重试）"""
        register_value = int((current / self.rated_current) * 4095)
        register_value = max(0, min(4095, register_value))

        def _set_current():
            response = self.client.write_register(address=1, value=register_value, unit=self.slave_id)
            if response.isError():
                return False

            self.current_current = current
            print(f"电流设置: {current}mA (寄存器值: {register_value:04X}h)")
            return True

        return self._send_command_with_retry(
            _set_current,
            3,
            "设置电流"
        )

    def _enable_high_voltage_internal(self, max_retries=3):
        """内部开启高压（带重试）"""
        for attempt in range(max_retries):
            try:
                print(f" 开启高压 ({attempt + 1}/{max_retries})...")

                response = self.client.write_coil(address=0, value=True, unit=self.slave_id)
                if response.isError():
                    print("高压开启命令发送失败")
                    continue

                print("高压开启命令已发送")
                time.sleep(1)

                status_bits = self._read_status_silent()
                if status_bits and len(status_bits) > 0:
                    if status_bits[0]:
                        print("高压已确认开启")
                        return True
                    else:
                        print("高压状态未更新，重试...")
                else:
                    print("状态读取失败，重试...")

            except ModbusException as e:
                print(f"开启高压时发生错误: {e}")

            time.sleep(0.5)

        print("高压开启失败")
        return False

    def enable_high_voltage(self, max_retries=3):
        """开启高压电源（公共接口）"""
        return self._enable_high_voltage_internal(max_retries)

    def set_voltage_kv(self, voltage_kv, max_retries=3):
        """设置电压（千伏单位，带重试）"""
        voltage_v = voltage_kv * 1000

        def _set_voltage_kv():
            return self.smart_set_voltage(voltage_v, auto_enable_hv=True)

        return self._send_command_with_retry(
            _set_voltage_kv,
            max_retries,
            f"设置电压{voltage_kv}kV"
        )

    def read_output_silent(self):
        """静默读取输出"""
        try:
            response = self.client.read_input_registers(address=0, count=2, unit=self.slave_id)
            if response.isError():
                return None

            registers = response.registers
            voltage_value = (registers[0] / 4095) * self.rated_voltage
            current_value = (registers[1] / 4095) * self.rated_current

            return {"voltage": voltage_value, "current": current_value}
        except:
            return None

    def get_connection_status(self):
        """获取连接状态"""
        return {
            "connected": not self.connection_lost,
            "control_acquired": self.control_acquired,
            "last_successful_command": self.last_successful_command,
            "current_voltage": self.current_voltage,
            "current_current": self.current_current
        }

    def disable_high_voltage(self, max_retries=3):
        """关闭高压电源"""
        for attempt in range(max_retries):
            try:
                print(f" 关闭高压 ({attempt + 1}/{max_retries})...")

                response = self.client.write_coil(address=0, value=False, unit=self.slave_id)
                if response.isError():
                    print("高压关闭命令发送失败")
                    continue

                print("高压关闭命令已发送")
                time.sleep(0.5)

                # 验证高压是否已关闭
                status_bits = self._read_status_silent()
                if status_bits and len(status_bits) > 0:
                    if not status_bits[0]:
                        print("高压已确认关闭")
                        return True
                    else:
                        print("高压状态未更新，重试...")
                else:
                    print("状态读取失败，重试...")

            except ModbusException as e:
                print(f"关闭高压时发生错误: {e}")

            time.sleep(0.5)

        print("高压关闭失败")
        return False

# ==================== 增强的模糊PID控制器 ====================
class EnhancedFuzzyPIDController:
    """增强版模糊PID控制器
    基于三项指标：差值、变化率、漂移速率
    """
    def __init__(self):
        # 初始PID参数（符合新需求：P=0.3, I=0.2, D=0.1）
        self.kp_base = 0.3  # 基础比例系数（差值0→P=0.3）
        self.ki_base = 0.2  # 基础积分系数
        self.kd_base = 0.1  # 基础微分系数

        self.kp = self.kp_base
        self.ki = self.ki_base
        self.kd = self.kd_base

        # 状态变量
        self.error_integral = 0
        self.last_error = 0
        self.integral_limit = 5.0

        # 模糊控制参数
        self.step_size = 0.15  # 初始步长 (kV)，范围：0.1-1.0kV（符合需求：0.15kV初始）
        self.step_time = 0.3   # 初始步时 (秒)，范围：0.2-4.0秒（符合需求：0.3秒初始）

        # 物理限制
        self.min_step = 0.1
        self.max_step = 1.0
        self.min_step_time = 0.2  # 符合步时约束的最小步时0.2秒（覆盖≥0.15秒等待时间）
        self.max_step_time = 4.0   # 物理规则允许的最大步时4秒

        # 历史记录
        self.error_history = deque(maxlen=10)
        self.voltage_history = deque(maxlen=10)
        self.mode_history = deque(maxlen=10)

        # 边界漂移检测
        self.boundary_drift_rate = 0.0
        self.last_boundary_voltage = None
        self.last_boundary_time = None

        # 隶属函数相关
        self.mode_voltage_ranges = {}  # 模式->{min, max, optimal}
        self.membership_cache = {}  # 缓存隶属度计算

        print("增强模糊PID控制器初始化完成")

    def adapt_step_parameters_enhanced(self, mode_consistent_count, voltage_difference, voltage_change_rate, boundary_drift_rate):
        """增强版自适应调节步长和步时（符合需求规范）
        基于需求：
        1. 检测结果始终为同一模式（无变化）→ 大步长(0.5-1kV)、小步时(0.2-0.3秒)
        2. 检测结果出现模式变化 → 小步长(0.1-0.3kV)、常规步时(0.3秒)或小步长大步时
        3. 第一次遍历规则：初始步长0.1kV，步时0.3秒，连续相同结果调大步长调小步时，结果变化调小步长调大步时
        4. 考虑电压差值、变化率和边界漂移速率
        """
        # 初始化
        new_step = self.step_size
        new_step_time = self.step_time

        # 规则1：连续3次遍历结果为同一模式（符合新需求遍历调整规则）
        # 新需求：连续3次遍历结果为同一模式→步长调至0.8kV、步时调至0.2秒
        if mode_consistent_count >= 3:
            # 步长调至0.8kV
            new_step = 0.8
            # 步时调至0.2秒
            new_step_time = 0.2
            print(f"[规则1] 连续{mode_consistent_count}次相同模式，步长调至0.8kV，步时调至0.2秒")

        # 规则2：检测结果出现变化（符合新需求遍历调整规则）
        # 新需求：结果变化→步长回调至0.2kV、步时调至0.3秒
        elif mode_consistent_count <= 1:
            # 步长回调至0.2kV
            new_step = 0.2
            # 步时调至0.3秒
            new_step_time = 0.3
            print(f"[规则2] 模式变化，步长回调至0.2kV，步时调至0.3秒")

        # 规则3：基于电压差值的调节（符合新需求：差值>0.5kV为差值大）
        if voltage_difference > 0.5:
            # 差值大，采用大步长快速接近
            new_step = min(self.max_step, max(0.5, new_step * 1.3))  # 确保至少0.5kV
            new_step_time = max(self.min_step_time, min(0.3, new_step_time * 0.8))  # 短步时
            print(f"[规则3] 电压差大({voltage_difference:.1f}kV>0.5kV)，大步长短步时: {new_step:.2f}kV, {new_step_time:.2f}s")

        elif voltage_difference <= 0.5:
            # 差值小，采用小步长精细调节
            new_step = max(self.min_step, min(0.2, new_step * 0.8))  # 确保不超过0.2kV
            new_step_time = min(self.max_step_time, max(0.5, new_step_time * 1.2))  # 长步时
            print(f"[规则3] 电压差小({voltage_difference:.1f}kV≤0.5kV)，小步长长步时: {new_step:.2f}kV, {new_step_time:.2f}s")

        # 规则4：基于电压变化率的调节（符合新需求：变化率≥0.1kV/秒为变化率高）
        if voltage_change_rate >= 0.1:
            # 变化率高，接近边界，采用小步长长步时
            new_step = max(self.min_step, min(0.2, new_step * 0.7))  # 小步长
            new_step_time = min(self.max_step_time, max(0.5, new_step_time * 1.2))  # 长步时
            print(f"[规则4] 变化率高({voltage_change_rate:.1f}kV/s≥0.1kV/s)，小步长长步时: {new_step:.2f}kV, {new_step_time:.2f}s")
        else:
            # 变化率低，采用大步长短步时
            new_step = min(self.max_step, max(0.5, new_step * 1.2))  # 大步长
            new_step_time = max(self.min_step_time, min(0.3, new_step_time * 0.8))  # 短步时
            print(f"[规则4] 变化率低({voltage_change_rate:.1f}kV/s<0.1kV/s)，大步长短步时: {new_step:.2f}kV, {new_step_time:.2f}s")

        # 规则5：基于边界漂移速率的调节（符合新需求：漂移速率>0.1kV/秒为快）
        if boundary_drift_rate > 0.1:
            # 漂移速率快，增大微分系数，减小步长，增加步时
            self.kd = min(0.4, self.kd + 0.2)  # D系数+0.2，最大0.4
            new_step = max(self.min_step, new_step - 0.1)  # 步长-0.1kV
            new_step_time = min(self.max_step_time, new_step_time + 0.2)  # 步时+0.2秒
            print(f"[规则5] 边界漂移快({boundary_drift_rate:.2f}kV/s>0.1kV/s)，KD增至{self.kd:.3f}, 步长{new_step:.2f}kV, 步时{new_step_time:.2f}s")
        elif boundary_drift_rate < 0.05:
            # 漂移速率慢，恢复微分系数
            self.kd = max(0.1, self.kd - 0.1)  # 回调
            print(f"[规则5] 边界漂移慢({boundary_drift_rate:.2f}kV/s<0.05kV/s)，KD回调至{self.kd:.3f}")

        # 强制范围限制（确保符合物理规则）
        # 步长范围：0.1-1.0kV
        new_step = max(self.min_step, min(self.max_step, new_step))
        # 步时范围：0.15-4.0秒（第一次遍历规则要求不低于0.15秒）
        new_step_time = max(self.min_step_time, min(self.max_step_time, new_step_time))

        self.step_size = new_step
        self.step_time = new_step_time

        print(f"[步长步时] 最终: {self.step_size:.2f}kV, {self.step_time:.2f}s")
        return self.step_size, self.step_time

    def adapt_pid_parameters(self, error, error_change, boundary_drift_rate, match_rate=None, match_rate_history=None):
        """动态适配PID参数（符合新需求）
        比例(P)系数随差值增大线性增大：差值0→P=0.3；差值1kV→P=1.0
        积分(I)系数：静态误差（连续3次匹配度＜90%）累积时，从0.2线性增至0.5
        微分(D)系数：边界漂移速率＞0.1kV/秒时，从0.1线性增至0.3
        """
        # 1. 比例(P)系数计算：线性关系 P = 0.3 + 0.7 * |error| (|error|≤1kV)
        error_abs = min(abs(error), 1.0)  # 限制误差在1kV以内
        self.kp = 0.3 + 0.7 * error_abs  # 线性映射

        # 2. 积分(I)系数计算：基于匹配度历史（流程6要求）
        # 如果提供了匹配度历史，检查是否连续3次匹配度＜90%
        if match_rate_history is not None and len(match_rate_history) >= 3:
            # 检查最近3次匹配度是否都小于90%
            recent_low_match = all(mr < 0.9 for mr in match_rate_history[-3:])
            if recent_low_match:
                # 连续3次匹配度＜90%，线性增加I系数从0.2到0.5
                # 基于低匹配度持续时间（简化：基于低匹配度次数）
                low_match_count = 0
                for mr in match_rate_history[-10:]:  # 检查最近10次
                    if mr < 0.9:
                        low_match_count += 1
                    else:
                        break

                # 线性映射：低匹配度次数越多，I系数越大，最大0.5
                # 假设最多连续10次低匹配度对应最大I系数0.5
                i_increase = min(0.3, low_match_count * 0.03)  # 每次增加0.03，最大增加0.3
                self.ki = min(0.5, self.ki_base + i_increase)
            else:
                # 匹配度正常，恢复基础值
                self.ki = self.ki_base
        else:
            # 没有匹配度历史或历史不足，保持基础值
            self.ki = self.ki_base

        # 3. 微分(D)系数计算：基于边界漂移速率（流程6要求：最大0.3）
        if boundary_drift_rate > 0.1:
            # 线性增加：边界漂移速率>0.1kV/秒时，从0.1线性增至0.3
            # 假设漂移速率最大1.0kV/秒对应D系数0.3
            drift_factor = min(1.0, boundary_drift_rate)  # 限制最大1.0
            d_increase = drift_factor * 0.2  # 0.1到0.3，增加0.2
            self.kd = min(0.3, self.kd_base + d_increase)  # 最大0.3
        elif boundary_drift_rate < 0.05:
            self.kd = self.kd_base  # 回调到基础值0.1
        else:
            # 保持当前值
            pass

        # 限制范围（符合新需求）
        self.kp = max(0.3, min(1.5, self.kp))  # P范围：0.3-1.5（与需求一致：差值1kV→P=1.0）
        self.ki = max(0.2, min(0.5, self.ki))  # I范围：0.2-0.5（流程6要求）
        self.kd = max(0.1, min(0.3, self.kd))  # D范围：0.1-0.3（流程6要求）

        return self.kp, self.ki, self.kd

    def calculate_adjustment_enhanced(self, target_voltage, current_voltage, mode_error, boundary_drift_rate=0.0):
        """增强版电压调整计算
        考虑边界漂移速率的PID控制
        """
        # 计算误差
        error = target_voltage - current_voltage

        # 记录历史
        self.error_history.append(error)
        self.voltage_history.append(current_voltage)

        # 计算误差变化率
        if len(self.error_history) > 1:
            error_change = error - self.error_history[-2]
        else:
            error_change = 0

        # 计算电压变化率（最近3次）
        if len(self.voltage_history) >= 3:
            voltage_change_rate = abs(self.voltage_history[-1] - self.voltage_history[-3]) / 3
        else:
            voltage_change_rate = 0

        # 动态适配PID参数（传递None作为匹配度信息，因为该方法不知道匹配度）
        kp, ki, kd = self.adapt_pid_parameters(error, error_change, boundary_drift_rate, None, None)

        # 积分项（带限制）
        self.error_integral += error * 0.1
        self.error_integral = max(-self.integral_limit, min(self.integral_limit, self.error_integral))

        # PID计算
        pid_output = (kp * error +
                     ki * self.error_integral +
                     kd * error_change)

        # 模糊调节：考虑模式误差
        if abs(mode_error) > 2.0:
            adjustment = pid_output * 1.3  # 模式误差大，增强调整
        elif abs(mode_error) < 0.5:
            adjustment = pid_output * 0.8  # 模式误差小，减弱调整
        else:
            adjustment = pid_output

        # 限制调整幅度（不超过当前步长）
        adjustment = max(-self.step_size, min(self.step_size, adjustment))

        # 记录最后误差
        self.last_error = error

        print(f"[PID] 误差={error:.3f}kV, KP={kp:.2f}, KI={ki:.3f}, KD={kd:.3f}, 调整={adjustment:.3f}kV")
        return adjustment, error, voltage_change_rate

    def update_boundary_drift(self, boundary_voltage, timestamp):
        """更新边界漂移速率"""
        if self.last_boundary_voltage is not None and self.last_boundary_time is not None:
            voltage_change = boundary_voltage - self.last_boundary_voltage
            time_change = timestamp - self.last_boundary_time

            if time_change > 0:
                self.boundary_drift_rate = abs(voltage_change) / time_change
                print(f"边界漂移速率: {self.boundary_drift_rate:.3f}kV/s")

        self.last_boundary_voltage = boundary_voltage
        self.last_boundary_time = timestamp
        return self.boundary_drift_rate

    def update_mode_voltage_ranges(self, mode_voltage_ranges):
        """更新模式电压范围信息，用于隶属函数计算"""
        self.mode_voltage_ranges = mode_voltage_ranges
        self.membership_cache.clear()  # 清除缓存
        print(f"模糊PID控制器更新模式电压范围: {len(mode_voltage_ranges)}个模式")

    def calculate_membership(self, voltage, mode_name):
        """计算隶属度：电压属于某个模式的程度（匹配度）
        根据需求：隶属度对应该电压范围内该电压的匹配度

        计算规则：
        1. 优先使用实际统计样本数据（如果有）
        2. 否则使用插值：从最优电压点的1.0线性下降到边界的0.0
        3. 边界外：基于距离边界的距离线性衰减到0
        """
        if mode_name not in self.mode_voltage_ranges:
            return 0.0

        info = self.mode_voltage_ranges[mode_name]
        min_v = info['min']
        max_v = info['max']
        optimal = info.get('optimal', (min_v + max_v) / 2)

        # 缓存键
        cache_key = f"{voltage:.2f}_{mode_name}"
        if cache_key in self.membership_cache:
            return self.membership_cache[cache_key]

        # 1. 优先检查是否有该电压点的实际样本数据
        if 'samples' in info and info['samples']:
            # 查找最接近的电压点样本
            samples = info['samples']  # [(voltage, ratio), ...]

            # 首先检查是否有完全匹配的电压点
            for sample_voltage, ratio in samples:
                if abs(sample_voltage - voltage) < 0.001:  # 容差
                    membership = ratio
                    # 缓存结果
                    self.membership_cache[cache_key] = membership
                    return membership

            # 如果没有完全匹配，进行线性插值
            # 按电压排序样本
            sorted_samples = sorted(samples, key=lambda x: x[0])

            if voltage < sorted_samples[0][0]:
                # 电压小于最小样本电压，使用边界外衰减
                pass  # 继续下面的边界外计算
            elif voltage > sorted_samples[-1][0]:
                # 电压大于最大样本电压，使用边界外衰减
                pass  # 继续下面的边界外计算
            else:
                # 在样本范围内，进行线性插值
                for i in range(len(sorted_samples) - 1):
                    v1, r1 = sorted_samples[i]
                    v2, r2 = sorted_samples[i + 1]

                    if v1 <= voltage <= v2:
                        # 线性插值
                        if v2 == v1:  # 避免除零
                            membership = r1
                        else:
                            t = (voltage - v1) / (v2 - v1)
                            membership = r1 + t * (r2 - r1)

                        # 缓存结果
                        self.membership_cache[cache_key] = membership
                        return membership

        # 2. 没有样本数据或边界外，使用数学模型计算
        # 边界外计算
        if voltage < min_v or voltage > max_v:
            # 超出范围，计算边界衰减
            boundary_width = min(0.5, (max_v - min_v) * 0.2)  # 边界宽度为范围宽度的20%，最大0.5kV

            if voltage < min_v:
                distance = min_v - voltage
                if distance > boundary_width:
                    membership = 0.0
                else:
                    membership = 1.0 - (distance / boundary_width)
            else:  # voltage > max_v
                distance = voltage - max_v
                if distance > boundary_width:
                    membership = 0.0
                else:
                    membership = 1.0 - (distance / boundary_width)
        else:
            # 在范围内，但没有样本数据，使用线性插值
            # 从最优点的1.0线性下降到边界的0.0
            range_width = max_v - min_v

            if range_width > 0:
                if voltage <= optimal:
                    # 在最小电压到最优点之间
                    if optimal == min_v:  # 避免除零
                        membership = 1.0
                    else:
                        distance_from_min = optimal - min_v
                        distance_from_optimal = optimal - voltage
                        membership = 1.0 - (distance_from_optimal / distance_from_min)
                else:
                    # 在最优点到最大电压之间
                    if max_v == optimal:  # 避免除零
                        membership = 1.0
                    else:
                        distance_from_max = max_v - optimal
                        distance_from_optimal = voltage - optimal
                        membership = 1.0 - (distance_from_optimal / distance_from_max)
            else:
                # 单点范围
                membership = 1.0 if abs(voltage - optimal) < 0.001 else 0.0

        # 限制在[0, 1]范围内
        membership = max(0.0, min(1.0, membership))

        # 缓存结果
        self.membership_cache[cache_key] = membership
        return membership

    def calculate_mode_match_rate(self, voltage, target_mode, other_modes=None):
        """计算电压对目标模式的匹配率（基于实际统计数据或隶属度）
        根据需求定义：匹配率是在步时内统计，各个模式的监测结果数量在总的监测数量中占的比重

        计算规则：
        1. 优先使用模式电压范围中的样本数据计算实际匹配率
        2. 如果没有样本数据，使用隶属度函数估算
        3. 考虑其他模式的干扰影响
        """
        if target_mode not in self.mode_voltage_ranges:
            return 0.0

        info = self.mode_voltage_ranges[target_mode]

        # 1. 优先使用样本数据计算实际匹配率
        if 'samples' in info and info['samples']:
            # 查找该电压点的实际匹配率
            samples = info['samples']  # [(voltage, ratio), ...]

            # 查找最接近的电压点样本
            closest_sample = None
            min_distance = float('inf')

            for sample_voltage, ratio in samples:
                distance = abs(sample_voltage - voltage)
                if distance < min_distance:
                    min_distance = distance
                    closest_sample = (sample_voltage, ratio)

            # 如果距离很近，使用该样本的匹配率
            if closest_sample and min_distance < 0.01:  # 10V容差
                sample_voltage, ratio = closest_sample
                return ratio

            # 如果没有足够近的样本，进行插值
            # 按电压排序样本
            sorted_samples = sorted(samples, key=lambda x: x[0])

            if voltage < sorted_samples[0][0]:
                # 电压小于最小样本电压，使用最小样本的匹配率
                match_rate = sorted_samples[0][1]
            elif voltage > sorted_samples[-1][0]:
                # 电压大于最大样本电压，使用最大样本的匹配率
                match_rate = sorted_samples[-1][1]
            else:
                # 在样本范围内，进行线性插值
                for i in range(len(sorted_samples) - 1):
                    v1, r1 = sorted_samples[i]
                    v2, r2 = sorted_samples[i + 1]

                    if v1 <= voltage <= v2:
                        if v2 == v1:  # 避免除零
                            match_rate = r1
                        else:
                            t = (voltage - v1) / (v2 - v1)
                            match_rate = r1 + t * (r2 - r1)
                        break
                else:
                    # 不应该执行到这里
                    match_rate = 0.0

            return match_rate

        # 2. 没有样本数据，使用隶属度函数估算
        target_membership = self.calculate_membership(voltage, target_mode)

        if not other_modes:
            # 如果没有提供其他模式，使用所有已知模式（除了目标模式）
            other_modes = [mode for mode in self.mode_voltage_ranges.keys() if mode != target_mode]

        # 计算其他模式的最大隶属度（干扰）
        max_other_membership = 0.0
        for mode in other_modes:
            if mode in self.mode_voltage_ranges:
                other_membership = self.calculate_membership(voltage, mode)
                if other_membership > max_other_membership:
                    max_other_membership = other_membership

        # 匹配率 = 目标模式隶属度 - 其他模式最大隶属度（考虑干扰）
        match_rate = max(0.0, target_membership - max_other_membership * 0.5)

        return match_rate

# ==================== 瞬时误判过滤器 ====================
class TransientErrorFilter:
    """瞬时误判过滤器
    过滤规则：
    1. 采样结果与前3次连续有效结果不一致
    2. 单次采样结果持续时间＜0.1秒
    """
    def __init__(self, debug=False):
        self.valid_history = deque(maxlen=4)  # 保存最近4次有效结果（非瞬时误判）
        self.current_mode = None
        self.mode_start_time = None
        self.min_duration = 0.1  # 最小持续时间阈值
        self.debug = debug  # 调试模式

    def reset(self):
        """重置过滤器状态"""
        self.valid_history.clear()
        self.current_mode = None
        self.mode_start_time = None
        if self.debug:
            print("[过滤器] 状态已重置")

    def filter_detection(self, detection_data):
        """过滤瞬时误判"""
        if not detection_data:
            return None

        detected_mode = detection_data.get('detected_mode')
        confidence = detection_data.get('confidence', 0)
        timestamp = detection_data.get('timestamp', time.time())

        # 无效模式直接返回（只过滤'none'模式，置信度不影响过滤）
        if detected_mode == 'none':
            if self.debug:
                print(f"[过滤器] 无效模式：{detected_mode} (置信度: {confidence:.2f})")
            return None

        if self.debug:
            print(f"[过滤器] 处理检测：{detected_mode} (置信度: {confidence:.2f})")
            print(f"[过滤器] 当前模式：{self.current_mode}，开始时间：{self.mode_start_time}")
            print(f"[过滤器] 当前有效历史：{[h['detected_mode'] for h in self.valid_history] if self.valid_history else '空'}")

        # 检查1：持续时间检查
        # 计算当前模式持续时间（如果是同一模式）
        current_duration = 0
        if detected_mode == self.current_mode and self.mode_start_time:
            current_duration = timestamp - self.mode_start_time
            if current_duration < self.min_duration:
                if self.debug:
                    print(f"[过滤器] 持续时间过短：{detected_mode} ({current_duration:.2f}s < {self.min_duration}s)")
                detection_data['transient_error'] = True
                return detection_data
        # 如果是不同模式，持续时间从0开始（新模式）

        # 检查2：历史一致性检查（只检查有效历史）
        if len(self.valid_history) >= 3:
            # 取最近3次有效结果
            recent_modes = [h['detected_mode'] for h in list(self.valid_history)[-3:] if h]

            if len(recent_modes) >= 3:
                # 检查最近3次有效结果是否一致
                if recent_modes[0] == recent_modes[1] == recent_modes[2]:
                    # 如果最近3次有效结果一致，且本次结果不同，可能为误判
                    if detected_mode != recent_modes[0]:
                        # 但如果是新模式，检查它是否已经持续了足够时间（通过current_duration）
                        # 注意：current_duration对于新模式是0（因为detected_mode != self.current_mode）
                        # 所以我们需要考虑：如果系统刚刚切换到新模式，我们是否应该接受？
                        # 根据需求：新模式需要持续至少min_duration才不被视为瞬时误判
                        if detected_mode == self.current_mode:
                            # 同一模式，已经通过持续时间检查
                            pass
                        else:
                            # 新模式，检查是否应该接受
                            # 这里我们采用保守策略：如果新模式是第一次出现，给与宽容
                            # 但实际上，如果历史中有3次一致的旧模式，新出现不同模式很可能是误判
                            # 除非新模式持续出现
                            if self.debug:
                                print(f"[过滤器] 警告：检测到新模式{detected_mode}，但历史中最近3次为{recent_modes[0]}")
                            # 暂时判定为瞬时误判
                            detection_data['transient_error'] = True
                            return detection_data

        # 所有检查通过，接受此检测结果
        detection_data['transient_error'] = False

        # 更新当前模式和开始时间（如果是新模式）
        if detected_mode != self.current_mode:
            if self.debug:
                print(f"[过滤器] 模式变化：{self.current_mode} -> {detected_mode}")
            self.current_mode = detected_mode
            self.mode_start_time = timestamp
        # 如果是同一模式，开始时间已在之前设置，保持不变

        # 添加到有效历史
        self.valid_history.append(detection_data)
        if self.debug:
            print(f"[过滤器] 接受有效结果：{detected_mode}，有效历史长度：{len(self.valid_history)}")
        return detection_data

# ==================== 控制系统核心 ====================
class EnhancedControlSystemCore:
    """增强版控制系统核心逻辑"""
    def __init__(self, modbus_port='COM5', detection_port=12345):
        self.detection_port = detection_port

        # 高压电源控制器
        self.hv_controller = RobustTCM6000iController(port=modbus_port)

        # 增强模糊PID控制器
        self.fuzzy_pid = EnhancedFuzzyPIDController()

        # 瞬时误判过滤器
        self.error_filter = TransientErrorFilter(debug=False)  # 调试模式关闭，可设为True以调试

        # GUI引用
        self.gui = None

        # 状态变量
        self.running = False
        self.mode_classes = {}  # 从YOLO模型加载的类别字典 {id: name}
        self.mode_classes_received = False
        self.mode_classes_client_address = None  # 发送模式种类的客户端地址
        self.confirmation_sent = False  # 是否已发送确认信息给监测模块
        self.detection_received = False  # 是否已收到监测结果
        self.target_mode = None
        self.current_voltage_kv = 0.0
        self.min_voltage = 0.0
        self.max_voltage = 20.0

        # 遍历状态
        self.exploration_active = False
        self.exploration_completed = False
        self.exploration_round = 1  # 遍历轮次
        self.max_exploration_rounds = 2  # 最大遍历轮次（符合需求：最多重试2次）
        self.explored_voltages = set()  # 记录已探索的电压值，用于跳过重复设置

        # 新需求：控制状态机
        self.control_state = 'idle'  # idle, exploring, waiting_for_target, target_control, stable, dynamic_maintenance, mode_switching
        self.exploration_mode_counts = defaultdict(lambda: defaultdict(int))  # 用于记录探索阶段的模式统计

        # 电压-模式映射（模式-电压范围数据库）
        self.voltage_mode_stats = defaultdict(lambda: defaultdict(int))  # 电压->模式->计数
        # 模式-电压范围数据库（字段：模式名、电压下限、电压上限、最优电压点、历史匹配度曲线）
        self.mode_voltage_ranges = {}  # 模式->{min, max, optimal, samples, total_count}

        # 检测结果处理
        self.latest_detection = None
        self.detection_history = deque(maxlen=200)
        self.detection_lock = threading.Lock()  # 保护检测结果的锁

        # 稳定判断
        self.stable_state = False
        self.best_match_rate = 0.0  # 匹配度第一
        self.best_match_voltage = None  # 最佳匹配电压
        self.stability_check_interval = 5.0  # 5秒稳定判断
        self.last_stability_check = 0

        # 初始优化标志
        self.initial_optimization_done = False  # 目标控制启动时是否已执行初始优化

        # 步骤6 PID模糊控制算法状态
        self.step6_pid_fuzzy_completed = False  # 步骤6（PID模糊控制算法）是否已完成
        self.best_match_recorded = False  # 是否已记录"匹配度第一"
        self.found_target_mode_voltage = None  # 找到目标模式时的电压值

        # 遍历过程中目标模式寻找
        self.target_mode_found_during_exploration = False  # 遍历过程中是否找到目标模式

        # 通信
        self.server_socket = None
        self.clients = []

        # 确认信息发送控制
        self.confirmation_thread = None
        self.stop_confirmation_event = threading.Event()
        self.confirmation_interval = 0.1  # 100ms
        self.confirmation_address = None  # 存储发送模式种类的客户端地址，用于持续发送确认





    def _ensure_hv_connected(self):
        """确保高压电源已连接"""
        try:
            # 检查当前连接状态
            status = self.hv_controller.get_connection_status()
            if status['connected'] and status['control_acquired']:
                return True

            print("尝试连接高压电源...")
            if not self.hv_controller.connect():
                print("连接高压电源失败")
                return False

            # 等待连接稳定
            time.sleep(0.5)

            # 尝试获取控制权
            print("尝试获取控制权...")
            if not self.hv_controller.ensure_control():
                print("警告: 无法获取控制权，尝试继续...")

            return True
        except Exception as e:
            print(f"连接高压电源时出错: {e}")
            return False

    def _update_fuzzy_pid_mode_ranges(self):
        """更新模糊PID控制器中的模式电压范围"""
        if hasattr(self.fuzzy_pid, 'update_mode_voltage_ranges'):
            self.fuzzy_pid.update_mode_voltage_ranges(self.mode_voltage_ranges)

    def get_actual_match_rate(self, voltage, mode_name):
        """获取实际匹配率：基于历史统计数据
        匹配率定义：在步时内统计，各个模式的监测结果数量在总的监测数量中占的比重（无模式不计入统计）

        参数：
            voltage: 电压值(kV)
            mode_name: 模式名称

        返回：
            实际匹配率(0.0-1.0)，如果没有数据返回0.0
        """
        # 四舍五入到0.01kV精度进行查找
        rounded_voltage = round(voltage, 2)

        if rounded_voltage not in self.voltage_mode_stats:
            return 0.0

        mode_counts = self.voltage_mode_stats[rounded_voltage]

        # 计算总有效样本数（排除'none'模式）
        total_samples = 0
        for mode, count in mode_counts.items():
            if mode != 'none':
                total_samples += count

        if total_samples == 0:
            return 0.0

        # 计算目标模式的匹配率
        target_count = mode_counts.get(mode_name, 0)
        match_rate = target_count / total_samples

        return match_rate

    # ==================== 通信功能 ====================
    def start_detection_server(self):
        """启动检测结果接收服务器"""
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind(('0.0.0.0', self.detection_port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)

            print(f"检测服务器已启动在端口 {self.detection_port}")

            # 启动accept线程
            accept_thread = threading.Thread(target=self._accept_connections, daemon=True)
            accept_thread.start()

            return True
        except Exception as e:
            print(f"启动检测服务器失败: {e}")
            return False

    def _accept_connections(self):
        """接受客户端连接"""
        print("等待监测模块连接...")
        while self.running:
            try:
                client_socket, address = self.server_socket.accept()
                print(f"监测模块已连接: {address}")

                client_socket.settimeout(2.0)
                self.clients.append({
                    'socket': client_socket,
                    'address': address,
                    'last_activity': time.time()
                })

                # 启动数据处理线程
                client_thread = threading.Thread(
                    target=self._handle_client,
                    args=(client_socket, address),
                    daemon=True
                )
                client_thread.start()

            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"接受连接错误: {e}")
                break

    def _handle_client(self, client_socket, address):
        """处理客户端数据"""
        buffer = b""
        while self.running:
            try:
                data = client_socket.recv(4096)
                if not data:
                    break

                buffer += data

                # 处理完整消息
                while b'\n' in buffer:
                    line, buffer = buffer.split(b'\n', 1)
                    try:
                        message = json.loads(line.decode('utf-8').strip())
                        self._process_message(message, address)
                    except json.JSONDecodeError:
                        print(f"JSON解析失败: {line}")
                    except Exception as e:
                        print(f"处理消息错误: {e}")

            except socket.timeout:
                continue
            except Exception as e:
                print(f"客户端处理错误: {e}")
                break

        # 清理客户端
        for i, client in enumerate(self.clients):
            if client['socket'] == client_socket:
                self.clients.pop(i)
                break
        client_socket.close()
        print(f"客户端断开连接: {address}")

    def _process_message(self, message, address):
        """处理接收到的消息"""
        msg_type = message.get('type', 'unknown')

        if msg_type == 'mode_classes' or msg_type == 'class_labels':
            self._process_mode_classes(message, address)
        elif msg_type == 'detection':
            self._process_detection(message, address)
        else:
            # 检查是否为没有type字段的检测结果消息
            if 'detected_mode' in message:
                # 将其作为检测结果处理
                self._process_detection(message, address)
            else:
                print(f"未知消息类型: {msg_type}")

    def _process_mode_classes(self, message, address):
        """处理模式种类消息（从监测模块接收）"""
        # 如果已经发送了确认信息，忽略后续的模式种类消息（监测模块应已停止发送）
        if self.confirmation_sent:
            print("已发送确认信息，忽略后续模式种类消息")
            return

        # 支持两种字段名：'class_names' 和 'labels'（来自监测模块的class_labels消息）
        class_data = None
        if 'class_names' in message:
            class_data = message['class_names']
        elif 'labels' in message:
            class_data = message['labels']
            print(f"收到class_labels消息，字段名: labels")
        else:
            print("模式种类消息缺少class_names或labels字段")
            return

        # 处理不同的数据格式：列表或字典
        if isinstance(class_data, list):
            # 监测模块发送的是列表格式 ['name1', 'name2', ...]
            # 转换为字典格式 {0: 'name1', 1: 'name2', ...}
            mode_classes_dict = {i: name for i, name in enumerate(class_data)}
            print(f"转换列表格式为字典格式，共{len(mode_classes_dict)}个类别")
        elif isinstance(class_data, dict):
            # 已经是字典格式 {id: 'name', ...}
            mode_classes_dict = class_data
        else:
            print(f"未知的类别数据格式: {type(class_data)}")
            return

        # 检查是否已经接收过相同的模式种类（避免重复处理）
        if self.mode_classes_received and self.mode_classes == mode_classes_dict:
            print("模式种类未变化，忽略重复消息")
            return

        # 总是使用监测模块发送的类别（它反映了当前训练文件）
        self.mode_classes = mode_classes_dict
        self.mode_classes_received = True
        self.mode_classes_client_address = address  # 记录发送模式种类的客户端地址
        self.confirmation_address = address  # 存储地址用于持续发送确认

        print(f"收到监测模块的模式种类: {list(self.mode_classes.values())}")
        print(f"共{len(self.mode_classes)}个类别")

        # 立即发送确认信息给监测模块，通知其开始发送监测结果
        self._send_confirmation(address)
        self.confirmation_sent = True  # 标记已发送确认信息

        # 启动持续发送确认信息的线程（100ms/次）
        self.stop_confirmation_event.clear()
        self.confirmation_thread = threading.Thread(
            target=self._continuous_confirmation_worker,
            daemon=True,
            name="ConfirmationThread"
        )
        self.confirmation_thread.start()
        print("已收到模式种类并启动持续确认信息发送（100ms/次），监测模块将开始发送监测结果")
        print("请选择目标模式和电压范围，然后开始电压遍历")

        # 通知GUI更新
        if self.gui:
            self.gui.update_mode_classes(self.mode_classes)

    def _process_detection(self, message, address):
        """处理检测结果消息"""
        required_fields = ['detected_mode', 'confidence', 'timestamp']
        for field in required_fields:
            if field not in message:
                print(f"检测消息缺少字段: {field}")
                return

        # 记录原始检测消息（用于调试）
        detected_mode = message.get('detected_mode', 'unknown')
        confidence = message.get('confidence', 0)
        timestamp = message.get('timestamp', time.time())
        print(f"收到检测消息: 模式='{detected_mode}', 置信度={confidence:.2f}, 时间={timestamp:.3f}")

        # 添加过滤处理
        filtered_detection = self.error_filter.filter_detection(message)
        if filtered_detection is None:
            print(f"检测结果被过滤器拒绝: {detected_mode}")
            # 即使被过滤器拒绝，如果是'none'模式，也记录到日志
            if detected_mode == 'none':
                print(f"注意: 监测模块发送了'none'模式，根据需求监测模块应只发送有效模式")
            return

        # 调试信息：显示检测到的模式和已接收的模式种类
        filtered_mode = filtered_detection.get('detected_mode')
        if filtered_mode and filtered_mode != 'none':
            # 检查检测到的模式是否在已接收的模式种类中
            mode_names = list(self.mode_classes.values()) if self.mode_classes else []
            if filtered_mode not in mode_names:
                print(f"警告: 检测到的模式 '{filtered_mode}' 不在已接收的模式种类中")
                print(f"已接收的模式种类: {mode_names}")
            else:
                print(f"检测结果有效: {filtered_mode} (置信度: {confidence:.2f})")

        # 更新最新检测结果和数据库（带锁保护）
        with self.detection_lock:
            self.latest_detection = filtered_detection
            self.detection_history.append(filtered_detection)

            # 更新数据库：每次有效检测结果都作为样本添加到电压-模式数据库
            if not filtered_detection.get('transient_error', False):
                detected_mode = filtered_detection['detected_mode']
                confidence = filtered_detection['confidence']
                if detected_mode != 'none' and self.current_voltage_kv > 0:
                    # 根据需求：每次调节电压并收到监测结果的过程都应该视作样本被添加进数据库
                    # 即使在遍历阶段也更新数据库，但遍历循环中的统计会更精确
                    # 原逻辑：if not self.exploration_active:
                    # 修改为：总是更新数据库，确保样本被记录
                    if True:  # 总是更新数据库
                        # 更新电压-模式统计
                        self.voltage_mode_stats[self.current_voltage_kv][detected_mode] += 1

                        # 更新模式电压范围
                        if detected_mode not in self.mode_voltage_ranges:
                            self.mode_voltage_ranges[detected_mode] = {
                                'min': self.current_voltage_kv,
                                'max': self.current_voltage_kv,
                                'optimal': self.current_voltage_kv,
                                'samples': [(self.current_voltage_kv, 1.0)],
                                'total_count': 1
                            }
                        else:
                            info = self.mode_voltage_ranges[detected_mode]
                            info['min'] = min(info['min'], self.current_voltage_kv)
                            info['max'] = max(info['max'], self.current_voltage_kv)
                            info['samples'].append((self.current_voltage_kv, 1.0))
                            info['total_count'] += 1

                        print(f"数据库更新: 电压{self.current_voltage_kv:.2f}kV -> 模式{detected_mode}")

        # 标记已收到监测结果
        if not self.detection_received:
            self.detection_received = True
            print("首次收到监测结果，开始接收实时监测数据")

            if not filtered_detection.get('transient_error', False):
                detected_mode = filtered_detection['detected_mode']
                confidence = filtered_detection['confidence']
                if detected_mode != 'none':
                    self.stop_confirmation_event.set()
                    print("收到首个有效监测结果，停止发送确认指令")


        # 显示检测结果（跳过瞬时误判）
        if not filtered_detection.get('transient_error', False):
            detected_mode = filtered_detection['detected_mode']
            confidence = filtered_detection['confidence']
            if detected_mode != 'none':
                print(f"检测结果: {detected_mode} (置信度: {confidence:.2f})")

                # 更新GUI
                if self.gui:
                    self.gui.update_current_mode(detected_mode, confidence)

    def _continuous_confirmation_worker(self):
        """持续发送确认信息的线程工作函数（100ms/次）"""
        print("开始持续发送确认信息（100ms/次）...")
        while self.running and not self.stop_confirmation_event.is_set():
            if self.confirmation_address:
                self._send_confirmation(self.confirmation_address)
            time.sleep(self.confirmation_interval)
        print("停止发送确认信息")

    def _send_confirmation(self, address):
        """发送确认信息给监测模块（带重试）"""
        confirmation = {
            'type': 'confirmation',
            'message': '监测模块已收到所有模式种类信息，请开始发送监测结果',
            'timestamp': time.time()
        }

        message = (json.dumps(confirmation) + '\n').encode()
        max_retries = 3

        for client in self.clients:
            if client['address'] == address:
                for attempt in range(max_retries):
                    try:
                        client['socket'].send(message)
                        print(f"确认信息已发送到 {address} (尝试 {attempt+1}/{max_retries})")

                        # 等待一小段时间让消息发送完成
                        time.sleep(0.1)
                        return True

                    except Exception as e:
                        print(f"发送确认信息失败 (尝试 {attempt+1}/{max_retries}): {e}")
                        if attempt < max_retries - 1:
                            time.sleep(0.5)  # 重试前等待

                print(f"确认信息发送失败，达到最大重试次数 {max_retries}")
                return False

        print(f"未找到客户端地址 {address}，无法发送确认信息")
        return False

    # ==================== 电压遍历功能（新需求版） ====================
    def start_exploration(self, min_voltage, max_voltage):
        """开始电压遍历与模式识别（新需求：探索阶段不需要目标模式）
        1. 模式-电压范围探索阶段（建立基础模式-电压对应规律）
        2. 遍历从下限到上限，建立模式-电压范围对照表
        3. 探索结束后调节到电压范围中点
        """
        if not self.mode_classes_received:
            print("错误: 尚未收到模式种类")
            return False

        if min_voltage >= max_voltage:
            print("错误: 最小电压必须小于最大电压")
            return False

        self.min_voltage = min_voltage
        self.max_voltage = max_voltage
        self.exploration_active = True
        self.exploration_completed = False
        self.exploration_round = 1
        self.target_mode_found_during_exploration = False
        self.explored_voltages.clear()  # 清除已探索电压记录
        self.control_state = 'exploring'  # 设置控制状态为探索阶段
        self.exploration_mode_counts.clear()  # 清空探索统计

        # 发送确认信息给监测模块（如果尚未发送）
        if not self.confirmation_sent:
            if self.mode_classes_client_address:
                self._send_confirmation(self.mode_classes_client_address)
                self.confirmation_sent = True
                print("已发送确认信息给监测模块，监测模块将开始发送监测结果")
            else:
                # 如果没有记录客户端地址，向所有客户端发送
                for client in self.clients:
                    self._send_confirmation(client['address'])
                self.confirmation_sent = True
                print("已向所有客户端发送确认信息")

        print(f"\n=== 开始第{self.exploration_round}轮电压遍历（探索阶段） ===")
        print(f"电压范围: {min_voltage:.1f}kV - {max_voltage:.1f}kV")
        print(f"初始步长: {self.fuzzy_pid.step_size:.2f}kV")
        print(f"初始步时: {self.fuzzy_pid.step_time:.2f}秒")

        # 重置过滤器状态，清除旧的历史数据
        self.error_filter.reset()

        # 启动遍历线程
        exploration_thread = threading.Thread(target=self._exploration_loop, daemon=True)
        exploration_thread.start()

        return True

    def _exploration_loop(self):
        """电压遍历循环（新需求版）
        1. 从电压下限到上限遍历，构建模式-电压范围对照表
        2. 实现差异化遍历：连续3次相同模式 -> 大步长小步时；模式变化 -> 小步长大步时
        3. 探索结束后调节到电压范围中点，生成对照表
        """
        # 连接高压电源
        print("正在连接高压电源...")
        if not self.hv_controller.connect():
            print("连接高压电源失败，请检查：")
            print("  1. 高压电源是否上电")
            print("  2. COM5端口是否正确")
            print("  3. 数据线是否连接")
            print("  4. 高压电源是否处于远程控制模式")
            self.exploration_active = False
            return
        else:
            print("高压电源连接成功")

        # 测试连接和获取控制权
        print("测试高压电源控制...")
        time.sleep(0.5)  # 等待连接稳定

        # 尝试获取控制权
        print("尝试获取控制权...")
        if not self.hv_controller.ensure_control():
            print("警告：无法获取控制权，尝试继续...")

        # 从最小电压开始遍历
        current_voltage = self.min_voltage
        last_mode = None
        mode_consistent_count = 0
        # 重置目标模式找到标志（探索阶段不需要目标模式）
        self.target_mode_found_during_exploration = False

        # 探索阶段不需要目标模式，只需构建模式-电压范围对照表

        # 等待检测模块初始化（在开始遍历前给检测模块时间开始发送数据）
        print("等待检测模块初始化...")
        initialization_start = time.time()
        initialization_timeout = 3.0  # 等待3秒
        detection_received_during_init = False

        while time.time() - initialization_start < initialization_timeout and self.exploration_active:
            with self.detection_lock:
                if self.latest_detection is not None:
                    detection_received_during_init = True
                    detected_mode = self.latest_detection.get('detected_mode', 'unknown')
                    print(f"检测模块已开始发送数据: 模式='{detected_mode}'")
                    break
            time.sleep(0.1)

        if not detection_received_during_init:
            print("警告: 在初始化等待期间未收到检测数据，但将继续遍历")
        else:
            print("检测模块初始化完成，开始电压遍历")

        while self.exploration_active and current_voltage <= self.max_voltage:
            # 检查电压是否已探索过（跳过已设定的电压值）
            while current_voltage <= self.max_voltage and round(current_voltage, 2) in self.explored_voltages:
                print(f"电压 {current_voltage:.2f}kV 已探索过，跳过...")
                current_voltage += 0.01  # 增加最小增量
                current_voltage = round(current_voltage, 2)

            if current_voltage > self.max_voltage:
                break

            # 设置电压 - 添加详细调试信息
            print(f"尝试设置电压: {current_voltage:.2f}kV...")
            if self.hv_controller.set_voltage_kv(current_voltage):
                self.current_voltage_kv = current_voltage
                print(f"✓ 电压设置成功: {current_voltage:.2f}kV")
                # 记录已探索电压
                self.explored_voltages.add(round(current_voltage, 2))

                # 强制等待≥0.20秒保障反馈真实性
                time.sleep(0.20)

                # 收集检测结果
                mode_counts = defaultdict(int)
                total_samples = 0
                valid_samples = 0

                # 记录电压设置时间
                voltage_set_time = time.time()
                # 获取当前最新检测结果的时间戳，作为起始点，避免处理旧的检测结果
                with self.detection_lock:
                    if self.latest_detection:
                        last_processed_timestamp = self.latest_detection.get('timestamp', 0)
                    else:
                        last_processed_timestamp = 0
                # 如果最新检测结果的时间戳早于电压设置时间，仍然使用它，确保只处理新的检测结果
                print(f"开始收集检测结果，电压设置时间: {voltage_set_time:.3f}, 最后处理时间戳初始值: {last_processed_timestamp:.3f}")

                # 统计步时内的检测结果
                start_time = time.time()
                while time.time() - start_time < self.fuzzy_pid.step_time:
                    # 使用锁安全地读取最新检测结果
                    current_detection = None
                    with self.detection_lock:
                        current_detection = self.latest_detection

                    if current_detection:
                        # 检查检测时间戳：只处理电压设置之后且未处理过的检测结果
                        detection_timestamp = current_detection.get('timestamp', 0)

                        # 只处理未处理过的检测结果（按时间戳顺序，确保每个检测只处理一次）
                        if detection_timestamp > last_processed_timestamp:

                            # 检查是否为非瞬时误判的有效检测
                            detected_mode = current_detection['detected_mode']
                            confidence = current_detection['confidence']
                            transient_error = current_detection.get('transient_error', False)

                            # 非瞬时误判的有效检测计入统计（置信度不影响纳入统计）
                            if not transient_error and detected_mode != 'none':
                                mode_counts[detected_mode] += 1
                                total_samples += 1
                                valid_samples += 1

                                # 更新最后处理的时间戳
                                last_processed_timestamp = detection_timestamp
                                print(f"统计检测结果: {detected_mode} (置信度: {confidence:.2f}, 时间: {detection_timestamp:.3f})")

                    time.sleep(0.02)  # 短时间等待

                # 显示检测统计信息
                if valid_samples > 0 and len(mode_counts) > 0:
                    print(f"检测统计: 有效样本={valid_samples}, 检测到{len(mode_counts)}个不同模式")

                # 分析检测结果
                if valid_samples > 0:
                    # 找出主要模式（出现次数最多的模式）
                    if mode_counts:
                        main_mode = max(mode_counts.items(), key=lambda x: x[1])[0]
                        main_count = mode_counts[main_mode]
                        main_ratio = main_count / valid_samples

                        # 记录电压-模式统计（记录所有检测到的模式，不仅是主要模式）
                        for mode, count in mode_counts.items():
                            self.voltage_mode_stats[current_voltage][mode] = count

                        # 更新模式电压范围
                        if main_mode not in self.mode_voltage_ranges:
                            self.mode_voltage_ranges[main_mode] = {
                                'min': current_voltage,
                                'max': current_voltage,
                                'optimal': current_voltage,
                                'samples': [(current_voltage, main_ratio)],
                                'total_count': main_count
                            }
                            # 实时更新GUI遍历结果（新模式添加）
                            if self.gui:
                                self.gui.update_exploration_results(self.mode_voltage_ranges)
                        else:
                            info = self.mode_voltage_ranges[main_mode]
                            info['min'] = min(info['min'], current_voltage)
                            info['max'] = max(info['max'], current_voltage)
                            info['samples'].append((current_voltage, main_ratio))
                            info['total_count'] += main_count

                            # 更新最优电压点（匹配率最高的电压）
                            max_ratio = max([r for _, r in info['samples']])
                            for volt, ratio in info['samples']:
                                if ratio == max_ratio:
                                    info['optimal'] = volt
                                    break

                        print(f"主要模式: {main_mode} (占比: {main_ratio:.1%}, 样本: {valid_samples})")

                        # 更新模糊PID控制器的模式电压范围
                        self._update_fuzzy_pid_mode_ranges()

                        # 调试信息：显示所有检测到的模式及其计数
                        if mode_counts and len(mode_counts) > 1:
                            other_modes = [(mode, count) for mode, count in mode_counts.items() if mode != main_mode]
                            if other_modes:
                                print(f"    其他模式: {', '.join([f'{mode}({count})' for mode, count in other_modes])}")

                        # 更新所有检测到的模式的电压范围（不仅仅是主要模式）
                        # 根据需求：匹配率是各个模式的监测结果数量在总的监测数量中占的比重
                        # 为所有检测到的模式记录匹配率，用于构建更精确的隶属函数
                        for mode, count in mode_counts.items():
                            if mode != main_mode:
                                ratio = count / valid_samples
                                # 记录所有检测到的模式（根据需求：所有模式都应记录电压范围）
                                # 移除5%阈值以显示所有模式类别
                                if mode not in self.mode_voltage_ranges:
                                    self.mode_voltage_ranges[mode] = {
                                        'min': current_voltage,
                                        'max': current_voltage,
                                        'optimal': current_voltage,
                                        'samples': [(current_voltage, ratio)],
                                        'total_count': count
                                    }
                                else:
                                    info = self.mode_voltage_ranges[mode]
                                    info['min'] = min(info['min'], current_voltage)
                                    info['max'] = max(info['max'], current_voltage)
                                    info['samples'].append((current_voltage, ratio))
                                    info['total_count'] += count

                                    # 更新最优电压点（匹配率最高的电压）
                                    max_ratio = max([r for _, r in info['samples']])
                                    for volt, r in info['samples']:
                                        if r == max_ratio:
                                            info['optimal'] = volt
                                            break
                                print(f"    记录次要模式: {mode} (匹配率: {ratio:.1%})")

                        # 实时更新GUI遍历结果
                        if self.gui:
                            self.gui.update_exploration_results(self.mode_voltage_ranges)

                        # 探索阶段：不检查目标模式，仅记录所有检测到的模式
                        # 差异化遍历逻辑：检查模式一致性，调整步长和步时
                        pass

                        # 检查模式一致性
                        if main_mode == last_mode:
                            mode_consistent_count += 1
                        else:
                            mode_consistent_count = 1
                            last_mode = main_mode

                        # 差异化遍历逻辑（新需求）
                        # 连续3次相同模式 -> 大步长小步时；模式变化 -> 小步长大步时
                        if mode_consistent_count >= 3:
                            # 大步长(0.5-1kV)，小步时(0.2-0.3秒)
                            self.fuzzy_pid.step_size = min(1.0, max(0.5, self.fuzzy_pid.step_size * 1.5))
                            self.fuzzy_pid.step_time = max(0.2, min(0.3, self.fuzzy_pid.step_time * 0.7))
                            print(f"[差异化遍历] 连续{mode_consistent_count}次相同模式，采用大步长小步时: {self.fuzzy_pid.step_size:.2f}kV, {self.fuzzy_pid.step_time:.2f}s")
                        elif mode_consistent_count <= 1 and last_mode is not None:
                            # 小步长(0.1-0.3kV)，大步时(0.3-0.4秒)
                            self.fuzzy_pid.step_size = max(0.1, min(0.3, self.fuzzy_pid.step_size * 0.7))
                            self.fuzzy_pid.step_time = min(0.4, max(0.3, self.fuzzy_pid.step_time * 1.3))
                            print(f"[差异化遍历] 模式变化，采用小步长大步时: {self.fuzzy_pid.step_size:.2f}kV, {self.fuzzy_pid.step_time:.2f}s")
                    else:
                        main_mode = None
                        main_ratio = 0
                else:
                    print(f"未检测到有效模式 (有效样本: {valid_samples})")
                    main_mode = None
                    main_ratio = 0
                    mode_consistent_count = 0

                # 计算电压差和变化率（探索阶段：使用与最大电压的差值）
                voltage_difference = self.max_voltage - current_voltage  # 默认值

                # 计算电压变化率（最近3个电压点）
                recent_voltages = list(self.fuzzy_pid.voltage_history)[-3:] if len(self.fuzzy_pid.voltage_history) >= 3 else []
                if len(recent_voltages) >= 3:
                    voltage_change_rate = abs(recent_voltages[-1] - recent_voltages[-3]) / 3
                else:
                    voltage_change_rate = 0

                # 自适应调节步长步时（增强版）
                boundary_drift_rate = self.fuzzy_pid.boundary_drift_rate
                step_size, step_time = self.fuzzy_pid.adapt_step_parameters_enhanced(
                    mode_consistent_count, voltage_difference, voltage_change_rate, boundary_drift_rate
                )

                # 更新控制器参数
                self.fuzzy_pid.step_size = step_size
                self.fuzzy_pid.step_time = step_time

                # 移动到下一个电压点
                current_voltage += step_size
                current_voltage = round(current_voltage, 2)

            else:
                print(f"电压设置失败: {current_voltage:.2f}kV")
                break

        # 遍历完成
        self.exploration_active = False
        self.exploration_completed = True
        self.control_state = 'waiting_for_target'

        # 探索阶段完成，调节到电压范围中点（避免系统剧烈扰动）
        midpoint = (self.min_voltage + self.max_voltage) / 2
        print(f"\n=== 电压遍历完成（探索阶段） ===")
        print(f"共进行{self.exploration_round}轮遍历")
        print(f"调节电压到范围中点: {midpoint:.2f}kV")
        self.hv_controller.set_voltage_kv(midpoint)
        self.current_voltage_kv = midpoint

        # 生成初始"模式-电压范围"对照表
        print("生成初始模式-电压范围对照表:")
        for mode, info in self.mode_voltage_ranges.items():
            print(f"  {mode}: {info['min']:.1f}kV - {info['max']:.1f}kV, 最优: {info['optimal']:.1f}kV")

        print("探索阶段完成，系统已调节到电压范围中点，等待用户选择目标模式")

        # 更新GUI
        if self.gui:
            self.gui.update_exploration_results(self.mode_voltage_ranges)

    # ==================== 目标模式模糊遍历（流程4） ====================
    def _fuzzy_exploration_for_target(self, target_mode_name):
        """流程4：模糊遍历寻找目标模式（新需求算法）
        实现需求文档中的模糊遍历算法：
        1. 实时判断：若接收到目标模式立即停止遍历
        2. 第一次遍历：将电压总范围均匀分为n个范围，取中值电压遍历
        3. 若没有接收到目标模式，用始末电压值+中值电压值共n+2个值，分为n+1个范围，取中值电压遍历
        4. 重复类似操作直到找到目标模式
        """
        if target_mode_name not in self.mode_classes.values():
            print(f"错误: 目标模式 '{target_mode_name}' 不在模式种类中")
            return False, None

        print(f"\n=== 开始模糊遍历寻找目标模式 '{target_mode_name}' ===")
        print(f"电压总范围: {self.min_voltage:.1f}kV - {self.max_voltage:.1f}kV")

        # 确保高压电源已连接
        if not self._ensure_hv_connected():
            print("错误: 无法连接高压电源")
            return False, None

        # 初始化参数（符合需求：初始步长0.15kV，步时0.3秒）
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 设置初始遍历参数
        self.fuzzy_pid.step_size = 0.15  # kV
        self.fuzzy_pid.step_time = 0.3   # 秒

        # 获取模式数量n
        n = len(self.mode_classes)
        print(f"模式种类数量 n = {n}")

        # 遍历重试逻辑（最多重试2次）
        max_retries = 2
        retry_count = 0

        while retry_count <= max_retries:
            print(f"\n--- 第{retry_count + 1}轮遍历 (步长={self.fuzzy_pid.step_size:.2f}kV, 步时={self.fuzzy_pid.step_time:.2f}s) ---")

            # 初始化电压点序列：起始值 + 中值点序列 + 结束值
            voltage_points = [self.min_voltage, self.max_voltage]
            iteration = 1
            target_found = False
            target_voltage = None

            while not target_found:
                print(f"\n第{iteration}次迭代...")

                # 对当前电压点序列排序去重
                sorted_points = sorted(set(voltage_points))

                # 生成中值电压序列：取相邻两个电压点的中值
                mid_points = []
                for i in range(len(sorted_points) - 1):
                    mid_voltage = (sorted_points[i] + sorted_points[i + 1]) / 2
                    mid_voltage = round(mid_voltage, 2)  # 四舍五入到0.01kV
                    mid_points.append(mid_voltage)

                # 第一次迭代的特殊规则：将电压范围均匀分为n个范围
                if iteration == 1:
                    mid_points = []
                    # 将电压总范围分为n个均匀区间，确保n>0
                    if n <= 0:
                        print(f"警告: 模式数量n={n}，使用默认值n=1")
                        n = 1
                    range_width = (self.max_voltage - self.min_voltage) / n
                    for i in range(n):
                        mid_voltage = self.min_voltage + (i + 0.5) * range_width
                        mid_voltage = round(mid_voltage, 2)
                        mid_points.append(mid_voltage)

                print(f"电压点序列: {sorted_points}")
                print(f"中值电压点: {mid_points}")

                # 按从低到高的顺序遍历中值电压点
                for voltage in sorted(mid_points):
                    # 检查电压是否已探索过（跳过重复设置）
                    if round(voltage, 2) in self.explored_voltages:
                        print(f"电压 {voltage:.2f}kV 已探索过，跳过...")
                        continue

                    # 设置电压
                    print(f"设置电压: {voltage:.2f}kV...")
                    if not self.hv_controller.set_voltage_kv(voltage):
                        print(f"电压设置失败: {voltage:.2f}kV")
                        continue

                    self.current_voltage_kv = voltage
                    self.explored_voltages.add(round(voltage, 2))
                    print(f"✓ 电压设置成功: {voltage:.2f}kV")

                    # 强制等待≥0.20秒保障反馈真实性
                    time.sleep(0.20)

                    # 统计步时内的检测结果
                    mode_counts = defaultdict(int)
                    valid_samples = 0
                    total_samples = 0

                    start_time = time.time()
                    voltage_set_time = time.time()
                    # 获取当前最新检测结果的时间戳，作为起始点，避免处理旧的检测结果
                    with self.detection_lock:
                        if self.latest_detection:
                            last_processed_timestamp = self.latest_detection.get('timestamp', 0)
                        else:
                            last_processed_timestamp = 0
                    # 如果最新检测结果的时间戳早于电压设置时间，仍然使用它，确保只处理新的检测结果
                    print(f"电压设置时间: {voltage_set_time:.3f}, 最后处理时间戳初始值: {last_processed_timestamp:.3f}")

                    # 实时判断：在步时统计过程中检查是否收到目标模式
                    while time.time() - start_time < self.fuzzy_pid.step_time:
                        # 读取最新检测结果
                        current_detection = None
                        with self.detection_lock:
                            current_detection = self.latest_detection

                        if current_detection:
                            detection_timestamp = current_detection.get('timestamp', 0)

                            # 只处理未处理过的检测结果（按时间戳顺序，确保每个检测只处理一次）
                            if detection_timestamp > last_processed_timestamp:

                                detected_mode = current_detection['detected_mode']
                                confidence = current_detection['confidence']
                                transient_error = current_detection.get('transient_error', False)

                                # 处理检测结果（置信度不影响纳入统计）
                                if detected_mode != 'none':
                                    # 实时判断：若接收到目标模式立即停止遍历（即使被标记为瞬时误判）
                                    if detected_mode == target_mode_name:
                                        print(f"实时检测到目标模式 '{target_mode_name}'，立即停止遍历！")
                                        target_found = True
                                        target_voltage = voltage

                                        # 更新模式电压范围数据库（实时检测到目标模式）
                                        # 计算匹配率：由于是单个检测，匹配率为1.0
                                        match_rate = 1.0
                                        if target_mode_name not in self.mode_voltage_ranges:
                                            self.mode_voltage_ranges[target_mode_name] = {
                                                'min': voltage,
                                                'max': voltage,
                                                'optimal': voltage,
                                                'samples': [(voltage, match_rate)],
                                                'total_count': 1
                                            }
                                        else:
                                            info = self.mode_voltage_ranges[target_mode_name]
                                            info['min'] = min(info['min'], voltage)
                                            info['max'] = max(info['max'], voltage)
                                            info['samples'].append((voltage, match_rate))
                                            info['total_count'] += 1

                                        # 更新电压-模式统计（四舍五入到0.01kV精度）
                                        rounded_voltage = round(voltage, 2)
                                        self.voltage_mode_stats[rounded_voltage][target_mode_name] = self.voltage_mode_stats[rounded_voltage].get(target_mode_name, 0) + 1

                                        print(f"已更新模式电压范围数据库，匹配率: {match_rate:.1%}")
                                        # 直接跳出内层循环
                                        break

                                    # 如果不是目标模式，且不是瞬时误判，则计入统计
                                    if not transient_error:
                                        mode_counts[detected_mode] += 1
                                        valid_samples += 1
                                        total_samples += 1  # 只对有效非目标模式检测计数
                                else:
                                    # 'none' 模式，不计入统计
                                    pass

                                last_processed_timestamp = detection_timestamp

                        # 如果已找到目标模式，跳出内层等待循环
                        if target_found:
                            break

                        time.sleep(0.02)  # 短时间等待

                    # 如果已找到目标模式，跳出电压遍历循环
                    if target_found:
                        break

                    # 分析统计结果（如果没有实时找到目标模式）
                    if valid_samples > 0 and not target_found:
                        # 找出主要模式（出现次数最多）
                        if mode_counts:
                            main_mode = max(mode_counts.items(), key=lambda x: x[1])[0]
                            main_count = mode_counts[main_mode]
                            main_ratio = main_count / valid_samples

                            print(f"检测统计: 有效样本={valid_samples}, 主要模式={main_mode} (占比={main_ratio:.1%})")

                            # 更新数据库中对应模式的电压范围
                            if main_mode not in self.mode_voltage_ranges:
                                self.mode_voltage_ranges[main_mode] = {
                                    'min': voltage,
                                    'max': voltage,
                                    'optimal': voltage,
                                    'samples': [(voltage, main_ratio)],
                                    'total_count': main_count
                                }
                            else:
                                info = self.mode_voltage_ranges[main_mode]
                                info['min'] = min(info['min'], voltage)
                                info['max'] = max(info['max'], voltage)
                                info['samples'].append((voltage, main_ratio))
                                info['total_count'] += main_count

                            # 更新电压-模式统计（主要模式）
                            rounded_voltage = round(voltage, 2)
                            self.voltage_mode_stats[rounded_voltage][main_mode] = self.voltage_mode_stats[rounded_voltage].get(main_mode, 0) + main_count

                            # 更新所有检测到的模式（不仅仅是主要模式）
                            for mode, count in mode_counts.items():
                                if mode != main_mode:
                                    ratio = count / valid_samples
                                    if mode not in self.mode_voltage_ranges:
                                        self.mode_voltage_ranges[mode] = {
                                            'min': voltage,
                                            'max': voltage,
                                            'optimal': voltage,
                                            'samples': [(voltage, ratio)],
                                            'total_count': count
                                        }
                                    else:
                                        info = self.mode_voltage_ranges[mode]
                                        info['min'] = min(info['min'], voltage)
                                        info['max'] = max(info['max'], voltage)
                                        info['samples'].append((voltage, ratio))
                                        info['total_count'] += count

                                    # 更新电压-模式统计（其他模式）
                                    rounded_voltage = round(voltage, 2)
                                    self.voltage_mode_stats[rounded_voltage][mode] = self.voltage_mode_stats[rounded_voltage].get(mode, 0) + count

                            # 检查目标模式匹配度
                            target_count = mode_counts.get(target_mode_name, 0)
                            target_ratio = target_count / valid_samples if valid_samples > 0 else 0

                            print(f"目标模式 '{target_mode_name}' 匹配度: {target_ratio:.1%}")

                            # 停止条件：目标模式匹配度≥50%
                            if target_ratio >= 0.5:
                                target_found = True
                                target_voltage = voltage
                                print(f"✓ 找到目标模式！匹配度={target_ratio:.1%}，电压={target_voltage:.2f}kV")
                                break
                        else:
                            # mode_counts为空但valid_samples>0的情况（理论上不会发生）
                            print("警告: 有效样本>0但mode_counts为空")
                    else:
                        print(f"未检测到有效模式 (有效样本: {valid_samples})")

                    # 如果已找到目标模式，跳出电压遍历循环
                    if target_found:
                        break

                # 如果已找到目标模式，跳出迭代循环
                if target_found:
                    break

                # 准备下一次迭代：将当前所有中值电压点加入电压点序列
                voltage_points.extend(mid_points)
                iteration += 1

                # 防止无限循环：最多迭代10次
                if iteration > 10:
                    print("达到最大迭代次数(10)，停止模糊遍历")
                    break

            # 检查遍历结果
            if target_found:
                print(f"\n模糊遍历成功！找到目标模式 '{target_mode_name}'，电压={target_voltage:.2f}kV")

                # 恢复原始参数
                self.fuzzy_pid.step_size = original_step_size
                self.fuzzy_pid.step_time = original_step_time

                return True, target_voltage
            else:
                print(f"\n第{retry_count + 1}轮遍历未找到目标模式")

                # 重试逻辑：调整参数重新遍历
                retry_count += 1
                if retry_count <= max_retries:
                    # 调整参数：步长降至0.2kV，步时增至0.5秒
                    self.fuzzy_pid.step_size = 0.2
                    self.fuzzy_pid.step_time = 0.5
                    print(f"调整参数重新遍历: 步长={self.fuzzy_pid.step_size:.2f}kV, 步时={self.fuzzy_pid.step_time:.2f}s")
                else:
                    print(f"已达到最大重试次数 ({max_retries})，未找到目标模式")

        # 恢复原始参数
        self.fuzzy_pid.step_size = original_step_size
        self.fuzzy_pid.step_time = original_step_time

        return False, None

    # ==================== 目标控制功能（改进版） ====================
    def start_target_control(self, target_mode_name, min_voltage=None, max_voltage=None):
        """启动目标模式控制

        """
        # 检查目标模式是否在模式种类中
        if target_mode_name not in self.mode_classes.values():
            print(f"错误: 目标模式 '{target_mode_name}' 不在模式种类中")
            print(f"可用模式: {list(self.mode_classes.values())}")
            return False

        # 检查是否已收到模式种类
        if not self.mode_classes_received:
            print("错误: 尚未收到模式种类")
            return False

        # 更新电压范围（如果提供了新值）
        if min_voltage is not None:
            self.min_voltage = min_voltage
        if max_voltage is not None:
            self.max_voltage = max_voltage

        # 验证电压范围
        if self.min_voltage >= self.max_voltage:
            print(f"错误: 电压范围无效 {self.min_voltage:.1f}kV >= {self.max_voltage:.1f}kV")
            return False

        self.target_mode = target_mode_name

        # 如果目标模式在模式电压范围中有记录，使用记录的信息；否则创建默认记录
        if target_mode_name in self.mode_voltage_ranges:
            mode_info = self.mode_voltage_ranges[target_mode_name]
            print(f"\n=== 启动目标控制 ===")
            print(f"目标模式: {target_mode_name}")
            print(f"电压范围: {mode_info['min']:.1f}kV - {mode_info['max']:.1f}kV")
            print(f"最优电压: {mode_info['optimal']:.1f}kV")
        else:
            # 目标模式没有历史数据，使用电压总范围中点作为初始最优电压
            midpoint = (self.min_voltage + self.max_voltage) / 2
            mode_info = {
                'min': self.min_voltage,
                'max': self.max_voltage,
                'optimal': midpoint,
                'samples': [],
                'total_count': 0
            }
            # 保存到模式电压范围字典中
            self.mode_voltage_ranges[target_mode_name] = mode_info
            print(f"\n=== 启动目标控制（新目标模式） ===")
            print(f"目标模式: {target_mode_name}")
            print(f"使用电压总范围: {self.min_voltage:.1f}kV - {self.max_voltage:.1f}kV")
            print(f"初始最优电压: {midpoint:.1f}kV")

        print(f"操作总范围: {self.min_voltage:.1f}kV - {self.max_voltage:.1f}kV")

        # 流程4：执行模糊遍历寻找目标模式
        print("\n=== 执行流程4：模糊遍历寻找目标模式 ===")
        target_found, found_voltage = self._fuzzy_exploration_for_target(target_mode_name)

        if not target_found:
            # 根据需求：最多重试2次，仍未找到则GUI弹窗提示
            print(f"错误: 未找到目标模式 '{target_mode_name}'，目标模式超出设定电压范围")
            if self.gui:
                # 在GUI中显示错误信息
                messagebox.showerror("目标模式错误", f"目标模式 '{target_mode_name}' 超出设定电压范围")
            return False

        print(f"✓ 流程4完成：找到目标模式 '{target_mode_name}'，电压={found_voltage:.2f}kV")

        # 设置到找到的电压点
        target_voltage = found_voltage
        self.hv_controller.set_voltage_kv(target_voltage)
        self.current_voltage_kv = target_voltage

        # 更新模糊PID控制器的模式电压范围
        self._update_fuzzy_pid_mode_ranges()

        # 重置最佳匹配度
        self.best_match_rate = 0.0
        self.best_match_voltage = target_voltage
        self.stable_state = False
        self.initial_optimization_done = False  # 需要执行初始优化

        # 重置步骤6相关状态
        self.step6_pid_fuzzy_completed = False  # 步骤6未完成
        self.best_match_recorded = False  # 匹配度第一未记录
        self.found_target_mode_voltage = target_voltage  # 记录当前电压

        # 重置过滤器状态
        self.error_filter.reset()

        # 流程5：锁定目标模式对应范围及最优匹配点
        print("\n=== 执行流程5：锁定目标模式对应范围及最优匹配点 ===")
        # 这里将执行PID模糊控制遍历，在_enhanced_control_loop中会根据情况调用
        # 或者可以在这里直接调用_restart_control_optimization()

        # 启动控制线程（将执行流程5和后续流程）
        control_thread = threading.Thread(target=self._enhanced_control_loop, daemon=True)
        control_thread.start()

        return True

    def _enhanced_control_loop(self):
        """增强版目标控制循环"""
        try:
            if self.target_mode is None:
                return

            # 流程5：如果步骤6未完成，执行PID模糊控制算法锁定目标模式范围及最优匹配点
            if not self.step6_pid_fuzzy_completed:
                print("步骤6未完成，开始执行流程5：PID模糊控制算法锁定目标模式范围及最优匹配点")
                self._restart_control_optimization()
                # 如果执行完流程5后目标模式被清空（可能出错），则退出
                if self.target_mode is None:
                    return
                # 流程5已执行，获取最新的模式信息，然后直接进入持续控制循环
                print("流程5执行完成，进入持续控制循环")
                mode_info = self.mode_voltage_ranges[self.target_mode]
                # 设置目标电压为最佳匹配电压
                target_voltage = self.best_match_voltage if self.best_match_voltage is not None else mode_info['optimal']
                self.current_voltage_kv = target_voltage
                # 跳过初始状态检查和调节，直接进入持续控制循环
                # 通过设置标志让下面的代码跳过初始调节
                process_5_executed = True
            else:
                mode_info = self.mode_voltage_ranges[self.target_mode]
                process_5_executed = False

            # 初始化target_voltage变量，将在下面的分支中设置
            target_voltage = None

            # 只有当流程5未执行时才进行初始状态检查和调节
            if not process_5_executed:
                # 初始目标电压为最优电压点
                target_voltage = mode_info['optimal']
                self.current_voltage_kv = target_voltage  # 设置当前电压为最优电压点

                print("开始目标模式定向调节阶段...")
                print(f"目标模式: {self.target_mode}, 最优电压点: {target_voltage:.2f}kV")
                print(f"电压范围: {mode_info['min']:.2f}kV - {mode_info['max']:.2f}kV")

                # 设置到最优电压点
                if not self.hv_controller.set_voltage_kv(target_voltage):
                    print("警告: 无法设置到最优电压点")
                else:
                    print(f"电压已设置为最优点: {target_voltage:.2f}kV")

                # 等待稳定
                time.sleep(0.5)

                # 检查初始电压是否在目标模式区间内
                current_in_range = mode_info['min'] <= self.current_voltage_kv <= mode_info['max']

                # 检查当前检测结果是否为目标模式
                initial_target_detected = False
                if self.latest_detection and not self.latest_detection.get('transient_error', False):
                    detected_mode = self.latest_detection['detected_mode']
                    confidence = self.latest_detection['confidence']
                    if detected_mode == self.target_mode:  #and confidence >= 0.5:
                        initial_target_detected = True

                print(f"初始状态: 电压在区间内={current_in_range}, 检测到目标模式={initial_target_detected}")

                # 根据情况执行相应的闭环调节
                if initial_target_detected and current_in_range:
                    print("情况1: 初始电压在目标模式区间内，启动边界二次验证")
                    self._boundary_verification()
                else:
                    print("情况2: 初始电压不在目标模式区间内，启动PID模糊控制调节")
                    self._pid_fuzzy_adjustment_to_target()
            else:
                # 流程5已执行，使用流程5中找到的最佳匹配电压
                target_voltage = self.best_match_voltage if self.best_match_voltage is not None else mode_info['optimal']
                print(f"流程5已执行，使用最佳匹配电压: {target_voltage:.2f}kV")
                # 确保电压已设置（_restart_control_optimization应该已经设置了）
                if abs(self.current_voltage_kv - target_voltage) > 0.01:
                    self.hv_controller.set_voltage_kv(target_voltage)
                    self.current_voltage_kv = target_voltage

            # 标记初始优化已完成
            self.initial_optimization_done = True
            print("初始优化完成，进入持续控制循环")

            # 控制循环
            while self.running and self.target_mode is not None:
                # 等待检测结果
                if self.latest_detection is None:
                    time.sleep(0.05)
                    continue

                # 跳过瞬时误判
                if self.latest_detection.get('transient_error', False):
                    time.sleep(0.05)
                    continue

                detected_mode = self.latest_detection['detected_mode']
                confidence = self.latest_detection['confidence']
                timestamp = self.latest_detection['timestamp']

                # 计算模式误差
                mode_error = 0
                boundary_drift_rate = 0

                if detected_mode != 'none' : #and confidence >= 0.5
                    if detected_mode == self.target_mode:
                        mode_error = 0  # 目标模式，无误差

                        # 更新边界漂移（如果检测到边界）
                        # TODO: 这里可以根据实际需要更新边界漂移检测

                    else:
                        # 检测到其他模式，计算模式误差
                        if detected_mode in self.mode_voltage_ranges:
                            detected_optimal = self.mode_voltage_ranges[detected_mode]['optimal']
                            mode_error = detected_optimal - target_voltage

                # 计算电压调整量（增强版）
                adjustment, error, voltage_change_rate = self.fuzzy_pid.calculate_adjustment_enhanced(
                    target_voltage, self.current_voltage_kv, mode_error, boundary_drift_rate
                )

                # 应用调整（稳定状态下不调整电压）
                if not self.stable_state and abs(adjustment) > 0.001:
                    new_voltage = self.current_voltage_kv + adjustment
                    new_voltage = max(self.min_voltage, min(self.max_voltage, new_voltage))

                    # 确保在目标模式的电压范围内
                    if new_voltage < mode_info['min']:
                        new_voltage = mode_info['min']
                    elif new_voltage > mode_info['max']:
                        new_voltage = mode_info['max']

                    if self.hv_controller.set_voltage_kv(new_voltage):
                        self.current_voltage_kv = new_voltage
                        print(f"电压调整: {adjustment:+.3f}kV -> {new_voltage:.3f}kV")
                elif self.stable_state:
                    # 稳定状态，保持电压不变，仅记录日志
                    pass

                # 稳定判断（每5秒）
                current_time = time.time()
                if current_time - self.last_stability_check >= self.stability_check_interval:
                    self._enhanced_stability_check()
                    self.last_stability_check = current_time

                # 等待步时
                time.sleep(max(0.15, self.fuzzy_pid.step_time))

        except Exception as e:
            print(f"目标控制循环出错: {e}")
            import traceback
            traceback.print_exc()
            # 尝试恢复，等待后重新启动控制循环
            time.sleep(2.0)
            print("尝试重新启动控制循环...")
            # 重新启动控制线程
            if self.running and self.target_mode is not None:
                control_thread = threading.Thread(target=self._enhanced_control_loop, daemon=True)
                control_thread.start()
            return

    def _boundary_verification(self):
        """边界二次验证（情况1）
        从当前电压向区间两侧遍历，验证并更新边界
        """
        print("\n=== 执行边界二次验证 ===")

        # 使用现有的_restart_control_optimization方法，它已经实现了边界搜索
        # 但需要确保它不会干扰后续控制
        self._restart_control_optimization()

        print("边界二次验证完成")

    def _pid_fuzzy_adjustment_to_target(self):
        """PID模糊控制调节向目标模式区间逼近（情况2）
        从当前电压向区间两侧遍历，直到找到目标模式
        """
        print("\n=== 执行PID模糊控制调节向目标模式区间逼近 ===")

        if self.target_mode is None:
            return

        mode_info = self.mode_voltage_ranges[self.target_mode]
        current_voltage = self.current_voltage_kv

        print(f"当前电压: {current_voltage:.2f}kV, 目标区间: {mode_info['min']:.2f}kV - {mode_info['max']:.2f}kV")

        # 检查当前电压相对于目标区间的位置
        if current_voltage < mode_info['min']:
            print("当前电压在目标区间左侧，向右搜索...")
            search_direction = 1  # 向右
            target_boundary = mode_info['min']
        elif current_voltage > mode_info['max']:
            print("当前电压在目标区间右侧，向左搜索...")
            search_direction = -1  # 向左
            target_boundary = mode_info['max']
        else:
            print("当前电压已在目标区间内，但未检测到目标模式，执行小范围搜索...")
            # 已经在区间内但未检测到目标模式，执行小范围搜索
            self._small_range_exploration()
            return

        # 保存原始参数
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 根据电压差值设置搜索参数
        voltage_diff = abs(current_voltage - target_boundary)

        if voltage_diff > 0.5:
            # 差值大，采用大步长快速逼近
            self.fuzzy_pid.step_size = min(1.0, max(0.5, voltage_diff * 0.5))
            self.fuzzy_pid.step_time = 0.3  # 短步时
            print(f"电压差值大({voltage_diff:.2f}kV)，采用大步长{self.fuzzy_pid.step_size:.2f}kV快速逼近")
        else:
            # 差值小，采用小步长精准调节
            self.fuzzy_pid.step_size = max(0.1, min(0.3, voltage_diff * 0.3))
            self.fuzzy_pid.step_time = 0.5  # 常规步时
            print(f"电压差值小({voltage_diff:.2f}kV)，采用小步长{self.fuzzy_pid.step_size:.2f}kV精准调节")

        # 搜索循环
        search_voltage = current_voltage
        max_steps = int(abs(voltage_diff) / self.fuzzy_pid.step_size) + 10
        step_count = 0

        while step_count < max_steps:
            # 移动一步
            search_voltage += search_direction * self.fuzzy_pid.step_size
            search_voltage = round(search_voltage, 2)

            # 检查是否超出物理范围
            if search_voltage < self.min_voltage or search_voltage > self.max_voltage:
                print(f"搜索电压超出物理范围: {search_voltage:.2f}kV")
                break

            # 设置电压
            if not self.hv_controller.set_voltage_kv(search_voltage):
                print(f"电压设置失败: {search_voltage:.2f}kV")
                break

            self.current_voltage_kv = search_voltage
            step_count += 1

            print(f"搜索步骤 {step_count}/{max_steps}: {search_voltage:.2f}kV")

            # 等待稳定
            time.sleep(self.fuzzy_pid.step_time)

            # 检查是否找到目标模式
            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            if match_rate >= 0.5:  # 找到目标模式
                print(f"找到目标模式，匹配率: {match_rate:.1%}")

                # 执行边界验证
                self._boundary_verification()
                break

            # 检查是否已到达目标边界
            if (search_direction > 0 and search_voltage >= target_boundary) or \
               (search_direction < 0 and search_voltage <= target_boundary):
                print(f"已到达目标边界: {search_voltage:.2f}kV")

                # 如果到达边界仍未找到目标模式，执行区间重检
                if match_rate < 0.5:
                    print("到达边界仍未找到目标模式，执行区间重检")
                    self._range_recheck()
                break

        # 恢复原始参数
        self.fuzzy_pid.step_size = original_step_size
        self.fuzzy_pid.step_time = original_step_time

        print("PID模糊控制调节完成")

    def _enhanced_stability_check(self):
        """增强版稳定检查（5秒窗口）"""
        if self.target_mode is None:
            return

        # 统计最近5秒内的检测结果
        window_start = time.time() - 5.0
        target_count = 0
        total_count = 0

        # 记录每次检测的时间戳和模式
        detection_records = []

        for detection in self.detection_history:
            if detection['timestamp'] >= window_start:
                if not detection.get('transient_error', False):
                    detected_mode = detection['detected_mode']
                    confidence = detection['confidence']

                    if detected_mode != 'none':
                        total_count += 1
                        detection_records.append((detection['timestamp'], detected_mode))
                        if detected_mode == self.target_mode:
                            target_count += 1

        if total_count > 0:
            current_match_rate = target_count / total_count
            print(f"[稳定检查] 匹配率={current_match_rate:.1%} ({target_count}/{total_count})")

            # 更新最佳匹配率（只有当当前匹配率更高时才更新）
            if current_match_rate > self.best_match_rate:
                self.best_match_rate = current_match_rate
                self.best_match_voltage = self.current_voltage_kv
                print(f"[稳定检查] 更新匹配度第一: {self.best_match_rate:.1%} @ {self.best_match_voltage:.2f}kV")

                # 执行5秒统计，更新最佳匹配电压
                self._update_best_match_voltage()

            # 稳定判断（基于新需求：匹配度≥90%稳定，匹配度≤80%不稳定）
            # 根据新需求：匹配度≥90%→保持当前电压，匹配度≤80%→重新执行流程5
            print(f"[稳定检查] 匹配度={current_match_rate:.1%} (阈值: 稳定≥90%, 不稳定≤80%)")

            if current_match_rate >= 0.9:  # 90%以上
                print(f"[稳定检查] 系统稳定 (匹配度在90%以上)")
                self.stable_state = True

                # 如果当前匹配率高于历史最佳，更新最佳匹配记录
                if current_match_rate > self.best_match_rate:
                    self.best_match_rate = current_match_rate
                    self.best_match_voltage = self.current_voltage_kv
                    print(f"[稳定检查] 更新匹配度第一: {self.best_match_rate:.1%} @ {self.best_match_voltage:.2f}kV")

            elif current_match_rate <= 0.8:  # 80%以下
                print(f"[稳定检查] 系统不稳定 (匹配度低于80%)，重新执行流程5...")
                self.stable_state = False

                # 重新执行流程5（锁定新边界 + 最优电压点）
                self._restart_control_optimization()

            else:  # 80%-90%之间
                print(f"[稳定检查] 系统临界状态 (匹配度{current_match_rate:.1%})，保持当前状态")
                # 不改变稳定状态，维持原状

            # 更新GUI
            if self.gui:
                self.gui.update_stability_state(self.stable_state, current_match_rate)

        else:
            print(f"[稳定检查] 无有效检测数据")

    def _dynamic_maintenance(self):
        """动态维持状态（PID模糊控制抗干扰）
        根据新需求两种情况：
        1. 监测结果仍包含目标模式（电压处于目标模式区间内）→ 小范围探索更新边界
        2. 监测结果不包含目标模式（电压偏离目标模式区间）→ 应急调节快速逼近
        容错机制：连续调节50次未出现目标模式，触发区间重检
        """
        if self.target_mode is None:
            return

        print("\n=== 进入动态维持状态 ===")

        # 检查当前电压是否在目标模式区间内
        mode_info = self.mode_voltage_ranges.get(self.target_mode)
        if not mode_info:
            print(f"错误: 目标模式 '{self.target_mode}' 无电压范围信息")
            return

        current_voltage = self.current_voltage_kv
        in_range = mode_info['min'] <= current_voltage <= mode_info['max']

        # 检查最近检测结果是否包含目标模式
        recent_target_detected = False
        recent_window_start = time.time() - 2.0  # 最近2秒
        target_count = 0
        total_count = 0

        for detection in self.detection_history:
            if detection['timestamp'] >= recent_window_start:
                if not detection.get('transient_error', False):
                    detected_mode = detection['detected_mode']
                    confidence = detection['confidence']
                    if detected_mode != 'none':
                        total_count += 1
                        if detected_mode == self.target_mode:
                            target_count += 1

        if total_count > 0:
            recent_match_rate = target_count / total_count
            recent_target_detected = recent_match_rate > 0.1  # 至少10%的检测结果是目标模式
            print(f"最近检测统计: 目标模式占比={recent_match_rate:.1%} (总数={total_count})")

        # 判断情况
        if recent_target_detected and in_range:
            print("情况a: 仍在目标模式区间内，执行小范围探索更新边界")
            self._small_range_exploration()
        else:
            print("情况b: 偏离目标模式区间，执行应急调节快速逼近")
            self._emergency_adjustment()

    def _small_range_exploration(self):
        """小范围探索更新边界（情况a）"""
        print("执行小范围探索...")

        mode_info = self.mode_voltage_ranges[self.target_mode]
        current_voltage = self.current_voltage_kv

        # 小范围探索参数：±0.5kV范围，小步长(0.1-0.2kV)，通过模糊控制动态调节
        search_range = 0.5  # kV
        min_voltage = max(self.min_voltage, current_voltage - search_range)
        max_voltage = min(self.max_voltage, current_voltage + search_range)

        print(f"小范围探索: {min_voltage:.2f}kV - {max_voltage:.2f}kV (当前: {current_voltage:.2f}kV)")

        # 保存原始步长步时
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 设置小范围探索参数
        self.fuzzy_pid.step_size = 0.15  # 中等步长
        self.fuzzy_pid.step_time = 0.5   # 中等步时

        # 记录边界变化
        left_boundary = None
        right_boundary = None

        # 向左探索边界
        left_voltage = current_voltage
        left_count = 0
        max_left_steps = 20  # 最大向左步数

        while left_voltage >= min_voltage and left_count < max_left_steps:
            if not self.hv_controller.set_voltage_kv(left_voltage):
                break

            self.current_voltage_kv = left_voltage
            time.sleep(self.fuzzy_pid.step_time)

            # 检查匹配率
            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            print(f"  左探 {left_voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

            if match_rate < 0.5:  # 匹配率低于50%，认为超出边界
                left_boundary = left_voltage
                print(f"  找到左边界: {left_boundary:.2f}kV")
                break

            left_voltage -= self.fuzzy_pid.step_size
            left_voltage = round(left_voltage, 2)
            left_count += 1

        # 向右探索边界
        right_voltage = current_voltage + self.fuzzy_pid.step_size
        right_count = 0
        max_right_steps = 20  # 最大向右步数

        while right_voltage <= max_voltage and right_count < max_right_steps:
            if not self.hv_controller.set_voltage_kv(right_voltage):
                break

            self.current_voltage_kv = right_voltage
            time.sleep(self.fuzzy_pid.step_time)

            # 检查匹配率
            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            print(f"  右探 {right_voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

            if match_rate < 0.5:  # 匹配率低于50%，认为超出边界
                right_boundary = right_voltage
                print(f"  找到右边界: {right_boundary:.2f}kV")
                break

            right_voltage += self.fuzzy_pid.step_size
            right_voltage = round(right_voltage, 2)
            right_count += 1

        # 更新模式电压范围
        if left_boundary is not None:
            mode_info['min'] = max(mode_info['min'], left_boundary + self.fuzzy_pid.step_size)
        if right_boundary is not None:
            mode_info['max'] = min(mode_info['max'], right_boundary - self.fuzzy_pid.step_size)

        print(f"更新后电压范围: {mode_info['min']:.2f}kV - {mode_info['max']:.2f}kV")

        # 在新区间内寻找最优电压点
        self._find_optimal_voltage_in_range(mode_info['min'], mode_info['max'])

        # 恢复原始参数
        self.fuzzy_pid.step_size = original_step_size
        self.fuzzy_pid.step_time = original_step_time

        print("小范围探索完成")

    def _emergency_adjustment(self):
        """应急调节快速逼近（情况b）"""
        print("执行应急调节快速逼近...")

        mode_info = self.mode_voltage_ranges[self.target_mode]

        # 以目标模式区间中点为临时靶点
        target_midpoint = (mode_info['min'] + mode_info['max']) / 2
        current_voltage = self.current_voltage_kv

        print(f"当前电压: {current_voltage:.2f}kV, 目标中点: {target_midpoint:.2f}kV")

        # 保存原始参数
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 设置应急调节参数：大步长(0.5-1kV)，短步时(0.2-0.3秒)
        self.fuzzy_pid.step_size = 0.7  # 大步长
        self.fuzzy_pid.step_time = 0.25  # 短步时

        # 容错机制计数
        adjustment_count = 0
        max_adjustments = 50

        while adjustment_count < max_adjustments:
            # 计算电压差值
            voltage_diff = target_midpoint - current_voltage

            # 确定调节方向
            if abs(voltage_diff) < 0.05:  # 接近目标
                print(f"已接近目标中点，差值: {voltage_diff:.2f}kV")
                break

            # 计算调节量（带PID模糊控制）
            adjustment, _, _ = self.fuzzy_pid.calculate_adjustment_enhanced(
                target_midpoint, current_voltage, 0, 0
            )

            # 限制调节幅度
            adjustment = max(-self.fuzzy_pid.step_size, min(self.fuzzy_pid.step_size, adjustment))

            new_voltage = current_voltage + adjustment
            new_voltage = max(self.min_voltage, min(self.max_voltage, new_voltage))

            # 设置电压
            if not self.hv_controller.set_voltage_kv(new_voltage):
                print("电压设置失败")
                break

            self.current_voltage_kv = new_voltage
            adjustment_count += 1

            print(f"应急调节 {adjustment_count}/{max_adjustments}: {adjustment:+.2f}kV -> {new_voltage:.2f}kV")

            # 等待稳定
            time.sleep(self.fuzzy_pid.step_time)

            # 检查是否找到目标模式
            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            if match_rate >= 0.5:  # 找到目标模式
                print(f"找到目标模式，匹配率: {match_rate:.1%}")
                # 执行小范围探索更新边界
                self._small_range_exploration()
                break

            current_voltage = new_voltage

        if adjustment_count >= max_adjustments:
            print(f"连续调节{max_adjustments}次未找到目标模式，触发区间重检")
            self._range_recheck()

        # 恢复原始参数
        self.fuzzy_pid.step_size = original_step_size
        self.fuzzy_pid.step_time = original_step_time

        print("应急调节完成")

    def _find_optimal_voltage_in_range(self, min_v, max_v):
        """在给定范围内寻找最优电压点（匹配率最高）"""
        print(f"在范围内寻找最优电压点: {min_v:.2f}kV - {max_v:.2f}kV")

        original_voltage = self.current_voltage_kv
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 设置精细搜索参数
        self.fuzzy_pid.step_size = 0.1  # 小步长
        self.fuzzy_pid.step_time = 0.5  # 中等步时

        search_voltages = []
        match_rates = []

        # 以0.2kV步长遍历范围
        step = 0.2
        voltage = min_v

        while voltage <= max_v:
            if not self.hv_controller.set_voltage_kv(voltage):
                print(f"电压设置失败: {voltage:.2f}kV")
                break

            self.current_voltage_kv = voltage
            time.sleep(self.fuzzy_pid.step_time)

            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            search_voltages.append(voltage)
            match_rates.append(match_rate)

            print(f"  电压 {voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

            voltage += step
            voltage = round(voltage, 2)

        # 找到最优电压点
        if match_rates:
            best_idx = match_rates.index(max(match_rates))
            best_voltage = search_voltages[best_idx]
            best_match_rate = match_rates[best_idx]

            # 设置到最优电压点
            if self.hv_controller.set_voltage_kv(best_voltage):
                self.current_voltage_kv = best_voltage
                self.best_match_rate = best_match_rate
                self.best_match_voltage = best_voltage

                # 更新模式电压范围中的最优电压点
                if self.target_mode in self.mode_voltage_ranges:
                    self.mode_voltage_ranges[self.target_mode]['optimal'] = best_voltage

                print(f"找到最优电压点: {best_voltage:.2f}kV (匹配率: {best_match_rate:.1%})")
            else:
                print(f"无法设置到最优电压点: {best_voltage:.2f}kV")
                # 恢复到原始电压
                self.hv_controller.set_voltage_kv(original_voltage)
                self.current_voltage_kv = original_voltage
        else:
            print("未找到有效匹配点")
            # 恢复到原始电压
            self.hv_controller.set_voltage_kv(original_voltage)
            self.current_voltage_kv = original_voltage

        # 恢复原始参数
        self.fuzzy_pid.step_size = original_step_size
        self.fuzzy_pid.step_time = original_step_time

    def _range_recheck(self):
        """区间重检（容错机制）"""
        print("执行区间重检...")

        mode_info = self.mode_voltage_ranges[self.target_mode]

        # 以小步长遍历原目标模式区间，更新边界
        original_voltage = self.current_voltage_kv
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 设置小步长精细遍历
        self.fuzzy_pid.step_size = 0.1
        self.fuzzy_pid.step_time = 0.5

        min_v = mode_info['min']
        max_v = mode_info['max']

        print(f"重检区间: {min_v:.2f}kV - {max_v:.2f}kV")

        # 遍历区间，更新边界
        left_boundary = min_v
        right_boundary = max_v

        # 从左向右检查边界
        voltage = min_v
        while voltage <= max_v:
            if not self.hv_controller.set_voltage_kv(voltage):
                break

            self.current_voltage_kv = voltage
            time.sleep(self.fuzzy_pid.step_time)

            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            print(f"  重检 {voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

            if match_rate >= 0.5:  # 找到有效边界
                left_boundary = voltage
                break

            voltage += self.fuzzy_pid.step_size
            voltage = round(voltage, 2)

        # 从右向左检查边界
        voltage = max_v
        while voltage >= min_v:
            if not self.hv_controller.set_voltage_kv(voltage):
                break

            self.current_voltage_kv = voltage
            time.sleep(self.fuzzy_pid.step_time)

            match_rate = self._quick_match_rate_check(duration=self.fuzzy_pid.step_time)
            print(f"  重检 {voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

            if match_rate >= 0.5:  # 找到有效边界
                right_boundary = voltage
                break

            voltage -= self.fuzzy_pid.step_size
            voltage = round(voltage, 2)

        # 更新电压范围
        if left_boundary < right_boundary:
            mode_info['min'] = left_boundary
            mode_info['max'] = right_boundary
            print(f"更新后区间: {left_boundary:.2f}kV - {right_boundary:.2f}kV")

            # 在新区间内寻找最优电压点
            self._find_optimal_voltage_in_range(left_boundary, right_boundary)
        else:
            print("区间重检失败，保持原区间")

        # 恢复原始参数
        self.fuzzy_pid.step_size = original_step_size
        self.fuzzy_pid.step_time = original_step_time

        # 恢复到原始电压
        self.hv_controller.set_voltage_kv(original_voltage)
        self.current_voltage_kv = original_voltage

        print("区间重检完成")

    def _update_best_match_voltage(self):
        """更新最佳匹配电压（5秒统计）"""
        if self.target_mode is None:
            return

        print(f"[最佳匹配] 执行5秒统计更新最佳匹配电压...")

        # 统计当前电压下的模式分布
        window_start = time.time() - 5.0
        mode_counts = defaultdict(int)
        total_count = 0

        for detection in self.detection_history:
            if detection['timestamp'] >= window_start:
                if not detection.get('transient_error', False):
                    detected_mode = detection['detected_mode']
                    confidence = detection['confidence']

                    if detected_mode != 'none':
                        mode_counts[detected_mode] += 1
                        total_count += 1

        if total_count > 0:
            target_count = mode_counts.get(self.target_mode, 0)
            current_match_rate = target_count / total_count

            # 如果当前匹配率更高，更新最佳记录
            if current_match_rate > self.best_match_rate:
                self.best_match_rate = current_match_rate
                self.best_match_voltage = self.current_voltage_kv
                print(f"[最佳匹配] 更新最佳匹配: {self.best_match_rate:.1%} @ {self.best_match_voltage:.2f}kV")

                # 更新模式电压范围中的最优电压点
                if self.target_mode in self.mode_voltage_ranges:
                    self.mode_voltage_ranges[self.target_mode]['optimal'] = self.best_match_voltage

    def _restart_control_optimization(self):
        """重新执行PID模糊控制算法
        通过控制电压步长并监测步时结果，向两边先后进行遍历操作，
        使电压值停在该目标模式对应电压范围内匹配度最高的范围内
        """
        print("\n=== 重新执行PID模糊控制算法 ===")

        try:
            if self.target_mode not in self.mode_voltage_ranges:
                print(f"错误: 目标模式 '{self.target_mode}' 不在模式电压范围中")
                return

            mode_info = self.mode_voltage_ranges[self.target_mode]

            # 保存当前电压和参数
            original_voltage = self.current_voltage_kv
            original_step_size = self.fuzzy_pid.step_size
            original_step_time = self.fuzzy_pid.step_time
            original_kp_base = self.fuzzy_pid.kp_base
            original_ki_base = self.fuzzy_pid.ki_base
            original_kd_base = self.fuzzy_pid.kd_base
            original_kp = self.fuzzy_pid.kp
            original_ki = self.fuzzy_pid.ki
            original_kd = self.fuzzy_pid.kd

            # 设置流程5 PID模糊控制遍历参数（符合新需求）
            # PID参数初始值：P=0.5，I=0.2，D=0.1
            self.fuzzy_pid.kp_base = 0.5
            self.fuzzy_pid.ki_base = 0.2
            self.fuzzy_pid.kd_base = 0.1
            self.fuzzy_pid.kp = 0.5
            self.fuzzy_pid.ki = 0.2
            self.fuzzy_pid.kd = 0.1
            # 遍历参数：初始步长0.3kV，步时0.5秒（符合新需求）
            self.fuzzy_pid.step_size = 0.3
            self.fuzzy_pid.step_time = 0.5

            print(f"目标模式: {self.target_mode}")
            print(f"电压范围: {mode_info['min']:.2f}kV - {mode_info['max']:.2f}kV")
            print(f"当前电压: {original_voltage:.2f}kV")
            print(f"当前匹配度: {self.best_match_rate:.1%}")

            # 使用模糊控制自适应调节搜索参数
            # 计算与最优电压点的差值
            voltage_difference = abs(original_voltage - mode_info['optimal'])

            # 基于历史数据计算模式一致性
            mode_consistent_count = 1
            if hasattr(self, 'detection_history') and len(self.detection_history) > 0:
                # 检查最近5次有效检测的模式一致性
                recent_modes = []
                for detection in list(self.detection_history)[-10:]:  # 最近10次检测
                    if not detection.get('transient_error', False):
                        detected_mode = detection.get('detected_mode', 'none')
                        confidence = detection.get('confidence', 0)
                        if detected_mode != 'none':
                            recent_modes.append(detected_mode)

                if len(recent_modes) >= 3:
                    # 检查模式一致性
                    if all(m == recent_modes[0] for m in recent_modes[:3]):
                        mode_consistent_count = 3
                    elif len(recent_modes) >= 5 and all(m == recent_modes[0] for m in recent_modes[:5]):
                        mode_consistent_count = 5

            # 计算电压变化率（基于历史电压记录）
            voltage_change_rate = 0.5  # 默认值
            if hasattr(self.fuzzy_pid, 'voltage_history') and len(self.fuzzy_pid.voltage_history) >= 3:
                recent_voltages = list(self.fuzzy_pid.voltage_history)[-3:]
                voltage_change_rate = abs(recent_voltages[-1] - recent_voltages[0]) / 3 if len(recent_voltages) >= 3 else 0.5

            boundary_drift_rate = self.fuzzy_pid.boundary_drift_rate

            # 使用模糊控制器调节步长步时
            step_size, step_time = self.fuzzy_pid.adapt_step_parameters_enhanced(
                mode_consistent_count, voltage_difference, voltage_change_rate, boundary_drift_rate
            )

            # 对于精细搜索，进一步减小步长（但保持最小步长限制）
            step_size = max(self.fuzzy_pid.min_step, step_size * 0.5)
            step_time = min(self.fuzzy_pid.max_step_time, step_time * 1.2)

            self.fuzzy_pid.step_size = step_size
            self.fuzzy_pid.step_time = step_time

            print(f"模糊控制调节搜索参数: 步长={step_size:.3f}kV, 步时={step_time:.2f}s")
            print(f"模式一致性计数: {mode_consistent_count}, 电压变化率: {voltage_change_rate:.2f}kV/s")

            # 向两边进行遍历搜索
            search_results = []  # (电压, 匹配率)
            left_boundary_voltage = None
            right_boundary_voltage = None

            # 边界搜索专用参数（符合新需求：边界遍历步长≤0.25kV，步时≥1秒）
            boundary_step_size = min(0.25, step_size * 0.5)  # 不超过0.25kV
            boundary_step_time = max(1.0, step_time * 1.5)   # 至少1秒
            print(f"边界搜索参数: 步长={boundary_step_size:.3f}kV, 步时={boundary_step_time:.2f}s")

            # 先向左（减小电压）搜索
            print(f"向左搜索...")
            left_search_voltage = original_voltage
            # 搜索整个模式范围，但至少搜索2kV范围
            left_boundary = max(mode_info['min'], original_voltage - 2.0)

            while left_search_voltage >= left_boundary:
                # 设置电压
                if not self.hv_controller.set_voltage_kv(left_search_voltage):
                    print(f"电压设置失败: {left_search_voltage:.2f}kV，跳过此点")
                    break

                self.current_voltage_kv = left_search_voltage

                # 等待稳定（使用边界步时，至少1秒）
                time.sleep(boundary_step_time)

                # 统计匹配率（使用边界步时，提高准确性）
                match_rate = self._quick_match_rate_check(duration=boundary_step_time)
                search_results.append((left_search_voltage, match_rate))

                print(f"  电压 {left_search_voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

                # 检查模式是否改变：如果匹配率低于50%，认为已超出目标模式范围，停止遍历，记录当前电压为左边界
                if match_rate < 0.5:
                    print(f"  匹配率低于50%，记录电压 {left_search_voltage:.2f}kV 为左边界，停止向左搜索")
                    left_boundary_voltage = left_search_voltage
                    break

                # 移动到下一个点（使用边界步长，不超过0.25kV）
                left_search_voltage -= boundary_step_size
                left_search_voltage = round(left_search_voltage, 2)

            # 向右（增加电压）搜索
            print(f"向右搜索...")
            right_search_voltage = original_voltage + boundary_step_size  # 从下一个点开始，使用边界步长
            # 搜索整个模式范围，但至少搜索2kV范围
            right_boundary = min(mode_info['max'], original_voltage + 2.0)

            while right_search_voltage <= right_boundary:
                # 设置电压
                if not self.hv_controller.set_voltage_kv(right_search_voltage):
                    print(f"电压设置失败: {right_search_voltage:.2f}kV，跳过此点")
                    break

                self.current_voltage_kv = right_search_voltage

                # 等待稳定（使用边界步时，至少1秒）
                time.sleep(boundary_step_time)

                # 统计匹配率（使用边界步时）
                match_rate = self._quick_match_rate_check(duration=boundary_step_time)
                search_results.append((right_search_voltage, match_rate))

                print(f"  电压 {right_search_voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

                # 检查模式是否改变：如果匹配率低于50%，认为已超出目标模式范围，停止遍历，记录当前电压为右边界
                if match_rate < 0.5:
                    print(f"  匹配率低于50%，记录电压 {right_search_voltage:.2f}kV 为右边界，停止向右搜索")
                    right_boundary_voltage = right_search_voltage
                    break

                # 移动到下一个点（使用边界步长，不超过0.25kV）
                right_search_voltage += boundary_step_size
                right_search_voltage = round(right_search_voltage, 2)

            # 根据新需求：在锁定目标模式电压范围后，在该范围内以0.2kV步长遍历
            # 确定边界范围
            if left_boundary_voltage is None:
                # 没有找到左边界，使用搜索的最小电压
                left_boundary_voltage = min([v for v, _ in search_results]) if search_results else original_voltage - 1.0
            if right_boundary_voltage is None:
                # 没有找到右边界，使用搜索的最大电压
                right_boundary_voltage = max([v for v, _ in search_results]) if search_results else original_voltage + 1.0

            # 确保边界有效且左边界<右边界
            left_boundary_voltage = max(self.min_voltage, left_boundary_voltage)
            right_boundary_voltage = min(self.max_voltage, right_boundary_voltage)

            if left_boundary_voltage < right_boundary_voltage:
                print(f"锁定目标模式电压范围: {left_boundary_voltage:.2f}kV - {right_boundary_voltage:.2f}kV")
                print("在该范围内以0.2kV步长遍历，计算每个电压点的匹配度...")

                # 以0.2kV步长遍历边界范围
                fine_search_results = []
                fine_step = 0.2
                fine_voltage = left_boundary_voltage

                while fine_voltage <= right_boundary_voltage:
                    if not self.hv_controller.set_voltage_kv(fine_voltage):
                        print(f"电压设置失败: {fine_voltage:.2f}kV，跳过此点")
                        break

                    self.current_voltage_kv = fine_voltage
                    time.sleep(boundary_step_time)  # 使用边界步时进行稳定

                    match_rate = self._quick_match_rate_check(duration=boundary_step_time)
                    fine_search_results.append((fine_voltage, match_rate))

                    print(f"  精细遍历 {fine_voltage:.2f}kV -> 匹配率 {match_rate:.1%}")

                    fine_voltage += fine_step
                    fine_voltage = round(fine_voltage, 2)

                # 如果精细遍历有结果，使用精细遍历的结果
                if fine_search_results:
                    search_results = fine_search_results
                    print(f"精细遍历完成，共测试{len(fine_search_results)}个电压点")
                else:
                    print("精细遍历无结果，使用原始搜索结果")
            else:
                print(f"边界无效: {left_boundary_voltage:.2f}kV >= {right_boundary_voltage:.2f}kV，跳过精细遍历")

            # 找到匹配度最高的电压
            if search_results:
                best_voltage, best_match_rate = max(search_results, key=lambda x: x[1])

                # 设置到最佳电压点
                if self.hv_controller.set_voltage_kv(best_voltage):
                    self.current_voltage_kv = best_voltage

                    print(f"\n找到最佳电压点: {best_voltage:.2f}kV (匹配率: {best_match_rate:.1%})")

                    # 执行5秒统计，更新匹配度第一
                    print("执行5秒统计更新匹配度第一...")
                    time.sleep(5.0)

                    # 执行5秒统计，更新最佳匹配记录
                    self._update_best_match_voltage()

                    # 如果5秒统计的匹配率更高，使用新的匹配率；否则使用搜索中找到的最佳匹配率
                    if self.best_match_rate < best_match_rate:
                        self.best_match_rate = best_match_rate
                        self.best_match_voltage = best_voltage
                        print(f"更新匹配度第一（基于搜索）: {self.best_match_rate:.1%} @ {self.best_match_voltage:.2f}kV")
                    else:
                        print(f"更新匹配度第一（基于5秒统计）: {self.best_match_rate:.1%} @ {self.best_match_voltage:.2f}kV")

                    # 更新模式电压范围中的最优电压点
                    if self.target_mode in self.mode_voltage_ranges:
                        self.mode_voltage_ranges[self.target_mode]['optimal'] = self.best_match_voltage
                else:
                    print(f"无法设置到最佳电压点: {best_voltage:.2f}kV，保持原电压")
                    best_voltage = original_voltage
                    best_match_rate = self.best_match_rate
            else:
                print("未找到更好的匹配点，保持原电压")
                best_voltage = original_voltage
                best_match_rate = self.best_match_rate

            # 恢复原始参数
            self.fuzzy_pid.step_size = original_step_size
            self.fuzzy_pid.step_time = original_step_time
            self.fuzzy_pid.kp_base = original_kp_base
            self.fuzzy_pid.ki_base = original_ki_base
            self.fuzzy_pid.kd_base = original_kd_base
            self.fuzzy_pid.kp = original_kp
            self.fuzzy_pid.ki = original_ki
            self.fuzzy_pid.kd = original_kd

            # 再次执行稳定判断（将在下一次检查时进行）
            self.stable_state = False
            self.last_stability_check = time.time() - self.stability_check_interval + 1  # 提前一点触发下次检查

            # 标记步骤6已完成，匹配度第一已记录
            self.step6_pid_fuzzy_completed = True
            self.best_match_recorded = True
            print(f"步骤6 PID模糊控制算法执行完成，匹配度第一已记录: {self.best_match_rate:.1%} @ {self.best_match_voltage:.2f}kV")

        except Exception as e:
            print(f"PID模糊控制算法执行出错: {e}")
            import traceback
            traceback.print_exc()
            # 恢复参数
            if 'original_step_size' in locals() and 'original_step_time' in locals():
                self.fuzzy_pid.step_size = original_step_size
                self.fuzzy_pid.step_time = original_step_time
            if 'original_kp_base' in locals():
                self.fuzzy_pid.kp_base = original_kp_base
                self.fuzzy_pid.ki_base = original_ki_base
                self.fuzzy_pid.kd_base = original_kd_base
                self.fuzzy_pid.kp = original_kp
                self.fuzzy_pid.ki = original_ki
                self.fuzzy_pid.kd = original_kd

    def _quick_match_rate_check(self, duration=0.5):
        """快速匹配率检查（用于搜索过程中的评估）
        统计最近duration时间内的检测结果，计算目标模式匹配率
        排除瞬时误判和'none'模式，置信度不影响统计
        """
        if self.target_mode is None:
            return 0.0

        window_end = time.time()
        window_start = window_end - duration
        target_count = 0
        total_count = 0

        # 使用锁保护detection_history访问
        with self.detection_lock:
            # 遍历检测历史，统计时间窗口内的有效检测
            for detection in self.detection_history:
                timestamp = detection.get('timestamp', 0)
                # 只统计时间窗口内的检测
                if timestamp < window_start:
                    continue
                if timestamp > window_end:
                    # detection_history按时间顺序添加，后续的检测时间戳更大，可以提前结束
                    break

                # 跳过瞬时误判
                if detection.get('transient_error', False):
                    continue

                detected_mode = detection.get('detected_mode', 'none')
                if detected_mode != 'none':
                    total_count += 1
                    if detected_mode == self.target_mode:
                        target_count += 1

        if total_count > 0:
            return target_count / total_count
        else:
            return 0.0

    def _directional_adjustment_for_mode_switch(self, target_mode_name, target_optimal_voltage):
        """模式切换后的定向电压调节（实现流程7的"先逼近后遍历"逻辑）

        参数：
            target_mode_name: 新目标模式名称
            target_optimal_voltage: 新目标模式的历史最优电压点

        返回：
            bool: 是否成功找到目标模式（匹配度≥50%）
            float: 找到目标模式时的电压值
        """
        print(f"\n=== 开始定向调节到目标模式 '{target_mode_name}' ===")
        print(f"目标最优电压: {target_optimal_voltage:.2f}kV")
        print(f"当前电压: {self.current_voltage_kv:.2f}kV")

        # 计算当前电压与目标最优电压的差值
        voltage_diff = target_optimal_voltage - self.current_voltage_kv
        voltage_diff_abs = abs(voltage_diff)

        # 保存原始参数
        original_step_size = self.fuzzy_pid.step_size
        original_step_time = self.fuzzy_pid.step_time

        # 根据差值设置调节参数（符合流程7要求）
        if voltage_diff_abs > 0.5:
            # 差值＞0.5kV→步长0.5kV、步时0.3秒快速逼近
            step_size = 0.5
            step_time = 0.3
            print(f"差值>{voltage_diff_abs:.2f}kV>0.5kV，采用快速逼近: 步长={step_size}kV, 步时={step_time}s")
        else:
            # 差值≤0.5kV→步长0.1kV、步时0.5秒精准遍历
            step_size = 0.1
            step_time = 0.5
            print(f"差值{voltage_diff_abs:.2f}kV≤0.5kV，采用精准遍历: 步长={step_size}kV, 步时={step_time}s")

        # 设置模糊PID控制器的步长步时
        self.fuzzy_pid.step_size = step_size
        self.fuzzy_pid.step_time = step_time

        # 设置临时目标模式用于匹配度检查
        temp_target = self.target_mode  # 保存当前目标模式
        self.target_mode = target_mode_name

        try:
            # 确定调节方向
            direction = 1 if voltage_diff > 0 else -1

            # 开始调节过程
            current_voltage = self.current_voltage_kv
            step_count = 0
            max_steps = int(voltage_diff_abs / step_size) + 10  # 加上一些容错步数

            print(f"开始定向调节，方向: {'增加' if direction > 0 else '减少'}电压，总步数估计: {max_steps}")

            while step_count < max_steps:
                # 计算下一步电压
                next_voltage = current_voltage + direction * step_size
                next_voltage = round(next_voltage, 2)

                # 检查电压是否超出总范围
                if next_voltage < self.min_voltage or next_voltage > self.max_voltage:
                    print(f"电压超出总范围: {next_voltage:.2f}kV，停止调节")
                    break

                # 设置电压
                if not self.hv_controller.set_voltage_kv(next_voltage):
                    print(f"电压设置失败: {next_voltage:.2f}kV")
                    break

                self.current_voltage_kv = next_voltage
                step_count += 1

                print(f"调节步骤 {step_count}/{max_steps}: 电压={next_voltage:.2f}kV")

                # 等待稳定（使用设置的步时）
                time.sleep(step_time)

                # 检查是否到达目标电压附近
                if abs(next_voltage - target_optimal_voltage) < step_size * 0.5:
                    print(f"已接近目标最优电压 {target_optimal_voltage:.2f}kV")

                # 检查匹配度（使用更长的检查时间以提高准确性）
                match_rate = self._quick_match_rate_check(duration=step_time * 1.5)
                print(f"  当前匹配度: {match_rate:.1%}")

                # 如果匹配度≥50%，认为已找到目标模式
                if match_rate >= 0.5:
                    print(f"✓ 找到目标模式 '{target_mode_name}'，匹配度={match_rate:.1%}，电压={next_voltage:.2f}kV")

                    # 恢复原始参数
                    self.fuzzy_pid.step_size = original_step_size
                    self.fuzzy_pid.step_time = original_step_time

                    # 恢复目标模式（将在调用者中正式设置）
                    self.target_mode = temp_target

                    return True, next_voltage

                # 更新当前电压
                current_voltage = next_voltage

                # 检查是否已到达或超过目标电压
                if (direction > 0 and current_voltage >= target_optimal_voltage) or \
                   (direction < 0 and current_voltage <= target_optimal_voltage):
                    print(f"已到达目标最优电压附近: {current_voltage:.2f}kV")

                    # 在目标电压点进行更长时间的匹配度检查
                    match_rate = self._quick_match_rate_check(duration=1.0)
                    print(f"在目标电压点检查匹配度: {match_rate:.1%}")

                    if match_rate >= 0.5:
                        print(f"✓ 在目标电压点找到目标模式，匹配度={match_rate:.1%}")

                        # 恢复原始参数
                        self.fuzzy_pid.step_size = original_step_size
                        self.fuzzy_pid.step_time = original_step_time

                        # 恢复目标模式
                        self.target_mode = temp_target

                        return True, current_voltage
                    else:
                        print(f"在目标电压点未找到目标模式，匹配度={match_rate:.1%}")
                        # 继续小范围搜索
                        break

            # 如果到达目标电压仍未找到，执行小范围搜索
            print("在定向调节路径上未找到目标模式，执行小范围搜索...")

            # 以当前电压为中心，进行小范围搜索
            search_range = 1.0  # 搜索范围±1kV
            search_step = 0.1   # 搜索步长0.1kV

            search_start = max(self.min_voltage, current_voltage - search_range)
            search_end = min(self.max_voltage, current_voltage + search_range)

            print(f"小范围搜索: {search_start:.2f}kV - {search_end:.2f}kV")

            # 先向左搜索
            search_voltage = current_voltage
            while search_voltage >= search_start:
                if not self.hv_controller.set_voltage_kv(search_voltage):
                    break

                self.current_voltage_kv = search_voltage
                time.sleep(0.5)  # 等待稳定

                match_rate = self._quick_match_rate_check(duration=0.5)
                print(f"  搜索电压 {search_voltage:.2f}kV -> 匹配度 {match_rate:.1%}")

                if match_rate >= 0.5:
                    print(f"✓ 在小范围搜索中找到目标模式，匹配度={match_rate:.1%}，电压={search_voltage:.2f}kV")

                    # 恢复原始参数
                    self.fuzzy_pid.step_size = original_step_size
                    self.fuzzy_pid.step_time = original_step_time

                    # 恢复目标模式
                    self.target_mode = temp_target

                    return True, search_voltage

                search_voltage -= search_step
                search_voltage = round(search_voltage, 2)

            # 向右搜索
            search_voltage = current_voltage + search_step
            while search_voltage <= search_end:
                if not self.hv_controller.set_voltage_kv(search_voltage):
                    break

                self.current_voltage_kv = search_voltage
                time.sleep(0.5)  # 等待稳定

                match_rate = self._quick_match_rate_check(duration=0.5)
                print(f"  搜索电压 {search_voltage:.2f}kV -> 匹配度 {match_rate:.1%}")

                if match_rate >= 0.5:
                    print(f"✓ 在小范围搜索中找到目标模式，匹配度={match_rate:.1%}，电压={search_voltage:.2f}kV")

                    # 恢复原始参数
                    self.fuzzy_pid.step_size = original_step_size
                    self.fuzzy_pid.step_time = original_step_time

                    # 恢复目标模式
                    self.target_mode = temp_target

                    return True, search_voltage

                search_voltage += search_step
                search_voltage = round(search_voltage, 2)

            # 未找到目标模式
            print(f"定向调节未找到目标模式 '{target_mode_name}'")

            # 恢复原始参数
            self.fuzzy_pid.step_size = original_step_size
            self.fuzzy_pid.step_time = original_step_time

            # 恢复目标模式
            self.target_mode = temp_target

            return False, current_voltage

        except Exception as e:
            print(f"定向调节过程中出错: {e}")
            import traceback
            traceback.print_exc()

            # 恢复参数
            self.fuzzy_pid.step_size = original_step_size
            self.fuzzy_pid.step_time = original_step_time

            # 恢复目标模式
            self.target_mode = temp_target

            return False, self.current_voltage_kv

    # ==================== 模式切换应急逻辑（改进版） ====================
    def switch_target_mode(self, new_target_mode):
        """切换目标模式（应急逻辑）"""
        print(f"\n=== 紧急切换目标模式 ===")
        print(f"从 '{self.target_mode}' 切换到 '{new_target_mode}'")

        # 停止当前控制
        old_target = self.target_mode
        self.target_mode = None

        # 保留当前调节数据（补充到遍历数据库）
        print("保留当前调节过程中的电压-反馈数据并补充到数据库...")

        # 记录最近10秒内的检测结果作为增量探索数据
        recent_window_start = time.time() - 10.0  # 最近2秒
        added_samples = 0

        for detection in self.detection_history:
            if detection['timestamp'] >= recent_window_start:
                if not detection.get('transient_error', False):
                    detected_mode = detection['detected_mode']
                    confidence = detection['confidence']

                    if detected_mode != 'none':
                        # 获取检测时的电压（简化：使用当前电压或最近电压历史）
                        # 由于没有记录每个检测对应的电压，使用当前电压作为近似
                        # 实际系统中应该记录电压-检测对应关系，这里简化处理
                        voltage = self.current_voltage_kv

                        # 更新电压-模式统计
                        if detected_mode not in self.voltage_mode_stats[voltage]:
                            self.voltage_mode_stats[voltage][detected_mode] = 1
                        else:
                            self.voltage_mode_stats[voltage][detected_mode] += 1

                        # 更新模式电压范围
                        if detected_mode not in self.mode_voltage_ranges:
                            self.mode_voltage_ranges[detected_mode] = {
                                'min': voltage,
                                'max': voltage,
                                'optimal': voltage,
                                'samples': [(voltage, 1.0)],
                                'total_count': 1
                            }
                        else:
                            info = self.mode_voltage_ranges[detected_mode]
                            info['min'] = min(info['min'], voltage)
                            info['max'] = max(info['max'], voltage)
                            info['samples'].append((voltage, 1.0))
                            info['total_count'] += 1

                            # 更新最优电压点（匹配率最高的电压）
                            max_ratio = max([r for _, r in info['samples']])
                            for volt, ratio in info['samples']:
                                if ratio == max_ratio:
                                    info['optimal'] = volt
                                    break

                        added_samples += 1

        print(f"已将最近{added_samples}个检测样本补充到数据库，视作一次增量探索阶段结束")

        # 快速更新模式-电压对照表
        if new_target_mode in self.mode_voltage_ranges:
            # 使用已有的电压范围信息
            mode_info = self.mode_voltage_ranges[new_target_mode]
            print(f"使用已有电压范围: {mode_info['min']:.1f}kV - {mode_info['max']:.1f}kV")

            # 设置到最优电压点
            optimal_voltage = mode_info['optimal']
        else:
            # 如果没有历史数据，使用电压总范围中点作为初始最优电压
            optimal_voltage = (self.min_voltage + self.max_voltage) / 2
            mode_info = {
                'min': self.min_voltage,
                'max': self.max_voltage,
                'optimal': optimal_voltage,
                'samples': [],
                'total_count': 0
            }
            # 保存到模式电压范围字典中
            self.mode_voltage_ranges[new_target_mode] = mode_info
            print(f"新模式 '{new_target_mode}'，使用电压总范围中点: {optimal_voltage:.2f}kV")

        # 执行定向调节（实现流程7的"先逼近后遍历"逻辑）
        print(f"\n=== 开始定向调节寻找目标模式 '{new_target_mode}' ===")
        target_found, found_voltage = self._directional_adjustment_for_mode_switch(new_target_mode, optimal_voltage)

        if target_found:
            print(f"✓ 找到目标模式 '{new_target_mode}'，电压={found_voltage:.2f}kV")

            # 更新模糊PID控制器的模式电压范围
            self._update_fuzzy_pid_mode_ranges()

            # 重置稳定状态
            self.stable_state = False
            self.best_match_rate = 0.0
            self.best_match_voltage = found_voltage

            # 重置步骤6相关状态（新目标模式需要重新执行步骤6）
            self.step6_pid_fuzzy_completed = False
            self.best_match_recorded = False
            self.found_target_mode_voltage = found_voltage

            # 重置过滤器状态，适应新模式
            self.error_filter.reset()

            # 启动新目标模式的控制（将执行流程5锁定范围及最优匹配点）
            self.target_mode = new_target_mode
            print(f"已切换到目标模式 '{new_target_mode}'，电压: {found_voltage:.2f}kV")
            print("将执行流程5：锁定目标模式对应范围及最优匹配点")

            # 启动控制线程，_enhanced_control_loop将检测到step6_pid_fuzzy_completed=False
            # 从而自动执行流程5（PID模糊控制算法）
            control_thread = threading.Thread(target=self._enhanced_control_loop, daemon=True)
            control_thread.start()

            return True
        else:
            print(f"定向调节未找到目标模式 '{new_target_mode}'")
            print(f"注意：目标模式可能超出当前电压范围，或需要重新探索")

            # 恢复原目标模式
            self.target_mode = old_target
            return False

    # ==================== 系统控制 ====================
    def stop_control(self):
        """停止控制"""
        self.target_mode = None
        self.stable_state = False
        self.best_match_rate = 0.0
        self.best_match_voltage = None

        # 重置步骤6相关状态
        self.step6_pid_fuzzy_completed = False
        self.best_match_recorded = False
        self.found_target_mode_voltage = None

        print("控制已停止")

    def stop_system(self):
        """停止系统"""
        self.running = False
        self.exploration_active = False

        # 停止确认线程
        self.stop_confirmation_event.set()
        if self.confirmation_thread and self.confirmation_thread.is_alive():
            self.confirmation_thread.join(timeout=2)

        # 关闭所有连接
        for client in self.clients:
            try:
                client['socket'].close()
            except:
                pass
        self.clients.clear()

        if self.server_socket:
            self.server_socket.close()

        # 断开高压电源
        self.hv_controller.disconnect()

        print("系统已停止")

# ==================== GUI界面（改进版） ====================
class EnhancedControlSystemGUI:
    """增强版控制系统GUI界面"""
    def __init__(self, control_system):
        self.control_system = control_system
        control_system.gui = self  # 双向引用

        self.root = tk.Tk()
        self.root.title("PID模糊控制系统 - 增强版")
        self.root.geometry("1100x750")

        # 状态变量
        self.mode_classes = None
        self.mode_voltage_ranges = None
        self.mode_radio_buttons = []  # 存储单选按钮
        self.mode_radio_frame = None  # 单选按钮框架

        self.setup_gui()

    def setup_gui(self):
        """设置GUI界面"""
        # 主框架
        main_frame = ttk.Frame(self.root, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        # 左侧面板 - 控制（带滚动条）
        left_frame = ttk.LabelFrame(main_frame, text="控制面板", padding=10)
        left_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 在左侧面板内添加画布和滚动条
        left_canvas = tk.Canvas(left_frame)
        left_scrollbar = ttk.Scrollbar(left_frame, orient="vertical", command=left_canvas.yview)
        left_inner_frame = ttk.Frame(left_canvas)

        # 配置滚动
        left_inner_frame.bind(
            "<Configure>",
            lambda e: left_canvas.configure(scrollregion=left_canvas.bbox("all"))
        )
        left_canvas.create_window((0, 0), window=left_inner_frame, anchor="nw")
        left_canvas.configure(yscrollcommand=left_scrollbar.set)

        # 放置画布和滚动条
        left_canvas.pack(side="left", fill="both", expand=True)
        left_scrollbar.pack(side="right", fill="y")

        # 右侧面板 - 状态（带滚动条）
        right_frame = ttk.LabelFrame(main_frame, text="系统状态", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        # 在右侧面板内添加画布和滚动条
        right_canvas = tk.Canvas(right_frame)
        right_scrollbar = ttk.Scrollbar(right_frame, orient="vertical", command=right_canvas.yview)
        right_inner_frame = ttk.Frame(right_canvas)

        # 配置滚动
        right_inner_frame.bind(
            "<Configure>",
            lambda e: right_canvas.configure(scrollregion=right_canvas.bbox("all"))
        )
        right_canvas.create_window((0, 0), window=right_inner_frame, anchor="nw")
        right_canvas.configure(yscrollcommand=right_scrollbar.set)

        # 放置画布和滚动条
        right_canvas.pack(side="left", fill="both", expand=True)
        right_scrollbar.pack(side="right", fill="y")


        # 2. 模式种类显示
        mode_classes_frame = ttk.LabelFrame(left_inner_frame, text="模式种类", padding=5)
        mode_classes_frame.pack(fill=tk.X, pady=5)

        self.mode_classes_label = ttk.Label(mode_classes_frame, text="等待加载模式种类...")
        self.mode_classes_label.pack(fill=tk.X, pady=2)

        # 3. 电压范围设置
        voltage_frame = ttk.LabelFrame(left_inner_frame, text="电压操作范围", padding=5)
        voltage_frame.pack(fill=tk.X, pady=5)

        ttk.Label(voltage_frame, text="最小电压 (kV):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.min_voltage_var = tk.StringVar(value="0.0")
        ttk.Entry(voltage_frame, textvariable=self.min_voltage_var, width=10).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(voltage_frame, text="最大电压 (kV):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.max_voltage_var = tk.StringVar(value="20.0")
        ttk.Entry(voltage_frame, textvariable=self.max_voltage_var, width=10).grid(row=1, column=1, padx=5, pady=2)

        # 移除"开始电压遍历"按钮，电压遍历将作为目标控制的一部分自动执行

        # 4. 目标模式选择
        target_frame = ttk.LabelFrame(left_inner_frame, text="目标模式控制", padding=5)
        target_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        ttk.Label(target_frame, text="选择目标模式:").pack(anchor=tk.W, padx=5, pady=2)
        self.target_mode_var = tk.StringVar()

        # 创建滚动框架用于显示单选按钮
        radio_container = ttk.Frame(target_frame)
        radio_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=2)

        # 创建画布和滚动条
        canvas = tk.Canvas(radio_container)
        scrollbar = ttk.Scrollbar(radio_container, orient="vertical", command=canvas.yview)
        self.mode_radio_frame = ttk.Frame(canvas)

        # 配置滚动
        self.mode_radio_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=self.mode_radio_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 初始提示标签
        self.mode_radio_label = ttk.Label(self.mode_radio_frame, text="等待接收模式种类...")
        self.mode_radio_label.pack(pady=10)

        ttk.Button(target_frame, text="启动目标控制",
                  command=self.start_target_control).pack(pady=5)

        # 5. 模式切换
        switch_frame = ttk.LabelFrame(left_inner_frame, text="模式切换应急", padding=5)
        switch_frame.pack(fill=tk.X, pady=5)

        ttk.Label(switch_frame, text="切换目标模式:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.switch_mode_var = tk.StringVar()
        self.switch_mode_combo = ttk.Combobox(switch_frame, textvariable=self.switch_mode_var, state="readonly")
        self.switch_mode_combo.grid(row=0, column=1, padx=5, pady=2)

        ttk.Button(switch_frame, text="紧急切换模式",
                  command=self.switch_target_mode).grid(row=1, column=0, columnspan=2, pady=5)

        # 6. PID参数显示
        pid_frame = ttk.LabelFrame(left_inner_frame, text="PID参数", padding=5)
        pid_frame.pack(fill=tk.X, pady=5)

        self.pid_kp_label = ttk.Label(pid_frame, text="KP: --")
        self.pid_kp_label.pack(fill=tk.X, pady=2)

        self.pid_ki_label = ttk.Label(pid_frame, text="KI: --")
        self.pid_ki_label.pack(fill=tk.X, pady=2)

        self.pid_kd_label = ttk.Label(pid_frame, text="KD: --")
        self.pid_kd_label.pack(fill=tk.X, pady=2)

        self.step_label = ttk.Label(pid_frame, text="步长/步时: --")
        self.step_label.pack(fill=tk.X, pady=2)

        # 7. 系统控制
        system_frame = ttk.LabelFrame(left_inner_frame, text="系统控制", padding=5)
        system_frame.pack(fill=tk.X, pady=5)

        ttk.Button(system_frame, text="停止控制",
                  command=self.stop_control).pack(fill=tk.X, pady=2)
        ttk.Button(system_frame, text="退出系统",
                  command=self.quit_system).pack(fill=tk.X, pady=2)

        # ========== 右侧状态面板 ==========
        # 1. 连接状态
        conn_frame = ttk.LabelFrame(right_inner_frame, text="连接状态", padding=5)
        conn_frame.pack(fill=tk.X, pady=5)

        self.conn_status_label = ttk.Label(conn_frame, text="检测模块: 未连接")
        self.conn_status_label.pack(fill=tk.X, pady=2)

        self.hv_status_label = ttk.Label(conn_frame, text="高压电源: 未连接")
        self.hv_status_label.pack(fill=tk.X, pady=2)

        self.model_status_label = ttk.Label(conn_frame, text="模式种类: 等待接收")
        self.model_status_label.pack(fill=tk.X, pady=2)

        # 2. 当前状态
        current_frame = ttk.LabelFrame(right_inner_frame, text="当前状态", padding=5)
        current_frame.pack(fill=tk.X, pady=5)

        self.current_voltage_label = ttk.Label(current_frame, text="当前电压: -- kV")
        self.current_voltage_label.pack(fill=tk.X, pady=2)

        self.current_mode_label = ttk.Label(current_frame, text="当前模式: --")
        self.current_mode_label.pack(fill=tk.X, pady=2)

        self.target_mode_label = ttk.Label(current_frame, text="目标模式: --")
        self.target_mode_label.pack(fill=tk.X, pady=2)

        self.stability_label = ttk.Label(current_frame, text="稳定状态: --")
        self.stability_label.pack(fill=tk.X, pady=2)

        self.match_rate_label = ttk.Label(current_frame, text="匹配度: --")
        self.match_rate_label.pack(fill=tk.X, pady=2)

        # 3. 遍历结果
        results_frame = ttk.LabelFrame(right_inner_frame, text="遍历结果", padding=5)
        results_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.results_text = scrolledtext.ScrolledText(results_frame, height=10)
        self.results_text.pack(fill=tk.BOTH, expand=True)

        # 4. 系统日志
        log_frame = ttk.LabelFrame(right_inner_frame, text="系统日志", padding=5)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=10)
        self.log_text.pack(fill=tk.BOTH, expand=True)

        # 启动状态更新
        self.update_status()


    def update_mode_classes(self, mode_classes):
        """更新模式种类显示"""
        self.mode_classes = mode_classes
        mode_names = list(mode_classes.values())
        self.mode_classes_label.config(text=f"收到{len(mode_names)}个模式: {', '.join(mode_names[:5])}" +
                                         (f"...等{len(mode_names)}个" if len(mode_names) > 5 else ""))

        # 获取当前选择的目标模式（如果有）
        current_selection = self.target_mode_var.get()

        # 清除现有单选按钮
        for widget in self.mode_radio_frame.winfo_children():
            widget.destroy()
        self.mode_radio_buttons.clear()

        # 创建单选按钮（按种类个数创建对应数量的选项）
        if mode_names:
            ttk.Label(self.mode_radio_frame, text="请选择目标模式:").pack(anchor=tk.W, pady=(0, 5))

            for i, mode_name in enumerate(mode_names):
                rb = ttk.Radiobutton(
                    self.mode_radio_frame,
                    text=mode_name,
                    variable=self.target_mode_var,
                    value=mode_name
                )
                rb.pack(anchor=tk.W, padx=20, pady=2)
                self.mode_radio_buttons.append(rb)

            # 设置选择：如果当前选择在列表中，则保持；否则选择第一个
            if current_selection in mode_names:
                self.target_mode_var.set(current_selection)
            elif mode_names:
                self.target_mode_var.set(mode_names[0])
        else:
            ttk.Label(self.mode_radio_frame, text="未收到模式种类").pack(pady=10)

        # 更新模式切换下拉框（保持下拉框用于切换）
        self.switch_mode_combo['values'] = mode_names

        self.log_message(f"更新模式种类: {len(mode_names)}个类别，已创建单选按钮")

    def update_exploration_results(self, mode_voltage_ranges):
        """更新遍历结果"""
        self.mode_voltage_ranges = mode_voltage_ranges

        # 更新结果文本框
        self.results_text.delete(1.0, tk.END)
        if mode_voltage_ranges:
            self.results_text.insert(tk.END, "识别到的模式电压范围:\n")
            for mode, info in mode_voltage_ranges.items():
                self.results_text.insert(tk.END,
                    f"  {mode}: {info['min']:.1f}kV - {info['max']:.1f}kV (最优: {info['optimal']:.1f}kV)\n")
        else:
            self.results_text.insert(tk.END, "未识别到任何模式")

        # 注意：模式切换下拉框已在update_mode_classes中设置为所有模式种类
        # 这里不更新下拉框，以确保切换选项包括所有模式（不仅仅是已识别的模式）
        # 根据需求：更换目标模式的选项应包括所有模式

    def update_current_mode(self, mode_name, confidence):
        """更新当前模式显示"""
        self.current_mode_label.config(text=f"当前模式: {mode_name} ({confidence:.1%})")

    def update_stability_state(self, stable, match_rate):
        """更新稳定状态显示"""
        if stable:
            self.stability_label.config(text="稳定状态: 稳定", foreground="green")
        else:
            self.stability_label.config(text="稳定状态: 调整中", foreground="orange")

        self.match_rate_label.config(text=f"匹配度: {match_rate:.1%}")

    #

    def start_target_control(self):
        """启动目标控制（自动包含电压遍历）"""
        try:
            # 获取电压范围
            min_voltage = float(self.min_voltage_var.get())
            max_voltage = float(self.max_voltage_var.get())

            if min_voltage >= max_voltage:
                messagebox.showerror("错误", "最小电压必须小于最大电压")
                return

            # 获取目标模式
            target_mode = self.target_mode_var.get()
            if not target_mode:
                messagebox.showwarning("警告", "请先选择目标模式")
                return

            if not self.control_system.mode_classes_received:
                messagebox.showerror("错误", "尚未收到模式种类")
                return

            self.log_message(f"启动目标控制: {target_mode}, 电压范围: {min_voltage:.1f}kV - {max_voltage:.1f}kV")

            # 调用start_target_control，它会执行模糊遍历寻找目标模式（流程4）
            if self.control_system.start_target_control(target_mode, min_voltage, max_voltage):
                self.log_message("目标控制流程已启动（包含模糊遍历寻找目标模式）")
            else:
                self.log_message("目标控制启动失败")

        except ValueError:
            messagebox.showerror("错误", "请输入有效的电压值")

    def switch_target_mode(self):
        """切换目标模式"""
        new_target_mode = self.switch_mode_var.get()
        if not new_target_mode:
            messagebox.showwarning("警告", "请选择要切换的目标模式")
            return

        # 不再检查exploration_completed，模式切换应使用现有数据
        # 如果还没有遍历数据，switch_target_mode方法会处理
        self.log_message(f"紧急切换目标模式到: {new_target_mode}")

        if self.control_system.switch_target_mode(new_target_mode):
            self.log_message("目标模式切换成功")
            self.target_mode_var.set(new_target_mode)
        else:
            self.log_message("目标模式切换失败")

    def stop_control(self):
        """停止控制"""
        self.control_system.stop_control()
        self.log_message("控制已停止")

    def quit_system(self):
        """退出系统"""
        if messagebox.askyesno("确认", "确定要退出系统吗？"):
            self.control_system.stop_system()
            self.root.quit()
            self.root.destroy()

    def log_message(self, message):
        """记录日志消息"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, formatted)
        self.log_text.see(tk.END)
        print(formatted.strip())

    def update_status(self):
        """更新状态显示"""
        # 连接状态
        client_count = len(self.control_system.clients)
        conn_text = f"检测模块: {'已连接' if client_count > 0 else '未连接'} ({client_count}个)"
        self.conn_status_label.config(text=conn_text)

        # 高压电源状态
        hv_text = f"高压电源: 已连接"  # 简化显示
        self.hv_status_label.config(text=hv_text)

        # 模式种类状态
        if self.control_system.mode_classes_received:
            model_text = f"模式种类: 已接收 ({len(self.control_system.mode_classes)}个类别)"
        else:
            model_text = "模式种类: 等待接收"
        self.model_status_label.config(text=model_text)

        # 当前电压
        self.current_voltage_label.config(text=f"当前电压: {self.control_system.current_voltage_kv:.2f} kV")

        # 目标模式
        if self.control_system.target_mode:
            self.target_mode_label.config(text=f"目标模式: {self.control_system.target_mode}")
        else:
            self.target_mode_label.config(text="目标模式: --")

        # PID参数显示
        if hasattr(self.control_system.fuzzy_pid, 'kp'):
            self.pid_kp_label.config(text=f"KP: {self.control_system.fuzzy_pid.kp:.3f}")
            self.pid_ki_label.config(text=f"KI: {self.control_system.fuzzy_pid.ki:.3f}")
            self.pid_kd_label.config(text=f"KD: {self.control_system.fuzzy_pid.kd:.3f}")
            self.step_label.config(text=f"步长/步时: {self.control_system.fuzzy_pid.step_size:.2f}kV / {self.control_system.fuzzy_pid.step_time:.2f}s")

        # 继续更新
        self.root.after(1000, self.update_status)

    def run(self):
        """运行GUI"""
        self.root.mainloop()

# ==================== 主函数 ====================
def main():
    """主函数"""
    print("=== PID模糊控制系统启动（增强版） ===")

    # 创建控制系统
    control_system = EnhancedControlSystemCore(modbus_port='COM5', detection_port=12345)
    control_system.running = True

    # 启动检测服务器
    if not control_system.start_detection_server():
        print("无法启动检测服务器")
        return

    # 启动GUI
    gui = EnhancedControlSystemGUI(control_system)

    print("系统已启动，等待监测模块连接...")
    print("监测模块应连接到: localhost:12345")
    print("模式种类将从监测模块自动接收")

    try:
        gui.run()
    except KeyboardInterrupt:
        print("\n用户中断")
    except Exception as e:
        print(f"系统错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        control_system.stop_system()
        print("系统已关闭")

if __name__ == "__main__":
    main()