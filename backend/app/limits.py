import hashlib,time
from starlette.responses import JSONResponse
from .config import settings
from .queue import connection

class RequestLimitMiddleware:
    def __init__(self,app):self.app=app
    async def __call__(self,scope,receive,send):
        if scope['type']!='http':return await self.app(scope,receive,send)
        cfg=settings();path=scope.get('path','')
        if path.startswith('/api') and scope['method'] not in ('GET','HEAD','OPTIONS'):
            parts=[];size=0
            while True:
                part=await receive()
                if part['type']!='http.request':break
                size+=len(part.get('body',b''))
                if size>65536:return await JSONResponse({'detail':'Request terlalu besar'},413)(scope,receive,send)
                parts.append(part)
                if not part.get('more_body'):break
            original=receive
            # Avoid recursive closure after rebinding.
            async def replay():
                if parts:return parts.pop(0)
                return await original()
            receive=replay
        if path=='/api/auth/login' and (cfg.app_env=='production' or cfg.rate_limit_enabled):
            try:
                from starlette.concurrency import run_in_threadpool
                def limit():
                    r=connection();ip=scope.get('client',('unknown',))[0]
                    key='mapauto:ratelimit:'+hashlib.sha256((ip+str(int(time.time()/60))).encode()).hexdigest()
                    n=r.incr(key)
                    if n==1:r.expire(key,70)
                    return n
                if await run_in_threadpool(limit)>20:return await JSONResponse({'detail':'Batas login per menit tercapai'},429)(scope,receive,send)
            except Exception:return await JSONResponse({'detail':'Layanan keamanan belum siap'},503)(scope,receive,send)
        await self.app(scope,receive,send)
