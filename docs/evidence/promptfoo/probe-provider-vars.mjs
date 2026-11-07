import fs from 'node:fs';
import {evaluate} from 'promptfoo';
const contexts=[];
const provider={id:()=> 'local-injected-vars',callApi:async(prompt,context)=>{
 contexts.push({...context.vars});
 context.vars.injected_by_provider='changed';
 return {output:'OK'};
}};
const tests=[{vars:{question:'easy'},metadata:{external_case_id:'easy'},options:{repeat:2},assert:[{type:'equals',value:'OK'}]}];
const record=await evaluate({prompts:['{{question}}'],providers:[provider],tests,writeLatestResults:false,sharing:false,outputPath:'real-injected-vars-export.json'},{cache:false,maxConcurrency:1,showProgressBar:false});
const summary=await record.toEvaluateSummary();
console.log(JSON.stringify({contexts,exportedVars:summary.results.map(r=>r.vars),exportedTestCaseVars:summary.results.map(r=>r.testCase.vars)}));
