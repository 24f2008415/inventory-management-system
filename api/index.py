from fastapi import FastAPI, Response, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List
import json
import os

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load telemetry data
BASE_DIR = os.path.dirname(__file__)
DATA_PATH = os.path.join(BASE_DIR, "telemetry.json")
if not os.path.exists(DATA_PATH):
    DATA_PATH = os.path.join(os.path.dirname(BASE_DIR), "telemetry.json")

try:
    with open(DATA_PATH, "r", encoding="utf-8") as f:
        telemetry = json.load(f)
except Exception:
    telemetry = []

class MetricsRequest(BaseModel):
    regions: List[str]
    threshold_ms: float

def p95_calc(arr):
    s = sorted(arr)
    r = (len(s) - 1) * 0.95
    n = int(r)
    l = r - n
    if n + 1 < len(s):
        return s[n] + l * (s[n+1] - s[n])
    return s[n]

@app.options("/{full_path:path}")
async def options_handler(full_path: str):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS",
            "Access-Control-Allow-Headers": "*"
        }
    )

@app.post("/")
@app.post("/api")
@app.post("/api/index")
async def calculate_metrics(req: MetricsRequest, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    results = []
    for reg in req.regions:
        recs = [r for r in telemetry if r.get("region") == reg]
        if not recs:
            continue
        lats = [r["latency_ms"] for r in recs]
        uptimes = [r["uptime_pct"] for r in recs]
        avg_lat = round(sum(lats) / len(lats), 2)
        p95_lat = round(p95_calc(lats), 2)
        avg_up = round(sum(uptimes) / len(uptimes), 3)
        breaches = sum(1 for l in lats if l > req.threshold_ms)
        results.append({
            "region": reg,
            "avg_latency": avg_lat,
            "p95_latency": p95_lat,
            "avg_uptime": avg_up,
            "breaches": breaches
        })
    return {"regions": results}

@app.get("/")
async def root():
    return {"message": "eShopCo Latency Diagnostics API is running"}
