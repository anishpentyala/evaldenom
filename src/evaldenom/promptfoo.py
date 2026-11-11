"""Experimental narrow offline Promptfoo JSON API.

Exact current SDK summary v3, explicit provider/prompt selection, repeated runs.
Input identity is (resolved vars, resolved assertions). No model/provider attestation.
Caller grader label is an explicit claim, just as in the core export contract.
"""
from .core import InputError, input_digest, freeze, _number

def rows_from_summary(summary,*,provider_id,prompt_index,grader):
    if not isinstance(summary,dict) or type(summary.get('version')) is not int or summary['version']!=3:
        raise InputError('only summary schema3 is supported in this probe')
    if not isinstance(summary.get('results'),list):raise InputError('missing results list')
    if not isinstance(provider_id,str) or not provider_id or type(prompt_index) is not int or prompt_index<0 or not isinstance(grader,str) or not grader:
        raise InputError('explicit provider, prompt index and grader required')
    selected=[];excluded=0
    for line,r in enumerate(summary['results'],1):
        if not isinstance(r,dict) or not isinstance(r.get('provider'),dict) or not isinstance(r['provider'].get('id'),str) or type(r.get('promptIdx')) is not int:
            raise InputError('unusable export row identity')
        if r['provider']['id']!=provider_id or r['promptIdx']!=prompt_index:
            excluded+=1;continue
        test=r.get('testCase')
        if not isinstance(test,dict) or not isinstance(test.get('metadata'),dict):raise InputError('missing external metadata identity')
        ident=test['metadata'].get('external_case_id')
        if not isinstance(ident,str) or not ident:raise InputError('missing external metadata identity')
        repeat=r.get('repeatIndex')
        if type(repeat) is not int or repeat<0:raise InputError('explicit zero-based repeatIndex required')
        if not isinstance(r.get('vars'),dict) or not isinstance(test.get('assert'),list) or not test['assert']:raise InputError('resolved vars and assertions required')
        reason=r.get('failureReason')
        if type(reason) is not int or reason not in (0,1,2):raise InputError('unknown failure reason')
        if type(r.get('success')) is not bool or (reason==0)!=r['success']:raise InputError('contradictory success/failure reason')
        metric={'status':'error' if reason==2 else 'ok','grader':grader,'direction':'higher'}
        if reason!=2:
            # Assertion failures can carry error text and score0. Provider errors
            # remain errors even with stale numeric scores.
            g=r.get('gradingResult')
            if (not isinstance(g,dict) or type(g.get('pass')) is not bool
                    or g['pass']!=r['success'] or not _number(g.get('score'))
                    or not _number(r.get('score'))
                    or g['score']!=r.get('score')):
                raise InputError('missing or contradictory aggregate grading evidence')
            metric['value']=r.get('score')
        identity={'vars':r['vars'],'assert':test['assert']}
        selected.append((line,{'id':ident,'trial':repeat+1,'input_digest':input_digest(identity),'metrics':{'aggregate':metric}}))
    if not selected:raise InputError('explicit selection matched no observations')
    return {'rows':selected,'selection':{'provider_id':provider_id,'prompt_index':prompt_index},'source_records':len(summary['results']),'excluded_by_explicit_selection':excluded}


def manifest_from_inline_tests(tests, *, grader):
    """Prospective narrow inline-test plan. Call BEFORE evaluate, not on exports.

    Only scalar vars, literal equals/contains assertions and options.repeat are
    supported. No file refs, defaultTest, scenarios, transforms or generators.
    This is a prototype, not a general Promptfoo configuration resolver.
    """
    if not isinstance(tests,list) or not tests:
        raise InputError('nonempty prospective inline tests required')
    if not isinstance(grader,str) or not grader:
        raise InputError('explicit grader required')
    rows=[]
    intended_observations=0
    for line,test in enumerate(tests,1):
        if not isinstance(test,dict) or set(test)-{'vars','assert','metadata','description','options'}:
            raise InputError('unsupported inline test field')
        if not isinstance(test.get('metadata'),dict):
            raise InputError('explicit external case identity required')
        ident=test['metadata'].get('external_case_id')
        if not isinstance(ident,str) or not ident:
            raise InputError('explicit external case identity required')
        variables=test.get('vars')
        if not isinstance(variables,dict) or any(type(v) not in (str,int,float,bool,type(None)) for v in variables.values()):
            raise InputError('only non-expanding scalar vars supported')
        assertions=test.get('assert')
        if not isinstance(assertions,list) or not assertions:
            raise InputError('explicit literal assertions required')
        for assertion in assertions:
            if (not isinstance(assertion,dict) or set(assertion)!={'type','value'}
                    or assertion['type'] not in ('equals','contains')
                    or not isinstance(assertion['value'],str)
                    or 'file://' in assertion['value'] or '{{' in assertion['value'] or '{%' in assertion['value']):
                raise InputError('only literal equals/contains assertions supported')
        options=test.get('options')
        if not isinstance(options,dict) or set(options)!={'repeat'}:
            raise InputError('explicit per-test repeat only; no options inheritance')
        count=options['repeat']
        if type(count) is not int or count<2:
            raise InputError('prototype requires repeat at least 2; single trials lack exported repeatIndex')
        intended_observations+=count
        if intended_observations>100000:
            raise InputError('prototype supports at most 100000 intended observations')
        rows.append((line,{'id':ident,'input':{'vars':variables,'assert':assertions},'trials':list(range(1,count+1))}))
    return freeze(rows,[{'name':'aggregate','grader':grader,'direction':'higher','min':0,'max':1}])


def summary_from_json_export(value):
    """Read the current on-disk JSON wrapper, without inferring older formats."""
    if not isinstance(value,dict) or not isinstance(value.get('evalId'),str) or not isinstance(value.get('results'),dict):
        raise InputError('expected pinned Promptfoo JSON export wrapper')
    summary=value['results']
    if type(summary.get('version')) is not int or summary['version']!=3:
        raise InputError('expected nested summary schema3')
    return summary


def audit_promptfoo_exports(manifest, exports, selections):
    """Audit explicitly selected provider/prompt slices from current JSON exports.

    exports maps run labels to parsed JSON wrapper objects, NOT filenames.
    selections maps the identical labels to provider_id, prompt_index and grader.
    Selection is deliberate and visible; never represented as whole-export audit.
    """
    if (not isinstance(exports,dict) or len(exports)<2
            or not isinstance(selections,dict) or set(exports)!=set(selections)):
        raise InputError('at least two exports with exactly matching selections required')
    runs={}
    provenance={}
    for name,value in exports.items():
        selection=selections[name]
        if not isinstance(selection,dict) or set(selection)!={'provider_id','prompt_index','grader'}:
            raise InputError('each explicit selection needs provider_id, prompt_index and grader')
        converted=rows_from_summary(summary_from_json_export(value),**selection)
        runs[name]=converted['rows']
        provenance[name]={
            'format':'promptfoo-0.125.1-json-summary-v3',
            'selection':dict(selection),
            'source_records':converted['source_records'],
            'selected_records':len(converted['rows']),
            'excluded_by_explicit_selection':converted['excluded_by_explicit_selection'],
        }
    from .core import audit
    report=audit(manifest,runs)
    report['source_adapters']=provenance
    report['limitations']=[
        'Only the explicitly selected provider/prompt slice in each export is audited; other rows are excluded with counts.',
        'Input identity binds exported vars and literal assertion definitions, not prompts, provider settings or model execution.',
        'Grader labels are caller claims. An aggregate score is not per-assertion evaluator attestation.',
        'Prospective inline-test freeze is valid only if those exact tests are executed without inherited defaults, transformations or expansion.',
    ]+[item.replace('No rows are selected, averaged, dropped, retried or rewritten.',
        'Within each selected slice, no rows are averaged, dropped, retried or rewritten.') for item in report['limitations']]
    return report


def manifest_from_inline_tests_text(text, *, grader):
    """Strict JSON text entry point. Repeated members/NaN never last-win."""
    from .core import loads
    if not isinstance(text,str):
        raise InputError('prospective plan must be UTF-8 decoded JSON text')
    return manifest_from_inline_tests(loads(text),grader=grader)


def audit_promptfoo_export_texts(manifest_text, export_texts, selections):
    """Strict text boundary for untrusted files, before any dict conversion.

    The object-level helpers cannot recover repeated JSON members lost by a
    caller's parser. File callers should read UTF-8 text and use this function.
    """
    from .core import loads
    if (not isinstance(manifest_text,str) or not isinstance(export_texts,dict)
            or any(not isinstance(text,str) for text in export_texts.values())):
        raise InputError('manifest and exports must be UTF-8 decoded JSON text')
    return audit_promptfoo_exports(loads(manifest_text),
        {label:loads(text) for label,text in export_texts.items()},selections)
