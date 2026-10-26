/* Live inspection transport. Demo remains explicitly selectable; tokens stay in memory. */
const demoHandlers = {
  login: $('form').onsubmit, start: $('startRun').onclick, pause: $('pauseRun').onclick,
  stop: $('stopRun').onclick, sync: syncStock, logout, history: openHistory, account: openAccount,
  render: renderRun, newer: newBatch
};
let sessionToken = '', liveInfo = null, liveBatchId = '', livePoll = null, pollBusy = false, commandBusy = false;
const liveMode = () => $('connectionMode').value === 'live';
const apiBase = String(window.MAP_API_BASE || '').replace(/\/$/, '');
async function api(path, method='GET', payload) {
  const response = await fetch(apiBase + '/api' + path, {
    method, headers: {'Content-Type':'application/json', ...(sessionToken?{Authorization:'Bearer '+sessionToken}:{})},
    body: payload === undefined ? undefined : JSON.stringify(payload)
  });
  const data = await response.json().catch(()=>({detail:'Respons backend tidak dikenali.'}));
  if (!response.ok) {
    if(response.status===401&&sessionToken){sessionToken='';cancelPolling();running=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());go(false)}
    throw new Error(data.detail || 'Backend belum dapat dihubungi.');
  }
  return data;
}
function applyLiveInfo(info) {
  liveInfo=info;
  $('connectionStatus').textContent='● '+info.state+' · Uji baca';
  $('connectionMessage').textContent=info.message || 'Mode inspeksi: tidak mengirim checkout atau transaksi.';
  $('checkSession').hidden=info.state!=='Perlu verifikasi';
  const owner=document.querySelector('.account-trigger');
  owner.querySelector('strong').textContent=info.name || 'Nama belum terbaca';
  owner.querySelector('span').textContent=info.subname || 'Merchant asli · Uji baca';
  if (Number.isInteger(info.stock)) updateMerchantStock(info.stock);
  else $('stockValue').textContent='— Tabung';
  $('lastSync').textContent=(info.last_sync?'Dibaca '+new Date(info.last_sync).toLocaleTimeString('id-ID'):'Belum dibaca')+(info.message?' · Perlu sinkronisasi':'');
}
function cancelPolling(){clearTimeout(livePoll);livePoll=null}
function schedulePolling(){cancelPolling();if(sessionToken)livePoll=setTimeout(pollLive,1000)}
async function pollLive(){
  if(!sessionToken||pollBusy)return;
  if(commandBusy){schedulePolling();return}
  pollBusy=true;
  try{
    applyLiveInfo(await api('/session'));
    if(liveBatchId){
      const report=await api('/batches/'+encodeURIComponent(liveBatchId));
      applyLiveBatch(report);
    }
  }catch(e){$('connectionMessage').textContent=e.message;$('connectionStatus').textContent='● Koneksi terputus';}
  finally{pollBusy=false;schedulePolling()}
}
function applyLiveBatch(data){
  liveBatchId=data.id;batchStarted=data.started;batch=data.rows;runMode=data.mode;speedMode=data.speed;
  running=['Berjalan','Dijeda','Menghentikan'].includes(data.state);paused=data.state==='Dijeda';stopRequested=data.state==='Menghentikan';completion=data.state;
  renderRun();
}
function normalizeLiveReport(data){return {...data,completion:data.state}}
$('connectionMode').onchange=()=>{$('liveAccessField').hidden=!liveMode();$('loginHint').textContent=liveMode()?'Masukkan kredensial hanya jika backend pengujian Anda sudah berjalan.':'Demo tidak melakukan login ke merchant.'};
$('connectionMode').onchange();
$('form').onsubmit=async e=>{
  if(!liveMode()){demoHandlers.login(e);return}
  e.preventDefault();
  if(commandBusy)return;
  if(!apiBase&&location.protocol==='file:'){toast('Jalankan melalui backend lokal, bukan membuka file HTML langsung.');return}
  const identity=$('identity').value.trim(),pin=$('pin').value,key=$('accessKey').value;
  if(!identity||!pin||!key){toast('Isi email/ponsel, PIN dan kunci akses backend.');return}
  commandBusy=true;const b=$('form').querySelector('button[type="submit"]');b.disabled=true;b.textContent='MENGHUBUNGKAN…';
  try{
    const result=await api('/login','POST',{identity,pin,access_key:key});
    sessionToken=result.session_token;
    $('pin').value='';$('accessKey').value='';
    go(true);applyLiveInfo(result);schedulePolling();
    document.querySelector('#dashboard .demo').textContent='UJI PLAYWRIGHT · TANPA TRANSAKSI';
    $('startRun').textContent='MULAI PEMERIKSAAN NIK';
    document.querySelector('#saleDialog .demo-note').textContent='Mode inspeksi · Berhenti sebelum checkout atau transaksi';
    document.querySelector('#historyDialog > .nik-help').textContent='Hasil tersimpan di backend dan hanya tersedia untuk sesi aplikasi ini. Login ulang tidak membuka riwayat sesi sebelumnya.';
  }catch(err){toast(err.message)}finally{commandBusy=false;b.disabled=false;b.textContent='MASUK'}
};
$('checkSession').onclick=async()=>{if(commandBusy)return;commandBusy=true;try{applyLiveInfo(await api('/session/check','POST',{}));toast('Pemeriksaan sesi selesai.')}catch(e){toast(e.message)}finally{commandBusy=false}};
syncStock=async function(){
  if(!liveMode())return demoHandlers.sync();
  if(commandBusy)return;
  commandBusy=true;$('stockDemo').disabled=true;$('stockDemo').textContent='Membaca stok…';
  try{applyLiveInfo(await api('/stock/sync','POST',{}));toast('Pembacaan stok selesai.')}catch(e){toast(e.message)}finally{commandBusy=false;$('stockDemo').disabled=false;$('stockDemo').textContent='↻ Sinkronkan stok'}
};
$('stockDemo').onclick=()=>syncStock();
$('startRun').onclick=async()=>{
  if(!liveMode())return demoHandlers.start();
  if(commandBusy||running)return;
  validateNiks();if($('continueSale').disabled)return;
  commandBusy=true;$('startRun').disabled=true;
  try{
    const report=await api('/batches','POST',{niks:validNiks,mode:document.querySelector('input[name="customerType"]:checked').value,speed:document.querySelector('input[name="speedMode"]:checked').value});
    $('runFilter').value='Semua';applyLiveBatch(report);stage('saleQueue');schedulePolling();
  }catch(e){toast(e.message)}finally{commandBusy=false;$('startRun').disabled=false}
};
async function controlLive(action){if(commandBusy||!liveBatchId)return;commandBusy=true;try{applyLiveBatch(await api('/batches/'+encodeURIComponent(liveBatchId)+'/control','POST',{action}))}catch(e){toast(e.message)}finally{commandBusy=false}}
$('pauseRun').onclick=()=>liveMode()?controlLive(paused?'resume':'pause'):demoHandlers.pause();
$('stopRun').onclick=()=>liveMode()?controlLive('stop'):demoHandlers.stop();
renderRun=function(){
  if(!liveMode())return demoHandlers.render();
  const done=batch.filter(r=>!['Menunggu','Diproses'].includes(r.status)).length;
  $('queueSummary').textContent=runMode+' · '+speedMode+' · Inspeksi merchant asli';
  const ready=batch.filter(r=>r.status==='Siap ditinjau').length,issues=batch.filter(r=>['Perlu diperiksa','Perlu verifikasi'].includes(r.status)).length;
  $('runTotals').innerHTML='<span>'+batch.length+' NIK</span><span>'+ready+' siap ditinjau</span><span>'+batch.filter(r=>r.status==='Limit').length+' limit</span><span>'+batch.filter(r=>r.status==='Dilewati').length+' dilewati</span><span class="bad">'+issues+' perlu diperiksa</span><span>0 transaksi dikirim</span>';
  $('runProgress').max=batch.length||1;$('runProgress').value=done;
  $('runState').textContent=completion+' · '+done+' / '+batch.length+' NIK';
  $('pauseRun').hidden=!running;$('pauseRun').disabled=stopRequested;$('pauseRun').textContent=paused?'LANJUTKAN PEMERIKSAAN':'JEDA';
  $('stopRun').hidden=!running;$('stopRun').disabled=stopRequested;$('newBatch').disabled=running;$('downloadRun').disabled=!done;
  drawRows(batch,'queueRows',$('runFilter').value);
};
for(const id of ['runFilter','historyFilter'])for(const value of ['Siap ditinjau','Perlu diperiksa','Perlu verifikasi']){const o=document.createElement('option');o.value=value;o.textContent=value;$(id).appendChild(o)}
newBatch=function(){if(liveMode()){if(running)return;liveBatchId=''}demoHandlers.newer()};
openHistory=async function(){
  if(!liveMode())return demoHandlers.history();
  try{
    history=(await api('/batches')).filter(r=>!['Berjalan','Dijeda','Menghentikan'].includes(r.state)).map(normalizeLiveReport);
    historyBack();$('historyDialog').showModal();
  }catch(e){toast(e.message)}
};
const oldHistoryBack=historyBack;
historyBack=function(){oldHistoryBack();if(liveMode()){
  const cards=$('historyList').querySelectorAll('.history-card:not(.history-live)');
  cards.forEach((card,i)=>{if(history[i])card.querySelector('span').textContent=history[i].mode+' · '+history[i].rows.length+' NIK · '+history[i].rows.filter(r=>r.status==='Siap ditinjau').length+' siap ditinjau · Tanpa transaksi'});
}};
const oldHistoryDetail=renderHistoryDetail;
renderHistoryDetail=function(){oldHistoryDetail();if(liveMode()&&selectedHistory){$('historyTotals').textContent=selectedHistory.rows.filter(r=>r.status==='Siap ditinjau').length+' siap ditinjau · 0 transaksi dikirim';}};
const oldExport=exportReport;
exportReport=function(report){if(!liveMode())return oldExport(report);
  const rows=report.rows.filter(r=>!['Menunggu','Diproses'].includes(r.status));
  const lines=['MAP.PRO — LAPORAN INSPEKSI PLAYWRIGHT','Belum checkout atau transaksi. Siap ditinjau bukan penjualan sukses.','Mulai: '+report.started,'Status: '+report.completion,'NIK | Status | Jenis | Keterangan',...rows.slice().reverse().map(r=>[r.nik,r.status,r.type,r.reason].join(' | '))];
  const blob=new Blob(['\uFEFF'+lines.join('\n')],{type:'text/plain;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='MAP-PRO-Inspeksi-'+report.started.replace(/[:.]/g,'-')+'.txt';document.body.appendChild(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
};
openAccount=function(){if(!liveMode())return demoHandlers.account();const panels=$('accountDialog').querySelectorAll('.account-panel');panels[0].querySelector('b').textContent=liveInfo?.name||'Nama belum terbaca';panels[0].querySelector('span').textContent=liveInfo?.subname||'Merchant asli';panels[0].querySelectorAll('span')[1].textContent='Status: '+(liveInfo?.state||'—');panels[1].querySelector('b').textContent='Lingkungan pengujian';panels[1].querySelector('small').textContent='Durasi langganan belum dihubungkan.';$('accountRunNote').textContent=liveInfo?.message||'Tidak ada transaksi otomatis dalam mode inspeksi.';$('accountDialog').showModal()};
logout=async function(){if(!liveMode())return demoHandlers.logout();if(commandBusy)return;commandBusy=true;try{await api('/logout','POST',{});cancelPolling();sessionToken='';liveBatchId='';liveInfo=null;running=false;document.querySelectorAll('dialog[open]').forEach(d=>d.close());batch=[];history=[];$('nikList').value='';go(false);toast('Browser merchant ditutup; sesi aplikasi dihapus.')}catch(e){toast(e.message)}finally{commandBusy=false}};
