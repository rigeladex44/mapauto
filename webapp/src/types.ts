export type User={id:number;username:string;role:'admin'|'operator'|'viewer';active:boolean;expires_at:number|null};
export type Merchant={id:number;name:string;reference:string;authorized:boolean;active:boolean;filters:string[];stock:number|null;stock_at:number|null;stock_simulated:boolean};
export type Job={id:number;merchant_id:number;kind:string;status:string;simulated:boolean;quantity:number;created_at:number;updated_at:number;worker_id:string|null;result:string};
export type Worker={id:string;heartbeat:number;paused:boolean;online:boolean};
export type Audit={id:number;actor_id:number|null;action:string;target:string;created_at:number};
export type Summary={merchants:number;stock:number;available:number;jobs:number;running:number;demo_mode:boolean;live_integration:boolean};
export type System={telegram_notifications:boolean;telegram_configured:boolean;demo_mode:boolean;live_integration:boolean};
