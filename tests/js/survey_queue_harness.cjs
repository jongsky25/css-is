// Execute the actual service-worker queue handler with deterministic network/IDB seams.
const fs = require('fs');
const vm = require('vm');
async function run(mode) {
  let rows = [{id:'attempt', action:mode.startsWith('combined') ? '/seq' : '/r/public', body:'submission_id=attempt', draftKey:'device-key', draftRevision:'revision', status:'pending'}];
  let calls = 0, messages = [];
  const sandbox = {URL, self:{location:{origin:'https://survey.test'}, addEventListener(){}, clients:{matchAll:async()=>[{postMessage:m=>messages.push(m)}]}},
    fetch:async(action,options)=>{
      calls++;
      if (options.headers.Accept !== 'application/json') throw new Error('Missing receipt negotiation');
      if (mode === 'network') throw new Error('Lost response');
      return {ok:!['refused','server'].includes(mode), status:mode==='refused'?403:mode==='server'?503:200,
        json:async()=>{
          if (mode === 'html') throw new Error('Not JSON');
          if (mode === 'wrong') return {ok:true,submission_id:'different'};
          if (mode === 'combined-partial') return {ok:true,submission_id:'attempt',recorded:1,unavailable:1};
          if (mode === 'combined-previous') return {ok:true,submission_id:'attempt',deduped:true};
          return {ok:true,submission_id:'attempt'};
        }};
    }};
  vm.createContext(sandbox);
  vm.runInContext(fs.readFileSync('static/js/sw.js','utf8'),sandbox);
  sandbox.qStore=async()=>({getAll:()=>({result:rows}),delete:id=>{rows=rows.filter(row=>row.id!==id)},put:row=>{rows=[row]}});
  sandbox.qReq=async request=>request.result;
  await sandbox.flushQueue();
  return {rows,calls,messages};
}
(async()=>{
  const results={};
  for (const mode of ['confirmed','html','wrong','network','refused','server','combined-partial','combined-previous','combined-malformed']) results[mode]=await run(mode);
  process.stdout.write(JSON.stringify(results));
})().catch(error=>{process.stderr.write(String(error));process.exit(1)});
