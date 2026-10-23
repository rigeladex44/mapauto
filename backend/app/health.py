import sys,time,urllib.request
from pathlib import Path
from .queue import connection

def main():
    connection().ping()
    if sys.argv[1]=='api':urllib.request.build_opener(urllib.request.ProxyHandler({})).open('http://127.0.0.1:8000/api/health',timeout=3)
    elif sys.argv[1]=='worker':
        # Process heartbeat written even with zero merchants/jobs.
        p=Path('/tmp/mapauto-worker-heartbeat')
        if not p.exists() or time.time()-p.stat().st_mtime>20:raise SystemExit(1)
if __name__=='__main__':main()
