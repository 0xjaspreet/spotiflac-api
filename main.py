"""
SpotiFLAC API v2.0
FastAPI wrapper for downloading Spotify content in FLAC via Qobuz/Amazon/Tidal.
Auto-fallback: tries each service in priority order. Per-track retry.
"""
import asyncio
import json
import logging
import os
import re
import subprocess
import time
import uuid
from pathlib import Path
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uvicorn

# Configuration
MUSIC_DIR = os.environ.get("MUSIC_DIR", "/music")
SPOTIFLAC_BIN = os.environ.get("SPOTIFLAC_BIN", "spotiflac")
MAX_CONCURRENT = int(os.environ.get("MAX_CONCURRENT", "3"))
DEFAULT_SERVICES = ["qobuz", "amazon", "tidal"]

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("spotiflac-api")

jobs: dict[str, dict] = {}

class DownloadRequest(BaseModel):
    url: str
    output_subdir: Optional[str] = None
    services: Optional[list[str]] = None

class DownloadResponse(BaseModel):
    job_id: str
    status: str
    message: str

class JobStatusResponse(BaseModel):
    job_id: str
    status: str
    progress: Optional[str] = None
    destination: Optional[str] = None
    error: Optional[str] = None
    files: list[str] = []

def run_spotiflac(url: str, output_dir: str, services: list[str]) -> dict:
    """Run spotiflac CLI directly. Returns result dict."""
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    cmd = ["spotiflac", url, output_dir]
    for s in services:
        cmd.extend(["--service", s])
    cmd.extend(["--quality", "6"])
    
    logger.info("Running: %s", " ".join(cmd[:4]) + " ...")
    start = time.time()
    
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=900,
        cwd=output_dir,
    )
    
    output = result.stdout + result.stderr
    elapsed = time.time() - start
    
    # Find FLAC files
    files = []
    for root, dirs, fnames in os.walk(output_dir):
        for f in fnames:
            if f.endswith(".flac"):
                files.append(os.path.join(root, f))
    
    # Parse summary
    tracks_ok = 0
    tracks_fail = 0
    for m in re.finditer(r"Completate\s*:\s*(\d+)", output):
        tracks_ok = int(m.group(1))
    for m in re.finditer(r"Fallite\s*:\s*(\d+)", output):
        tracks_fail = int(m.group(1))
    
    success = result.returncode == 0 and tracks_ok > 0
    error = output[-500:] if not success else None
    
    return {
        "success": success,
        "files": files,
        "error": error,
        "tracks_ok": tracks_ok,
        "tracks_fail": tracks_fail,
        "elapsed": round(elapsed, 1),
        "services_used": services,
    }

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("SpotiFLAC API v2.0 starting - MUSIC_DIR=%s", MUSIC_DIR)
    Path(MUSIC_DIR).mkdir(parents=True, exist_ok=True)
    yield
    logger.info("SpotiFLAC API shutting down")

app = FastAPI(title="SpotiFLAC API", version="2.0.0", lifespan=lifespan)

@app.get("/health")
def health():
    return {
        "status": "ok",
        "version": "2.0.0",
        "music_dir": MUSIC_DIR,
        "default_services": DEFAULT_SERVICES,
        "max_concurrent": MAX_CONCURRENT,
        "active_jobs": sum(1 for j in jobs.values() if j["status"] in ("queued", "running")),
    }

@app.post("/api/download")
def download(req: DownloadRequest):
    """Queue a download. Returns job_id immediately."""
    job_id = str(uuid.uuid4())[:8]
    dest = os.path.join(MUSIC_DIR, req.output_subdir) if req.output_subdir else MUSIC_DIR
    svcs = req.services or DEFAULT_SERVICES
    
    jobs[job_id] = {
        "status": "queued",
        "url": req.url,
        "destination": dest,
        "services": svcs,
        "progress": None,
        "error": None,
        "files": [],
        "started_at": None,
        "completed_at": None,
    }
    
    def run_job(jid, url, outdir, svc_list):
        logger.info("Job %s: starting - %s (services: %s)", jid, url, svc_list)
        jobs[jid]["status"] = "running"
        jobs[jid]["started_at"] = time.time()
        
        r = run_spotiflac(url, outdir, svc_list)
        
        if r["success"]:
            jobs[jid]["status"] = "completed"
            jobs[jid]["files"] = r["files"]
            jobs[jid]["progress"] = f"{r['tracks_ok']}/{r['tracks_ok']+r['tracks_fail']} tracks, {r['elapsed']}s"
            logger.info("Job %s: %d tracks in %.1fs", jid, r["tracks_ok"], r["elapsed"])
        else:
            jobs[jid]["status"] = "failed"
            jobs[jid]["error"] = r["error"]
            logger.error("Job %s: failed - %s", jid, r["error"][:200] if r["error"] else "unknown")
        
        jobs[jid]["completed_at"] = time.time()
    
    asyncio.create_task(asyncio.to_thread(run_job, job_id, req.url, dest, svcs))
    
    return DownloadResponse(
        job_id=job_id,
        status="queued",
        message=f"Download queued for {req.url}",
    )

@app.get("/api/status/{job_id}")
def get_job_status(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found")
    j = jobs[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=j["status"],
        progress=j["progress"],
        destination=j["destination"],
        error=j["error"],
        files=j["files"],
    )

@app.get("/api/status")
def list_jobs():
    return {
        "total": len(jobs),
        "active": sum(1 for j in jobs.values() if j["status"] in ("queued", "running")),
        "jobs": [
            {
                "job_id": jid,
                "status": j["status"],
                "url": j["url"],
                "destination": j["destination"],
                "progress": j["progress"],
                "error": j["error"][:200] if j["error"] else None,
                "files_count": len(j["files"]),
            }
            for jid, j in list(jobs.items())[-20:]
        ],
    }

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=9118, log_level="info")
