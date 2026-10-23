export const date=(v:number|null)=>v?new Date(v*1000).toLocaleString('id-ID'):'—';
export const number=(v:number)=>v.toLocaleString('id-ID');
export const statusLabel=(v:string)=>({queued:'Antrean',running:'Berjalan',succeeded:'Berhasil',failed:'Gagal',cancelled:'Dibatalkan'}[v]??v);
