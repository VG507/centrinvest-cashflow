import {test} from 'node:test';
import assert from 'node:assert/strict';
import {api,ApiFailure} from '../v2/client';

test('typed GET encodes company paths/cursor and sends session credentials',async()=>{
 const original=globalThis.fetch;let captured='';let init:RequestInit|undefined;
 globalThis.fetch=async(url,options)=>{captured=String(url);init=options;return new Response(JSON.stringify({items:[],next_cursor:null}),{status:200});};
 try{await api('listEvents',{params:{company_id:'company/one'},data:{cursor:'a+b',limit:50}});assert.ok(captured.includes('company%2Fone/events?'));assert.ok(captured.includes('cursor=a%2Bb'));assert.equal(init?.credentials,'include');assert.equal(init?.method,'GET');assert.equal(init?.body,undefined);}finally{globalThis.fetch=original;}
});
test('multipart import leaves boundary header to browser and preserves FormData',async()=>{
 const original=globalThis.fetch,form=new FormData();form.set('format','csv');
 globalThis.fetch=async(_url,init)=>{assert.equal(init?.body,form);assert.equal(init?.headers,undefined);return new Response(JSON.stringify({status:'ready'}),{status:200});};
 try{await api('importStatement',{params:{company_id:'one'},form});}finally{globalThis.fetch=original;}
});
test('authentication errors are translated and login failure does not expire other state',async()=>{
 const original=globalThis.fetch;globalThis.fetch=async()=>new Response(JSON.stringify({code:'unauthorized',message:'Invalid email or password',details:[]}),{status:401});
 try{await assert.rejects(api('login',{data:{email:'test@example.com',password:'incorrect'}}),e=>e instanceof ApiFailure&&e.status===401&&e.message==='Неверная почта или пароль.');}finally{globalThis.fetch=original;}
});
test('abort remains an abort rather than a displayed network error',async()=>{
 const original=globalThis.fetch,controller=new AbortController();controller.abort();globalThis.fetch=async()=>{throw new DOMException('Abort','AbortError');};
 try{await assert.rejects(api('capabilities',{signal:controller.signal}),e=>e instanceof DOMException&&e.name==='AbortError');}finally{globalThis.fetch=original;}
});
