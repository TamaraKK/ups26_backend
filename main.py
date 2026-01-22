from fastapi import FastAPI
import models
from database import engine, SessionLocal
from routers import groups, devices, projects
from fastapi.middleware.cors import CORSMiddleware

import metrics_logs_pb2
from fastapi_mqtt import FastMQTT, MQTTConfig
from prometheus_client import Gauge, Counter, generate_latest
from fastapi import Response
import httpx
import time
from datetime import datetime, timezone

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="IoT Manager API")

origins = [
    "http://localhost:8280",
    "http://127.0.0.1:8280",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(groups.router)
app.include_router(devices.router)
app.include_router(projects.router)

DEVICE_STATUS_GAUGE = Gauge(
    "device_runtime_status", 
    "Runtime status of devices (1=Online, 0=Offline)", 
    ["serial"]
)
PROM_METRICS = {
    "GAUGE": Gauge("device_metric_gauge", "Gauge from devices", ["source", "metric_name"]),
    "COUNTER": Gauge("device_metric_counter", "Counter from devices", ["source", "metric_name"])
}

mqtt_config = MQTTConfig(host="hivemq_broker", port=1883)
mqtt_client = FastMQTT(config=mqtt_config)
mqtt_client.init_app(app)

LOKI_URL = "http://loki:3100/loki/api/v1/push"

async def send_to_loki(source, log_entry):
    payload = {
        "streams": [{
            "stream": {"source": source, "job": "device_logs"},
            "values": [[str(log_entry.timestamp_ns), log_entry.message]]
        }]
    }
    async with httpx.AsyncClient() as client:
        try:
            await client.post(LOKI_URL, json=payload)
        except Exception as e:
            print(f"Loki Error: {e}")

@mqtt_client.on_connect()
def connect(client, flags, rc, properties):
    mqtt_client.subscribe("telemetry/#") 
    print("Connected to HiveMQ")


@mqtt_client.on_message()
async def message(client, topic, payload, qos, properties):
    try:
        telemetry = metrics_logs_pb2.IoTDeviceTelemetry()
        telemetry.ParseFromString(payload)
        
        # Берем ID из вложенного объекта info
        device_id = telemetry.info.device_id or "unknown"

        # 2. RUNTIME СТАТУС (Prometheus)
        # Ставим 1, так как получили сообщение. 
        # Если сообщений не будет, Prometheus через время сам поймет, что данных нет.
        DEVICE_STATUS_GAUGE.labels(serial=device_id).set(1)

        # 3. POSTGRES: Обновляем метаданные из паспорта устройства
        db = SessionLocal()
        try:
            device = db.query(models.Device).filter(models.Device.serial == device_id).first()
            if device:
                device.last_sync = datetime.now(timezone.utc)
                # Дополнительно сохраняем уровень заряда, если он пришел
                if telemetry.state.battery_level:
                    device.battery_level = telemetry.state.battery_level
                db.commit()
        finally:
            db.close()

        # 4. LOKI: Отправляем логи (теперь с уровнем важности)
        for log in telemetry.logs:
            # Превращаем Enum (0, 1, 2...) в строку (INFO, WARN...)
            lvl = metrics_logs_pb2.LogLevel.Name(log.level)
            await send_to_loki(device_id, log.message, lvl)

        # 5. PROMETHEUS: Числовые метрики
        for m in telemetry.metrics:
            if m.type == metrics_logs_pb2.GAUGE:
                PROM_METRICS["GAUGE"].labels(source=device_id, metric_name=m.name).set(m.value)
            elif m.type == metrics_logs_pb2.COUNTER:
                PROM_METRICS["COUNTER"].labels(source=device_id, metric_name=m.name).inc(m.value)

        print(f"Done: {device_id} (Firmware: {telemetry.info.firmware_version})")

    except Exception as e:
        print(f"Error parsing new proto: {e}")





# --- Endpoint для Prometheus ---
@app.get("/metrics")
def metrics():
    """Экспозиция метрик для скрейпинга Прометеем"""
    return Response(generate_latest(), media_type="text/plain")

@app.get("/")
def root():
    return {"ok": True, "msg": "IoT management API running. See /docs"}
