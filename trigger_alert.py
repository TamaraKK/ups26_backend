import paho.mqtt.client as mqtt
import metrics_logs_pb2
from google.protobuf.timestamp_pb2 import Timestamp
import time
import schedule

# MQTT Broker details
broker_address = "localhost"
broker_port = 1883
topic = "telemetry/test-device"

def send_low_battery_metric():
    # Create a new MQTT client instance
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION1)

    # Connect to the MQTT broker
    client.connect(broker_address, broker_port, 60)

    # Create a telemetry message
    telemetry = metrics_logs_pb2.IoTDeviceTelemetry()
    telemetry.info.device_id = "test-device"
    telemetry.state.battery_level = 5.0  # Low battery

    # Get current time
    now = time.time()
    seconds = int(now)
    nanos = int((now - seconds) * 10**9)
    timestamp = Timestamp(seconds=seconds, nanos=nanos)

    telemetry.metrics.add(name="temperature", value=25.5, timestamp=timestamp)

    # Serialize the message
    payload = telemetry.SerializeToString()

    # Publish the message
    client.publish(topic, payload, qos=1)

    print(f"Sent message to topic {topic}")

    # Disconnect from the broker
    client.disconnect()

# Schedule the job
schedule.every(15).seconds.do(send_low_battery_metric)

print("Sending low battery metric every 15 seconds for 6 minutes...")
# Run the job for 6 minutes
end_time = time.time() + 6 * 60
while time.time() < end_time:
    schedule.run_pending()
    time.sleep(1)

print("Finished sending metrics.")