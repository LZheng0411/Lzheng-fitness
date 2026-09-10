// Exercise the actual inline helper, including cross-week and mixed-event inputs.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const targets=process.argv.slice(2);
if(!targets.length)targets.push(path.join(__dirname,'../skills/lzheng-fitness-workbench-builder/assets/workbench-template.html'));
for(const target of targets){
 const html=fs.readFileSync(target,'utf8'),start=html.indexOf('  function patchTrainingDates(');
 assert(start>=0);const end=html.indexOf('\n  }',start)+5,ctx=vm.createContext({});vm.runInContext(html.slice(start,end),ctx);
 const original={A:{date:'2030-01-08',exercises:[{name:'示例动作',w:'20kg',sets:3}],schedule_status:'scheduled'},B:{date:'2030-01-10',extra:'unchanged'}};
 const events=[{date:'2030-01-01',type:'training',day:'A',status:'done',record:'past'},{date:'2030-01-08',type:'training',day:'A',status:'planned',detail:{prescription:'keep'}},{date:'2030-01-09',type:'recovery',title:'休息',extra:'restore me'},{date:'2030-01-09',type:'cardio',title:'步行',minutes:20},{date:'2030-01-10',type:'training',day:'B',status:'planned'},{date:'2030-01-15',type:'training',day:'A',status:'planned',extra:'future'}];
 const clone=x=>JSON.parse(JSON.stringify(x)),plain=x=>JSON.parse(JSON.stringify(x));
 const before=JSON.stringify({events,original}),next=clone(original);next.A.date='2030-01-09';
 const after=plain(ctx.patchTrainingDates(events,original,next));
 assert.deepEqual(after.filter(e=>!['2030-01-08','2030-01-09'].includes(e.date)),events.filter(e=>!['2030-01-08','2030-01-09'].includes(e.date)));
 assert.deepEqual(after.find(e=>e.date==='2030-01-09'&&e.type==='training'),{...events[1],date:'2030-01-09'});
 assert.deepEqual(after.find(e=>e.type==='cardio'),events[3]);assert.equal(after.find(e=>e.date==='2030-01-08').title,'未排期');
 assert.deepEqual(plain(ctx.patchTrainingDates(events,original,original)),events);
 const deferred=clone(original);deferred.A.date=null;
 assert.equal(ctx.patchTrainingDates(events,original,deferred).filter(e=>e.type==='training').length,3);
 assert.deepEqual(plain(ctx.patchTrainingDates(events,original,original)),events,'undo uses the exact original snapshots');
 const collision=clone(original);collision.A.date='2030-01-15';assert.throws(()=>ctx.patchTrainingDates(events,original,collision),/已有训练/);
 assert.equal(JSON.stringify({events,original}),before,'inputs must never mutate, including after conflict');
 console.log('SCHEDULE_DATE_PATCH: PASS '+path.basename(target));
}
