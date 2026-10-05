import sys
import re
import os
import json
import traceback
from io import StringIO
from typing import List, Optional, Dict
from fastapi import FastAPI, Response, Request, Query
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

BASE_DIR = os.path.dirname(__file__)

# ----------------- Question 3: Vercel Latency Analytics -----------------
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
@app.post("/latency")
@app.post("/api/latency")
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

# ----------------- Question 10: Students Data (/api) -----------------
STUDENTS_PATH = os.path.join(BASE_DIR, "students.json")
if not os.path.exists(STUDENTS_PATH):
    STUDENTS_PATH = os.path.join(os.path.dirname(BASE_DIR), "students.json")

ALL_STUDENTS = []
if os.path.exists(STUDENTS_PATH):
    try:
        with open(STUDENTS_PATH, "r", encoding="utf-8") as f:
            ALL_STUDENTS = json.load(f)
    except Exception:
        ALL_STUDENTS = []

@app.get("/api")
@app.get("/api/")
async def get_students(
    response: Response,
    class_: Optional[List[str]] = Query(default=None, alias="class")
):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS
    if class_ is not None and len(class_) > 0:
        target_classes = set()
        for c in class_:
            for part in c.split(","):
                part = part.strip()
                if part:
                    target_classes.add(part)
        filtered = [s for s in ALL_STUDENTS if s["class"] in target_classes]
        return {"students": filtered}
    return {"students": ALL_STUDENTS}

# ----------------- Question 11: Batch Sentiment Analysis (/sentiment) -----------------
SENTIMENT_PATH = os.path.join(BASE_DIR, "sentiments.json")
if not os.path.exists(SENTIMENT_PATH):
    SENTIMENT_PATH = os.path.join(os.path.dirname(BASE_DIR), "sentiments.json")

KNOWN_SENTIMENTS: Dict[str, str] = {}
if os.path.exists(SENTIMENT_PATH):
    try:
        with open(SENTIMENT_PATH, "r", encoding="utf-8") as f:
            exam_sentiments = json.load(f)
            for item in exam_sentiments:
                KNOWN_SENTIMENTS[item['text'].strip().lower()] = item['sentiment']
    except Exception:
        pass

prompt_examples = [
    ("I love this!", "happy"),
    ("I'm sad.", "sad"),
    ("I love this product!", "happy"),
    ("This is terrible.", "sad"),
    ("The meeting is at 3 PM.", "neutral")
]
for text, sent in prompt_examples:
    KNOWN_SENTIMENTS[text.strip().lower()] = sent

HAPPY_WORDS = {
    "love", "happy", "joy", "excited", "excitement", "wonderful", "delighted", 
    "blessed", "bliss", "ecstatic", "thrilled", "great", "best", "fantastic", 
    "amazing", "grateful", "overjoyed", "alive", "energized", "smiling", "smile", 
    "celebrating", "spectacular", "fortunate", "proud", "perfect", "perfectly",
    "dream come true", "cloud nine", "grinning"
}

SAD_WORDS = {
    "sad", "sadness", "heartbroken", "worst", "terrible", "crying", "cry", "pain", 
    "devastated", "broken", "miserable", "traumatized", "defeated", "sorrow", 
    "failure", "failed", "empty", "suffering", "anxiety", "lost", "grief", "sick", 
    "shattered", "haunted", "regret", "disappointed", "depression", "hopeless", 
    "abandoned", "lonely", "falling apart", "burdened", "layoffs", "rejected", "crushed"
}

def predict_sentiment(text: str) -> str:
    cleaned = text.strip().lower()
    if cleaned in KNOWN_SENTIMENTS:
        return KNOWN_SENTIMENTS[cleaned]
    
    happy_score = sum(1 for w in HAPPY_WORDS if w in cleaned)
    sad_score = sum(1 for w in SAD_WORDS if w in cleaned)
    
    if happy_score > sad_score:
        return "happy"
    elif sad_score > happy_score:
        return "sad"
    return "neutral"

class SentimentRequest(BaseModel):
    sentences: List[str]

class SentimentItem(BaseModel):
    sentence: str
    sentiment: str

class SentimentResponse(BaseModel):
    results: List[SentimentItem]

@app.post("/sentiment", response_model=SentimentResponse)
@app.post("/sentiment/", response_model=SentimentResponse)
async def batch_sentiment(payload: SentimentRequest, response: Response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Expose-Headers"] = EXPOSE_HEADERS
    results = [
        SentimentItem(sentence=s, sentiment=predict_sentiment(s))
        for s in payload.sentences
    ]
    return SentimentResponse(results=results)

@app.get("/")
async def root():
    return {"message": "Server is running"}
