import fs from 'node:fs';
import {evaluate} from 'promptfoo';
const tests=JSON.parse(fs.readFileSync('prospective-tests.json','utf8'));
for(const name of ['baseline','candidate']) {
  const provider={id:()=>`local-synthetic-${name}`,callApi:async(prompt)=>({output:name==='candidate'||prompt.includes('easy')?'OK':'NO'})};
  const evaluation=await evaluate({prompts:['{{question}}'],providers:[provider],tests,writeLatestResults:false,sharing:false,outputPath:`real-${name}-export.json`},{maxConcurrency:1,showProgressBar:false,cache:false});
  const summary=await evaluation.toEvaluateSummary();
  console.log(JSON.stringify({name,version:summary.version,rows:summary.results.length,scores:summary.results.map(r=>r.score)}));
}
