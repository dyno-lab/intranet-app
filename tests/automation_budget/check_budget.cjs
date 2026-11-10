const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const src=fs.readFileSync(path.join(__dirname,'../../app/templates/automation/_budget_mockup.html'),'utf8');
for(const m of src.matchAll(/<script[^>]*>([\s\S]*?)<\/script>/g))new vm.Script(m[1]);
assert(Buffer.byteLength(src)<1000000);assert(!src.includes('root.querySelector(\'#ab-demo-data\')'));
const model=src.split('/* FB_MODEL_START */')[1].split('/* FB_MODEL_END */')[0];
const seed=src.slice(src.indexOf('const proposals='),src.indexOf('const state='));
const ctx=vm.createContext({});vm.runInContext(model+seed+';globalThis.p=proposals[0]',ctx);
const p=ctx.p,t=ctx.totals(p);assert.equal(t.total,200000);assert.equal(t.allocated,190000);assert.equal(t.unallocated,10000);assert.equal(t.available,165000);
assert.throws(()=>ctx.checkCategory(p,'new',10001));ctx.checkCategory(p,'new',10000);
assert.throws(()=>ctx.checkCategory(p,'transport',59999));
assert.equal(ctx.room(p,p.categories[0],'trips'),15000);
assert.throws(()=>ctx.record(p,{category:'transport',item:'trips',kind:'expense',amount:15001,date:'2026-11-10',concept:'Límite'}),/supera el disponible/);
ctx.record(p,{id:'test',category:'transport',item:'trips',kind:'commitment',amount:5000,date:'2026-11-10',concept:'Reserva'});
const available=ctx.totals(p).available;ctx.pay(p,'test',2000,'payment-test');assert.equal(ctx.totals(p).available,available);assert.equal(p.movements.find(m=>m.id==='test').pending,3000);
assert.throws(()=>ctx.pay(p,'test',3001,'payment-excess'));
assert(!/\bimport\s*\(/.test(src),'Startup must not depend on a deferred chart module.');
assert(!/\bsrc\s*=/.test(src),'The mockup should not need external resources.');
for(const c of p.categories){const u=ctx.used(p,c.id);assert(u.paid+u.committed<=c.budget);assert(c.budget<=p.total);}
const clone=()=>JSON.parse(JSON.stringify(ctx.p));
const tx={id:'tx',from:'salary',to:'transport',fromItem:'',toItem:'trips',amount:10000,reason:'Más actividades',at:'2026-11-10T15:00:00Z'};
const before=JSON.stringify(p),beforeTotals=JSON.stringify(ctx.totals(p)),beforeExpenses=JSON.stringify(ctx.chartData(p).expenses);
for(const [entry,role] of [[tx,'viewer'],[{...tx,reason:'  '},'admin'],[{...tx,to:'salary'},'admin'],[{...tx,amount:80001},'admin'],[{...tx,fromItem:'trips'},'admin']]){
 assert.throws(()=>ctx.transfer(p,entry,role));assert.equal(JSON.stringify(p),before,'Rejected transfer must be atomic.');
}
const log=ctx.transfer(p,tx,'supervisor');
assert.equal(JSON.stringify(ctx.totals(p)),beforeTotals,'Redistribution must preserve every general total.');
assert.equal(JSON.stringify(ctx.chartData(p).expenses),beforeExpenses);
assert.equal(p.categories[0].budget,70000);assert.equal(p.categories[0].items[0].budget,50000);
assert.equal(log.fromBefore,80000);assert.equal(log.fromAfter,70000);assert.equal(log.toBefore,60000);assert.equal(log.toAfter,70000);assert.equal(log.reason,tx.reason);assert.equal(log.at,tx.at);
const q=clone(),original=JSON.stringify(q);assert.throws(()=>ctx.transfer(q,{...tx,from:'transport',to:'salary',fromItem:'trips',toItem:'',amount:20001},'admin'),/transferible/);assert.equal(JSON.stringify(q),original);
ctx.transfer(q,{...tx,from:'transport',to:'salary',fromItem:'trips',toItem:'',amount:20000},'admin');assert.equal(ctx.room(q,q.categories[0],'trips'),0);
const blank={total:200000,categories:[{id:'a',name:'A',budget:100000,items:[]}],movements:[]};
assert.equal(ctx.chartData(blank).history.length,0);assert.equal(ctx.chartData(blank).allocation.reduce((s,r)=>s+r.value,0),200000);
for(const date of ['', '2026-02-30','2026-11-11'])assert.throws(()=>ctx.record(blank,{id:'x',category:'a',kind:'expense',amount:100,date,concept:'X'}),/fecha/);
for(const [id,date,amount] of [['x','2026-11-03',500],['y','2026-10-12',300],['z','2026-11-03',200]])ctx.record(blank,{id,category:'a',kind:'expense',amount,date,concept:'Gasto'});
ctx.record(blank,{id:'reserve',category:'a',kind:'commitment',amount:9000,date:'2026-11-04',concept:'Reserva'});
assert.equal(JSON.stringify(ctx.chartData(blank).history),JSON.stringify([{date:'2026-10-12',amount:300,cumulative:300},{date:'2026-11-03',amount:700,cumulative:1000}]));
assert.equal(ctx.chartData(blank).expenses[0].value,1000);
const prev=ctx.totals(blank).available;ctx.pay(blank,'reserve',2500,'partial','2026-11-10');assert.equal(ctx.totals(blank).available,prev);assert.equal(ctx.chartData(blank).history.at(-1).cumulative,3500);
console.log('PASS: startup syntax, offline startup, allocations, spending limits, partial payments, transfer permissions and atomicity, category/sub-item balances, required reasons, date validation, sorted daily aggregation, charts exclude pending commitments.');

const large=vm.runInContext("proposals.find(p=>p.id==='p1000000')",ctx);
assert(large,'The million-dollar scenario must be selectable.');
assert.deepEqual(JSON.parse(JSON.stringify(ctx.totals(large))),{total:100000000,paid:24500000,committed:8900000,allocated:100000000,unallocated:0,available:66600000,categoryAvailable:66600000});
const expectedLarge=[['salary',600000,150000,50000,400000],['transport',100000,25000,10000,65000],['materials',80000,18000,12000,50000],['water',20000,4000,1000,15000],['electricity',40000,9000,3000,28000],['vehicle-rent',60000,15000,5000,40000],['rent',100000,24000,8000,68000]];
for(const [id,budget,paid,committed,available] of expectedLarge){
  const c=large.categories.find(c=>c.id===id),u=ctx.used(large,id);
  assert.equal(c.budget,budget*100);assert.equal(u.paid,paid*100);assert.equal(u.committed,committed*100);assert.equal(c.budget-u.paid-u.committed,available*100);
  assert(c.items.reduce((n,i)=>n+i.budget,0)<=c.budget);
  for(const i of c.items)assert(ctx.room(large,c,i.id)>=0);
}
assert.equal(ctx.balanceAt(large,'2026-09-30').available,91280000);
const octoberLarge=ctx.monthReview(large,'2026-10');
assert.equal(octoberLarge.total.paidMonth,8350000);assert.equal(octoberLarge.total.paidCumulative,17070000);assert.equal(octoberLarge.total.committed,10000000);assert.equal(octoberLarge.total.available,72930000);assert.equal(octoberLarge.total.missingCount,3);assert.equal(octoberLarge.total.missingAmount,1920000);
assert.equal(ctx.monthReview(large,'2026-11').total.paidMonth,7430000);
assert.equal(ctx.monthReview(large,'2026-11').total.missingAmount,300000);
assert.equal(ctx.chartData(large).allocation.reduce((n,r)=>n+r.value,0),100000000);
assert.equal(ctx.chartData(large).expenses.reduce((n,r)=>n+r.value,0),24500000);
const currentLarge=ctx.totals(large).available;
ctx.pay(large,'million-payroll',100000,'million-next-payment','2026-11-10');
assert.equal(ctx.totals(large).available,currentLarge,'Partial payroll payments must not reduce availability twice.');
assert.equal(ctx.balanceAt(large,'2026-10-31').available,72930000,'Later payments must preserve the October cutoff.');
console.log('PASS: $1,000,000 assigned to seven categories, 21 payments, 7 pending commitments, monthly balances and missing receipts, historical transfer and payroll partial payment.');
