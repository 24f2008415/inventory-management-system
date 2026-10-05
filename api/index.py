import sys
import re
import os
import json
import traceback
from io import StringIO
from typing import List
from fastapi import FastAPI, Response, Request
from pydantic import BaseModel

app = FastAPI()

EXPOSE_HEADERS = "*, Access-Control-Allow-Origin, access-control-allow-origin"

@app.middleware("http")
async def enforce_wildcard_cors(request: Request, call_next):
    if request.method == "OPTIONS":
        response = Response(status_code=200)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "POST, GET, OPTIONS, PUT, DELETE"
    response.headers["Access-Control-Allow-Headers"] = "*"
    response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS
    return response

# ----------------- Question: Vercel Latency Analytics -----------------
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
async def options_handler(full_path: str = ""):
    return Response(
        status_code=200,
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "POST, GET, OPTIONS, PUT, DELETE",
            "Access-Control-Allow-Headers": "*",
            "Access-Control-Expose-Headers": EXPOSE_HEADERS
        }
    )

@app.post("/")
@app.post("/api")
@app.post("/api/index")
@app.post("/api/latency")
@app.post("/latency")
async def calculate_metrics(req: MetricsRequest, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS
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

# ----------------- Question: Code Interpreter with AI Error Analysis -----------------
class CodeInterpreterRequest(BaseModel):
    code: str

class CodeInterpreterResponse(BaseModel):
    error: List[int]
    result: str

def execute_python_code(code: str) -> dict:
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    try:
        exec(code, {})
        output = sys.stdout.getvalue()
        return {"success": True, "output": output}
    except Exception:
        output = traceback.format_exc()
        return {"success": False, "output": output}
    finally:
        sys.stdout = old_stdout

def extract_lines_from_traceback(tb: str) -> List[int]:
    matches = re.findall(r'File "<string>", line (\d+)', tb)
    if matches:
        return [int(matches[-1])]
    return []

@app.post("/code-interpreter", response_model=CodeInterpreterResponse)
@app.post("/code-interpreter/", response_model=CodeInterpreterResponse)
async def code_interpreter_endpoint(req: CodeInterpreterRequest, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS
    res = execute_python_code(req.code)
    if res["success"]:
        return CodeInterpreterResponse(error=[], result=res["output"])
    else:
        err_lines = extract_lines_from_traceback(res["output"])
        return CodeInterpreterResponse(error=err_lines, result=res["output"])

@app.get("/")
@app.get("/{full_path:path}")
async def root(full_path: str = ""):
    return {"message": "Server is running"}
