import fs from 'node:fs';
import {evaluate} from 'promptfoo';
const provider={id:()=> 'local-fixed-synthetic', callApi:async(prompt)=>{
  if(prompt.includes('broken'))return {error:'synthetic local provider failure'};
  return {output:prompt.includes('easy')?'OK':'NO'};
}};
const evaluation=await evaluate({
  prompts:['{{question}}'], providers:[provider],
  tests:JSON.parse(fs.readFileSync('prospective-tests.json','utf8')),writeLatestResults:false,sharing:false,outputPath:['real-sdk-export.json','real-sdk-export.jsonl'],
},{maxConcurrency:1,showProgressBar:false,cache:false});
const summary=await evaluation.toEvaluateSummary();
fs.writeFileSync('real-local-summary.json',JSON.stringify(summary,null,2)+'\n');
console.log(JSON.stringify(summary.results.map(r=>({testIdx:r.testIdx,promptIdx:r.promptIdx,repeatIndex:r.repeatIndex,repeatGroupId:r.repeatGroupId,vars:r.vars,failureReason:r.failureReason,success:r.success,score:r.score,error:r.error,testCase:r.testCase,gradingResult:r.gradingResult})),null,2));
