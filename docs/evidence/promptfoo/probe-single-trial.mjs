import fs from 'node:fs';
import {evaluate} from 'promptfoo';
const provider={id:()=> 'local-single-synthetic',callApi:async()=>({output:'OK'})};
const tests=[{vars:{question:'easy'},metadata:{external_case_id:'easy'},assert:[{type:'equals',value:'OK'}]}];
const record=await evaluate({prompts:['{{question}}'],providers:[provider],tests,writeLatestResults:false,sharing:false,outputPath:'real-single-export.json'},{cache:false,maxConcurrency:1,showProgressBar:false});
const summary=await record.toEvaluateSummary();
console.log(JSON.stringify(summary.results.map(r=>({hasRepeatIndex:Object.hasOwn(r,'repeatIndex'),repeatIndex:r.repeatIndex,vars:r.vars,testCase:r.testCase,provider:r.provider,promptIdx:r.promptIdx,success:r.success,failureReason:r.failureReason,gradingResult:r.gradingResult})),null,2));
