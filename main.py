from fastapi import FastAPI
import models
from database import engine
from routers import groups, devices
from fastapi.middleware.cors import CORSMiddleware

# import metrics_logs_pb2
# from fastapi_mqtt import FastMQTT, MQTTConfig
# from prometheus_client import Gauge, Counter, generate_latest
# from fastapi import Response
# import httpx
# import time

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


# PROM_METRICS = {
#     "GAUGE": Gauge("device_metric_gauge", "Gauge from devices", ["source", "metric_name"]),
#     "COUNTER": Counter("device_metric_counter", "Counter from devices", ["source", "metric_name"])
# }

# mqtt_config = MQTTConfig(host="hivemq_broker", port=1883)
# mqtt_client = FastMQTT(config=mqtt_config)
# mqtt_client.init_app(app)

# LOKI_URL = "http://loki:3100/loki/api/v1/push"

# async def send_to_loki(source, log_entry):
#     payload = {
#         "streams": [{
#             "stream": {"source": source, "job": "device_logs"},
#             "values": [[str(log_entry.timestamp_ns), log_entry.message]]
#         }]
#     }
#     async with httpx.AsyncClient() as client:
#         try:
#             await client.post(LOKI_URL, json=payload)
#         except Exception as e:
#             print(f"Loki Error: {e}")

# @mqtt_client.on_connect()
# def connect(client, flags, rc, properties):
#     mqtt_client.subscribe("telemetry/#") 
#     print("Connected to HiveMQ")

# @mqtt_client.on_message()
# async def message(client, topic, payload, qos, properties):
#     try:
#         # 1. Распаковка Protobuf
#         telemetry = metrics_logs_pb2.TelemetryMessage()
#         telemetry.ParseFromString(payload)
#         source = telemetry.source or "unknown"

#         # 2. Обработка ЛОГОВ -> в Loki
#         for log in telemetry.logs:
#             await send_to_loki(source, log)

#         # 3. Обработка МЕТРИК -> в Prometheus
#         for metric in telemetry.metrics:
#             if metric.type == metrics_logs_pb2.Metric.MetricType.GAUGE:
#                 PROM_METRICS["GAUGE"].labels(source=source, metric_name=metric.name).set(metric.value)
#             elif metric.type == metrics_logs_pb2.Metric.MetricType.COUNTER:
#                 PROM_METRICS["COUNTER"].labels(source=source, metric_name=metric.name).inc(metric.value)

#         # 4. Метаданные -> в Postgres (опционально, если нужно сохранить факт получения)
#         print(f"Processed telemetry from {source}: {len(telemetry.logs)} logs, {len(telemetry.metrics)} metrics")

#     except Exception as e:
#         print(f"Parsing error: {e}")



# # --- Endpoint для Prometheus ---
# @app.get("/metrics")
# def metrics():
#     """Экспозиция метрик для скрейпинга Прометеем"""
#     return Response(generate_latest(), media_type="text/plain")

@app.get("/")
def root():
    return {"ok": True, "msg": "IoT management API running. See /docs"}
