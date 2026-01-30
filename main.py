from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
import telemetry_pb2
from fastapi_mqtt import FastMQTT, MQTTConfig
from prometheus_client import CollectorRegistry, Gauge, push_to_gateway
import httpx
import time
from datetime import datetime, timezone
import models
from database import engine, SessionLocal
import tempfile
from sqlalchemy import update
from utils.coredump import CoreDumpDecoder
import json
import asyncio
from contextlib import asynccontextmanager
from routers.model_alerts import run_predictive_background_task



models.Base.metadata.create_all(bind=engine)



@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(run_predictive_background_task(SessionLocal))
    print("background task: predictive analytics started")
    
    yield 
    
    task.cancel() 
    try:
        await task
    except asyncio.CancelledError:
        print("background task: predictive analytics stopped")

app = FastAPI(
    title="IoT Manager API (Hybrid Mode)",
    lifespan=lifespan
)

origins = ["http://localhost:8280", "http://127.0.0.1:8280"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

from routers import groups, devices, issues, projects, metadata, issues, traces, model_alerts
from model import model
app.include_router(groups.router)
app.include_router(devices.router)
app.include_router(projects.router)
app.include_router(issues.router)
app.include_router(metadata.router)
app.include_router(traces.router)
app.include_router(model.router)
app.include_router(model_alerts.router)

mqtt_config = MQTTConfig(host="hivemq_broker", port=1883)
mqtt_client = FastMQTT(config=mqtt_config)
mqtt_client.init_app(app)

LOKI_URL = "http://loki:3100/loki/api/v1/push"
PUSHGATEWAY_URL = "pushgateway:9091"


async def send_logs_batch_to_loki(source_value, telemetry_logs):
    if not telemetry_logs:
        return

    grouped_logs = {}
    
    try:
        level_names = {v: k for k, v in telemetry_pb2.LogLevel.items()}
    except Exception:
        level_names = {}

    for log in telemetry_logs:
        # Проверяем, что log — это объект с нужными атрибутами
        level_num = getattr(log, 'level', 0)
        message = getattr(log, 'message', '')
        timestamp = getattr(log, 'timestamp', None)
        
        level_name = level_names.get(level_num, "UNKNOWN")
        
        if level_name not in grouped_logs:
            grouped_logs[level_name] = []
        
        current_ts_ns = str(int(time.time() * 10**9))
        grouped_logs[level_name].append([current_ts_ns, message])

    # 2. Формируем payload. ВАЖНО: используем 'serial', как в поиске
    streams = []
    for level, values in grouped_logs.items():
        streams.append({
            "stream": {
                "serial": str(source_value), # Метка должна совпадать с тем, что ищем
                "job": "device_logs",
                "level": level
            },
            "values": values
        })
    
    payload = {"streams": streams}
    
    async with httpx.AsyncClient() as client:
        try:
            resp = await client.post(LOKI_URL, json=payload, timeout=5.0)
            if resp.status_code not in [200, 204]:
                print(f"Loki Push Error: {resp.status_code} - {resp.text}")
        except Exception as e:
            print(f"Loki Batch Error (Network/HTTP): {type(e).__name__} - {e}")


@mqtt_client.on_connect()
def connect(client, flags, rc, properties):
    client.subscribe("telemetry/#") 
    print("Connected to HiveMQ")

@mqtt_client.subscribe("telemetry/#")
@mqtt_client.on_message()
async def message(client, topic, payload, qos, properties):
    try:
        # 1. Распаковка Protobuf
        telemetry = telemetry_pb2.IoTDeviceTelemetry()
        telemetry.ParseFromString(payload)
        device_serial = telemetry.info.device_id or "unknown"

        registry = CollectorRegistry()
        
        status_g = Gauge("device_runtime_status", "Online status", ["serial"], registry=registry)
        status_g.labels(serial=device_serial).set(1)

        # 3. Динамические метрики (из fake.py прилетят cpu_usage и ram_usage)
        for m in telemetry.metrics:
            g = Gauge(f"device_{m.name.replace('.', '_')}", f"Metric: {m.name}", ["source"], registry=registry)
            g.labels(source=device_serial).set(m.value)

        # 4. Состояние устройства
        if telemetry.state:
            bat = Gauge("device_battery_level", "Battery level", ["source"], registry=registry)
            bat.labels(source=device_serial).set(telemetry.state.battery_level)
            
            sig = Gauge("device_signal_strength", "Signal strength", ["source"], registry=registry)
            sig.labels(source=device_serial).set(telemetry.state.signal_strength)

        try:
            push_to_gateway(
                PUSHGATEWAY_URL, 
                job="telemetry_processor", # Фиксированное имя job
                registry=registry,
                grouping_key={'serial': device_serial} # ID устройства передаем сюда
            )
        except Exception as e:
            print(f"Pushgateway Error: {e}")    

        # 6. Отправка логов в Loki
        if telemetry.logs:
            await send_logs_batch_to_loki(device_serial, telemetry.logs)
  


        if telemetry.coredump:

            with tempfile.NamedTemporaryFile(mode='wb', suffix='.b64', delete=False) as tmp:
                tmp.write(telemetry.coredump)
                temp_core_path = tmp.name
                
            
                decoder = CoreDumpDecoder(prog="utils/esp32.elf", core=temp_core_path)
                coredump = decoder.info_corefile()

                
                type_mapping = {
                    'abort': models.IssueTypeEnum.abort,
                    'assert': models.IssueTypeEnum.assertion,
                    'watchdog': models.IssueTypeEnum.watchdog
                }
                
                coredump_type = type_mapping.get(coredump.get("type", "").lower())

                with SessionLocal() as db:
                    
                    device = db.query(models.Device).filter(models.Device.serial == device_serial).first()
    
                    if not device:
                        print(f"Device {device_serial} not found")
                        return

                    issue = db.query(models.Issue).filter(
                        models.Issue.name == coredump["reason"]
                    ).first()

                    if not issue:
                        issue = models.Issue(
                            name=coredump["reason"],
                            type=coredump_type,
                            
                        )
                        db.add(issue)
                        db.flush()

                    new_trace = models.Trace(
                        issue_id=issue.id,
                        device_id=device.id,
                        core_dump=json.dumps(coredump),
                        occurrence=datetime.now()
                    )

                    db.add(new_trace)
                    

                    db.commit()
                    
            

        with SessionLocal() as db:
            db.query(models.Device).filter(models.Device.serial == device_serial).update({
                "last_sync": datetime.now(timezone.utc)
            })
            db.commit()

    except Exception as e:
        print(f"MQTT Processing Error: {e}")
