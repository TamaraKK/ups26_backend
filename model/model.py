import pandas as pd
from statsmodels.tsa.seasonal import STL
from adtk.detector import InterQuartileRangeAD
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
import models
from utils.dependencies import get_db
import httpx

router = APIRouter(prefix="/model", tags=["Model"])


PROMETHEUS_BASE = "http://prometheus:9090/api/v1"

async def get_data_from_db(device_id: int, db: Session, metric_name: str, limit_minutes=150):
    serial = db.query(models.Device.serial).filter(models.Device.id == device_id).scalar()
    
    if not serial:
        print(f"DEBUG: Device with id {device_id} not found in DB")
        return pd.DataFrame()

    url = f"{PROMETHEUS_BASE}/query_range"
    params = {
        "query": f'{metric_name}{{serial="{serial}"}}',
        "start": pd.Timestamp.now().timestamp() - (limit_minutes * 60),
        "end": pd.Timestamp.now().timestamp(),
        "step": "60s"
    }

    async with httpx.AsyncClient() as client:
        resp = await client.get(url, params=params)
        data = resp.json()
        
    results = data.get("data", {}).get("result", [])
    if not results:
        return pd.DataFrame()

    values = results[0].get("values", []) 
    
    df = pd.DataFrame(values, columns=['timestamp', 'value'])
    df['timestamp'] = pd.to_datetime(df['timestamp'].astype(float), unit='s')
    df['value'] = pd.to_numeric(df['value'])
    
    return df.set_index('timestamp').sort_index()

@router.get('/get_device_anomalies')
async def get_device_anomalies(device_id: int, metric: str = "device_cpu_usage", db: Session = Depends(get_db)):
    df = await get_data_from_db(device_id, db, metric_name=metric)
    
    if df.empty:
        return {"error": "No data found for this device/metric"}
    
    report = get_device_diagnostics(df['value'])
    return report

def get_device_diagnostics(df, period=30):
      #stl = STL(df['mcu_internal_temp_celsius'], period=period, robust=True)
      # модель анализирует датафрейм только по одной метрике, например device_cpu_usage, и метрики только числовые.
      #
      stl = STL(df, period=period, robust=True)

      res = stl.fit()

      iqr_detector = InterQuartileRangeAD(c=4)
      anomalies = iqr_detector.fit_detect(res.resid)

      anomaly_timestamps = anomalies[anomalies].index.strftime('%Y-%m-%d %H:%M:%S').tolist()

      trend_diff = res.trend.iloc[-1] - res.trend.iloc[0]

      return {
            "status": "warning" if len(anomaly_timestamps) > 0 else "stable",
            "anomaly_count": len(anomaly_timestamps),
            "critical_points": anomaly_timestamps, 
            "degradation_value": round(trend_diff, 2),
            "is_degrading": bool(trend_diff > 2.0)
      }