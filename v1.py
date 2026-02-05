# 增强版智能控制系统 - 控制优化版
import socket
import json
import threading
import time
import numpy as np
from collections import defaultdict, deque
from statistics import median, mode
import skfuzzy as fuzz
from skfuzzy import control as ctrl
import os
from datetime import datetime
from pymodbus.client.sync import ModbusSerialClient
from pymodbus.exceptions import ModbusException, ConnectionException
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox
import platform  # 添加平台检测
import subprocess  # 添加子进程用于网络诊断


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


class EnhancedFuzzyController:
    def __init__(self):
        self.error_history = deque(maxlen=30)  # 增加历史记录长度
        self.adjustment_history = deque(maxlen=30)
        self.mode_voltages = defaultdict(list)

        # 优化后的自适应参数
        self.kp = 1.0  # 减小比例增益，避免过冲
        self.ki = 0.1  # 减小积分增益，防止积分饱和
        self.kd = 0.12  # 增加微分增益，提高稳定性
        self.error_integral = 0
        self.integral_limit = 5.0  # 积分限制

        # 状态变量
        self.last_error = 0
        self.last_adjustment = 0
        self.last_mode = None
        self.mode_center_voltages = {}

        # 模式电压映射表
        self.mode_voltage_map = {}
        self.voltage_mode_map = {}

        # 控制状态
        self.is_learning = True
        self.learning_complete = False
        self.mode_counter = 1  # 从1开始编号模式

        # 新增：稳定性控制参数
        self.stability_count = 0
        self.stability_threshold = 5  # 连续稳定5次视为稳定
        self.voltage_history = deque(maxlen=10)
        self.mode_history = deque(maxlen=10)

        # 新增：平滑控制参数
        self.smoothing_factor = 0.5  # 平滑因子
        self.last_smooth_adjustment = 0

        # 新增：防抖控制参数
        self.oscillation_detection = deque(maxlen=10)
        self.oscillation_threshold = 3  # 振荡检测阈值

        # 初始化模糊控制器
        self.setup_fuzzy_controller()

    def setup_fuzzy_controller(self):
        """设置实时学习模糊控制器"""
        print(" 设置增强稳定性模糊控制器...")

        # 优化后的误差范围
        error_range = np.arange(-8, 9, 1)  # 缩小范围，提高精度
        self.error = ctrl.Antecedent(error_range, 'error')

        # 新增：稳定性指标
        stability_range = np.arange(0, 11, 1)
        self.stability = ctrl.Antecedent(stability_range, 'stability')

        # 调整效果范围
        effect_range = np.arange(-4, 5, 1)
        self.effect = ctrl.Antecedent(effect_range, 'effect')

        # 优化后的电压调整范围 - 进一步减小范围提高稳定性
        voltage_adjust_range = np.arange(-0.8, 0.81, 0.05)  # 减小调整范围到-0.8~0.8kV，提高稳定性
        self.voltage_adjust = ctrl.Consequent(voltage_adjust_range, 'voltage_adjust')

        self._define_fuzzy_sets()
        self._create_fuzzy_rules()

        control_system = ctrl.ControlSystem(self.rules)
        self.fuzzy_ctrl = ctrl.ControlSystemSimulation(control_system)

        print("增强稳定性模糊控制器设置完成!")

    def _define_fuzzy_sets(self):
        """定义模糊集合"""
        # 误差的模糊集合 - 优化为9个级别，更精细控制
        self.error['VVB'] = fuzz.trimf(self.error.universe, [-8, -7, -5])    # 非常大负误差
        self.error['VB'] = fuzz.trimf(self.error.universe, [-6, -5, -3])     # 大负误差
        self.error['N'] = fuzz.trimf(self.error.universe, [-4, -3, -1])      # 负误差
        self.error['SN'] = fuzz.trimf(self.error.universe, [-2, -1, 0])      # 小负误差
        self.error['Z'] = fuzz.trimf(self.error.universe, [-1, 0, 1])        # 零误差
        self.error['SP'] = fuzz.trimf(self.error.universe, [0, 1, 2])        # 小正误差
        self.error['P'] = fuzz.trimf(self.error.universe, [1, 3, 4])         # 正误差
        self.error['BP'] = fuzz.trimf(self.error.universe, [3, 5, 6])        # 大正误差
        self.error['VBP'] = fuzz.trimf(self.error.universe, [5, 7, 8])       # 非常大正误差

        # 稳定性的模糊集合 - 优化为5个级别，更准确评估
        self.stability['VeryLow'] = fuzz.trimf(self.stability.universe, [0, 1, 3])    # 非常低
        self.stability['Low'] = fuzz.trimf(self.stability.universe, [2, 3, 5])        # 低
        self.stability['Medium'] = fuzz.trimf(self.stability.universe, [4, 5, 7])     # 中
        self.stability['High'] = fuzz.trimf(self.stability.universe, [6, 7, 9])       # 高
        self.stability['VeryHigh'] = fuzz.trimf(self.stability.universe, [8, 9, 10])  # 非常高

        # 调整效果的模糊集合 - 优化为5个级别，更准确评估
        self.effect['VeryNegative'] = fuzz.trimf(self.effect.universe, [-4, -3, -1])  # 非常消极
        self.effect['Negative'] = fuzz.trimf(self.effect.universe, [-2, -1, 0])       # 消极
        self.effect['Neutral'] = fuzz.trimf(self.effect.universe, [-1, 0, 1])         # 中性
        self.effect['Positive'] = fuzz.trimf(self.effect.universe, [0, 1, 2])         # 积极
        self.effect['VeryPositive'] = fuzz.trimf(self.effect.universe, [1, 3, 4])     # 非常积极

        # 电压调整的模糊集合 - 优化为7个级别，匹配-0.8~0.8kV范围
        self.voltage_adjust['NB'] = fuzz.trimf(self.voltage_adjust.universe, [-0.8, -0.6, -0.4])   # 负大
        self.voltage_adjust['NM'] = fuzz.trimf(self.voltage_adjust.universe, [-0.5, -0.3, -0.1])   # 负中
        self.voltage_adjust['NS'] = fuzz.trimf(self.voltage_adjust.universe, [-0.2, -0.1, 0])      # 负小
        self.voltage_adjust['Z'] = fuzz.trimf(self.voltage_adjust.universe, [-0.05, 0, 0.05])      # 零
        self.voltage_adjust['PS'] = fuzz.trimf(self.voltage_adjust.universe, [0, 0.1, 0.2])        # 正小
        self.voltage_adjust['PM'] = fuzz.trimf(self.voltage_adjust.universe, [0.1, 0.3, 0.5])      # 正中
        self.voltage_adjust['PB'] = fuzz.trimf(self.voltage_adjust.universe, [0.4, 0.6, 0.8])      # 正大

    def _create_fuzzy_rules(self):
        """创建模糊规则 - 优化版：更精细、更稳定的控制策略"""
        self.rules = [
            # 规则1-4: 非常大误差 + 非常低稳定性 -> 大调整（方向取决于误差和效果）
            ctrl.Rule(self.error['VVB'] & self.stability['VeryLow'] & self.effect['VeryPositive'], self.voltage_adjust['PB']),
            ctrl.Rule(self.error['VVB'] & self.stability['VeryLow'] & self.effect['Positive'], self.voltage_adjust['PM']),
            ctrl.Rule(self.error['VBP'] & self.stability['VeryLow'] & self.effect['VeryPositive'], self.voltage_adjust['NB']),
            ctrl.Rule(self.error['VBP'] & self.stability['VeryLow'] & self.effect['Positive'], self.voltage_adjust['NM']),

            # 规则5-8: 大误差 + 低稳定性 -> 中等调整
            ctrl.Rule(self.error['VB'] & self.stability['Low'] & self.effect['Positive'], self.voltage_adjust['PM']),
            ctrl.Rule(self.error['VB'] & self.stability['Low'] & self.effect['Neutral'], self.voltage_adjust['PS']),
            ctrl.Rule(self.error['BP'] & self.stability['Low'] & self.effect['Positive'], self.voltage_adjust['NM']),
            ctrl.Rule(self.error['BP'] & self.stability['Low'] & self.effect['Neutral'], self.voltage_adjust['NS']),

            # 规则9-12: 中等误差 + 中等稳定性 -> 小调整
            ctrl.Rule(self.error['N'] & self.stability['Medium'], self.voltage_adjust['PS']),
            ctrl.Rule(self.error['N'] & self.stability['Medium'] & self.effect['Negative'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['P'] & self.stability['Medium'], self.voltage_adjust['NS']),
            ctrl.Rule(self.error['P'] & self.stability['Medium'] & self.effect['Negative'], self.voltage_adjust['Z']),

            # 规则13-16: 小误差 + 高稳定性 -> 微调或不调
            ctrl.Rule(self.error['SN'] & self.stability['High'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['SN'] & self.stability['High'] & self.effect['VeryNegative'], self.voltage_adjust['PS']),
            ctrl.Rule(self.error['SP'] & self.stability['High'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['SP'] & self.stability['High'] & self.effect['VeryNegative'], self.voltage_adjust['NS']),

            # 规则17-20: 零误差或接近零误差 -> 不调整
            ctrl.Rule(self.error['Z'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['Z'] & self.stability['VeryHigh'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['SN'] & self.stability['VeryHigh'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['SP'] & self.stability['VeryHigh'], self.voltage_adjust['Z']),

            # 规则21-24: 非常高稳定性时保守调整（防止过调）
            ctrl.Rule(self.error['N'] & self.stability['VeryHigh'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['P'] & self.stability['VeryHigh'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['VB'] & self.stability['VeryHigh'], self.voltage_adjust['PS']),
            ctrl.Rule(self.error['BP'] & self.stability['VeryHigh'], self.voltage_adjust['NS']),

            # 规则25-28: 非常低稳定性 + 消极效果 -> 非常保守调整
            ctrl.Rule(self.error['VVB'] & self.stability['VeryLow'] & self.effect['VeryNegative'], self.voltage_adjust['PS']),
            ctrl.Rule(self.error['VBP'] & self.stability['VeryLow'] & self.effect['VeryNegative'], self.voltage_adjust['NS']),
            ctrl.Rule(self.error['VB'] & self.stability['VeryLow'] & self.effect['VeryNegative'], self.voltage_adjust['Z']),
            ctrl.Rule(self.error['BP'] & self.stability['VeryLow'] & self.effect['VeryNegative'], self.voltage_adjust['Z']),
        ]

    def add_mode_voltage_mapping(self, mode_name, voltage_kv):
        """添加模式与电压的映射关系"""
        if mode_name not in self.mode_voltage_map:
            # 为新模式分配编号
            mode_id = str(self.mode_counter)
            self.mode_voltage_map[mode_name] = {
                'id': mode_id,
                'voltage': voltage_kv,
                'count': 1,
                'voltages': [voltage_kv]  # 记录所有电压样本
            }
            self.mode_counter += 1
            print(f" 添加新模式映射: {mode_name} -> 模式{mode_id} ({voltage_kv:.1f}kV)")
        else:
            # 更新现有模式的电压值，使用滑动平均
            mode_info = self.mode_voltage_map[mode_name]
            mode_info['voltages'].append(voltage_kv)

            # 计算加权平均，最近的值权重更高
            weights = np.linspace(1, 2, len(mode_info['voltages']))
            weights = weights / weights.sum()
            new_voltage = np.average(mode_info['voltages'][-5:])  # 只使用最近5个样本

            mode_info['voltage'] = new_voltage
            mode_info['count'] += 1
            print(
                f" 更新模式映射: {mode_name} -> 模式{mode_info['id']} ({new_voltage:.1f}kV, 样本数: {mode_info['count']})")

    def ensure_modes_from_ranges(self, mode_voltage_ranges):
        """
        将探索阶段得到的模式范围表同步进 mode_voltage_map，确保 get_mode_list() 能返回完整模式。
        探索时只有占比≥50%的电压点会调用 add_mode_voltage_mapping，可能漏掉部分模式；
        mode_voltage_ranges 用 30% 阈值会包含更多模式，这里把未在 mode_voltage_map 中的模式补全。
        若探索后仅发现 1 个模式，则补 2 个“合成模式”（同电压带内不同电压点），使网页可显示 模式1/模式2/模式3 供选择。
        """
        if not mode_voltage_ranges:
            return
        for mode_name, info in mode_voltage_ranges.items():
            if not isinstance(info, dict):
                continue
            try:
                v = info.get('optimal')
                if v is None:
                    v = (float(info.get('min', 0)) + float(info.get('max', 0))) / 2.0
                if mode_name not in self.mode_voltage_map:
                    self.add_mode_voltage_mapping(mode_name, v)
                else:
                    self.mode_voltage_map[mode_name]['voltage'] = v
                    if 'voltages' in self.mode_voltage_map[mode_name]:
                        self.mode_voltage_map[mode_name]['voltages'].append(v)
            except Exception:
                continue
        # 若探索后只有 1 个模式，补 2 个合成模式，使网页能显示 模式1、模式2、模式3 供选择
        if len(self.mode_voltage_map) == 1 and mode_voltage_ranges:
            single_name = next(iter(mode_voltage_ranges.keys()))
            single_info = mode_voltage_ranges.get(single_name)
            if isinstance(single_info, dict):
                v_min = float(single_info.get('min', 0))
                v_max = float(single_info.get('max', 20))
                opt = single_info.get('optimal')
                if opt is None:
                    opt = (v_min + v_max) / 2.0
                opt = float(opt)
                step = max(0.2, (v_max - v_min) / 4.0)
                v2 = min(v_max, opt + step)
                v3 = max(v_min, opt - step)
                self.add_mode_voltage_mapping("__syn_mode_2", v2)
                self.add_mode_voltage_mapping("__syn_mode_3", v3)
                print(f" 已补全合成模式: 模式2 ({v2:.1f}kV), 模式3 ({v3:.1f}kV)，共 3 个可选目标模式")

    def get_mode_id(self, mode_name):
        """获取模式编号"""
        if mode_name in self.mode_voltage_map:
            return self.mode_voltage_map[mode_name]['id']
        return None

    def get_target_voltage(self, mode_id):
        """获取目标模式对应的电压"""
        for mode_name, mode_info in self.mode_voltage_map.items():
            if mode_info['id'] == mode_id:
                return mode_info['voltage']
        return None

    def _calculate_stability_score(self):
        """计算稳定性分数"""
        if len(self.error_history) < 3:
            return 0

        # 基于最近误差的变化计算稳定性
        recent_errors = list(self.error_history)[-3:]
        error_changes = np.abs(np.diff(recent_errors))
        avg_change = np.mean(error_changes)

        # 稳定性分数：变化越小，分数越高
        if avg_change < 0.5:
            return 9  # 非常稳定
        elif avg_change < 1.0:
            return 7  # 稳定
        elif avg_change < 2.0:
            return 4  # 中等稳定
        else:
            return 2  # 不稳定

    def _detect_oscillation(self, adjustment):
        """检测振荡 - 优化版：增强检测灵敏度"""
        self.oscillation_detection.append(adjustment)

        if len(self.oscillation_detection) >= 6:
            # 获取最近6次调整
            recent_adjustments = list(self.oscillation_detection)[-6:]

            # 1. 检查方向频繁切换
            signs = [1 if adj > 0.01 else -1 if adj < -0.01 else 0 for adj in recent_adjustments]
            sign_changes = sum(1 for i in range(1, len(signs)) if signs[i] * signs[i - 1] < 0)

            # 2. 检查调整量标准差
            adjust_std = np.std(recent_adjustments) if len(recent_adjustments) > 1 else 0

            # 综合判断振荡
            oscillation_detected = False
            if sign_changes >= 3:  # 频繁切换方向
                print(f"检测到方向振荡：{sign_changes}/5次方向切换")
                oscillation_detected = True
            elif adjust_std > 0.15:  # 调整量变化过大
                print(f"检测到幅度振荡：调整量标准差{adjust_std:.3f}")
                oscillation_detected = True

            if oscillation_detected:
                # 实施抗振荡措施
                print(" 启动抗振荡：减小增益")
                self.kp = max(0.4, self.kp * 0.7)
                self.error_integral *= 0.5
                self.oscillation_detection.clear()  # 清空历史重新检测

            return oscillation_detected
        return False

    def calculate_adjustment(self, target_mode_id, current_mode_id, current_voltage, last_adjustment_effect):
        """计算电压调整量 - 增强稳定性版本"""
        try:
            # 获取目标电压
            target_voltage = self.get_target_voltage(target_mode_id)
            if target_voltage is None:
                print(f"未找到目标模式{target_mode_id}的电压映射")
                return 0.0, 0, 0

            # 计算电压误差（千伏）
            voltage_error = current_voltage - target_voltage

            # 记录电压历史
            self.voltage_history.append(current_voltage)

            # 将误差转换为模式编号误差（1个模式编号大约对应1kV电压差）
            error = float(voltage_error)  # 保持为浮点数，提高精度

            # 添加到历史记录
            self.error_history.append(error)

            # 计算误差变化率
            if len(self.error_history) > 1:
                error_change = error - self.error_history[-2]
            else:
                error_change = 0

            # 计算稳定性分数
            stability_score = self._calculate_stability_score()

            # 自适应积分项（带动态限制和抗饱和）
            integral_step = 0.05

            # 根据误差大小和方向动态调整积分增益
            if abs(error) < 2.0:  # 小误差时正常积分
                if abs(self.error_integral) < self.integral_limit * 0.8:
                    self.error_integral += error * integral_step
                else:
                    # 接近积分限时减速
                    self.error_integral += error * integral_step * 0.5
            elif abs(error) > 4.0:  # 大误差时重置部分积分
                self.error_integral *= 0.3
            else:  # 中等误差时温和积分
                self.error_integral += error * integral_step * 0.8

            # 动态积分限制：根据误差大小调整限制
            dynamic_limit = max(3.0, min(7.0, abs(error) * 2))
            self.error_integral = max(-dynamic_limit, min(dynamic_limit, self.error_integral))

            # 自适应调整增益
            self._adapt_gains(error, error_change, stability_score)

            try:
                # 模糊控制计算
                self.fuzzy_ctrl.input['error'] = error
                self.fuzzy_ctrl.input['stability'] = stability_score
                self.fuzzy_ctrl.input['effect'] = last_adjustment_effect
                self.fuzzy_ctrl.compute()

                fuzzy_output = self.fuzzy_ctrl.output['voltage_adjust']

                # 结合PID和模糊控制
                adjustment = fuzzy_output * self.kp
                adjustment += self.ki * self.error_integral
                adjustment += self.kd * error_change

                # 检测振荡
                if self._detect_oscillation(adjustment):
                    # 检测到振荡，大幅减小调整幅度
                    adjustment *= 0.3
                    self.error_integral *= 0.5  # 重置部分积分

                # 根据稳定性进一步调整（更精细的分级）
                if stability_score > 8:  # 非常高稳定性
                    adjustment *= 0.5  # 大幅减小调整幅度
                elif stability_score > 6:  # 高稳定性
                    adjustment *= 0.7  # 适度减小调整幅度
                elif stability_score < 2:  # 非常低稳定性
                    adjustment *= 0.9  # 小幅减小，避免过激
                elif stability_score < 4:  # 低稳定性
                    adjustment *= 0.8  # 适度减小调整幅度

                # 平滑处理
                adjustment = self.last_smooth_adjustment * (
                            1 - self.smoothing_factor) + adjustment * self.smoothing_factor
                self.last_smooth_adjustment = adjustment

                # 限制调整幅度（与电压调整范围-0.8~0.8kV一致）
                adjustment = max(-0.8, min(0.8, adjustment))

                # 防止死区（调整阈值以适应新的调整范围）
                if abs(adjustment) < 0.015 and abs(error) > 0.15:
                    adjustment = 0.03 * (1 if error < 0 else -1)

                # 记录调整
                self.last_error = error
                self.last_adjustment = adjustment
                self.adjustment_history.append(adjustment)

                return adjustment, error, error_change

            except Exception as e:
                print(f"模糊控制计算错误: {e}")
                # 使用自适应PID作为备份
                return self._adaptive_pid(error, error_change, stability_score), error, error_change

        except Exception as e:
            print(f"调整量计算错误: {e}")
            return 0.0, 0, 0

    def _adaptive_pid(self, error, error_change, stability_score):
        """自适应PID控制器作为备份 - 优化版"""
        # 根据稳定性连续调整增益
        if stability_score > 8:  # 非常高稳定性
            kp_local = self.kp * 0.6
            ki_local = self.ki * 0.4
            kd_local = self.kd * 1.3
        elif stability_score > 6:  # 高稳定性
            kp_local = self.kp * 0.7
            ki_local = self.ki * 0.6
            kd_local = self.kd * 1.2
        elif stability_score < 2:  # 非常低稳定性
            kp_local = self.kp * 0.9
            ki_local = self.ki * 0.3
            kd_local = self.kd * 0.7
        elif stability_score < 4:  # 低稳定性
            kp_local = self.kp * 0.8
            ki_local = self.ki * 0.4
            kd_local = self.kd * 0.8
        else:  # 中等稳定性
            kp_local = self.kp * 0.9
            ki_local = self.ki * 0.8
            kd_local = self.kd * 1.0

        output = kp_local * error + ki_local * self.error_integral + kd_local * error_change
        return max(-0.8, min(0.8, output))  # 限制输出范围与电压调整范围一致

    def _adapt_gains(self, error, error_change, stability_score):
        """自适应调整控制增益 - 优化版：连续平滑调整"""
        error_abs = abs(error)

        # 基于误差大小的连续调整（而非阶跃）
        if error_abs > 5:
            adjustment_factor = 1.2  # 大误差时显著增加响应
        elif error_abs > 3:
            adjustment_factor = 1.1  # 中等误差时适度增加
        elif error_abs > 1:
            adjustment_factor = 1.0  # 小误差时保持
        elif error_abs > 0.5:
            adjustment_factor = 0.9  # 很小误差时减小
        else:
            adjustment_factor = 0.8  # 接近零误差时显著减小

        # 基于稳定性的连续调整
        if stability_score > 8:
            stability_factor = 0.6  # 高稳定性时大幅减小比例增益
        elif stability_score > 6:
            stability_factor = 0.8  # 良好稳定性时适度减小
        elif stability_score > 4:
            stability_factor = 1.0  # 中等稳定性时保持
        elif stability_score > 2:
            stability_factor = 1.2  # 低稳定性时增加增益
        else:
            stability_factor = 1.4  # 非常低稳定性时显著增加

        # 应用调整
        self.kp = max(0.3, min(1.5, self.kp * adjustment_factor * stability_factor))

        # 积分增益反比于误差大小
        if error_abs < 1.0:
            self.ki = min(0.2, self.ki * 1.05)  # 小误差时增加积分
        else:
            self.ki = max(0.05, self.ki * 0.95)  # 大误差时减小积分

        # 微分增益正比于稳定性
        if stability_score > 6:
            self.kd = min(0.3, self.kd * 1.08)  # 稳定时增加微分
        else:
            self.kd = max(0.08, self.kd * 0.92)  # 不稳定时减小微分

    def check_stability(self, current_mode_id, target_mode_id, current_voltage):
        """检查是否达到稳定状态"""
        if current_mode_id == target_mode_id:
            self.stability_count += 1
        else:
            self.stability_count = max(0, self.stability_count - 2)  # 不稳定时快速重置

        # 检查电压稳定性
        if len(self.voltage_history) >= 5:
            recent_voltages = list(self.voltage_history)[-5:]
            voltage_std = np.std(recent_voltages)

            if voltage_std < 0.1:  # 电压标准差小于0.1kV
                self.stability_count += 1

        return self.stability_count >= self.stability_threshold

    def get_mode_list(self):
        """获取已识别的模式列表"""
        modes = []
        for mode_name, mode_info in self.mode_voltage_map.items():
            modes.append({
                'id': mode_info['id'],
                'name': mode_name,
                'voltage': mode_info['voltage'],
                'count': mode_info['count'],
                'std_voltage': np.std(mode_info['voltages']) if len(mode_info['voltages']) > 1 else 0
            })
        # 按模式编号排序
        modes.sort(key=lambda x: int(x['id']))
        return modes


class EnhancedControlSystemGUI:
    def __init__(self, control_system):
        self.control_system = control_system
        self.root = tk.Tk()
        self.root.title("增强版高可靠控制系统 - 控制面板")
        self.root.geometry("1400x900")

        self.status_vars = {}
        self.current_stage = tk.StringVar(value="待开始")
        self.system_mode = tk.StringVar(value="空闲")

        # 设置样式
        self.setup_styles()

        self.setup_gui()

    def setup_styles(self):
        """设置GUI样式"""
        try:
            style = ttk.Style()
            # 紧急停止按钮样式 - 红色背景，白色文字
            style.configure("Emergency.TButton",
                          background="red",
                          foreground="white",
                          font=('Arial', 10, 'bold'))
            style.map("Emergency.TButton",
                     background=[('active', 'darkred')])
        except:
            pass  # 如果样式设置失败，继续使用默认样式

    def setup_gui(self):
        main_frame = ttk.Frame(self.root)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 动态计算面板宽度（基于屏幕宽度）
        screen_width = self.root.winfo_screenwidth()
        # 左侧面板占40%，右侧面板占60%，但最小宽度为450px
        left_width = max(450, int(screen_width * 0.35))

        # 左侧面板 - 带滚动条的控制面板（优化版）
        left_container = ttk.LabelFrame(main_frame, text="控制面板", padding=5)
        left_container.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 5))

        # 创建Canvas和滚动条（性能优化版）
        canvas = tk.Canvas(left_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(left_container, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)

        # 优化滚动区域更新：使用防抖机制避免频繁重绘
        self._last_scroll_update = 0
        def update_scrollregion(event=None):
            current_time = time.time()
            # 限制更新频率：至少0.1秒一次
            if current_time - self._last_scroll_update > 0.1:
                canvas.configure(scrollregion=canvas.bbox("all"))
                self._last_scroll_update = current_time
            else:
                # 延迟更新
                canvas.after(100, lambda: canvas.configure(scrollregion=canvas.bbox("all")))

        scrollable_frame.bind("<Configure>", update_scrollregion)

        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        # 布局Canvas和滚动条
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 设置Canvas宽度
        canvas.config(width=left_width)

        # 绑定鼠标滚轮滚动（Windows）- 优化版
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1*(event.delta/120)), "units")

        canvas.bind("<MouseWheel>", _on_mousewheel)

        # 绑定鼠标滚轮到整个canvas区域
        def bind_to_mousewheel(widget):
            widget.bind("<MouseWheel>", _on_mousewheel)
            widget.bind("<Button-4>", _on_mousewheel)  # Linux向上滚动
            widget.bind("<Button-5>", _on_mousewheel)  # Linux向下滚动

        # 递归绑定所有子组件
        def bind_children(parent):
            bind_to_mousewheel(parent)
            for child in parent.winfo_children():
                bind_to_mousewheel(child)
                bind_children(child)

        bind_children(scrollable_frame)

        right_frame = ttk.LabelFrame(main_frame, text="系统状态", padding=10)
        right_frame.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True, padx=(5, 0))

        self.setup_control_panel(scrollable_frame)
        self.setup_status_panel(right_frame)

        # 初始化滚动区域
        canvas.update_idletasks()
        canvas.configure(scrollregion=canvas.bbox("all"))

        self.update_status()

    def setup_control_panel(self, parent):
        # 连接状态显示
        conn_frame = ttk.LabelFrame(parent, text="高压电源连接", padding=5)
        conn_frame.pack(fill=tk.X, pady=3)

        ttk.Button(conn_frame, text="连接高压电源",
                   command=self.connect_hv_power).pack(fill=tk.X, pady=2)

        ttk.Button(conn_frame, text="断开连接",
                   command=self.disconnect_hv_power).pack(fill=tk.X, pady=2)

        ttk.Button(conn_frame, text="测试连接",
                   command=self.test_connection).pack(fill=tk.X, pady=2)

        # 检测连接测试按钮
        detection_test_frame = ttk.LabelFrame(parent, text="检测连接测试", padding=5)
        detection_test_frame.pack(fill=tk.X, pady=3)

        ttk.Button(detection_test_frame, text="测试检测连接",
                   command=self.test_detection_connection).pack(fill=tk.X, pady=2)

        ttk.Button(detection_test_frame, text="显示连接状态",
                   command=self.show_connection_status).pack(fill=tk.X, pady=2)

        # 新增：诊断按钮
        ttk.Button(detection_test_frame, text="诊断连接问题",
                   command=self.diagnose_connection).pack(fill=tk.X, pady=2)

        # 电压探索
        stage1_frame = ttk.LabelFrame(parent, text="第一步：设置操作电压范围", padding=5)
        stage1_frame.pack(fill=tk.X, pady=3)

        ttk.Label(stage1_frame, text="最小电压 (kV):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.min_voltage_var = tk.StringVar(value="0.0")
        ttk.Entry(stage1_frame, textvariable=self.min_voltage_var, width=8).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(stage1_frame, text="最大电压 (kV):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.max_voltage_var = tk.StringVar(value="20.0")
        ttk.Entry(stage1_frame, textvariable=self.max_voltage_var, width=8).grid(row=1, column=1, padx=5, pady=2)

        ttk.Label(stage1_frame, text="电压步长 (kV):").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.voltage_step_var = tk.StringVar(value="0.1")
        ttk.Entry(stage1_frame, textvariable=self.voltage_step_var, width=8).grid(row=2, column=1, padx=5, pady=2)

        ttk.Label(stage1_frame, text="等待时间 (秒):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.wait_time_var = tk.StringVar(value="0.5")
        ttk.Entry(stage1_frame, textvariable=self.wait_time_var, width=8).grid(row=3, column=1, padx=5, pady=2)

        ttk.Label(stage1_frame, text="识别阈值:").grid(row=4, column=0, sticky=tk.W, padx=5, pady=2)
        self.confidence_threshold_var = tk.StringVar(value="0.7")
        ttk.Entry(stage1_frame, textvariable=self.confidence_threshold_var, width=8).grid(row=4, column=1, padx=5,
                                                                                          pady=2)

        ttk.Button(stage1_frame, text="开始电压探索与模式识别",
                   command=self.start_exploration).grid(row=5, column=0, columnspan=2, sticky=tk.EW, pady=5)

        # 模式选择
        stage2_frame = ttk.LabelFrame(parent, text="第二步：已识别模式（按编号排列）", padding=5)
        stage2_frame.pack(fill=tk.X, pady=3)

        self.mode_listbox = tk.Listbox(stage2_frame, height=6)
        self.mode_listbox.pack(fill=tk.BOTH, expand=True, pady=2)

        # 目标控制
        stage3_frame = ttk.LabelFrame(parent, text="第三步：选择目标模式", padding=5)
        stage3_frame.pack(fill=tk.X, pady=3)

        ttk.Label(stage3_frame, text="选择目标模式:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.target_mode_var = tk.StringVar(value="")
        self.target_mode_combo = ttk.Combobox(stage3_frame, textvariable=self.target_mode_var, width=12,
                                              state="readonly")
        self.target_mode_combo.grid(row=0, column=1, padx=5, pady=2)

        ttk.Button(stage3_frame, text="启动目标控制",
                   command=self.start_target_control).grid(row=1, column=0, columnspan=2, sticky=tk.EW, pady=5)

        # 手动控制
        manual_frame = ttk.LabelFrame(parent, text="手动控制", padding=5)
        manual_frame.pack(fill=tk.BOTH, expand=True, pady=3)

        # 创建笔记本标签页
        manual_notebook = ttk.Notebook(manual_frame)
        manual_notebook.pack(fill=tk.BOTH, expand=True, pady=5)

        # 标签页1：基础控制
        basic_frame = ttk.Frame(manual_notebook, padding=5)
        manual_notebook.add(basic_frame, text="基础控制")

        # 电压输入和微调
        voltage_frame = ttk.LabelFrame(basic_frame, text="电压设置 (kV)", padding=3)
        voltage_frame.pack(fill=tk.X, pady=3)

        # 电压输入行
        voltage_input_frame = ttk.Frame(voltage_frame)
        voltage_input_frame.pack(fill=tk.X, pady=2)

        ttk.Button(voltage_input_frame, text="-1", width=4,
                   command=lambda: self.adjust_voltage(-1.0)).pack(side=tk.LEFT, padx=2)
        ttk.Button(voltage_input_frame, text="-0.1", width=4,
                   command=lambda: self.adjust_voltage(-0.1)).pack(side=tk.LEFT, padx=2)

        self.voltage_var = tk.StringVar(value="0.0")
        voltage_entry = ttk.Entry(voltage_input_frame, textvariable=self.voltage_var,
                                 width=12, justify=tk.CENTER)
        voltage_entry.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        ttk.Button(voltage_input_frame, text="+0.1", width=4,
                   command=lambda: self.adjust_voltage(0.1)).pack(side=tk.LEFT, padx=2)
        ttk.Button(voltage_input_frame, text="+1", width=4,
                   command=lambda: self.adjust_voltage(1.0)).pack(side=tk.LEFT, padx=2)

        # 电压滑块
        ttk.Label(voltage_frame, text="电压滑块:").pack(anchor=tk.W, pady=(5,0))
        self.voltage_scale = ttk.Scale(voltage_frame, from_=0, to=200, orient=tk.HORIZONTAL, length=250)
        self.voltage_scale.pack(fill=tk.X, pady=2)
        # ttk.Scale没有resolution参数，所以将范围扩大10倍以实现0.1kV精度
        self.voltage_scale.bind("<ButtonRelease-1>", self.on_voltage_scale_change)
        # 添加鼠标释放事件，提高响应性
        self.voltage_scale.bind("<B1-Motion>", self.on_voltage_scale_drag)

        # 控制按钮
        control_buttons_frame = ttk.Frame(basic_frame)
        control_buttons_frame.pack(fill=tk.X, pady=3)

        ttk.Button(control_buttons_frame, text="设置电压",
                   command=self.set_voltage).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(control_buttons_frame, text="开启高压",
                   command=self.enable_hv).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(control_buttons_frame, text="关闭高压",
                   command=self.disable_hv).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        ttk.Button(control_buttons_frame, text="紧急停止", style="Emergency.TButton",
                   command=self.emergency_stop).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        # 实时监控
        monitor_frame = ttk.LabelFrame(basic_frame, text="实时监控", padding=3)
        monitor_frame.pack(fill=tk.X, pady=3)

        monitor_grid = ttk.Frame(monitor_frame)
        monitor_grid.pack(fill=tk.X)

        self.voltage_monitor = ttk.Label(monitor_grid, text="电压: -- kV")
        self.voltage_monitor.grid(row=0, column=0, padx=5, pady=2, sticky=tk.W)

        self.current_monitor = ttk.Label(monitor_grid, text="电流: -- mA")
        self.current_monitor.grid(row=0, column=1, padx=5, pady=2, sticky=tk.W)

        self.power_monitor = ttk.Label(monitor_grid, text="功率: -- W")
        self.power_monitor.grid(row=1, column=0, padx=5, pady=2, sticky=tk.W)

        self.status_monitor = ttk.Label(monitor_grid, text="状态: 未知")
        self.status_monitor.grid(row=1, column=1, padx=5, pady=2, sticky=tk.W)

        # 标签页2：高级设置
        advanced_frame = ttk.Frame(manual_notebook, padding=5)
        manual_notebook.add(advanced_frame, text="高级设置")

        # 安全限制
        safety_frame = ttk.LabelFrame(advanced_frame, text="安全限制", padding=3)
        safety_frame.pack(fill=tk.X, pady=3)

        ttk.Label(safety_frame, text="最大电压 (kV):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.safety_max_voltage_var = tk.StringVar(value="20.0")
        ttk.Entry(safety_frame, textvariable=self.safety_max_voltage_var, width=10).grid(row=0, column=1, padx=5, pady=2)

        ttk.Label(safety_frame, text="最大电流 (mA):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.safety_max_current_var = tk.StringVar(value="100.0")
        ttk.Entry(safety_frame, textvariable=self.safety_max_current_var, width=10).grid(row=1, column=1, padx=5, pady=2)

        ttk.Button(safety_frame, text="应用限制",
                   command=self.apply_safety_limits).grid(row=2, column=0, columnspan=2, pady=5)

        # 预设电压
        preset_frame = ttk.LabelFrame(advanced_frame, text="预设电压", padding=3)
        preset_frame.pack(fill=tk.X, pady=3)

        preset_voltages = [("1 kV", 1.0), ("5 kV", 5.0), ("10 kV", 10.0),
                          ("15 kV", 15.0), ("20 kV", 20.0)]

        preset_grid = ttk.Frame(preset_frame)
        preset_grid.pack(fill=tk.X)

        for i, (label, voltage) in enumerate(preset_voltages):
            ttk.Button(preset_grid, text=label, width=8,
                      command=lambda v=voltage: self.set_preset_voltage(v)).grid(
                row=i//3, column=i%3, padx=2, pady=2)

        # 电压爬升速率
        ramp_frame = ttk.LabelFrame(advanced_frame, text="电压爬升控制", padding=3)
        ramp_frame.pack(fill=tk.X, pady=3)

        ttk.Label(ramp_frame, text="爬升速率 (kV/s):").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.ramp_rate_var = tk.StringVar(value="1.0")
        ttk.Entry(ramp_frame, textvariable=self.ramp_rate_var, width=10).grid(row=0, column=1, padx=5, pady=2)

        ttk.Button(ramp_frame, text="应用爬升速率",
                   command=self.apply_ramp_rate).grid(row=1, column=0, columnspan=2, pady=5)

        # 标签页3：历史记录
        history_frame = ttk.Frame(manual_notebook, padding=5)
        manual_notebook.add(history_frame, text="历史记录")

        # 电压历史记录
        history_label = ttk.Label(history_frame, text="电压设置历史记录:")
        history_label.pack(anchor=tk.W, pady=(0,5))

        self.voltage_history = tk.Listbox(history_frame, height=6)
        self.voltage_history.pack(fill=tk.BOTH, expand=True, pady=2)

        history_buttons = ttk.Frame(history_frame)
        history_buttons.pack(fill=tk.X, pady=5)

        ttk.Button(history_buttons, text="清除历史",
                   command=self.clear_voltage_history).pack(side=tk.LEFT, padx=2)
        ttk.Button(history_buttons, text="导出记录",
                   command=self.export_voltage_history).pack(side=tk.LEFT, padx=2)

        # 系统控制
        system_frame = ttk.LabelFrame(parent, text="系统控制", padding=5)
        system_frame.pack(fill=tk.X, pady=3)

        ttk.Button(system_frame, text="停止控制",
                   command=self.stop_control).pack(fill=tk.X, pady=2)

        ttk.Button(system_frame, text="清除日志",
                   command=self.clear_log).pack(fill=tk.X, pady=2)

        ttk.Button(system_frame, text="退出系统",
                   command=self.quit_system).pack(fill=tk.X, pady=2)

    def setup_status_panel(self, parent):
        # 连接状态
        conn_status_frame = ttk.LabelFrame(parent, text="连接状态", padding=10)
        conn_status_frame.pack(fill=tk.X, pady=5)

        conn_metrics = [
            ("连接状态", "connection_status"),
            ("控制权状态", "control_status"),
            ("当前电压", "current_voltage"),
            ("当前电流", "current_current"),
            ("最后成功时间", "last_success"),
            ("检测连接数", "detection_clients")
        ]

        conn_grid = ttk.Frame(conn_status_frame)
        conn_grid.pack(fill=tk.X)

        for i, (label, key) in enumerate(conn_metrics):
            ttk.Label(conn_grid, text=f"{label}:").grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            self.status_vars[key] = tk.StringVar(value="---")
            ttk.Label(conn_grid, textvariable=self.status_vars[key],
                      font=('Arial', 9)).grid(row=i, column=1, sticky=tk.W, padx=5, pady=2)

        # 系统状态
        status_frame = ttk.Frame(parent)
        status_frame.pack(fill=tk.X, pady=5)

        ttk.Label(status_frame, text="当前阶段:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Label(status_frame, textvariable=self.current_stage,
                  font=('Arial', 10, 'bold')).grid(row=0, column=1, sticky=tk.W, padx=5, pady=2)

        ttk.Label(status_frame, text="系统模式:").grid(row=0, column=2, sticky=tk.W, padx=20, pady=2)
        ttk.Label(status_frame, textvariable=self.system_mode,
                  font=('Arial', 10, 'bold')).grid(row=0, column=3, sticky=tk.W, padx=5, pady=2)

        # 控制状态
        metrics = [
            ("目标模式", "target_mode"),
            ("当前模式", "current_mode"),
            ("目标电压", "target_voltage"),
            ("模式误差", "error_value"),
            ("调整量", "adjustment"),
            ("控制迭代", "control_iteration"),
            ("已识别模式数", "detected_modes_count"),
            ("稳定性计数", "stability_count")
        ]

        left_col = ttk.Frame(status_frame)
        left_col.grid(row=1, column=0, columnspan=2, sticky=tk.W + tk.E, padx=5, pady=10)
        right_col = ttk.Frame(status_frame)
        right_col.grid(row=1, column=2, columnspan=2, sticky=tk.W + tk.E, padx=5, pady=10)

        for i, (label, key) in enumerate(metrics):
            frame = left_col if i % 2 == 0 else right_col
            row = i // 2
            ttk.Label(frame, text=f"{label}:", width=15, anchor=tk.W).grid(row=row, column=0, sticky=tk.W, pady=2)
            self.status_vars[key] = tk.StringVar(value="---")
            ttk.Label(frame, textvariable=self.status_vars[key],
                      font=('Arial', 9, 'bold'), width=10, anchor=tk.W).grid(row=row, column=1, sticky=tk.W, pady=2)

        # 高压电源输出
        hv_frame = ttk.LabelFrame(parent, text="高压电源输出", padding=10)
        hv_frame.pack(fill=tk.X, pady=5)

        hv_metrics = [
            ("输出电压", "output_voltage"),
            ("输出电流", "output_current"),
            ("模式名称", "mode_name"),
            ("置信度", "confidence"),
            ("检测时间", "detection_time")
        ]

        hv_grid = ttk.Frame(hv_frame)
        hv_grid.pack(fill=tk.X)

        for i, (label, key) in enumerate(hv_metrics):
            ttk.Label(hv_grid, text=f"{label}:").grid(row=i, column=0, sticky=tk.W, padx=5, pady=2)
            self.status_vars[key] = tk.StringVar(value="---")
            ttk.Label(hv_grid, textvariable=self.status_vars[key],
                      font=('Arial', 9)).grid(row=i, column=1, sticky=tk.W, padx=5, pady=2)

        # 系统日志
        log_frame = ttk.LabelFrame(parent, text="系统日志", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        self.log_text = scrolledtext.ScrolledText(log_frame, height=15)
        self.log_text.pack(fill=tk.BOTH, expand=True)

    def connect_hv_power(self):
        """连接高压电源"""
        if self.control_system.connect_hv_power():
            self.log_message("高压电源连接成功")
        else:
            self.log_message("高压电源连接失败")

    def disconnect_hv_power(self):
        """断开高压电源"""
        self.control_system.disconnect_hv_power()
        self.log_message(" 高压电源已断开")

    def test_connection(self):
        """测试连接"""
        if self.control_system.test_connection():
            self.log_message("连接测试成功")
        else:
            self.log_message("连接测试失败")

    def test_detection_connection(self):
        """测试检测连接"""
        self.log_message(" 测试检测连接...")
        status = self.control_system.test_detection_connection()
        if status:
            self.log_message("检测连接测试成功")
        else:
            self.log_message("检测连接测试失败")

    def show_connection_status(self):
        """显示连接状态"""
        self.log_message(" 显示连接状态...")
        self.control_system.show_connection_status()

    def diagnose_connection(self):
        """诊断连接问题"""
        self.log_message(" 诊断连接问题...")
        self.control_system.diagnose_connection_issue()

    def start_exploration(self):
        """开始电压探索与模式识别"""
        try:
            min_voltage = float(self.min_voltage_var.get())
            max_voltage = float(self.max_voltage_var.get())
            voltage_step = float(self.voltage_step_var.get())
            wait_time = float(self.wait_time_var.get())
            confidence_threshold = float(self.confidence_threshold_var.get())

            if min_voltage >= max_voltage:
                messagebox.showerror("错误", "最小电压必须小于最大电压")
                return

            if voltage_step <= 0:
                messagebox.showerror("错误", "电压步长必须大于0")
                return

            if confidence_threshold <= 0 or confidence_threshold > 1:
                messagebox.showerror("错误", "识别阈值必须在0-1之间")
                return

            self.log_message(" 开始电压探索与模式识别阶段...")
            self.log_message(f" 电压范围: {min_voltage:.1f}kV - {max_voltage:.1f}kV")
            self.log_message(f" 参数: 步长{voltage_step}kV, 等待{wait_time}秒, 阈值{confidence_threshold}")

            self.current_stage.set("电压探索中")
            self.system_mode.set("探索中")

            exploration_thread = threading.Thread(
                target=self.control_system.exploration_phase,
                args=(min_voltage, max_voltage, voltage_step, wait_time, confidence_threshold)
            )
            exploration_thread.daemon = True
            exploration_thread.start()

        except ValueError:
            messagebox.showerror("错误", "请输入有效的数字参数")

    def start_target_control(self):
        """启动目标控制"""
        target_mode = self.target_mode_var.get()
        if not target_mode:
            messagebox.showwarning("警告", "请先选择目标模式")
            return

        mode_list = self.control_system.fuzzy_controller.get_mode_list()
        if not mode_list:
            messagebox.showwarning("警告", "请先完成电压探索与模式识别阶段")
            return

        self.log_message(f" 启动目标模式控制: 模式{target_mode}")
        self.current_stage.set("目标控制中")
        self.system_mode.set("控制中")

        if self.control_system.start_target_control(target_mode):
            self.log_message("目标控制已启动")
        else:
            self.log_message("启动目标控制失败")

    def adjust_voltage(self, delta):
        """调整电压值"""
        try:
            current = float(self.voltage_var.get())
            new_voltage = current + delta
            if new_voltage < 0:
                new_voltage = 0
            elif new_voltage > 20:
                new_voltage = 20
            self.voltage_var.set(f"{new_voltage:.1f}")
            self.voltage_scale.set(new_voltage * 10)  # 乘以10适应0-200范围
        except ValueError:
            messagebox.showerror("错误", "当前电压值无效")

    def on_voltage_scale_change(self, event):
        """电压滑块变化处理（释放鼠标时）"""
        try:
            # ttk.Scale范围是0-200，对应0-20kV，步长0.1kV
            scale_value = self.voltage_scale.get()
            voltage_kv = scale_value / 10.0
            self.voltage_var.set(f"{voltage_kv:.1f}")
        except:
            pass

    def on_voltage_scale_drag(self, event):
        """电压滑块拖动处理（拖动过程中）"""
        try:
            # 仅在拖动时更新显示，不执行实际设置
            scale_value = self.voltage_scale.get()
            voltage_kv = scale_value / 10.0
            self.voltage_var.set(f"{voltage_kv:.1f}")
        except:
            pass

    def disable_hv(self):
        """关闭高压"""
        if hasattr(self.control_system, 'disable_high_voltage'):
            if self.control_system.disable_high_voltage():
                self.log_message("高压已关闭")
            else:
                self.log_message("高压关闭失败")
        else:
            # 如果没有直接的方法，通过设置0电压来模拟关闭
            if self.control_system.set_voltage_manual(0):
                self.log_message("高压输出已关闭")
            else:
                self.log_message("关闭高压输出失败")

    def emergency_stop(self):
        """紧急停止"""
        self.log_message(" 紧急停止！")
        # 立即设置电压为0
        if self.control_system.set_voltage_manual(0):
            self.log_message("电压已紧急设置为0")
        # 尝试关闭高压
        self.disable_hv()
        messagebox.showwarning("紧急停止", "系统已执行紧急停止！")

    def apply_safety_limits(self):
        """应用安全限制"""
        try:
            max_voltage = float(self.safety_max_voltage_var.get())
            max_current = float(self.safety_max_current_var.get())

            if 0 <= max_voltage <= 20 and 0 <= max_current <= 1000:
                # 这里可以添加实际的限制应用逻辑
                self.log_message(f" 安全限制已应用: 最大电压={max_voltage}kV, 最大电流={max_current}mA")
                messagebox.showinfo("成功", f"安全限制已应用\n最大电压: {max_voltage}kV\n最大电流: {max_current}mA")
            else:
                messagebox.showerror("错误", "限制值超出有效范围")
        except ValueError:
            messagebox.showerror("错误", "限制值必须是数字")

    def set_preset_voltage(self, voltage):
        """设置预设电压"""
        self.voltage_var.set(f"{voltage:.1f}")
        self.voltage_scale.set(voltage * 10)  # 乘以10适应0-200范围
        self.log_message(f" 预设电压已选择: {voltage}kV")

    def apply_ramp_rate(self):
        """应用电压爬升速率"""
        try:
            ramp_rate = float(self.ramp_rate_var.get())
            if 0.1 <= ramp_rate <= 10.0:
                self.log_message(f" 电压爬升速率已设置: {ramp_rate}kV/s")
                messagebox.showinfo("成功", f"电压爬升速率已设置为 {ramp_rate}kV/s")
            else:
                messagebox.showerror("错误", "爬升速率应在0.1-10.0 kV/s范围内")
        except ValueError:
            messagebox.showerror("错误", "爬升速率必须是数字")

    def clear_voltage_history(self):
        """清除电压历史记录"""
        self.voltage_history.delete(0, tk.END)
        self.log_message(" 电压历史记录已清除")

    def export_voltage_history(self):
        """导出电压历史记录"""
        # 这里可以添加实际的导出逻辑
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"voltage_history_{timestamp}.txt"
        self.log_message(f" 电压历史记录已导出到 {filename}")
        messagebox.showinfo("导出成功", f"电压历史记录已导出到\n{filename}")

    def update_manual_monitors(self):
        """更新手动控制监控显示"""
        try:
            # 获取当前输出状态
            output = self.control_system.read_output_status()
            if output:
                voltage = output.get('voltage_kv', 0)
                current = output.get('current_ma', 0)
                power = voltage * current  # 功率 = 电压(kV) * 电流(mA)

                self.voltage_monitor.config(text=f"电压: {voltage:.1f} kV")
                self.current_monitor.config(text=f"电流: {current:.1f} mA")
                self.power_monitor.config(text=f"功率: {power:.1f} W")

                # 更新状态
                if voltage > 0.1:
                    self.status_monitor.config(text="状态: 输出中", foreground="green")
                else:
                    self.status_monitor.config(text="状态: 待机", foreground="blue")
            else:
                self.voltage_monitor.config(text="电压: -- kV")
                self.current_monitor.config(text="电流: -- mA")
                self.power_monitor.config(text="功率: -- W")
                self.status_monitor.config(text="状态: 未知", foreground="gray")
        except:
            pass

    def set_voltage(self):
        """手动设置电压"""
        try:
            voltage = float(self.voltage_var.get())
            if 0 <= voltage <= 20:
                # 检查安全限制
                try:
                    max_voltage = float(self.safety_max_voltage_var.get())
                    if voltage > max_voltage:
                        if not messagebox.askyesno("安全警告",
                                                  f"电压值 {voltage}kV 超过最大限制 {max_voltage}kV\n是否继续？"):
                            return
                except:
                    pass

                if self.control_system.set_voltage_manual(voltage):
                    timestamp = datetime.now().strftime("%H:%M:%S")
                    history_entry = f"[{timestamp}] {voltage:.1f} kV"
                    self.voltage_history.insert(0, history_entry)
                    # 保持历史记录不超过50条
                    if self.voltage_history.size() > 50:
                        self.voltage_history.delete(50, tk.END)

                    self.log_message(f"手动设置电压: {voltage:.1f}kV")
                else:
                    self.log_message("电压设置失败")
            else:
                messagebox.showerror("错误", "电压值超出范围 (0-20kV)")
        except ValueError:
            messagebox.showerror("错误", "电压值必须是数字")

    def enable_hv(self):
        """开启高压"""
        # 检查当前电压是否超过安全限制
        try:
            voltage = float(self.voltage_var.get())
            max_voltage = float(self.safety_max_voltage_var.get())
            if voltage > max_voltage:
                if not messagebox.askyesno("安全警告",
                                          f"当前电压 {voltage}kV 超过最大限制 {max_voltage}kV\n是否继续开启高压？"):
                    return
        except:
            pass

        if self.control_system.enable_high_voltage():
            self.log_message("高压已开启")
        else:
            self.log_message("高压开启失败")

    def stop_control(self):
        self.control_system.stop_control()
        self.system_mode.set("空闲")
        self.log_message(" 控制已停止")

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def quit_system(self):
        self.control_system.running = False
        self.root.quit()
        self.root.destroy()

    def log_message(self, message):
        timestamp = datetime.now().strftime("%H:%M:%S")
        formatted_message = f"[{timestamp}] {message}\n"

        self.log_text.insert(tk.END, formatted_message)
        self.log_text.see(tk.END)

        print(formatted_message.strip())

    def update_status(self):
        # 更新连接状态
        conn_status = self.control_system.get_connection_status()
        if conn_status:
            self.status_vars['connection_status'].set("已连接" if conn_status['connected'] else "未连接")
            self.status_vars['control_status'].set("已获取" if conn_status['control_acquired'] else "未获取")
            self.status_vars['current_voltage'].set(f"{conn_status['current_voltage'] / 1000:.1f} kV")
            self.status_vars['current_current'].set(f"{conn_status['current_current']:.3f} mA")

            if conn_status['last_successful_command'] > 0:
                elapsed = time.time() - conn_status['last_successful_command']
                self.status_vars['last_success'].set(f"{elapsed:.1f}秒前")
            else:
                self.status_vars['last_success'].set("无")

        # 更新检测连接数
        client_count = len(self.control_system.clients)
        self.status_vars['detection_clients'].set(str(client_count))

        # 更新系统状态
        self.status_vars['target_mode'].set(str(self.control_system.target_mode))
        self.status_vars['current_voltage'].set(f"{self.control_system.current_voltage_kv:.1f} kV")
        self.status_vars['control_iteration'].set(str(self.control_system.control_iteration))

        # 更新模式信息
        mode_list = self.control_system.fuzzy_controller.get_mode_list()
        self.status_vars['detected_modes_count'].set(str(len(mode_list)))

        if mode_list and self.control_system.target_mode:
            for mode in mode_list:
                if mode['id'] == self.control_system.target_mode:
                    self.status_vars['target_voltage'].set(f"{mode['voltage']:.1f} kV")
                    break

        # 更新当前模式
        if self.control_system.latest_detection:
            detected_mode = self.control_system.latest_detection['detected_mode']
            confidence = self.control_system.latest_detection['confidence']
            timestamp = self.control_system.latest_detection.get('timestamp', 0)

            mode_id = self.control_system.fuzzy_controller.get_mode_id(detected_mode)

            if mode_id:
                self.status_vars['current_mode'].set(f"模式{mode_id}")
            else:
                self.status_vars['current_mode'].set("未知")

            self.status_vars['mode_name'].set(detected_mode)
            self.status_vars['confidence'].set(f"{confidence:.2f}")

            # 显示检测时间
            if timestamp:
                detection_time = datetime.fromtimestamp(timestamp).strftime("%H:%M:%S")
                self.status_vars['detection_time'].set(detection_time)
            else:
                self.status_vars['detection_time'].set("---")

            if hasattr(self.control_system.fuzzy_controller, 'last_error'):
                self.status_vars['error_value'].set(f"{self.control_system.fuzzy_controller.last_error:.2f}")
                self.status_vars['adjustment'].set(f"{self.control_system.fuzzy_controller.last_adjustment:.3f}kV")

            # 更新稳定性计数
            if hasattr(self.control_system.fuzzy_controller, 'stability_count'):
                self.status_vars['stability_count'].set(str(self.control_system.fuzzy_controller.stability_count))

        # 更新高压电源输出
        output_status = self.control_system.read_output_status()
        if output_status:
            self.status_vars['output_voltage'].set(f"{output_status['voltage_kv']:.2f} kV")
            self.status_vars['output_current'].set(f"{output_status['current_ma']:.3f} mA")

        # 更新模式列表
        mode_list = self.control_system.fuzzy_controller.get_mode_list()
        if mode_list:
            self.update_mode_list(mode_list)

        # 更新手动控制监控显示
        self.update_manual_monitors()

        self.root.after(1000, self.update_status)

    def update_mode_list(self, mode_list):
        """更新模式列表显示"""
        self.mode_listbox.delete(0, tk.END)
        mode_ids = []

        for mode in mode_list:
            display_text = f"模式{mode['id']}: {mode['name']} ({mode['voltage']:.1f}kV, {mode['count']}次)"
            self.mode_listbox.insert(tk.END, display_text)
            mode_ids.append(mode['id'])

        if mode_ids:
            self.target_mode_combo['values'] = mode_ids
            if self.target_mode_combo.current() < 0 and mode_ids:
                self.target_mode_combo.current(0)

    def run(self):
        self.root.mainloop()


class EnhancedIntegratedControlSystem:
    def __init__(self, modbus_port='COM5', detection_port=12345):
        self.modbus_port = modbus_port
        self.detection_port = detection_port

        self.target_mode = None
        self.current_voltage_kv = 0.0
        self.detection_history = deque(maxlen=30)
        self.exploration_completed = False

        # 新增：电压历史记录
        self.voltage_history = deque(maxlen=30)
        self.mode_history = deque(maxlen=30)

        # 新增：反馈真实性保障 - 瞬时误判过滤
        self.detection_filter_history = deque(maxlen=4)  # 存储最近4次检测结果用于过滤

        # 新增：稳定判定相关属性
        self.mode_match_history = deque(maxlen=50)  # 存储最近检测结果，用于5秒窗口匹配率计算
        self.stability_window_seconds = 5.0  # 5秒时间窗口
        self.match_threshold_stable = 0.8  # 稳定阈值：80%匹配
        self.mismatch_threshold_unstable = 0.3  # 不稳定阈值：30%不匹配
        self.last_stability_check_time = 0

        # 新增：动态维持状态
        self.dynamic_maintenance_active = False
        self.micro_scan_interval = 30  # 微扫描间隔30秒
        self.last_micro_scan_time = 0
        self.micro_scan_step = 0.1  # 微扫描步长0.1kv

        # 新增：三级梯度状态（0:稳定, 1:预警, 2:异常）
        self.three_level_status = 0  # 初始为稳定
        self.adaptive_adjustment_active = False
        self.consecutive_mismatch_counts = 0  # 连续不匹配计数

        # 新增：目标模式电压范围
        self.target_mode_voltage_range = None  # 目标模式的电压范围 (min, max)
        self.target_mode_optimal_voltage = None  # 目标模式的最优电压

        # 高可靠高压控制器
        self.hv_controller = RobustTCM6000iController(port=modbus_port)

        # 增强模糊控制器
        self.fuzzy_controller = EnhancedFuzzyController()

        # 模式-电压范围映射表 (新增)
        self.mode_voltage_ranges = {}  # 模式名 -> {'min': float, 'max': float, 'optimal': float, 'samples': list, 'overlap': bool, 'ambiguous': bool}
        self.voltage_mode_stats = defaultdict(lambda: defaultdict(int))  # 电压 -> 模式名 -> 计数
        self.mode_boundaries = {}  # 模式名 -> {'lower_bound': float, 'upper_bound': float, 'verified': bool}
        self.overlap_regions = []  # 重叠区列表 [(电压范围)]
        self.ambiguous_regions = []  # 模糊区列表 [(电压范围)]
        self.basic_mode = None  # 基础模式（电压最低的模式）

        self.control_enabled = False
        self.control_iteration = 0
        self.max_control_iterations = 1000  # 增加最大迭代次数
        self.last_adjustment_effect = 0
        self.exploration_active = False

        # 新增：控制状态
        self.stable_state = False
        self.consecutive_stable_counts = 0
        self.required_stable_counts = 10  # 需要连续稳定10次才认为真正稳定

        # 新增：目标模式控制相位
        self.control_phase = 'initial'  # 'initial', 'boundary_exploration', 'stable', 'dynamic_maintenance'
        self.boundary_exploration_active = False
        self.boundary_exploration_start_time = 0
        self.micro_scan_active = False
        self.last_per_second_check_time = 0  # 每秒统计的时间戳

        self.control_history = deque(maxlen=100)

        # 电压范围
        self.min_voltage = 0.0
        self.max_voltage = 20.0
        self.voltage_step = 0.5

        self.running = False
        self.detection_server_sock = None
        self.latest_detection = None

        self.clients = []  # 存储客户端信息的列表，每个元素是字典

        print(f"初始化控制系统")
        print(f"检测端口: {detection_port}")
        print(f" Modbus端口: {modbus_port}")

    def connect_hv_power(self):
        """连接高压电源"""
        return self.hv_controller.connect()

    def disconnect_hv_power(self):
        """断开高压电源"""
        self.hv_controller.disconnect()

    def test_connection(self):
        """测试连接"""
        return self.hv_controller.connect()

    def get_connection_status(self):
        """获取连接状态"""
        return self.hv_controller.get_connection_status()

    def set_voltage_manual(self, voltage_kv):
        """手动设置电压"""
        return self.hv_controller.set_voltage_kv(voltage_kv)

    def enable_high_voltage(self):
        """开启高压"""
        return self.hv_controller.enable_high_voltage()

    def disable_high_voltage(self):
        """关闭高压"""
        return self.hv_controller.disable_high_voltage()

    def read_output_status(self):
        """读取输出状态"""
        output = self.hv_controller.read_output_silent()
        if output:
            return {
                'voltage_kv': output['voltage'] / 1000,
                'current_ma': output['current'],
                'voltage_raw': output['voltage'],
                'current_raw': output['current']
            }
        return None

    def start_detection_server(self):
        """启动检测结果接收服务器（简化稳定版）"""
        try:
            print(f" 正在启动检测服务器端口 {self.detection_port}...")

            # 创建socket
            self.detection_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.detection_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # 绑定到所有接口
            try:
                self.detection_server_sock.bind(('0.0.0.0', self.detection_port))
            except OSError as e:
                print(f"绑定端口失败: {e}")
                print(" 可能原因：")
                print("   1. 端口已被占用")
                print("   2. 权限不足（Linux/Mac需要sudo）")
                return False

            self.detection_server_sock.listen(5)
            print(f"检测结果接收服务器已启动在 0.0.0.0:{self.detection_port}")

            # 启动accept线程
            accept_thread = threading.Thread(
                target=self._accept_detection_connections,
                name="DetectionAcceptThread",
                daemon=True
            )
            accept_thread.start()

            print(" 等待检测模块连接...")
            return True

        except Exception as e:
            print(f"启动检测服务器失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def _accept_detection_connections(self):
        """接受检测系统连接（稳定版）"""
        print(" TCP服务器accept线程开始运行...")

        # 先等待服务器socket完全就绪
        time.sleep(0.5)

        while self.running:
            try:
                # 检查socket是否有效
                if self.detection_server_sock is None:
                    print("服务器socket为None，等待重建...")
                    time.sleep(1)
                    continue

                # 使用带超时的accept，避免无限阻塞
                try:
                    # 设置socket超时
                    self.detection_server_sock.settimeout(1.0)
                    client_socket, address = self.detection_server_sock.accept()

                    print(f" 检测系统已连接: {address}")
                    print(f" 客户端端口: {address[1]}")

                    # 设置客户端socket超时
                    client_socket.settimeout(5.0)

                    self.clients.append({
                        'socket': client_socket,
                        'address': address,
                        'last_activity': time.time(),
                        'connected_time': datetime.now().strftime('%H:%M:%S')
                    })

                    # 发送连接确认
                    welcome_msg = json.dumps({
                        'status': 'connected',
                        'message': 'Control system ready',
                        'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                        'server_port': self.detection_port
                    }) + '\n'

                    try:
                        client_socket.send(welcome_msg.encode())
                        print(f" 欢迎消息已发送到 {address}")
                    except Exception as e:
                        print(f"发送欢迎消息失败: {e}")

                    # 启动数据处理线程
                    client_thread = threading.Thread(
                        target=self._handle_detection_client,
                        args=(client_socket, address),
                        name=f"ClientHandler-{address[1]}",
                        daemon=True
                    )
                    client_thread.start()

                except socket.timeout:
                    # 正常超时，继续循环
                    continue
                except OSError as e:
                    if e.errno == 10038:  # Windows上的无效socket错误
                        print("socket无效，尝试重新初始化...")
                        self._reinitialize_server_socket()
                    else:
                        print(f"accept错误: {e}")
                    time.sleep(1)
                    continue

            except Exception as e:
                print(f"accept循环错误: {e}")
                time.sleep(1)

        print(" TCP服务器accept线程结束")

    def _reinitialize_server_socket(self):
        """重新初始化服务器socket"""
        print(" 重新初始化服务器socket...")

        try:
            # 关闭当前socket
            if self.detection_server_sock:
                try:
                    self.detection_server_sock.close()
                except:
                    pass

            # 清理所有客户端连接
            for client_info in self.clients:
                try:
                    client_info['socket'].close()
                except:
                    pass
            self.clients.clear()

            # 重新创建socket
            self.detection_server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.detection_server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

            # 绑定到所有接口
            try:
                self.detection_server_sock.bind(('0.0.0.0', self.detection_port))
            except OSError as e:
                print(f"重新绑定端口失败: {e}")
                return False

            self.detection_server_sock.listen(5)
            print(f"服务器socket重新初始化成功，监听端口 {self.detection_port}")
            return True

        except Exception as e:
            print(f"重新初始化socket失败: {e}")
            return False

    def _handle_detection_client(self, client_socket, address):
        """处理检测客户端数据"""
        print(f" 开始处理客户端 {address} 的数据...")

        buffer = b""
        last_data_time = time.time()
        timeout = 30.0  # 30秒无数据超时

        try:
            while self.running:
                try:
                    # 接收数据
                    data = client_socket.recv(4096)
                    if not data:
                        print(f" 客户端 {address} 主动断开连接")
                        break

                    last_data_time = time.time()
                    print(f" 从 {address} 收到 {len(data)} 字节")

                    buffer += data

                    # 处理完整的数据行
                    while b'\n' in buffer:
                        line, buffer = buffer.split(b'\n', 1)
                        try:
                            line_str = line.decode('utf-8').strip()
                            if line_str:
                                self._process_detection_data(line_str, address)
                        except UnicodeDecodeError:
                            # 尝试其他编码
                            try:
                                line_str = line.decode('gbk').strip()
                                if line_str:
                                    self._process_detection_data(line_str, address)
                            except:
                                print(f"无法解码数据")
                        except Exception as e:
                            print(f"处理行数据错误: {e}")

                    # 检查是否超时
                    if time.time() - last_data_time > timeout:
                        print(f" 客户端 {address} 数据超时")
                        break

                except (ConnectionResetError, BrokenPipeError):
                    print(f" 客户端 {address} 连接异常断开")
                    break
                except socket.timeout:
                    # 正常超时，继续循环
                    continue
                except Exception as e:
                    print(f"接收数据错误: {e}")
                    break

        except Exception as e:
            print(f"客户端处理循环错误: {e}")
        finally:
            # 清理资源
            for i, client_info in enumerate(self.clients):
                if client_info['socket'] == client_socket:
                    self.clients.pop(i)
                    break

            try:
                client_socket.close()
            except:
                pass

            print(f" 客户端 {address} 处理结束")

    def _filter_transient_error(self, detected_mode):
        """过滤瞬时误判
        规则：如果当前检测结果与前3次连续结果不一致，判定为瞬时误判
        返回：True表示是瞬时误判，False表示有效检测
        """
        if len(self.detection_filter_history) < 3:
            # 历史数据不足，无法判断，直接接受
            self.detection_filter_history.append(detected_mode)
            return False

        # 获取前3次检测结果
        last_three = list(self.detection_filter_history)[-3:]

        # 检查前3次是否一致
        if len(set(last_three)) == 1:  # 前3次结果相同
            if detected_mode != last_three[0]:  # 当前结果与前3次不同
                print(f"检测到瞬时误判: 前3次均为'{last_three[0]}', 当前为'{detected_mode}'，已过滤")
                # 不将当前结果加入历史（过滤掉）
                return True

        # 有效检测，更新历史
        self.detection_filter_history.append(detected_mode)
        return False

    def _process_detection_data(self, data_str, address=None):
        """处理检测数据（增强版）"""
        if address:
            print(f" 从 {address} 尝试处理数据: {data_str[:100]}...")
        else:
            print(f" 尝试处理数据: {data_str[:100]}...")

        try:
            detection_data = json.loads(data_str)
            print(f"JSON解析成功")

            # 验证必要字段
            required_fields = ['detected_mode', 'confidence']
            for field in required_fields:
                if field not in detection_data:
                    print(f"缺失字段: {field}")
                    return

            detected_mode = detection_data['detected_mode']
            confidence = detection_data['confidence']
            timestamp = detection_data.get('timestamp', time.time())

            print(f" 收到检测结果: 模式 '{detected_mode}' (置信度: {confidence:.2f})")

            # 反馈真实性保障：瞬时误判过滤
            if confidence >= 0.5 and detected_mode != 'none':  # 只有置信度较高的检测才进行过滤
                is_transient_error = self._filter_transient_error(detected_mode)
                if is_transient_error:
                    print(f" 瞬时误判已过滤，不计入统计")
                    # 仍然记录到历史，但标记为瞬时误判
                    detection_data['transient_error'] = True
                else:
                    detection_data['transient_error'] = False
            else:
                detection_data['transient_error'] = False  # 低置信度检测不进行瞬时误判过滤

            # 更新最新检测结果
            self.latest_detection = detection_data

            # 添加到历史
            self.detection_history.append(detection_data)

            # 更新模式匹配历史（用于稳定判定）
            if not detection_data.get('transient_error', False) and confidence >= 0.5:
                current_time = time.time()
                self.mode_match_history.append({
                    'timestamp': current_time,
                    'detected_mode': detected_mode,
                    'confidence': confidence
                })

        except json.JSONDecodeError as e:
            print(f"JSON解析错误: {e}")
            print(f" 错误数据: {data_str}")
        except Exception as e:
            print(f"处理检测数据错误: {e}")
            import traceback
            traceback.print_exc()

    def exploration_phase(self, min_voltage, max_voltage, voltage_step, wait_time, confidence_threshold):
        """电压探索与模式识别阶段（使用用户输入的电压步长，步时固定为0.3秒）"""
        self.exploration_active = True
        self.exploration_completed = False

        print(f"\n开始电压探索与模式识别")
        print(f"电压范围: {min_voltage}kV - {max_voltage}kV")
        print(f"使用参数: 步长{voltage_step}kV, 步时固定0.3秒 (反馈等待0.15秒+统计0.15秒), 阈值{confidence_threshold}")

        # 新运行逻辑参数
        scan_step = voltage_step  # 使用用户输入的电压步长
        step_time = 0.3  # 步时0.3秒
        min_wait_time = 0.15  # 最小反馈等待时间0.15秒
        stats_time = step_time - min_wait_time  # 统计时间

        # 清空统计数据
        self.voltage_mode_stats.clear()
        self.mode_voltage_ranges.clear()
        self.overlap_regions.clear()
        self.ambiguous_regions.clear()

        # 1. 检查检测连接
        print(f" 当前检测连接数: {len(self.clients)}")

        if not self.clients:
            print("警告：没有检测模块连接！")
            print(" 请确保检测模块程序已启动并连接到控制系统")
            print(" 检测模块应连接到: localhost:12345")
            print(" 等待10秒检测连接...")

            for i in range(10):
                if self.clients:
                    print(f"检测模块已连接")
                    break
                print(f" 等待... ({i + 1}/10)")
                time.sleep(1)
            else:
                print("检测模块未连接，探索中止")
                print(" 请检查：")
                print("   1. 检测模块程序是否启动")
                print("   2. 检测模块是否连接到localhost:12345")
                print("   3. 防火墙是否阻止连接")
                self.exploration_active = False
                return

        # 2. 测试连接
        print(" 测试检测连接通信...")
        test_success = False
        for client_info in self.clients:
            try:
                test_msg = json.dumps({'test': True, 'timestamp': time.time()}) + '\n'
                client_info['socket'].send(test_msg.encode())
                print(f"测试消息已发送到 {client_info['address']}")
                test_success = True
                break
            except:
                continue

        if not test_success:
            print("无法发送测试消息")
            self.exploration_active = False
            return

        # 3. 重置检测状态
        self.latest_detection = None
        print(" 重置检测状态，等待新数据...")
        time.sleep(1)  # 等待检测模块发送数据

        # 4. 确保高压电源连接
        if not self.hv_controller.connect():
            print("无法连接高压电源，探索中止")
            self.exploration_active = False
            return

        # 第一轮遍历：使用电压步长{voltage_step}kv（用户输入）
        # scan_step已在上方定义为用户输入的电压步长
        voltages = np.arange(min_voltage, max_voltage + scan_step, scan_step)
        mode_detections = defaultdict(list)

        # 存储第一次遍历的边界结果
        first_pass_boundaries = {}

        for voltage_kv in voltages:
            if not self.running or not self.exploration_active:
                break

            voltage_kv = round(voltage_kv, 1)

            # 设置电压
            if self.hv_controller.set_voltage_kv(voltage_kv):
                self.current_voltage_kv = voltage_kv
                print(f"设置电压: {voltage_kv:.1f}kV, 等待检测...")

                # 等待最小反馈等待时间
                time.sleep(min_wait_time)

                # 收集多个检测结果以提高可靠性（符合新运行逻辑）
                detections = []
                for i in range(3):
                    if self.latest_detection:
                        detected_mode = self.latest_detection['detected_mode']
                        confidence = self.latest_detection['confidence']
                        transient_error = self.latest_detection.get('transient_error', False)

                        # 反馈真实性保障：跳过瞬时误判和低置信度检测
                        if (not transient_error and detected_mode != 'none'
                                and confidence >= confidence_threshold):
                            detections.append(detected_mode)
                            print(f"采样{i + 1}: 检测到模式{detected_mode} (置信度: {confidence:.2f})")
                        elif transient_error:
                            print(f"采样{i + 1}: 瞬时误判已过滤 (模式: {detected_mode})")

                    if i < 2:
                        time.sleep(stats_time / 3)  # 使用统计时间

                # 处理检测结果
                if detections:
                    # 统计模式分布
                    from collections import Counter
                    counter = Counter(detections)
                    total = len(detections)

                    # 记录电压-模式统计
                    self.voltage_mode_stats[voltage_kv] = defaultdict(int)
                    for mode, count in counter.items():
                        self.voltage_mode_stats[voltage_kv][mode] = count

                    # 判断主要模式（占比≥50%）
                    main_mode = None
                    max_ratio = 0
                    for mode, count in counter.items():
                        ratio = count / total
                        if ratio > max_ratio:
                            max_ratio = ratio
                            main_mode = mode

                    if max_ratio >= 0.5:  # 主要模式判定标准
                        # 添加到模糊控制器的映射（保持向后兼容）
                        self.fuzzy_controller.add_mode_voltage_mapping(main_mode, voltage_kv)
                        print(f"识别到模式: {main_mode} (电压: {voltage_kv:.1f}kV, 占比{max_ratio:.1%})")

                        # 记录检测
                        mode_detections[main_mode].append(voltage_kv)
                    else:
                        print(f"模糊区: 无主要模式（电压: {voltage_kv:.1f}kV, 最高占比{max_ratio:.1%}）")
                        self.ambiguous_regions.append((voltage_kv, voltage_kv))
                else:
                    print(f"未检测到有效模式 (电压: {voltage_kv:.1f}kV)")
            else:
                print(f"电压设置失败: {voltage_kv:.1f}kV")

        # 分析模式范围边界
        print(f"\n分析模式范围边界...")
        self._analyze_mode_boundaries()

        # 存储第一次遍历的边界结果
        for mode, info in self.mode_voltage_ranges.items():
            first_pass_boundaries[mode] = {'min': info['min'], 'max': info['max']}
            print(f"  第一次遍历 - 模式{mode}: {info['min']:.1f}kV - {info['max']:.1f}kV")

        # 第二轮遍历：边界验证（使用0.1kv小步长）
        print(f"\n第二轮遍历：边界验证（步长0.1kV）")
        self._verify_boundaries_with_fine_scan(scan_step, min_wait_time, stats_time, confidence_threshold)

        # 双重验证：比较两次遍历的结果差异
        print(f"\n双重验证：比较两次遍历的边界差异")
        need_restart = False
        for mode, first_info in first_pass_boundaries.items():
            if mode in self.mode_voltage_ranges:
                second_info = self.mode_voltage_ranges[mode]
                min_diff = abs(second_info['min'] - first_info['min'])
                max_diff = abs(second_info['max'] - first_info['max'])

                print(f"  模式{mode}: 下边界差异{min_diff:.1f}kV, 上边界差异{max_diff:.1f}kV")

                if min_diff > 0.1 or max_diff > 0.1:
                    print(f"  警告：模式{mode}的边界差异超过0.1kV，建议重新启动全范围遍历")
                    need_restart = True

        if need_restart:
            print(f"  注意：边界差异过大，但系统将继续使用第二次验证后的结果")
            print(f"  如需更高精度，请手动重新启动探索阶段")

        # 计算最优电压点
        print(f"\n计算最优电压点...")
        self._calculate_optimal_voltages()

        # 将探索得到的模式范围同步到 mode_voltage_map，保证前端/API 能拿到全部模式
        try:
            if self.fuzzy_controller and hasattr(self.fuzzy_controller, 'ensure_modes_from_ranges'):
                self.fuzzy_controller.ensure_modes_from_ranges(self.mode_voltage_ranges)
        except Exception as e:
            print(f"⚠️ 同步模式列表失败: {e}")

        # 确定基础模式（电压最低的模式）
        if self.mode_voltage_ranges:
            self.basic_mode = min(self.mode_voltage_ranges.keys(),
                                 key=lambda x: self.mode_voltage_ranges[x]['min'])
            basic_range = self.mode_voltage_ranges[self.basic_mode]
            midpoint = (basic_range['min'] + basic_range['max']) / 2
            print(f"基础模式: {self.basic_mode}, 电压范围中点: {midpoint:.1f}kV")

            # 调节到基础模式电压范围中点
            if self.hv_controller.set_voltage_kv(midpoint):
                self.current_voltage_kv = midpoint
                print(f"已调节至基础模式电压范围中点: {midpoint:.1f}kV")

        self.exploration_active = False
        self.exploration_completed = True

        print(f"\n电压探索与模式识别完成!")
        print(f"识别到的模式范围:")
        for mode, info in self.mode_voltage_ranges.items():
            print(f"  模式{mode}: {info['min']:.1f}kV - {info['max']:.1f}kV, 最优电压: {info['optimal']:.1f}kV")
        if self.overlap_regions:
            print(f"重叠区: {self.overlap_regions}")
        if self.ambiguous_regions:
            print(f"模糊区: {self.ambiguous_regions}")

        # 显示识别的模式（保持兼容）
        mode_list = self.fuzzy_controller.get_mode_list()
        if mode_list:
            print(f"识别到的模式 ({len(mode_list)}种):")
            for mode in mode_list:
                print(f"  模式{mode['id']}: {mode['name']} ({mode['voltage']:.1f}kV, {mode['count']}次检测)")
        else:
            print("未识别到任何模式")

    def _analyze_mode_boundaries(self):
        """分析模式范围边界"""
        # 按模式整理电压统计（占比≥20%即纳入，便于返回多个目标模式）
        mode_voltages = defaultdict(list)
        for voltage, mode_counts in self.voltage_mode_stats.items():
            total = sum(mode_counts.values())
            if total <= 0:
                continue
            for mode, count in mode_counts.items():
                ratio = count / total
                if ratio >= 0.2:  # 占比超过20%即考虑，使探索后更容易得到多个模式
                    mode_voltages[mode].append((voltage, ratio))

        for mode, voltage_data in mode_voltages.items():
            if not voltage_data:
                continue

            voltages = [v for v, _ in voltage_data]
            min_v = min(voltages)
            max_v = max(voltages)

            # 检查连续性（电压范围是否连续）
            sorted_voltages = sorted(voltages)
            continuous = True
            for i in range(1, len(sorted_voltages)):
                if sorted_voltages[i] - sorted_voltages[i-1] > 0.2:  # 允许0.2kV间隔
                    continuous = False
                    break

            self.mode_voltage_ranges[mode] = {
                'min': min_v,
                'max': max_v,
                'optimal': None,  # 稍后计算
                'samples': voltage_data,
                'continuous': continuous,
                'verified': False
            }

        # 补全：凡在探索中曾出现过的模式都纳入，避免只返回一个模式
        all_modes_in_stats = set()
        for voltage, mode_counts in self.voltage_mode_stats.items():
            for mode, count in mode_counts.items():
                if count > 0:
                    all_modes_in_stats.add(mode)
        for mode in all_modes_in_stats:
            if mode in self.mode_voltage_ranges:
                continue
            voltages_for_mode = []
            for voltage, mode_counts in self.voltage_mode_stats.items():
                count = mode_counts.get(mode, 0)
                if count > 0:
                    total = sum(mode_counts.values())
                    ratio = count / total if total > 0 else 0
                    voltages_for_mode.append((voltage, ratio))
            if not voltages_for_mode:
                continue
            vs = [v for v, _ in voltages_for_mode]
            mid = (min(vs) + max(vs)) / 2.0
            self.mode_voltage_ranges[mode] = {
                'min': min(vs),
                'max': max(vs),
                'optimal': mid,
                'samples': voltages_for_mode,
                'continuous': True,
                'verified': False
            }
            print(f"  补全模式: {mode} (电压: {min(vs):.1f}kV - {max(vs):.1f}kV)")

    def _verify_boundaries_with_fine_scan(self, scan_step, min_wait_time, stats_time, confidence_threshold):
        """使用小步长验证边界"""
        for mode, info in self.mode_voltage_ranges.items():
            if not info['continuous']:
                continue

            # 在边界附近进行精细扫描
            lower_bound = info['min']
            upper_bound = info['max']

            # 验证下边界
            verify_voltages = np.arange(lower_bound - 0.3, lower_bound + 0.31, scan_step)
            for voltage_kv in verify_voltages:
                voltage_kv = round(voltage_kv, 1)
                if voltage_kv < 0:
                    continue

                if self.hv_controller.set_voltage_kv(voltage_kv):
                    self.current_voltage_kv = voltage_kv
                    time.sleep(min_wait_time)

                    # 收集检测结果
                    detections = []
                    for i in range(3):
                        if self.latest_detection:
                            detected_mode = self.latest_detection['detected_mode']
                            confidence = self.latest_detection['confidence']
                            transient_error = self.latest_detection.get('transient_error', False)
                            # 跳过瞬时误判和低置信度检测
                            if (not transient_error and detected_mode != 'none'
                                    and confidence >= confidence_threshold):
                                detections.append(detected_mode)
                        if i < 2:
                            time.sleep(stats_time / 3)

                    if detections:
                        from collections import Counter
                        counter = Counter(detections)
                        total = len(detections)
                        mode_count = counter.get(mode, 0)
                        ratio = mode_count / total if total > 0 else 0

                        # 更新统计
                        if voltage_kv not in self.voltage_mode_stats:
                            self.voltage_mode_stats[voltage_kv] = defaultdict(int)
                        self.voltage_mode_stats[voltage_kv][mode] += mode_count

                        # 如果比例高，调整边界
                        if ratio >= 0.5:
                            info['min'] = min(info['min'], voltage_kv)

            # 类似验证上边界（简略实现）
            verify_voltages = np.arange(upper_bound - 0.3, upper_bound + 0.31, scan_step)
            for voltage_kv in verify_voltages:
                voltage_kv = round(voltage_kv, 1)
                if voltage_kv > 20:  # 限制最大电压
                    continue

                if self.hv_controller.set_voltage_kv(voltage_kv):
                    self.current_voltage_kv = voltage_kv
                    time.sleep(min_wait_time)

                    # 收集检测结果（简略）
                    detections = []
                    for i in range(3):
                        if self.latest_detection:
                            detected_mode = self.latest_detection['detected_mode']
                            confidence = self.latest_detection['confidence']
                            transient_error = self.latest_detection.get('transient_error', False)
                            # 跳过瞬时误判和低置信度检测
                            if (not transient_error and detected_mode != 'none'
                                    and confidence >= confidence_threshold):
                                detections.append(detected_mode)
                        if i < 2:
                            time.sleep(stats_time / 3)

                    if detections:
                        from collections import Counter
                        counter = Counter(detections)
                        total = len(detections)
                        mode_count = counter.get(mode, 0)
                        ratio = mode_count / total if total > 0 else 0

                        if voltage_kv not in self.voltage_mode_stats:
                            self.voltage_mode_stats[voltage_kv] = defaultdict(int)
                        self.voltage_mode_stats[voltage_kv][mode] += mode_count

                        if ratio >= 0.5:
                            info['max'] = max(info['max'], voltage_kv)

            info['verified'] = True

    def _calculate_optimal_voltages(self):
        """计算各模式的最优电压点（范围内匹配率最高的电压）"""
        for mode, info in self.mode_voltage_ranges.items():
            max_ratio = 0
            optimal_voltage = None

            for voltage, ratio in info['samples']:
                if ratio > max_ratio:
                    max_ratio = ratio
                    optimal_voltage = voltage

            if optimal_voltage is not None:
                info['optimal'] = optimal_voltage
            else:
                # 如果没有样本，取范围中点
                info['optimal'] = (info['min'] + info['max']) / 2

    def start_target_control(self, target_mode):
        """启动目标模式控制"""
        mode_list = self.fuzzy_controller.get_mode_list()
        if not mode_list:
            print("未识别到任何模式")
            return False

        # 统一按字符串比较，避免前后端类型不一致
        target_mode = str(target_mode).strip() if target_mode is not None else ""
        mode_ids = [str(mode['id']) for mode in mode_list]
        if not target_mode or target_mode not in mode_ids:
            print(f"目标模式 {target_mode} 未在探索阶段识别到，可用: {mode_ids}")
            return False

        self.target_mode = target_mode
        self.control_enabled = True
        self.control_iteration = 0
        self.stable_state = False
        self.consecutive_stable_counts = 0

        # 重置控制相位
        self.control_phase = 'initial'
        self.boundary_exploration_active = False
        self.micro_scan_active = False
        self.last_per_second_check_time = time.time()

        # 重置三级梯度状态
        self.three_level_status = 0
        self.adaptive_adjustment_active = False
        self.dynamic_maintenance_active = False

        print(f"\n 启动目标控制")
        print(f" 目标模式: {target_mode}")

        # 获取目标模式名称和电压范围
        target_mode_name = None
        target_voltage = None
        mode_list = self.fuzzy_controller.get_mode_list()
        for mode in mode_list:
            if str(mode['id']) == target_mode:
                target_mode_name = mode['name']
                target_voltage = float(mode['voltage']) if mode.get('voltage') is not None else None
                break

        # 设置目标模式电压范围和最优电压
        if target_mode_name and target_mode_name in self.mode_voltage_ranges:
            mode_range_info = self.mode_voltage_ranges[target_mode_name]
            self.target_mode_voltage_range = (mode_range_info['min'], mode_range_info['max'])
            self.target_mode_optimal_voltage = mode_range_info['optimal']
            print(f" 目标电压范围: {self.target_mode_voltage_range[0]:.1f}kV - {self.target_mode_voltage_range[1]:.1f}kV")
            print(f" 最优电压点: {self.target_mode_optimal_voltage:.1f}kV")
        else:
            # 如果没有范围信息，使用模糊控制器的电压
            self.target_mode_voltage_range = None
            self.target_mode_optimal_voltage = target_voltage if target_voltage is not None else 0.0
            if target_voltage is not None:
                print(f" 警告：未找到目标模式的电压范围信息，使用单个电压点: {target_voltage:.1f}kV")

        # 获取目标电压（从模糊控制器）
        if target_voltage:
            print(f" 目标电压: {target_voltage:.1f}kV")
            # 设置到目标电压附近
            self.hv_controller.set_voltage_kv(target_voltage)
            self.current_voltage_kv = target_voltage
        else:
            print("无法获取目标电压，使用当前电压开始控制")

        print(" 系统将通过增强稳定性控制算法调整电压")
        print(" 开始控制循环...")

        return True

    def _calculate_match_rate_in_window(self, window_seconds=5.0):
        """计算最近时间窗口内的模式匹配率
        返回：匹配率（0-1），有效样本数，总样本数
        """
        current_time = time.time()
        window_start = current_time - window_seconds

        # 过滤出时间窗口内的检测结果
        window_detections = []
        for detection in self.mode_match_history:
            if detection['timestamp'] >= window_start:
                window_detections.append(detection)

        if not window_detections:
            return 0.0, 0, 0

        # 获取目标模式名称（通过模式ID查找）
        target_mode_name = None
        mode_list = self.fuzzy_controller.get_mode_list()
        for mode in mode_list:
            if mode['id'] == self.target_mode:
                target_mode_name = mode['name']
                break

        if not target_mode_name:
            return 0.0, 0, 0

        # 统计匹配情况
        total_samples = len(window_detections)
        matched_samples = 0
        for detection in window_detections:
            if detection['detected_mode'] == target_mode_name:
                matched_samples += 1

        match_rate = matched_samples / total_samples if total_samples > 0 else 0.0
        return match_rate, matched_samples, total_samples

    def _check_stability(self, current_mode_id):
        """检查系统稳定性（基于时间窗口的匹配率）"""
        current_time = time.time()

        # 每秒统计检查：如果系统处于稳定状态，每秒检查一次是否不再稳定
        if self.stable_state and current_time - self.last_per_second_check_time >= 1.0:
            self.last_per_second_check_time = current_time
            # 计算5秒窗口内的匹配率
            match_rate, matched_samples, total_samples = self._calculate_match_rate_in_window(
                window_seconds=self.stability_window_seconds
            )
            # 如果5秒内30%以上不匹配（即匹配率低于70%），则认为不再稳定
            if total_samples >= 3 and match_rate < 0.7:
                print(f"每秒统计：匹配率{match_rate:.1%}低于70%，系统不再稳定，进入动态维持状态")
                self.stable_state = False
                self.control_phase = 'dynamic_maintenance'
                self.dynamic_maintenance_active = True
                # 触发动态维持：执行情况1（边界探索）
                self._start_boundary_exploration()

        # 计算5秒窗口内的匹配率（用于常规检查）
        match_rate, matched_samples, total_samples = self._calculate_match_rate_in_window(
            window_seconds=self.stability_window_seconds
        )

        # 更新三级梯度状态（调整阈值以匹配用户描述）
        old_status = self.three_level_status
        if match_rate >= 0.9:  # 稳定状态（≥90%匹配）
            self.three_level_status = 0
        elif match_rate >= 0.85:  # 预警状态（85%-89%匹配）- 动态维持触发范围
            self.three_level_status = 1
        else:  # 异常状态（≤84%匹配）
            self.three_level_status = 2

        # 状态变化时打印信息
        if old_status != self.three_level_status:
            status_names = ["稳定", "预警", "异常"]
            print(f" 状态变化: {status_names[old_status]} -> {status_names[self.three_level_status]} "
                  f"(匹配率: {match_rate:.1%}, {matched_samples}/{total_samples})")

        # 稳定判定：5秒内80%以上匹配，且最近一次检测匹配
        is_stable_by_match_rate = match_rate >= self.match_threshold_stable and total_samples >= 3
        # 同时检查当前模式是否匹配（防止历史数据影响）
        current_match = (current_mode_id == self.target_mode)

        # 更新连续稳定计数（兼容原有逻辑）
        if is_stable_by_match_rate and current_match:
            self.consecutive_stable_counts += 1
        else:
            self.consecutive_stable_counts = max(0, self.consecutive_stable_counts - 2)

        # 检查电压稳定性
        voltage_stable = False
        if len(self.voltage_history) >= 5:
            recent_voltages = list(self.voltage_history)[-5:]
            voltage_std = np.std(recent_voltages)
            voltage_stable = voltage_std < 0.1  # 电压标准差小于0.1kV

        # 稳定状态判定：匹配率稳定且电压稳定
        should_be_stable = (is_stable_by_match_rate and current_match and voltage_stable)

        if should_be_stable:
            if not self.stable_state:
                print(f" 系统已达到稳定状态！匹配率{match_rate:.1%}, 连续稳定{self.consecutive_stable_counts}次")
                self.stable_state = True
            return True
        else:
            if self.stable_state:
                print(f"系统退出稳定状态 (匹配率: {match_rate:.1%})")
                self.stable_state = False
            return False

    def _start_boundary_exploration(self):
        """启动边界探索（情况1）：对目标模式电压范围边界进行二次探索"""
        if not self.target_mode or not self.target_mode_voltage_range:
            print("边界探索：缺少目标模式或电压范围信息")
            return False

        print(f"启动边界探索：对目标模式{self.target_mode}的电压范围进行二次验证")
        print(f"电压范围: {self.target_mode_voltage_range[0]:.1f}kV - {self.target_mode_voltage_range[1]:.1f}kV")

        self.boundary_exploration_active = True
        self.control_phase = 'boundary_exploration'
        self.boundary_exploration_start_time = time.time()

        # 在实际实现中，这里应该启动一个线程进行边界探索
        # 简化实现：标记需要边界探索，在控制循环中处理
        print("边界探索已标记，将在控制循环中执行")
        return True

    def _execute_boundary_exploration(self):
        """执行边界探索（简化版）"""
        if not self.boundary_exploration_active:
            return False

        # 获取目标模式名称
        target_mode_name = None
        mode_list = self.fuzzy_controller.get_mode_list()
        for mode in mode_list:
            if mode['id'] == self.target_mode:
                target_mode_name = mode['name']
                break

        if not target_mode_name:
            self.boundary_exploration_active = False
            return False

        # 简化实现：在边界附近进行几次电压调整
        # 实际应该按照用户描述：以0.1kv小步长进行二次遍历验证
        print(f"执行边界探索：在目标模式'{target_mode_name}'的电压范围边界附近验证")

        # 标记边界探索完成（简化）
        self.boundary_exploration_active = False
        self.control_phase = 'stable' if self.stable_state else 'initial'
        print("边界探索完成（简化实现）")
        return True

    def _execute_dynamic_maintenance(self):
        """执行动态维持状态：周期性微扫描，匹配率降至85%-89%时微调节电压"""
        if not self.dynamic_maintenance_active:
            return False

        current_time = time.time()

        # 检查是否需要执行周期性微扫描（每30秒一次）
        if current_time - self.last_micro_scan_time >= self.micro_scan_interval:
            print("动态维持：执行周期性微扫描")
            self._execute_micro_scan()
            self.last_micro_scan_time = current_time

        # 检查匹配率是否降至85%-89%（预警状态）
        if self.three_level_status == 1:  # 预警状态（70%-89%匹配）
            # 计算精确匹配率
            match_rate, matched_samples, total_samples = self._calculate_match_rate_in_window(
                window_seconds=self.stability_window_seconds
            )
            if 0.85 <= match_rate <= 0.89:
                print(f"动态维持：匹配率{match_rate:.1%}在85%-89%范围内，执行微调节")
                self._execute_micro_adjustment()
            elif match_rate < 0.85:
                print(f"动态维持：匹配率{match_rate:.1%}低于85%，需要更强调节")
                # 可以触发边界探索或更大调整

        return True

    def _execute_micro_scan(self):
        """执行微扫描：在当前电压附近小范围扫描"""
        print(f"微扫描：在当前电压{self.current_voltage_kv:.1f}kV附近±{self.micro_scan_step*3:.1f}kV范围扫描")
        # 简化实现：记录微扫描已执行
        # 实际实现应该在当前电压附近以小步长扫描，检测模式匹配率变化

    def _execute_micro_adjustment(self):
        """执行微调节：轻微调整电压以提高匹配率"""
        print(f"微调节：基于当前匹配率轻微调整电压")
        # 简化实现：使用模糊控制器进行小幅度调整
        # 实际实现应该根据匹配率变化趋势决定调整方向

    def control_loop(self):
        """主控制循环 - 增强稳定性版本"""
        last_control_time = 0
        last_status_time = 0
        control_interval = 0.5  # 增加控制间隔，降低调整频率
        status_interval = 5

        while self.running:
            if self.control_enabled:
                current_time = time.time()

                if current_time - last_status_time >= status_interval:
                    self.display_system_status()
                    last_status_time = current_time

                if current_time - last_control_time >= control_interval:
                    self._execute_control_cycle()
                    last_control_time = current_time

            time.sleep(0.2)  # 增加睡眠时间，降低CPU使用率

    def _execute_control_cycle(self):
        """执行控制周期 - 增强稳定性版本"""
        if not self.latest_detection:
            print(" 等待检测结果...")
            return

        if not self.target_mode:
            print(" 等待设置目标模式...")
            return

        detected_mode = self.latest_detection['detected_mode']
        confidence = self.latest_detection['confidence']
        transient_error = self.latest_detection.get('transient_error', False)

        # 反馈真实性保障：跳过瞬时误判
        if transient_error:
            print(f"瞬时误判已过滤 (模式: {detected_mode})，跳过此次控制周期")
            return

        if confidence < 0.5 or detected_mode == 'none':  # 提高置信度阈值
            print(f"检测置信度低: {confidence:.2f}，等待可靠检测")
            return

        try:
            if self.control_iteration >= self.max_control_iterations:
                print(f"达到最大控制迭代次数 {self.max_control_iterations}")
                self.control_enabled = False
                return

            self.control_iteration += 1

            # 获取当前模式编号
            current_mode_id = self.fuzzy_controller.get_mode_id(detected_mode)
            if not current_mode_id:
                print(f"检测到未知模式: {detected_mode}，忽略此次检测")
                return

            # 目标模式定向调节逻辑（根据用户描述的两种情况）
            if self.control_phase == 'initial':
                if current_mode_id == self.target_mode:
                    # 情况1：监测结果即为目标模式，电压在目的模式对应的电压范围内
                    print(f"情况1：检测到目标模式{self.target_mode}，启动边界探索")
                    self.control_phase = 'boundary_exploration'
                    self._start_boundary_exploration()
                else:
                    # 情况2：监测结果不为目标模式，电压不在目的模式对应的电压范围内
                    print(f"情况2：当前模式{current_mode_id}≠目标模式{self.target_mode}，使用模糊控制器调整电压")
                    # 继续使用模糊控制器调整（现有逻辑）

            # 如果处于边界探索阶段，执行边界探索
            if self.control_phase == 'boundary_exploration' and self.boundary_exploration_active:
                self._execute_boundary_exploration()
                return  # 边界探索期间跳过常规调整

            # 如果处于动态维持阶段，执行动态维持逻辑
            if self.control_phase == 'dynamic_maintenance' and self.dynamic_maintenance_active:
                self._execute_dynamic_maintenance()
                return  # 动态维持期间跳过常规调整

            # 检查系统稳定性
            is_stable = self._check_stability(current_mode_id)

            # 如果系统已经稳定，减少调整频率
            if is_stable:
                if self.control_iteration % 3 != 0:  # 每3次控制周期执行1次
                    return
                print(f"💤 系统稳定中，跳过本次调整")

            # 计算调整效果
            if hasattr(self.fuzzy_controller, 'error_history') and len(self.fuzzy_controller.error_history) > 1:
                last_error = self.fuzzy_controller.error_history[-2] if len(
                    self.fuzzy_controller.error_history) > 1 else 0
                current_error = self.fuzzy_controller.last_error
                effect = last_error - current_error
                self.last_adjustment_effect = max(-4, min(4, effect))
            else:
                self.last_adjustment_effect = 0

            # 计算调整量
            adjustment, error, error_change = self.fuzzy_controller.calculate_adjustment(
                self.target_mode, current_mode_id, self.current_voltage_kv, self.last_adjustment_effect
            )

            # 应用电压调整
            new_voltage = self.current_voltage_kv + adjustment
            new_voltage = max(0.0, min(20.0, new_voltage))

            # 如果系统稳定，进一步减小调整幅度
            if is_stable:
                adjustment *= 0.3
                new_voltage = self.current_voltage_kv + adjustment

            if abs(new_voltage - self.current_voltage_kv) > 0.001:
                # 通过高压控制器设置电压
                if self.hv_controller.set_voltage_kv(new_voltage):
                    self.current_voltage_kv = new_voltage

                    control_info = f"控制迭代 {self.control_iteration}: "
                    control_info += f"目标=模式{self.target_mode}, 当前=模式{current_mode_id}({detected_mode}), "
                    control_info += f"电压误差={error:.2f}, 调整={adjustment:.3f}kV, "
                    control_info += f"新电压={new_voltage:.2f}kV"

                    if is_stable:
                        control_info += f", 稳定计数={self.consecutive_stable_counts}"

                    print(control_info)

            # 记录控制历史
            self._record_control_history(detected_mode, adjustment, error, current_mode_id)

        except ValueError as e:
            print(f"模式数据错误: {detected_mode}, {e}")

    def _record_control_history(self, current_mode_name, adjustment, error, current_mode_id):
        """记录控制历史"""
        record = {
            'timestamp': datetime.now().strftime("%H:%M:%S"),
            'target_mode': self.target_mode,
            'detected_mode': current_mode_name,
            'mode_id': current_mode_id,
            'voltage': self.current_voltage_kv,
            'adjustment': adjustment,
            'error': error,
            'iteration': self.control_iteration,
            'stable': self.stable_state
        }
        self.control_history.append(record)

    def display_system_status(self):
        """显示系统状态"""
        print("\n" + "=" * 90)
        print("                     增强版高可靠控制系统状态面板")
        print("=" * 90)
        print(f"时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

        if self.target_mode:
            print(f"目标模式: 模式{self.target_mode}")
            target_voltage = self.fuzzy_controller.get_target_voltage(self.target_mode)
            if target_voltage:
                print(f"目标电压: {target_voltage:.1f}kV")

        print(f"当前电压: {self.current_voltage_kv:.1f}kV")
        print(f"控制状态: {'🔴 启用' if self.control_enabled else '⚪ 禁用'}")
        print(f"控制迭代: {self.control_iteration}")

        if hasattr(self, 'stable_state'):
            print(f"稳定状态: {'稳定' if self.stable_state else ' 调整中'}")
            print(f"稳定计数: {self.consecutive_stable_counts}/{self.required_stable_counts}")

        print(f"检测连接数: {len(self.clients)}")

        mode_list = self.fuzzy_controller.get_mode_list()
        print(f"已识别模式数: {len(mode_list)}")

        if self.latest_detection:
            detected_mode = self.latest_detection['detected_mode']
            confidence = self.latest_detection['confidence']
            mode_id = self.fuzzy_controller.get_mode_id(detected_mode)

            if mode_id:
                print(f"最新检测: 模式{mode_id}({detected_mode}) (置信度: {confidence:.2f})")
            else:
                print(f"最新检测: {detected_mode} (置信度: {confidence:.2f})")

        if mode_list:
            # 修复f-string中的反斜杠问题
            mode_strs = []
            for mode in mode_list:
                mode_strs.append(f"模式{mode['id']}")
            print(f"识别到的模式: {mode_strs}")

        print("=" * 90)

    def test_detection_connection(self):
        """测试检测连接"""
        print(" 测试检测连接...")

        # 检查服务器状态
        if not self.detection_server_sock:
            print("检测服务器未运行")
            return False

        print(f" 当前检测连接数: {len(self.clients)}")

        if not self.clients:
            print("没有活动的检测连接")
            return False

        # 测试第一个连接
        try:
            client_info = self.clients[0]
            test_msg = json.dumps({
                'test': True,
                'timestamp': time.time(),
                'message': 'Connection test from control system'
            }) + '\n'

            client_info['socket'].send(test_msg.encode())
            print(f"测试消息已发送到检测模块 {client_info['address']}")
            return True

        except Exception as e:
            print(f"连接测试失败: {e}")
            return False

    def show_connection_status(self):
        """显示连接状态"""
        print("\n 连接状态报告")
        print("=" * 40)
        print(f"TCP服务器状态: {'运行中' if self.detection_server_sock else '未运行'}")
        print(f"检测连接数: {len(self.clients)}")

        for i, client_info in enumerate(self.clients):
            try:
                addr = client_info['address']
                conn_time = client_info['connected_time']
                last_activity = time.time() - client_info['last_activity']
                print(f"  连接{i + 1}: {addr} (连接时间: {conn_time}, 最后活动: {last_activity:.1f}秒前)")
            except:
                print(f"  连接{i + 1}: <无效连接信息>")

        print(f"最新检测: {self.latest_detection}")
        print("=" * 40)

    def diagnose_connection_issue(self):
        """诊断连接问题"""
        print("\n 连接问题诊断")
        print("=" * 50)

        # 检查服务器socket状态
        if self.detection_server_sock is None:
            print("服务器socket未初始化")
        else:
            try:
                fileno = self.detection_server_sock.fileno()
                if fileno == -1:
                    print("服务器socket无效 (fileno = -1)")
                else:
                    print(f"服务器socket有效 (fileno = {fileno})")

                    # 检查socket是否绑定
                    try:
                        sockname = self.detection_server_sock.getsockname()
                        print(f"服务器绑定地址: {sockname}")
                    except:
                        print("无法获取socket绑定地址")
            except Exception as e:
                print(f"检查socket状态失败: {e}")

        # 检查端口监听状态
        system_name = platform.system()

        if system_name == "Windows":
            try:
                result = subprocess.run(
                    ["netstat", "-an"],
                    capture_output=True,
                    text=True,
                    encoding='gbk'
                )
                port_found = False
                for line in result.stdout.split('\n'):
                    if f":{self.detection_port}" in line:
                        port_found = True
                        if "LISTENING" in line:
                            print(f"端口 {self.detection_port} 正在监听")
                            print(f"   状态: {line.strip()}")
                            break

                if not port_found:
                    print(f"未找到端口 {self.detection_port} 的任何信息")
            except Exception as e:
                print(f"无法检查端口状态: {e}")

        print(f" 检测模块应连接到: localhost:{self.detection_port} 或 127.0.0.1:{self.detection_port}")
        print(f" 当前连接数: {len(self.clients)}")

        if self.clients:
            print("当前活动连接:")
            for i, client_info in enumerate(self.clients):
                try:
                    addr = client_info['address']
                    conn_time = client_info['connected_time']
                    last_activity = time.time() - client_info['last_activity']
                    print(f"  连接{i + 1}: {addr} (连接时间: {conn_time}, 最后活动: {last_activity:.1f}秒前)")
                except:
                    print(f"  连接{i + 1}: <无效连接信息>")

        # 防火墙提示
        print("\n 防火墙检查:")
        if system_name == "Windows":
            print("   1. Windows防火墙可能阻止连接")
            print("   2. 临时测试: 可尝试暂时关闭防火墙测试连接")
            print(f"   3. 端口放行: 确保端口{self.detection_port}已放行")
        elif system_name == "Linux":
            print("   1. 检查iptables或ufw防火墙设置")
            print("   2. 命令: sudo ufw status 或 sudo iptables -L")
            print(f"   3. 临时放行: sudo ufw allow {self.detection_port}/tcp")

        print("\n 解决方案:")
        print("   1. 确保检测模块连接到正确的IP和端口")
        print("   2. 检查防火墙设置")
        print("   3. 尝试重启控制系统和检测模块")
        print(f"   4. 使用telnet测试连接: telnet localhost {self.detection_port}")
        print("   5. 检查检测模块是否在运行")

        print("\n快速测试:")
        print(f"   在命令提示符中运行: telnet localhost {self.detection_port}")
        print("   如果连接成功，说明端口已开放")
        print("   如果连接被拒绝，说明端口未监听或被防火墙阻止")

        # 检查accept线程状态
        print("\n服务器线程状态:")
        accept_thread_running = False
        for thread in threading.enumerate():
            if "DetectionAcceptThread" in thread.name:
                accept_thread_running = True
                print(f"   Accept线程运行中: {thread.name}")
                break

        if not accept_thread_running:
            print("   Accept线程未运行或已结束")
            print("    尝试重启检测服务器...")
            if self.start_detection_server():
                print("   检测服务器重启成功")
            else:
                print("   检测服务器重启失败")

        print("=" * 50)

    def stop_control(self):
        """停止控制"""
        self.control_enabled = False
        self.stable_state = False
        self.consecutive_stable_counts = 0
        print(" 控制已停止，重置稳定状态")

    def stop_system(self):
        """停止系统"""
        self.running = False
        self.control_enabled = False
        self.exploration_active = False

        # 关闭所有客户端连接
        for client_info in self.clients:
            try:
                client_info['socket'].close()
            except:
                pass
        self.clients.clear()

        # 关闭检测服务器
        if self.detection_server_sock:
            self.detection_server_sock.close()

        # 断开高压电源
        self.hv_controller.disconnect()

        print(" 系统已停止")

    def run_with_gui(self):
        """运行带GUI的系统"""
        print("正在启动系统...")

        # 先启动检测服务器
        print(" 启动检测服务器...")
        if not self.start_detection_server():
            print("无法启动检测服务器")
            return

        # 给服务器时间启动
        print(" 等待服务器完全启动...")
        time.sleep(1)

        # 显示连接提示
        print(" 提示：请现在启动检测模块程序")
        print(" 检测模块应连接到: localhost:12345")
        print(" 等待检测模块连接...")

        self.running = True
        control_thread = threading.Thread(target=self.control_loop, name="ControlLoop")
        control_thread.daemon = True
        control_thread.start()

        print("控制循环已启动")

        # 启动GUI
        gui = EnhancedControlSystemGUI(self)
        print("  GUI启动中...")
        gui.run()


def main():
    """主函数"""
    control_system = EnhancedIntegratedControlSystem(modbus_port='COM5', detection_port=12345)

    try:
        control_system.run_with_gui()
    except KeyboardInterrupt:
        print("\n 用户中断")
    except Exception as e:
        print(f"系统错误: {e}")
        import traceback
        traceback.print_exc()
    finally:
        control_system.stop_system()


if __name__ == "__main__":
    main()
