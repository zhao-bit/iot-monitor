from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
import uvicorn
import time
import threading
import sys
import os
import importlib.util

def load_v1_module():
    current_dir = os.path.dirname(os.path.abspath(__file__))
    v1_file = os.path.join(current_dir, "v1.py")
    if not os.path.exists(v1_file):
        sys.exit(1)
    spec = importlib.util.spec_from_file_location("v1", v1_file)
    v1_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(v1_module)
    return (
        v1_module.RobustTCM6000iController,
        v1_module.EnhancedFuzzyPIDController,
        v1_module.EnhancedControlSystemCore
    )

RobustTCM6000iController, EnhancedFuzzyPIDController, EnhancedControlSystemCore = load_v1_module()

app = FastAPI(
    title="高压智能控制系统API（真实版）",
    description="集成真实硬件控制的后端API - 基于v1.py",
    version="2.0.0-real"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class SystemInitRequest(BaseModel):
    modbus_port: str = "COM5"
    detection_port: int = 12345

class VoltageRequest(BaseModel):
    voltage_kv: float = Field(..., ge=0.0, le=30.0)

class ExplorationRequest(BaseModel):
    min_voltage: float = 0.0
    max_voltage: float = 20.0

class TargetControlRequest(BaseModel):
    target_mode: str
    min_voltage: float | None = None
    max_voltage: float | None = None

control_system = None

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
    connected = False
    if control_system and control_system.hv_controller:
        try:
            cs = control_system.hv_controller.get_connection_status()
            connected = bool(cs.get("connected"))
        except:
            connected = False
    return {
        "status": "healthy",
        "timestamp": time.time(),
        "system_initialized": control_system is not None and control_system.running if control_system else False,
        "modbus_connected": connected,
        "detection_clients": len(control_system.clients) if control_system else 0
    }

@app.post("/api/system/init")
def system_init(req: SystemInitRequest):
    global control_system
    try:
        if control_system and control_system.running:
            control_system.stop_system()
            time.sleep(0.3)
        control_system = EnhancedControlSystemCore(modbus_port=req.modbus_port, detection_port=req.detection_port)
        control_system.running = True
        if not control_system.start_detection_server():
            raise HTTPException(status_code=500, detail="无法启动检测服务器")
        if not control_system._ensure_hv_connected():
            raise HTTPException(status_code=500, detail="无法连接高压电源")
        return {
            "success": True,
            "message": "系统初始化成功",
            "modbus_port": req.modbus_port,
            "detection_port": req.detection_port
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"系统初始化失败: {str(e)}")

@app.post("/api/system/shutdown")
def system_shutdown():
    global control_system
    try:
        if control_system:
            control_system.stop_system()
            return {"success": True, "message": "系统已关闭"}
        return {"success": True, "message": "系统未运行"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"关闭系统失败: {str(e)}")

@app.get("/api/system/status")
def system_status():
    global control_system
    if not control_system:
        return {
            "system": {
                "running": False,
                "exploration_active": False,
                "control_enabled": False
            },
            "power": {"connected": False, "control_acquired": False, "voltage_kv": 0.0, "current_ma": 0.0},
            "detection": {"active": False, "clients": 0, "latest_detection": None, "server_running": False},
            "control": {
                "target_mode": None,
                "current_mode": None,
                "current_voltage_kv": 0.0,
                "stable_state": False,
                "best_match_rate": 0.0,
                "mode_count": 0
            },
            "timestamp": time.time()
        }
    try:
        output = control_system.hv_controller.read_output_silent()
        voltage_kv = (output["voltage"] / 1000.0) if output else 0.0
        current_ma = (output["current"] * 1000.0) if output else 0.0
        conn = control_system.hv_controller.get_connection_status()
        latest = control_system.latest_detection
        return {
            "system": {
                "running": control_system.running,
                "exploration_active": getattr(control_system, "exploration_active", False),
                "control_enabled": getattr(control_system, "control_enabled", False)
            },
            "power": {
                "connected": bool(conn.get("connected")),
                "control_acquired": bool(conn.get("control_acquired")),
                "voltage_kv": control_system.current_voltage_kv if hasattr(control_system, "current_voltage_kv") else voltage_kv,
                "current_ma": current_ma,
                "port": getattr(control_system, "modbus_port", "N/A"),
                "last_successful_command": conn.get("last_successful_command")
            },
            "detection": {
                "active": len(control_system.clients) > 0,
                "clients": len(control_system.clients),
                "latest_detection": latest,
                "server_running": control_system.server_socket is not None
            },
            "control": {
                "target_mode": getattr(control_system, "target_mode", None),
                "current_mode": latest.get("detected_mode") if latest else None,
                "current_voltage_kv": control_system.current_voltage_kv if hasattr(control_system, "current_voltage_kv") else voltage_kv,
                "stable_state": getattr(control_system, "stable_state", False),
                "best_match_rate": getattr(control_system, "best_match_rate", 0.0),
                "mode_count": len(getattr(control_system, "mode_voltage_ranges", {}) or {})
            },
            "timestamp": time.time()
        }
    except Exception as e:
        return {"error": str(e), "timestamp": time.time()}

@app.post("/api/power/set_voltage")
def set_voltage(req: VoltageRequest):
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    try:
        ok = control_system.hv_controller.set_voltage_kv(req.voltage_kv)
        if not ok:
            raise HTTPException(status_code=500, detail="设置电压失败")
        control_system.current_voltage_kv = req.voltage_kv
        return {"success": True, "voltage_kv": req.voltage_kv}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"设置电压失败: {str(e)}")

@app.post("/api/power/enable")
def enable_power():
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    ok = control_system.hv_controller.enable_high_voltage()
    if not ok:
        raise HTTPException(status_code=500, detail="开启高压失败")
    return {"success": True}

@app.post("/api/power/disable")
def disable_power():
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    ok = control_system.hv_controller.disable_high_voltage()
    if not ok:
        raise HTTPException(status_code=500, detail="关闭高压失败")
    return {"success": True}

@app.get("/api/power/status")
def power_status():
    global control_system
    if not control_system:
        return {"success": False, "voltage_kv": 0.0, "current_ma": 0.0, "timestamp": time.time()}
    output = control_system.hv_controller.read_output_silent()
    if output:
        return {
            "success": True,
            "voltage_kv": (output["voltage"] / 1000.0),
            "current_ma": (output["current"] * 1000.0),
            "timestamp": time.time()
        }
    return {"success": False, "voltage_kv": 0.0, "current_ma": 0.0, "timestamp": time.time()}

@app.post("/api/control/exploration/start")
def start_exploration(req: ExplorationRequest):
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    if not getattr(control_system, "mode_classes_received", False):
        raise HTTPException(status_code=400, detail="尚未收到模式种类")
    ok = control_system.start_exploration(req.min_voltage, req.max_voltage)
    if not ok:
        raise HTTPException(status_code=500, detail="电压探索启动失败")
    return {"success": True}

@app.post("/api/control/exploration/stop")
def stop_exploration():
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    control_system.exploration_active = False
    return {"success": True}

@app.post("/api/control/target/start")
def start_control(req: TargetControlRequest):
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    if not getattr(control_system, "mode_classes_received", False):
        raise HTTPException(status_code=400, detail="尚未收到模式种类")
    names = list(control_system.mode_classes.values()) if control_system.mode_classes else []
    if req.target_mode not in names:
        raise HTTPException(status_code=400, detail="目标模式不存在")
    ok = control_system.start_target_control(req.target_mode, req.min_voltage, req.max_voltage)
    if not ok:
        raise HTTPException(status_code=500, detail="启动目标控制失败")
    return {"success": True}

@app.post("/api/control/target/stop")
def stop_control():
    global control_system
    if not control_system:
        raise HTTPException(status_code=400, detail="系统未初始化")
    control_system.stop_control()
    return {"success": True}

@app.get("/api/control/modes")
def get_modes():
    global control_system
    modes = []
    if control_system and control_system.mode_voltage_ranges:
        for name, info in control_system.mode_voltage_ranges.items():
            modes.append({
                "name": name,
                "min": float(info.get("min", 0.0)),
                "max": float(info.get("max", 0.0)),
                "optimal": float(info.get("optimal", 0.0)),
                "count": int(info.get("total_count", 0))
            })
    return {"success": True, "modes": modes, "count": len(modes)}

@app.post("/api/emergency/stop")
def emergency_stop():
    global control_system
    if control_system:
        control_system.stop_control()
        control_system.hv_controller.disable_high_voltage()
        control_system.hv_controller.set_voltage_kv(0.0)
    return {"success": True}

@app.get("/api/detection/connection_status")
def get_detection_connection_status():
    global control_system
    if not control_system:
        return {"success": False, "server_running": False, "clients": 0, "client_info": []}
    info = []
    for i, client in enumerate(control_system.clients):
        info.append({"index": i + 1, "address": client.get("address")})
    return {"success": True, "server_running": control_system.server_socket is not None, "clients": len(control_system.clients), "client_info": info}

@app.get("/api/control/classes")
def get_mode_classes():
    global control_system
    if not control_system:
        return {"success": False, "received": False, "classes": []}
    names = []
    if getattr(control_system, "mode_classes", None):
        try:
            names = list(control_system.mode_classes.values())
        except Exception:
            names = []
    return {
        "success": True,
        "received": bool(getattr(control_system, "mode_classes_received", False)),
        "classes": sorted(set(names))
    }

@app.get("/api/control/pid")
def get_pid_params():
    global control_system
    if not control_system or not hasattr(control_system, "fuzzy_pid"):
        return {
            "success": False,
            "pid": {
                "kp": 0.0,
                "ki": 0.0,
                "kd": 0.0,
                "kp_base": 0.0,
                "ki_base": 0.0,
                "kd_base": 0.0,
                "step_size": 0.0,
                "step_time": 0.0
            }
        }
    fp = control_system.fuzzy_pid
    return {
        "success": True,
        "pid": {
            "kp": float(getattr(fp, "kp", 0.0)),
            "ki": float(getattr(fp, "ki", 0.0)),
            "kd": float(getattr(fp, "kd", 0.0)),
            "kp_base": float(getattr(fp, "kp_base", 0.0)),
            "ki_base": float(getattr(fp, "ki_base", 0.0)),
            "kd_base": float(getattr(fp, "kd_base", 0.0)),
            "step_size": float(getattr(fp, "step_size", 0.0)),
            "step_time": float(getattr(fp, "step_time", 0.0))
        }
    }

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
