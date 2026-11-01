'use strict';
// Canonical decision rules -> five Skills + the portable knowledge projection.
const fs = require('node:fs'), path = require('node:path'), crypto = require('node:crypto');
const root = path.resolve(__dirname, '..');
const skills = ['lzheng-strength-training-review', 'lzheng-fitness-plan', 'lzheng-strength-cycle-planner', 'lzheng-training-return', 'lzheng-training-system'];
const relative = 'references/training-progression-protocol.md';
function safe(file) { for (let p=path.resolve(file);;p=path.dirname(p)) { if(fs.existsSync(p)&&fs.lstatSync(p).isSymbolicLink())throw Error('Linked destination: '+p);if(path.dirname(p)===p)break; } }
function sync({write=false, installedRoots=[]}={}) {
  const source=path.join(root,'skills',skills[0],relative);safe(source);
  // Git stores Markdown with LF, even when the maintainer's working copy has CRLF.
  const text=fs.readFileSync(source,'utf8').replace(/\r\n/g,'\n'), version=text.match(/^版本：(.+)$/m)?.[1];
  if(!version)throw Error('Missing training protocol version');
  const sha256=crypto.createHash('sha256').update(text).digest('hex');
  const targets=skills.slice(1).map(name=>({file:path.join(root,'skills',name,relative),data:text}));
  targets.push({file:path.join(root,'knowledge/training-progression.json'),data:JSON.stringify({version,sha256,text},null,2)+'\n'});
  for(const dir of installedRoots){if(!path.isAbsolute(dir))throw Error('Installed root must be absolute');for(const name of skills){const file=path.join(dir,name,relative);safe(file);if(!fs.existsSync(path.join(dir,name,'SKILL.md')))throw Error('Missing installed Skill: '+name);targets.push({file,data:text});}}
  targets.forEach(({file})=>safe(file));
  const drift=targets.filter(({file,data})=>!fs.existsSync(file)||fs.readFileSync(file,'utf8').replace(/\r\n/g,'\n')!==data);
  if(!write&&drift.length)throw Error('Training protocol drift: '+drift.map(x=>path.relative(root,x.file)).join(', '));
  if(write)for(const {file,data} of drift){fs.mkdirSync(path.dirname(file),{recursive:true});fs.writeFileSync(file,data);}
  return {version,sha256,checked:targets.length,updated:write?drift.length:0};
}
if(require.main===module){try{const args=process.argv.slice(2),installedRoots=[];let write=false;for(let i=0;i<args.length;i++){if(args[i]==='--write')write=true;else if(args[i]==='--check')write=false;else if(args[i]==='--installed-root'&&args[i+1])installedRoots.push(args[++i]);else throw Error('Usage: --check|--write [--installed-root absolute-path]');}console.log(JSON.stringify(sync({write,installedRoots})));}catch(e){console.error(e.message);process.exitCode=1;}}
module.exports={sync};
