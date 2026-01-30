import time
import psutil
import platform
import uuid
import random
import paho.mqtt.client as mqtt
import telemetry_pb2
from google.protobuf.timestamp_pb2 import Timestamp

# --- ИМИТАЦИЯ СУШИЛКИ (ИЗОЛИРОВАННАЯ ЛОГИКА) ---
class DryerSimulator:
    def __init__(self):
        self._generate_new_cycle()
        self.time_to_now = 0.0
        self.dryer_temp_now = 0.0
        self._needs_reset = False
        self._is_first_call = True

    def _generate_new_cycle(self):
        self.dryer_temp_req = float(random.choice(range(40, 101, 5)))
        self.total_time = float(random.choice(range(30, 181, 10)))
        self.temp_step = random.choice([i * 0.25 for i in range(1, 9)])

    def get_metrics(self):
        if self._needs_reset:
            self._generate_new_cycle()
            self.time_to_now = 0.0
            self.dryer_temp_now = 0.0
            self._needs_reset = False
            return self._current_state()

        if self._is_first_call:
            self._is_first_call = False
            return self._current_state()

        self.time_to_now += 1.0

        if self.dryer_temp_now < self.dryer_temp_req:
            self.dryer_temp_now += self.temp_step
            if self.dryer_temp_now > self.dryer_temp_req:
                self.dryer_temp_now = self.dryer_temp_req
        else:
            chance = random.random()
            if chance < 0.80:
                var = random.uniform(0.01, 0.05)
                self.dryer_temp_now = self.dryer_temp_req * (1 + var * random.choice([-1, 1]))
            elif chance < 0.85:
                self.dryer_temp_now = self.dryer_temp_req * (1 + 0.50 * random.choice([-1, 1]))
            else:
                self.dryer_temp_now = self.dryer_temp_req

        if self.time_to_now >= self.total_time:
            self._needs_reset = True
        
        return self._current_state()

    def _current_state(self):
        return {
            "time_to_now": self.time_to_now,
            "total_time": self.total_time,
            "dryer_temp_now": round(self.dryer_temp_now, 2),
            "dryer_temp_req": self.dryer_temp_req
        }

# --- НАСТРОЙКИ ---
BROKER = "10.82.109.205"
PORT = 1883
TOPIC_BASE = "telemetry"
ERROR_CHANCE = 0.2
NUM_DEVICES = 15

LOG_MESSAGES = {
    telemetry_pb2.INFO: ["System heartbeat stable", "Metrics collected successfully", "Peripheral sensor connected"],
    telemetry_pb2.WARN: ["High memory pressure detected", "CPU temperature exceeding threshold", "Slow response from MQTT broker"],
    telemetry_pb2.ERROR: ["Failed to read from hardware sensor", "Database connection timeout", "Invalid CRC checksum"]
}

def get_now():
    ts = Timestamp()
    ts.GetCurrentTime()
    return ts

def get_system_info():
    """Возвращает ОБЩУЮ системную информацию, не зависящую от устройства."""
    return {
        "firmware": f"{platform.system()} {platform.release()}",
        "model": platform.machine()
    }

def create_payload(device_id, dryer_sim, common_sys_info):
    telemetry = telemetry_pb2.IoTDeviceTelemetry()

    # 1. ПАСПОРТ УСТРОЙСТВА
    telemetry.info.device_id = device_id
    telemetry.info.firmware_version = common_sys_info["firmware"]
    telemetry.info.hardware_model = common_sys_info["model"]

    # 2. ЗАРЯД БАТАРЕИ И ОНЛАЙН СТАТУС (остается общим для всех)
    # telemetry.state.is_online = True
    battery = psutil.sensors_battery()
    if battery:
        telemetry.state.battery_level = float(battery.percent)

    # 3. СИСТЕМНЫЕ МЕТРИКИ (CPU, RAM, TEMP - остаются общими)
    cpu_load = psutil.cpu_percent(interval=None)
    ram = psutil.virtual_memory()
    cpu_temp = 0.0
    try:
        temps = psutil.sensors_temperatures()
        if 'coretemp' in temps:
            cpu_temp = temps['coretemp'][0].current
        elif temps:
            cpu_temp = list(temps.values())[0][0].current
    except:
        cpu_temp = 0.0

    # 4. МЕТРИКИ СУШИЛКИ (уникальны для каждого симулятора)
    d = dryer_sim.get_metrics()

    all_metrics = [
        ("cpu_usage", cpu_load),
        ("ram_usage_percent", ram.percent),
        ("cpu_temperature", cpu_temp),
        ("dryer_temp_now", d["dryer_temp_now"]),
        ("dryer_temp_req", d["dryer_temp_req"]),
        ("total_time", d["total_time"]),
        ("time_to_now", d["time_to_now"]),
    ]

    for name, val in all_metrics:
        m_pb = telemetry.metrics.add()
        m_pb.name = name
        m_pb.type = telemetry_pb2.GAUGE
        m_pb.value = float(val)
        m_pb.timestamp.CopyFrom(get_now())

    # 5. ЛОГИ (генерируются для каждого устройства)
    log_stats = telemetry.logs.add()
    log_stats.level = telemetry_pb2.INFO
    log_stats.message = "Device health check: OK"
    log_stats.timestamp.CopyFrom(get_now())

    log_event = telemetry.logs.add()
    lvl = random.choice([telemetry_pb2.WARN, telemetry_pb2.ERROR]) if random.random() < ERROR_CHANCE else telemetry_pb2.INFO
    log_event.level = lvl
    log_event.message = random.choice(LOG_MESSAGES[lvl])
    log_event.timestamp.CopyFrom(get_now())

    return telemetry.SerializeToString(), lvl, log_event.message, d["time_to_now"]

def main():
    # Создаем словарь симуляторов для каждого устройства
    devices = {}
    base_mac = uuid.getnode()
    for i in range(NUM_DEVICES):
        # Генерируем уникальный ID для каждого устройства
        device_id = f"node-{hex(base_mac + i)[2:]}"
        devices[device_id] = DryerSimulator()

    common_sys_info = get_system_info()
    client = mqtt.Client(callback_api_version=mqtt.CallbackAPIVersion.VERSION2, protocol=mqtt.MQTTv5)

    print(f"Connecting to {BROKER}...")
    try:
        client.connect(BROKER, PORT)
    except Exception as e:
        print(f"Connection error: {e}")
        return

    client.loop_start()
    print(f"Started sending data for {NUM_DEVICES} devices...")

    try:
        while True:
            start_loop = time.time()

            # Проходим по всем устройствам и отправляем их телеметрию
            for device_id, dryer_sim in devices.items():
                payload, level, msg, dryer_time_now = create_payload(device_id, dryer_sim, common_sys_info)
                topic = f"{TOPIC_BASE}/{device_id}"
                pub = client.publish(topic, payload, qos=1)
                # Не будем ждать подтверждения публикации, чтобы ускорить отправку
                # pub.wait_for_publish(timeout=1.0) 

                ts = time.strftime('%H:%M:%S')
                color = "\033[91m" if level == telemetry_pb2.ERROR else "\033[93m" if level == telemetry_pb2.WARN else ""
                print(f"[{ts}] SENT to {device_id} | Dryer Time: {int(dryer_time_now)}s | Event: {color}{msg}\033[0m")
            
            # Компенсация времени выполнения кода, чтобы основной цикл шел ~1.0 сек
            elapsed = time.time() - start_loop
            sleep_time = 3.0 - elapsed
            
            # Выводим предупреждение, если отправка занимает больше секунды
            if sleep_time < 0:
                print(f"\033[93m[WARNING] Loop took {elapsed:.2f}s, which is longer than the 1s interval. Consider reducing NUM_DEVICES or optimizing the code.\033[0m")
            
            time.sleep(max(0, sleep_time))

    except KeyboardInterrupt:
        print("\nStopping...")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    main()

