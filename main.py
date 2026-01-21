from fastapi import FastAPI
import models
from database import engine
from routers import groups, devices
from fastapi.middleware.cors import CORSMiddleware

models.Base.metadata.create_all(bind=engine)

app = FastAPI(title="IoT Manager API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(groups.router)
app.include_router(devices.router)

@app.get("/")
def root():
    return {"ok": True, "msg": "IoT management API running. See /docs"}
