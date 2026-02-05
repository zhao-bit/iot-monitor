# hv_api_server_real.py - 高压控制系统【真实】HTTP API服务器
# 基于最新的 v1.py，集成所有功能

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import time
import threading
import sys
import os
import importlib.util


# 动态加载v1.py模块
def load_v1_module():
    """动态加载v1.py模块"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    v1_file = os.path.join(current_dir, "v1.py")

    if not os.path.exists(v1_file):
        print(f"❌ 找不到v1.py文件")
        print(f"   当前目录: {current_dir}")
        print(f"   期望路径: {v1_file}")
        sys.exit(1)

    try:
        spec = importlib.util.spec_from_file_location("v1", v1_file)
        v1_module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(v1_module)

        return (
            v1_module.RobustTCM6000iController,
            v1_module.EnhancedFuzzyController,
            v1_module.EnhancedIntegratedControlSystem
        )
    except Exception as e:
        print(f"❌ 无法导入v1模块: {e}")
        import traceback
        traceback.print_exc()
        print(f"💡 请检查v1.py文件是否完整")
        print(f"   文件路径: {v1_file}")
        sys.exit(1)


# 加载模块
RobustTCM6000iController, EnhancedFuzzyController, EnhancedIntegratedControlSystem = load_v1_module()
print("✅ v1模块加载成功")

app = FastAPI(
    title="高压智能控制系统API（真实版）",
    description="集成真实硬件控制的后端API - 基于v1.py",
    version="2.0.0-real"
)

# 允许跨域
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ========== 请求模型 ==========

class SystemInitRequest(BaseModel):
    modbus_port: str = "COM5"
    detection_port: int = 12345
    model_path: str = "best.pt"
    camera_id: int = 1


class VoltageRequest(BaseModel):
    voltage_kv: float = Field(..., ge=0.0, le=30.0)


class ExplorationRequest(BaseModel):
    min_voltage: float = 0.0
    max_voltage: float = 20.0
    voltage_step: float = 0.5
    wait_time: float = 1.0
    confidence_threshold: float = 0.7


class TargetControlRequest(BaseModel):
    target_mode: str


# ========== 全局系统实例 ==========

control_system = None
control_thread = None
exploration_thread = None


# ========== API接口 ==========

@app.get("/")
def root():
    return {
        "service": "高压智能控制系统API（真实版）",
        "version": "2.0.0-real",
        "docs": "/docs",
        "status": "running" if control_system and control_system.running else "stopped"
    }


@app.get("/api/health")
def health():
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "system_initialized": control_system is not None and control_system.running if control_system else False,
        "modbus_connected": control_system.hv_controller.client.is_socket_open() if control_system and control_system.hv_controller and control_system.hv_controller.client else False,
        "detection_clients": len(control_system.clients) if control_system else 0
    }


@app.post("/api/system/init")
def system_init(req: SystemInitRequest):
    """初始化系统：创建控制实例、连接Modbus、启动检测服务器"""
    global control_system, control_thread

    try:
        # 如果系统已运行，先关闭
        if control_system and control_system.running:
            stop_system_internal()

        # 创建新的控制系统实例
        print(f"🔧 初始化系统...")
        print(f"   Modbus端口: {req.modbus_port}")
        print(f"   检测端口: {req.detection_port}")
        control_system = EnhancedIntegratedControlSystem(
            modbus_port=req.modbus_port,
            detection_port=req.detection_port
        )
        # 先标记系统运行状态，确保内部线程（如检测accept线程）能正常进入循环
        control_system.running = True

        # 启动检测服务器
        if not control_system.start_detection_server():
            raise HTTPException(status_code=500, detail="无法启动检测服务器")

        # 连接高压电源
        if not control_system.connect_hv_power():
            raise HTTPException(status_code=500, detail="无法连接高压电源")

        # 启动控制循环线程
        if control_thread and control_thread.is_alive():
            pass
        else:
            control_thread = threading.Thread(
                target=control_system.control_loop,
                name="ControlLoop",
                daemon=True
            )
            control_thread.start()
            print("✅ 控制循环线程已启动")

        print("✅ 系统初始化成功")

        return {
            "success": True,
            "message": "系统初始化成功",
            "config": req.dict(),
            "modbus_port": req.modbus_port,
            "detection_port": req.detection_port
        }

    except Exception as e:
        print(f"❌ 系统初始化失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"系统初始化失败: {str(e)}")


@app.post("/api/system/shutdown")
def system_shutdown():
    """关闭系统：停止所有控制、断开连接"""
    global control_system

    try:
        if control_system:
            stop_system_internal()
            return {
                "success": True,
                "message": "系统已关闭"
            }
        else:
            return {
                "success": True,
                "message": "系统未运行"
            }
    except Exception as e:
        print(f"❌ 关闭系统失败: {e}")
        raise HTTPException(status_code=500, detail=f"关闭系统失败: {str(e)}")


def stop_system_internal():
    """内部停止系统函数"""
    global control_system

    if control_system:
        control_system.stop_system()
        time.sleep(0.5)


@app.get("/api/system/status")
def system_status():
    """获取系统状态 - 包含GUI中显示的所有状态信息"""
    global control_system

    if not control_system:
        return {
            "system": {
                "running": False,
                "control_enabled": False,
                "exploration_active": False,
                "control_phase": None,
                "three_level_status": 0
            },
            "power": {
                "connected": False,
                "control_acquired": False,
                "voltage_kv": 0.0,
                "current_ma": 0.0,
                "port": "N/A",
                "last_successful_command": None
            },
            "detection": {
                "active": False,
                "clients": 0,
                "latest_detection": None,
                "server_running": False
            },
            "control": {
                "target_mode": None,
                "current_mode": None,
                "current_voltage_kv": 0.0,
                "target_voltage": None,
                "mode_error": None,
                "adjustment": None,
                "control_iteration": 0,
                "mode_count": 0,
                "stability_count": None,
                "stable_state": False,
                "consecutive_stable_counts": 0
            },
            "phase": {
                "current_stage": "待开始",
                "system_mode": "空闲"
            },
            "timestamp": time.time()
        }

    try:
        # 读取电源状态
        power_status = control_system.read_output_status()
        voltage_kv = power_status['voltage_kv'] if power_status else 0.0
        current_ma = power_status['current_ma'] if power_status else 0.0

        # 获取连接状态
        conn_status = control_system.get_connection_status()
        power_connected = False
        control_acquired = False
        last_successful_command = None

        if conn_status:
            power_connected = conn_status.get('connected', False)
            control_acquired = conn_status.get('control_acquired', False)
            last_successful_command = conn_status.get('last_successful_command', None)

        # 检查Modbus连接
        if hasattr(control_system.hv_controller, 'client') and control_system.hv_controller.client:
            try:
                power_connected = control_system.hv_controller.client.is_socket_open()
            except:
                pass

        # 获取模式列表
        mode_list = []
        if control_system.fuzzy_controller:
            try:
                mode_list = control_system.fuzzy_controller.get_mode_list()
            except Exception as e:
                print(f"⚠️ 获取模式列表失败: {e}")

        # 获取当前电压
        current_voltage = voltage_kv
        if hasattr(control_system, 'current_voltage_kv'):
            current_voltage = control_system.current_voltage_kv

        # 获取当前模式
        current_mode = None
        current_mode_id = None
        if control_system.latest_detection:
            detected_mode_name = control_system.latest_detection.get('detected_mode', None)
            if detected_mode_name:
                current_mode_id = control_system.fuzzy_controller.get_mode_id(
                    detected_mode_name) if control_system.fuzzy_controller else None
                current_mode = detected_mode_name

        # 获取目标电压
        target_voltage = None
        if control_system.target_mode and control_system.fuzzy_controller:
            target_voltage = control_system.fuzzy_controller.get_target_voltage(control_system.target_mode)

        # 获取模式误差和调整量
        mode_error = None
        adjustment = None
        if hasattr(control_system.fuzzy_controller, 'last_error'):
            mode_error = control_system.fuzzy_controller.last_error
        if hasattr(control_system.fuzzy_controller, 'last_adjustment'):
            adjustment = control_system.fuzzy_controller.last_adjustment

        # 获取稳定性计数
        stability_count = None
        if hasattr(control_system.fuzzy_controller, 'stability_count'):
            stability_count = control_system.fuzzy_controller.stability_count

        # 确定当前阶段和系统模式
        current_stage = "待开始"
        system_mode = "空闲"

        if control_system.exploration_active:
            current_stage = "电压探索中"
            system_mode = "探索中"
        elif control_system.control_enabled:
            current_stage = "目标控制中"
            system_mode = "控制中"
            if control_system.stable_state:
                system_mode = "稳定控制"

        return {
            "system": {
                "running": control_system.running,
                "control_enabled": control_system.control_enabled,
                "exploration_active": getattr(control_system, 'exploration_active', False),
                "control_phase": getattr(control_system, 'control_phase', None),
                "three_level_status": getattr(control_system, 'three_level_status', 0)
            },
            "power": {
                "connected": power_connected,
                "control_acquired": control_acquired,
                "voltage_kv": voltage_kv,
                "current_ma": current_ma,
                "port": getattr(control_system, 'modbus_port', "N/A"),
                "last_successful_command": last_successful_command
            },
            "detection": {
                "active": len(control_system.clients) > 0,
                "clients": len(control_system.clients),
                "latest_detection": control_system.latest_detection,
                "server_running": control_system.detection_server_sock is not None
            },
            "control": {
                "target_mode": getattr(control_system, 'target_mode', None),
                "current_mode": current_mode,
                "current_mode_id": current_mode_id,
                "current_voltage_kv": current_voltage,
                "target_voltage": target_voltage,
                "mode_error": mode_error,
                "adjustment": adjustment,
                "control_iteration": getattr(control_system, 'control_iteration', 0),
                "mode_count": len(mode_list),
                "stability_count": stability_count,
                "stable_state": getattr(control_system, 'stable_state', False),
                "consecutive_stable_counts": getattr(control_system, 'consecutive_stable_counts', 0)
            },
            "phase": {
                "current_stage": current_stage,
                "system_mode": system_mode
            },
            "timestamp": time.time()
        }
    except Exception as e:
        print(f"❌ 获取系统状态失败: {e}")
        import traceback
        traceback.print_exc()
        return {
            "error": str(e),
            "timestamp": time.time()
        }


@app.post("/api/power/set_voltage")
def set_voltage(req: VoltageRequest):
    """设置电压"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        success = control_system.set_voltage_manual(req.voltage_kv)
        if success:
            return {
                "success": True,
                "message": f"电压已设置为 {req.voltage_kv} kV",
                "voltage_kv": req.voltage_kv
            }
        else:
            raise HTTPException(status_code=500, detail="设置电压失败")
    except Exception as e:
        print(f"❌ 设置电压失败: {e}")
        raise HTTPException(status_code=500, detail=f"设置电压失败: {str(e)}")


@app.post("/api/power/enable")
def enable_power():
    """开启高压"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        success = control_system.enable_high_voltage()
        if success:
            return {"success": True, "message": "高压已开启"}
        else:
            raise HTTPException(status_code=500, detail="开启高压失败")
    except Exception as e:
        print(f"❌ 开启高压失败: {e}")
        raise HTTPException(status_code=500, detail=f"开启高压失败: {str(e)}")


@app.post("/api/power/disable")
def disable_power():
    """关闭高压"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        success = control_system.disable_high_voltage()
        if success:
            return {"success": True, "message": "高压已关闭"}
        else:
            raise HTTPException(status_code=500, detail="关闭高压失败")
    except Exception as e:
        print(f"❌ 关闭高压失败: {e}")
        raise HTTPException(status_code=500, detail=f"关闭高压失败: {str(e)}")


@app.get("/api/power/status")
def power_status():
    """获取电源状态"""
    global control_system

    if not control_system:
        return {
            "success": False,
            "voltage_kv": 0.0,
            "current_ma": 0.0,
            "timestamp": time.time()
        }

    try:
        output = control_system.read_output_status()
        if output:
            return {
                "success": True,
                "voltage_kv": output['voltage_kv'],
                "current_ma": output['current_ma'],
                "timestamp": time.time()
            }
        else:
            return {
                "success": False,
                "voltage_kv": 0.0,
                "current_ma": 0.0,
                "timestamp": time.time()
            }
    except Exception as e:
        print(f"❌ 获取电源状态失败: {e}")
        return {
            "success": False,
            "voltage_kv": 0.0,
            "current_ma": 0.0,
            "timestamp": time.time()
        }


@app.post("/api/control/exploration/start")
def start_exploration(req: ExplorationRequest):
    """开始电压探索"""
    global control_system, exploration_thread

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    if not control_system.running:
        raise HTTPException(status_code=400, detail="系统未运行，请先初始化系统")

    if control_system.exploration_active:
        raise HTTPException(status_code=400, detail="电压探索已在运行中")

    # 在启动探索前检查是否已有检测模块连接
    if not getattr(control_system, "clients", None) or len(control_system.clients) == 0:
        raise HTTPException(
            status_code=400,
            detail="检测模块未连接：请先在“实时检测”页面启动摄像头检测（检测系统API 8001，控制端口 12345），确保检测画面正常后再开始电压探索"
        )

    # 验证参数
    if req.min_voltage >= req.max_voltage:
        raise HTTPException(status_code=400, detail="最小电压必须小于最大电压")

    if req.voltage_step <= 0:
        raise HTTPException(status_code=400, detail="电压步长必须大于0")

    try:
        # 在后台线程中运行探索
        exploration_thread = threading.Thread(
            target=control_system.exploration_phase,
            args=(
                req.min_voltage,
                req.max_voltage,
                req.voltage_step,
                req.wait_time,
                req.confidence_threshold
            ),
            name="ExplorationThread",
            daemon=True
        )
        exploration_thread.start()

        print(f"🚀 电压探索已启动: {req.min_voltage}-{req.max_voltage}kV, 步长{req.voltage_step}kV")

        return {
            "success": True,
            "message": "电压探索已启动",
            "params": req.dict()
        }
    except Exception as e:
        print(f"❌ 启动电压探索失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动电压探索失败: {str(e)}")


@app.post("/api/control/exploration/stop")
def stop_exploration():
    """停止电压探索"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        control_system.exploration_active = False
        return {"success": True, "message": "电压探索已停止"}
    except Exception as e:
        print(f"❌ 停止电压探索失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止电压探索失败: {str(e)}")


@app.post("/api/control/target/start")
def start_control(req: TargetControlRequest):
    """开始目标控制"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    if not control_system.running:
        raise HTTPException(status_code=400, detail="系统未运行，请先初始化系统")

    try:
        # 检查模式是否存在
        mode_list = control_system.fuzzy_controller.get_mode_list()
        if not mode_list:
            raise HTTPException(
                status_code=400,
                detail="未识别到任何模式，请先完成电压探索"
            )

        # 统一按字符串比较，避免前端传数字导致匹配失败
        mode_ids = [str(mode['id']) for mode in mode_list]
        target_mode_str = str(req.target_mode).strip() if req.target_mode is not None else ""

        if not target_mode_str or target_mode_str not in mode_ids:
            mode_info = ", ".join([f"模式{mode['id']}({mode['name']})" for mode in mode_list])
            raise HTTPException(
                status_code=400,
                detail=f"目标模式「{req.target_mode}」不存在或未选择。可用模式: {mode_info}"
            )

        success = control_system.start_target_control(target_mode_str)
        if success:
            print(f"🎯 目标控制已启动: 模式{target_mode_str}")
            return {
                "success": True,
                "message": f"目标控制已启动: 模式{target_mode_str}"
            }
        else:
            raise HTTPException(status_code=500, detail="启动目标控制失败")
    except HTTPException:
        raise
    except Exception as e:
        print(f"❌ 启动目标控制失败: {e}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"启动目标控制失败: {str(e)}")


@app.post("/api/control/target/stop")
def stop_control():
    """停止目标控制"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        control_system.stop_control()
        return {"success": True, "message": "目标控制已停止"}
    except Exception as e:
        print(f"❌ 停止目标控制失败: {e}")
        raise HTTPException(status_code=500, detail=f"停止目标控制失败: {str(e)}")


@app.get("/api/control/modes")
def get_modes():
    """获取已识别的模式列表"""
    global control_system

    if not control_system:
        return {
            "success": True,
            "modes": [],
            "count": 0
        }

    try:
        mode_list = control_system.fuzzy_controller.get_mode_list()

        # 转换为API格式（id 统一为字符串，voltage 转为 float 便于前端）
        modes = []
        for mode in mode_list:
            modes.append({
                "id": str(mode['id']),
                "name": mode['name'],
                "voltage": float(mode['voltage']) if mode.get('voltage') is not None else 0.0,
                "count": int(mode['count']) if mode.get('count') is not None else 0
            })

        return {
            "success": True,
            "modes": modes,
            "count": len(modes)
        }
    except Exception as e:
        print(f"❌ 获取模式列表失败: {e}")
        return {
            "success": False,
            "modes": [],
            "count": 0,
            "error": str(e)
        }


@app.post("/api/emergency/stop")
def emergency_stop():
    """紧急停止：立即关闭所有电源和控制"""
    global control_system

    try:
        if control_system:
            # 停止所有控制
            control_system.control_enabled = False
            control_system.exploration_active = False

            # 设置电压为0
            control_system.set_voltage_manual(0.0)

            # 关闭高压
            control_system.disable_high_voltage()

            print("🛑 紧急停止完成")

        return {
            "success": True,
            "message": "紧急停止完成",
            "voltage_kv": 0.0,
            "timestamp": time.time()
        }
    except Exception as e:
        print(f"❌ 紧急停止失败: {e}")
        raise HTTPException(status_code=500, detail=f"紧急停止失败: {str(e)}")


@app.post("/api/detection/test_connection")
def test_detection_connection():
    """测试检测连接"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        success = control_system.test_detection_connection()
        return {
            "success": success,
            "message": "检测连接测试完成",
            "clients": len(control_system.clients) if control_system else 0
        }
    except Exception as e:
        print(f"❌ 测试检测连接失败: {e}")
        raise HTTPException(status_code=500, detail=f"测试检测连接失败: {str(e)}")


@app.get("/api/detection/connection_status")
def get_detection_connection_status():
    """获取检测连接状态"""
    global control_system

    if not control_system:
        return {
            "success": False,
            "server_running": False,
            "clients": 0,
            "client_info": []
        }

    try:
        client_info = []
        for i, client in enumerate(control_system.clients):
            try:
                client_info.append({
                    "index": i + 1,
                    "address": client['address'],
                    "connected_time": client.get('connected_time', 'N/A'),
                    "last_activity": time.time() - client.get('last_activity', time.time())
                })
            except:
                pass

        return {
            "success": True,
            "server_running": control_system.detection_server_sock is not None,
            "clients": len(control_system.clients),
            "client_info": client_info
        }
    except Exception as e:
        print(f"❌ 获取检测连接状态失败: {e}")
        return {
            "success": False,
            "server_running": False,
            "clients": 0,
            "client_info": [],
            "error": str(e)
        }


@app.post("/api/detection/diagnose")
def diagnose_detection_connection():
    """诊断检测连接问题"""
    global control_system

    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")

    try:
        control_system.diagnose_connection_issue()
        return {
            "success": True,
            "message": "诊断完成，请查看服务器日志"
        }
    except Exception as e:
        print(f"❌ 诊断检测连接失败: {e}")
        raise HTTPException(status_code=500, detail=f"诊断失败: {str(e)}")


# ========== 启动 ==========

if __name__ == "__main__":
    print("=" * 60)
    print("高压智能控制系统 Real API 服务器")
    print("接口地址: http://localhost:8000")
    print("文档地址: http://localhost:8000/docs")
    print("=" * 60)
    print("⚠️  注意：这是真实硬件控制版本，请确保：")
    print("   1. Modbus设备已连接")
    print("   2. v1.py文件在同一目录")
    print("   3. 所有依赖库已安装")
    print("=" * 60)

    uvicorn.run(app, host="0.0.0.0", port=8000)
