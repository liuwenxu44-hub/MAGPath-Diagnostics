"""Reconcile supplied evidence. A match is not third-party authentication."""
from pathlib import Path
import re


def _text(value):
    return isinstance(value, str) and bool(value.strip())


def receipt_relation(receipt, files, spec, exit_code):
    """Return result association, inventory detail and discrepancies; never alter numerical fields."""
    byrole = {f['role']: f for f in files}
    src = byrole.get('source')
    issues, matches, claimed = [], [], []
    def issue(code, where, reason, severity='ERROR'):
        issues.append(dict(code=code, location=where, details=reason, dimension='process', severity=severity))
    def compare(where, expected, actual, bind=False):
        if not isinstance(expected, str) or not re.fullmatch(r'[0-9a-fA-F]{64}', expected):
            issue('INVALID_RECEIPT_DIGEST', where, 'Expected a SHA-256 digest.')
        elif actual and expected.lower() != actual['sha256']:
            issue('RECEIPT_EVIDENCE_CONFLICT', where, dict(receipt=expected.lower(), supplied=actual['sha256'], role=actual['role']))
        elif actual:
            if bind: matches.append(where)
            claimed.append(where)
    if not isinstance(receipt, dict):
        return dict(status='NOT_VERIFIABLE', matched_source_fields=[], checked_claims=[]), []
    if 'source_sha256' in receipt:
        compare('receipt.source_sha256',receipt['source_sha256'],src,True)
    outputs=receipt.get('artifacts',[])
    if not isinstance(outputs,list):
        issue('INVALID_RECEIPT_ARTIFACT_LIST','receipt.artifacts','Expected a list.')
        outputs=[]
    seen=set()
    required=[v for k,v in byrole.items() if k.startswith('process.required_artifacts[')]
    # Only exact logical filenames or standard native source roles identify the selected table.
    logical={Path(src['path']).name} if src else set()
    if spec.get('adapter')=='AMBER_RESULTS_V2_0_8': logical.add('results.tsv')
    for i,d in enumerate(outputs):
        loc=f'receipt.artifacts[{i}]'
        if not isinstance(d,dict) or not _text(d.get('name')):
            issue('INVALID_RECEIPT_ARTIFACT',loc,'Missing logical artifact name.');continue
        key=d['name']
        if key in seen:issue('DUPLICATE_RECEIPT_ARTIFACT',loc,key)
        seen.add(key)
        if key in logical:compare(loc,d.get('sha256'),src,True)
        for supplied in required:
            if Path(supplied['path']).name==key and supplied.get('path')!=(src or {}).get('path'):
                compare(loc,d.get('sha256'),supplied)
    inputs=receipt.get('input_sha256',{})
    if not isinstance(inputs,dict):issue('INVALID_RECEIPT_INPUTS','receipt.input_sha256','Expected a filename-to-digest object.')
    else:
        for role,actual in byrole.items():
            if not role.startswith('witnesses.'):continue
            name=Path(actual['path']).name
            if name in inputs:compare('receipt.input_sha256.'+name,inputs[name],actual)
    if spec.get('adapter')=='AMBER_RESULTS_V2_0_8' and 'minimum_length' in receipt:
        val=receipt['minimum_length'];actual=spec.get('minimum_length',0)
        if isinstance(val,bool) or not (isinstance(val,int) and val>=0):
            issue('INVALID_RECEIPT_MINIMUM_LENGTH','receipt.minimum_length',val)
        elif isinstance(actual,bool) or str(val)!=str(actual):
            issue('RECEIPT_EVIDENCE_CONFLICT','receipt.minimum_length',dict(receipt=val,supplied=actual))
        else:claimed.append('receipt.minimum_length')
    if src and 'results_tsv_present' in receipt and receipt['results_tsv_present'] is not True:
        issue('RECEIPT_EVIDENCE_CONFLICT','receipt.results_tsv_present',dict(receipt=receipt['results_tsv_present'],supplied=True))
    listed=receipt.get('required_artifacts',[])
    if not isinstance(listed,list) or not all(_text(v) for v in listed):
        issue('INVALID_RECEIPT_REQUIRED_LIST','receipt.required_artifacts','Expected logical names.')
    else:
        supplied_names={Path(a['path']).name for a in required}
        for name in listed:
            if name not in supplied_names:
                issue('RECEIPT_REQUIRED_OUTPUT_NOT_WITNESSED','receipt.required_artifacts',name,'INSUFFICIENT_EVIDENCE')
            presence={'index.html':'index_html_present','results.tsv':'results_tsv_present'}.get(name)
            if presence in receipt and receipt[presence] is False:
                issue('RECEIPT_REPORTS_MISSING_REQUIRED_OUTPUT','receipt.'+presence,name)
    # A receipt honestly recording a missing HTML report is evidence of
    # incompleteness, not evidence that its source association is contradictory.
    contradicted=any(x['severity']=='ERROR' and x['code']!='RECEIPT_REPORTS_MISSING_REQUIRED_OUTPUT' for x in issues)
    bound=bool(matches) and src is not None and src['hash_status']=='MATCH' and byrole.get('process.receipt',{}).get('hash_status')=='MATCH'
    if not bound and not contradicted:
        issue('RECEIPT_RESULT_LINK_UNVERIFIED','receipt.source_result',
              'Exit and supplied inventory are observable; this receipt does not bind the selected results bytes.','INSUFFICIENT_EVIDENCE')
    return dict(status='CONTRADICTORY' if contradicted else 'MATCHED_SUPPLIED_RESULT_BYTES' if bound else 'NOT_VERIFIABLE',
                matched_source_fields=matches,checked_claims=claimed,recorded_exit_code=exit_code),issues


def comparison_plan(ls,rs):
    """Display labels are never evidence of submission identity or comparison intent."""
    valid={'REPLAY_SAME_SUBMISSION','COMPARE_PREDICTIONS'}
    plans=[s.get('comparison',{}) if isinstance(s,dict) else {} for s in (ls,rs)]
    if not all(isinstance(c,dict) for c in plans): return 'CONFLICTING_OR_INVALID',None
    a,b=plans
    ids=[c.get('submission_id') for c in plans]
    purposes=[c.get('purpose') for c in plans]
    if any(i is not None and not _text(i) for i in ids):return 'CONFLICTING_OR_INVALID',ids
    if any(p is not None for p in purposes):
        if not all(isinstance(p,str) and p in valid for p in purposes) or purposes[0]!=purposes[1]:return 'CONFLICTING_OR_INVALID',ids
        if purposes[0]=='REPLAY_SAME_SUBMISSION' and all(ids) and ids[0]!=ids[1]:return 'CONFLICTING_OR_INVALID',ids
        return purposes[0],ids
    if all(ids):
        return ('REPLAY_SAME_SUBMISSION' if ids[0]==ids[1] else 'COMPARE_PREDICTIONS'),ids
    return 'UNSPECIFIED',ids


def sample_relation(left,right,la,ra,base_l,base_r,loader):
    names=[s.get('selector',{}).get('Sample') if isinstance(s,dict) and isinstance(s.get('selector'),dict) else None for s in (left,right)]
    result=dict(left=names[0],right=names[1],relation='UNRESOLVED',crosswalk_sha256=None)
    if not all(_text(n) for n in names):return result
    if names[0]==names[1]:
        result['relation']='SAME_NATIVE_ID';return result
    # A shared crosswalk is an explicit caller-supplied correspondence, not proof of common origin.
    loaded=[]
    for s,base in ((left,base_l),(right,base_r)):
        d=s.get('sample_crosswalk')
        if d is None:return result
        wrapper={'source_files':[],'issues':[]}
        obj,ident=loader(d,'sample_crosswalk',base,wrapper,'json')
        if wrapper['issues'] or not ident or ident.get('hash_status')!='MATCH' or not isinstance(obj,dict):return result
        loaded.append((obj,ident['sha256']))
    (obj,h),(_,other)=loaded
    scope_keys=('dataset_id','family_id','assembly_id')
    ids=obj.get('sample_ids')
    if (h==other and _text(obj.get('canonical_sample_id')) and isinstance(ids,list)
            and all(_text(i) for i in ids) and len(ids)==len(set(ids)) and all(i in ids for i in names)
            and all(_text(obj.get(k)) and obj[k]==la.get(k)==ra.get(k) for k in scope_keys)):
        result.update(relation='EXPLICIT_SUPPLIED_ALIAS',crosswalk_sha256=h,canonical_sample_id=obj['canonical_sample_id'])
    return result
