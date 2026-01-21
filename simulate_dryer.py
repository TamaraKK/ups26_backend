# import metrics_logs_pb2
# import paho.mqtt.client as mqtt
# import time

# # 1. Формируем сообщение
# telemetry = metrics_logs_pb2.TelemetryMessage()
# telemetry.source = "Dryer_Pro_2000"

# # Добавляем лог
# log = telemetry.logs.add()
# log.timestamp_ns = time.time_ns()
# log.message = "Сушилка начала цикл нагрева"

# # Добавляем метрику (температуру)
# metric = telemetry.metrics.add()
# metric.name = "temperature"
# metric.value = 65.5
# metric.type = metrics_logs_pb2.Metric.MetricType.GAUGE

# # 2. Отправляем в MQTT
# client = mqtt.Client()
# client.connect("localhost", 1883) # подключаемся к проброшенному порту HiveMQ
# payload = telemetry.SerializeToString()
# client.publish("telemetry/dryer", payload)
# print("Данные отправлены!")
# client.disconnect()