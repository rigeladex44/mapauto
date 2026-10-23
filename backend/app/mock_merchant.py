"""Synthetic merchant fixture ONLY. No MyPertamina URLs, accounts or transactions."""
import secrets
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
app=FastAPI(docs_url=None,redoc_url=None)

def identity(request):
    merchant=request.cookies.get('mock_merchant')
    if not merchant:raise HTTPException(401,'Mock login required')
    return merchant
@app.get('/health')
def health():return {'status':'ok','synthetic':True}
@app.get('/login',response_class=HTMLResponse)
def login_page():
    return '<h1>MOCK MERCHANT · SYNTHETIC ONLY</h1><label>Merchant<input id="merchant"></label><button id="login" onclick="document.cookie=\'mock_merchant=\'+encodeURIComponent(document.querySelector(\'#merchant\').value)+\'; SameSite=Strict; path=/\';location.href=\'/portal\'">Login mock</button>'
@app.get('/portal',response_class=HTMLResponse)
def portal(request:Request):
    identity(request)
    return '<h1>MOCK PORTAL</h1><div id="status">ready</div><input id="nik"><input id="otp"><button id="verify">Verifikasi mock</button><script>document.querySelector("#verify").onclick=()=>{document.querySelector("#status").textContent=document.querySelector("#otp").value==="246810"?"verified":"rejected";};</script>'
@app.get('/identity')
def who(request:Request):return {'merchant':identity(request)}
@app.post('/submit')
async def submit(request:Request):
    merchant=identity(request);data=await request.json()
    if not data.get('key'):raise HTTPException(422,'key required')
    # Redis supplies mock service idempotency across fixture restarts.
    from .queue import connection
    r=connection();key='mapauto:mock:receipt:'+data['key']
    receipt=r.get(key)
    if not receipt:
        receipt=secrets.token_hex(8);r.set(key,receipt,nx=True,ex=86400);receipt=r.get(key)
    return {'receipt':receipt,'synthetic':True,'merchant':merchant}
