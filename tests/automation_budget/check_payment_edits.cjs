const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync(path.join(__dirname,'../../app/templates/automation/_budget_mockup.html'),'utf8');
const model=source.split('/* FB_MODEL_START */')[1].split('/* FB_MODEL_END */')[0];
const seed=source.slice(source.indexOf('const proposals='),source.indexOf('const state='));
const ctx=vm.createContext({});vm.runInContext(model+seed,ctx);
const fresh=()=>JSON.parse(vm.runInContext("JSON.stringify(proposals.find(p=>p.id==='p1000000'))",ctx));
const at='2026-11-10T16:00:00Z',reason='Corrección de prueba';
function rejected(p,fn){const before=JSON.stringify(p);assert.throws(fn);assert.equal(JSON.stringify(p),before,'A rejected edit must be atomic.');}
assert.equal(typeof ctx.editPayment,'function','Registered payments need an edit operation.');
assert.equal(typeof ctx.editItem,'function','Item edits need validated, auditable model behavior.');
{
  const p=fresh(),receipt=JSON.stringify(p.movements.find(m=>m.id==='million-expense-4').receipt);
  const event=ctx.editPayment(p,'million-expense-4',{date:'2026-10-28',category:'materials',item:'activities',amount:350000,concept:'Materiales corregidos'},'supervisor',reason,at);
  assert.equal(ctx.totals(p).available,66650000);assert.equal(ctx.used(p,'transport').paid,2100000);assert.equal(ctx.used(p,'materials').paid,2150000);
  assert.equal(ctx.monthReview(p,'2026-10').total.paidMonth,8700000);assert.equal(ctx.balanceAt(p,'2026-10-31').available,72580000);
  assert.equal(JSON.stringify(p.movements.find(m=>m.id==='million-expense-4').receipt),receipt);
  assert.equal(event.before.amount,400000);assert.equal(event.after.amount,350000);assert.equal(event.reason,reason);assert.equal(event.role,'supervisor');
  assert.equal(ctx.filteredPaymentEdits(p,{month:'2026-11',category:'transport'}).length,1);assert.equal(ctx.filteredPaymentEdits(p,{month:'2026-10',category:'materials'}).length,1);
  ctx.editPayment(p,'million-expense-4',{amount:300000},'admin','Segundo ajuste',at);assert.equal(event.after.amount,350000,'Earlier audit snapshots must not change.');
}
{
  const p=fresh(),id='million-payroll-partial';
  ctx.changePeriod(p,'2026-10','close','admin','',at);const snapshot=JSON.stringify(ctx.balanceAt(p,'2026-10-31'));
  ctx.editPayment(p,id,{amount:4000000,date:'2026-11-09',concept:'Anticipo corregido'},'admin',reason,at);
  assert.equal(ctx.totals(p).paid,23500000);assert.equal(ctx.totals(p).committed,9900000);assert.equal(ctx.totals(p).available,66600000);assert.equal(p.movements.find(m=>m.id==='million-payroll').pending,6000000);assert.equal(JSON.stringify(ctx.balanceAt(p,'2026-10-31')),snapshot);
  ctx.editPayment(p,id,{amount:10000000},'admin',reason,at);assert.equal(p.movements.find(m=>m.id==='million-payroll').pending,0);
  ctx.editPayment(p,id,{amount:5000000},'admin',reason,at);assert.equal(p.movements.find(m=>m.id==='million-payroll').pending,5000000);
  for(const changes of [{amount:10000001},{category:'transport',item:'trips'},{date:'2026-10-26'},{date:'2026-10-24'}])rejected(p,()=>ctx.editPayment(p,id,changes,'admin',reason,at));
}
{
  const p=fresh(),id='million-expense-7';
  for(const changes of [{amount:0},{amount:-1},{amount:1.5},{amount:NaN},{amount:999999999},{date:'2026-11-11'},{date:'2026-02-30'},{date:'2026-08-31'},{category:'unknown'},{item:'unknown'},{concept:'  '}])rejected(p,()=>ctx.editPayment(p,id,changes,'admin',reason,at));
  rejected(p,()=>ctx.editPayment(p,id,{amount:1},'viewer',reason,at));rejected(p,()=>ctx.editPayment(p,id,{amount:1},'admin',' ',at));rejected(p,()=>ctx.editPayment(p,id,{amount:1},'admin',reason,'bad'));
  rejected(p,()=>ctx.editPayment(p,'million-payroll',{amount:1},'admin',reason,at));
  ctx.changePeriod(p,'2026-10','close','admin','',at);
  rejected(p,()=>ctx.editPayment(p,'million-expense-5',{concept:'Cambiar septiembre'},'admin',reason,at));
  rejected(p,()=>ctx.editPayment(p,'million-expense-6',{date:'2026-11-10'},'admin',reason,at));
  rejected(p,()=>ctx.editPayment(p,id,{date:'2026-10-31'},'admin',reason,at));
  ctx.changePeriod(p,'2026-10','reopen','admin','Corregir octubre',at);ctx.editPayment(p,'million-expense-6',{amount:650000},'admin',reason,at);assert.equal(ctx.monthReview(p,'2026-10').total.paidMonth,8300000);
}
{
  const p={total:100000,categories:[{id:'a',name:'A',budget:10000,createdOn:'2026-09-01',items:[]},{id:'b',name:'B',budget:90000,createdOn:'2026-09-01',items:[]}],movements:[]};
  ctx.captureBudget(p,'2026-09-01');p.categories[0].budget=50000;p.categories[1].budget=50000;ctx.captureBudget(p,'2026-10-01');ctx.record(p,{id:'late',category:'a',kind:'expense',amount:20000,date:'2026-10-02',concept:'Luego de asignación'});
  rejected(p,()=>ctx.editPayment(p,'late',{date:'2026-09-15'},'admin',reason,at));
}
{
  const p=fresh(),before=JSON.stringify(ctx.totals(p)),october=JSON.stringify(ctx.balanceAt(p,'2026-10-31'));
  ctx.changePeriod(p,'2026-10','close','admin','',at);
  const event=ctx.editItem(p,'salary','benefits',{name:'Beneficios del personal',budget:19000000},'supervisor',reason,at);
  assert.equal(JSON.stringify(ctx.totals(p)),before);assert.equal(JSON.stringify(ctx.balanceAt(p,'2026-10-31')),october);assert.equal(event.before.budget,20000000);assert.equal(event.after.budget,19000000);assert.equal(event.reason,reason);
  for(const changes of [{budget:20100000},{budget:-1},{budget:1.5},{name:'Personal del programa'},{name:' '}])rejected(p,()=>ctx.editItem(p,'salary','benefits',changes,'admin',reason,at));
  rejected(p,()=>ctx.editItem(p,'salary','staff',{budget:19999999},'admin',reason,at));rejected(p,()=>ctx.editItem(p,'salary','benefits',{budget:18000000},'viewer',reason,at));rejected(p,()=>ctx.editItem(p,'salary','benefits',{budget:18000000},'admin',' ',at));
  p.monthLocks['2026-11']={closed:true};rejected(p,()=>ctx.editItem(p,'salary','benefits',{budget:18000000},'admin',reason,at));
}
console.log('PASS: direct payment edits, categories and months, preserved receipts, partial and fully paid commitments, atomic rejection, historical budget limits, closed periods and reopening, filtered audit, item names and budgets, permissions and reasons.');
