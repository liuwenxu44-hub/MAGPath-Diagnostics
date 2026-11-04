"""External post-hoc evaluation-alignment diagnostics; no fitting or tool execution."""
from __future__ import annotations
import argparse, csv, hashlib, itertools, json, math
from collections import Counter, defaultdict
from decimal import Decimal
from fractions import Fraction
from pathlib import Path

EVIDENCE_ROLE='POSTHOC_EXPLANATORY_ANALYSIS'
FAMILIES=('marine','strain_madness','plant_associated')
REASON_STATUS={'EXPLICIT':'ASSIGNED','EXPLICIT_BIN':'ASSIGNED','EXPLICIT_UNBINNED':'UNBINNED',
 'OMITTED_UNKNOWN_REASON':'TOOL_ABSTAIN','TOOL_ABSTAIN':'TOOL_ABSTAIN',
 'HARD_FAIL_INVALID_OUTPUT':'HARD_FAIL_INVALID_OUTPUT','INVALID_OUTPUT':'HARD_FAIL_INVALID_OUTPUT'}

def finite_decimal(value):
 if value is None or value=='NA':raise ValueError('SCORE_UNAVAILABLE')
 if isinstance(value,bool):raise ValueError('INVALID_SCORE')
 try:out=Decimal(str(value))
 except Exception as exc:raise ValueError('INVALID_SCORE') from exc
 if not out.is_finite():raise ValueError('NONFINITE_NUMBER')
 return out

def read_tsv(path):
 with Path(path).open(newline='',encoding='utf-8') as f:
  reader=csv.DictReader(f,delimiter='\t'); rows=list(reader)
  if not reader.fieldnames or len(set(reader.fieldnames))!=len(reader.fieldnames): raise ValueError('INVALID_HEADER')
  if any(None in r or None in r.values() for r in rows): raise ValueError('INVALID_TSV_WIDTH')
 return rows

def write_tsv(path,rows,fields=None):
 rows=list(rows)
 with Path(path).open('x',newline='',encoding='utf-8') as f:
  w=csv.DictWriter(f,fieldnames=fields or list(rows[0]),delimiter='\t',lineterminator='\n');w.writeheader();w.writerows(rows)

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()

def grouped_brier(masses,unknown,targets,scale=1):
 masses={k:Fraction(v) for k,v in masses.items()}; u=Fraction(unknown);s=Fraction(scale)
 if s<=0 or u<0 or any(v<0 for v in masses.values()) or sum(masses.values())+u!=s: raise ValueError('INVALID_SIMPLEX')
 if not targets or '__UNKNOWN__' in targets: raise ValueError('INVALID_TARGET')
 good=sum(masses.get(k,0) for k in targets)
 return ((good-s)**2+sum(v*v for k,v in masses.items() if k not in targets)+u*u)/(s*s)

def event_binary_brier(p,correct):
 p=Fraction(p)
 if not 0<=p<=1 or correct not in (0,1): raise ValueError('INVALID_EVENT')
 return (p-correct)**2+(1-p-(1-correct))**2

def expected_restricted_loss(p,q):
 p,q=Fraction(p),Fraction(q)
 if not 0<=p<=1 or not 0<=q<=1: raise ValueError('INVALID_PROBABILITY')
 return 2*p*p-2*(1+q)*p+2

def probability_diagnostic(q):
 q=Fraction(q); pstar=(1+q)/2
 return {'q':str(q),'calibrated_p':str(q),'hard_p':'1','restricted_optimal_p':str(pstar),
 'loss_at_q':str(expected_restricted_loss(q,q)),'loss_at_1':str(expected_restricted_loss(1,q)),
 'loss_at_restricted_optimum':str(expected_restricted_loss(pstar,q)),
 'binary_event_loss_at_q':str(q*event_binary_brier(q,1)+(1-q)*event_binary_brier(q,0)),
 'binary_event_loss_at_1':str(2*(1-q)),'evidence_role':EVIDENCE_ROLE}

def ranks(values):
 values={k:finite_decimal(v) for k,v in values.items()}
 return {k:1+sum(v>x for v in values.values()) for k,x in values.items()}

def pair_statistics(a,b):
 if a.keys()!=b.keys():raise ValueError('UNPAIRED_SUBMISSION_SET')
 a={k:finite_decimal(v) for k,v in a.items()};b={k:finite_decimal(v) for k,v in b.items()}
 pairs=[]; counts=Counter()
 for l,r in itertools.combinations(sorted(a),2):
  da,db=a[l]-a[r],b[l]-b[r]
  kind=('BOTH_TIE' if da==0 and db==0 else 'P01_TIE_ONLY' if da==0 else 'P05_TIE_ONLY' if db==0 else 'STRICT_REVERSAL' if da*db<0 else 'CONCORDANT')
  counts[kind]+=1;pairs.append({'left':l,'right':r,'pair_state':kind})
 c,d=counts['CONCORDANT'],counts['STRICT_REVERSAL'];ta,tb=counts['P01_TIE_ONLY'],counts['P05_TIE_ONLY']
 den=math.sqrt((c+d+ta)*(c+d+tb))
 return {'total_pairs':len(pairs),'non_tie_pairs_both_policies':c+d,'strict_reversals':d,'concordant_pairs':c,'tie_changes':ta+tb,'both_ties':counts['BOTH_TIE'],'tau_b':(c-d)/den if den else 'NOT_ESTIMABLE'},pairs

def panel_analysis(metrics,panel):
 if any(r['family_id'] not in FAMILIES for r in panel):raise ValueError('UNDECLARED_FAMILY_USE_PORTABLE_INTERFACE')
 if any(r['family_id'] not in FAMILIES or r['policy_id'] not in ('P01','P05') for r in metrics):raise ValueError('UNDECLARED_FAMILY_OR_POLICY_USE_PORTABLE_INTERFACE')
 panel=[r for r in panel if r['family_id'] in FAMILIES]
 identities={(r['family_id'],r['submission_id']):r for r in panel}
 if len(identities)!=len(panel):raise ValueError('DUPLICATE_SUBMISSION_ID')
 methods={f:{r['method_name'] for r in panel if r['family_id']==f} for f in FAMILIES}
 common=set.intersection(*methods.values())
 summaries=[];pair_rows=[];score_rows=[];subset_checks=[];version_rows=[];denoms=[]
 for family in FAMILIES:
  info={sid:r for (f,sid),r in identities.items() if f==family}
  reps={min(s for s in info if info[s]['method_name']==m) for m in methods[family]}
  if reps!={s for s,r in info.items() if r['method_representative']=='YES'}:raise ValueError('REPRESENTATIVE_RULE_DRIFT')
  common_ids={s for s in reps if info[s]['method_name'] in common}
  bypolicy={p:{} for p in ('P01','P05')}
  for r in metrics:
   if r['family_id']!=family or r['policy_id'] not in bypolicy:continue
   if r['submission_id'] in bypolicy[r['policy_id']]:raise ValueError('DUPLICATE_METRIC')
   if r['matching_policy']!='SPLIT_TOLERANT_MANY_TO_ONE' or r['weighting_policy']!='BASE_PAIR_WEIGHTED' or r['truth_policy']!='STRICT_SINGLETON_ONLY':raise ValueError('POLICY_IDENTITY_DRIFT')
   d=finite_decimal(r['denominator_weight']); correct=finite_decimal(r['compatible_correct_weight'])
   if d<=0 or not 0<=correct<=d:raise ValueError('INVALID_SCORE_DENOMINATOR')
   expected=2*correct/(d+correct)
   if abs(expected-finite_decimal(r['policy_score']))>Decimal('1e-15'):raise ValueError('SCORE_ARITHMETIC_MISMATCH')
   bypolicy[r['policy_id']][r['submission_id']]=r
  if any(set(x)!=set(info) for x in bypolicy.values()):raise ValueError('INCOMPLETE_POLICY_PANEL')
  for p,records in bypolicy.items():
   ds={r['denominator_weight'] for r in records.values()}
   if len(ds)!=1:raise ValueError('INCONSISTENT_DENOMINATOR_WITHIN_PANEL')
   denoms.append({'family':family,'policy':p,'denominator_bp':next(iter(ds)),'denominator_origin':'ORIGINAL_FULL_SUBMISSION_INTERSECTION' if p=='P05' else 'COMPLETE_TRUTH','recomputed_for_subset':'NO','evidence_role':EVIDENCE_ROLE})
  panels={'A_FULL_SUBMISSION':set(info),'B_METHOD_REPRESENTATIVE':reps,'C_COMMON_METHOD':common_ids}
  for label,ids in panels.items():
   vals={p:{s:Decimal(records[s]['policy_score']) for s in ids} for p,records in bypolicy.items()}
   stats,pairs=pair_statistics(vals['P01'],vals['P05'])
   summaries.append({'family':family,'panel':label,'methods':len({info[s]['method_name'] for s in ids}),'method_version_identities':len({(info[s]['method_name'],info[s]['method_version']) for s in ids}),'submissions':len(ids),**stats,'evidence_role':EVIDENCE_ROLE})
   rr={p:ranks(v) for p,v in vals.items()}
   for s in sorted(ids):
    for p in bypolicy:
     row=bypolicy[p][s]
     score_rows.append({'family':family,'panel':label,'policy':p,'submission':s,'method':info[s]['method_name'],'version':info[s]['method_version'],'score':row['policy_score'],'rank':rr[p][s],'denominator_bp':row['denominator_weight'],'correct_bp':row['compatible_correct_weight'],'evidence_role':EVIDENCE_ROLE})
   for pair in pairs:
    l,r=pair['left'],pair['right'];same=info[l]['method_name']==info[r]['method_name']
    identity=('DIFFERENT_METHOD_NAMES' if not same else 'SAME_METHOD_DIFFERENT_VERSION' if info[l]['method_version']!=info[r]['method_version'] else 'SAME_METHOD_SAME_VERSION_DIFFERENT_SUBMISSION')
    pr={'family':family,'panel':label,**pair,'left_method':info[l]['method_name'],'right_method':info[r]['method_name'],'left_version':info[l]['method_version'],'right_version':info[r]['method_version'],'identity_relation':identity,
        'P01_left':bypolicy['P01'][l]['policy_score'],'P01_right':bypolicy['P01'][r]['policy_score'],'P05_left':bypolicy['P05'][l]['policy_score'],'P05_right':bypolicy['P05'][r]['policy_score'],
        'retained_in_B':'YES' if {l,r}<=reps else 'NO','retained_in_C':'YES' if {l,r}<=common_ids else 'NO','evidence_role':EVIDENCE_ROLE}
    pair_rows.append(pr)
    if label=='A_FULL_SUBMISSION' and same:version_rows.append(pr)
  for label in ('B_METHOD_REPRESENTATIVE','C_COMMON_METHOD'):
   ids=panels[label]
   fullpairs=[r for r in pair_rows if r['family']==family and r['panel']=='A_FULL_SUBMISSION']
   deleted=[r for r in fullpairs if not {r['left'],r['right']}<=ids]
   full_scores={(r['policy'],r['submission']):r for r in score_rows if r['family']==family and r['panel']=='A_FULL_SUBMISSION'}
   kept_scores={(r['policy'],r['submission']):r for r in score_rows if r['family']==family and r['panel']==label}
   score_changes=sum(finite_decimal(r['score'])!=finite_decimal(full_scores[k]['score']) for k,r in kept_scores.items())
   denominator_changes=sum(finite_decimal(r['denominator_bp'])!=finite_decimal(full_scores[k]['denominator_bp']) for k,r in kept_scores.items())
   order_changes=0
   for p in bypolicy:
    for l,r in itertools.combinations(sorted(ids),2):
     d_full=finite_decimal(full_scores[(p,l)]['score'])-finite_decimal(full_scores[(p,r)]['score'])
     d_kept=finite_decimal(kept_scores[(p,l)]['score'])-finite_decimal(kept_scores[(p,r)]['score'])
     order_changes+=((d_full>0)-(d_full<0))!=((d_kept>0)-(d_kept<0))
   subset_checks.append({'family':family,'to_panel':label,'retained_pairs':len(ids)*(len(ids)-1)//2,'deleted_pairs':len(deleted),
    'deleted_strict_reversals':sum(r['pair_state']=='STRICT_REVERSAL' for r in deleted),'retained_score_changes':score_changes,'retained_pair_order_changes_within_each_policy':order_changes,'denominator_changes':denominator_changes,'basis':'SAME_FROZEN_METRIC_ROWS_FILTERED_NOT_REEVALUATED','evidence_role':EVIDENCE_ROLE})
 return {'summaries':summaries,'pairs':pair_rows,'scores':score_rows,'subset_checks':subset_checks,'within_method_pairs':version_rows,'denominators':denoms,'common_method_names':sorted(common),'identity_rows':panel}

def account_rows(rows):
 counts=Counter();bp=Counter();reasons=defaultdict(lambda:[0,0]);seen=set()
 for r in rows:
  key=r['contig_id'];n=int(r['contig_length']);s=r['assignment_status'];c=r['candidate_bin_id'];reason=r['reason_code']
  if not key or key in seen:raise ValueError('DUPLICATE_OR_MISSING_CONTIG')
  if n<=0:raise ValueError('INVALID_CONTIG_LENGTH')
  if s not in ('ASSIGNED','UNBINNED','TOOL_ABSTAIN','HARD_FAIL_INVALID_OUTPUT'):raise ValueError('UNDECLARED_ASSIGNMENT_STATUS')
  if (s=='ASSIGNED') != bool(c):raise ValueError('STATUS_CANDIDATE_CONFLICT')
  if not reason:raise ValueError('MISSING_REASON_PROVENANCE')
  if reason in REASON_STATUS and REASON_STATUS[reason]!=s:raise ValueError('STATUS_REASON_CONFLICT')
  seen.add(key);counts[s]+=1;bp[s]+=n;reasons[(s,reason)][0]+=1;reasons[(s,reason)][1]+=n
 total_n=sum(counts.values());total_bp=sum(bp.values())
 return {'counts':dict(counts),'base_pairs':dict(bp),'total_records':total_n,'total_bp':total_bp,
 'reason_rows':[{'status':s,'recorded_reason':r,'records':n,'bp':b,'inferred_from_length':'NO','reason_interpretation':'UNKNOWN_PRESERVED' if r=='OMITTED_UNKNOWN_REASON' or r not in REASON_STATUS else 'EXISTING_TOOL_OUTPUT_CATEGORY_NOT_CAUSAL_INFERENCE','evidence_role':EVIDENCE_ROLE} for (s,r),(n,b) in sorted(reasons.items())]}

def curve_admission(scores,source_kind,has_frozen_provenance):
 if not scores:return {'status':'AURC_NOT_ESTIMABLE_HARD_ASSIGNMENT_NO_SCORE','aurc':None}
 if source_kind!='PREDICTION_SIDE' or not has_frozen_provenance:raise ValueError('NO_VALID_PREDICTION_SIDE_ORDERING')
 if any(not math.isfinite(float(x)) for x in scores):raise ValueError('INVALID_SCORE')
 return {'status':'ORDERING_ADMITTED_CURVE_NOT_COMPUTED','aurc':None}

def compare_scope(a,b):
 keys=('dataset','assembly','denominator_id','weighting','matching','score_event')
 missing=[k for k in keys if not a.get(k) or not b.get(k)]
 if missing:raise ValueError('MISSING_SCOPE:'+','.join(missing))
 return {k:(a[k],b[k]) for k in keys if a[k]!=b[k]}

def main():
 p=argparse.ArgumentParser(description=__doc__);sub=p.add_subparsers(dest='command',required=True)
 q=sub.add_parser('score-space');q.add_argument('--q',default='1/2')
 d=sub.add_parser('panels');d.add_argument('--metrics',required=True);d.add_argument('--panel',required=True);d.add_argument('--output',required=True)
 a=sub.add_parser('account');a.add_argument('--records',required=True)
 sub.add_parser('synthetic-demo')
 args=p.parse_args()
 if args.command=='score-space':print(json.dumps(probability_diagnostic(args.q),indent=2))
 elif args.command=='account':print(json.dumps(account_rows(read_tsv(args.records)),indent=2))
 elif args.command=='panels':
  out=Path(args.output);out.mkdir(exist_ok=False);result=panel_analysis(read_tsv(args.metrics),read_tsv(args.panel))
  for key in ('summaries','pairs','scores','subset_checks','within_method_pairs','denominators','identity_rows'):write_tsv(out/(key+'.tsv'),result[key])
  print(json.dumps({'common_methods':result['common_method_names'],'summaries':result['summaries']},indent=2))
 else:
  sample=[{'contig_id':'s1','contig_length':'100','candidate_bin_id':'C1','assignment_status':'ASSIGNED','reason_code':'EXPLICIT_BIN'},{'contig_id':'s2','contig_length':'50','candidate_bin_id':'','assignment_status':'UNBINNED','reason_code':'EXPLICIT_UNBINNED'},{'contig_id':'s3','contig_length':'25','candidate_bin_id':'','assignment_status':'TOOL_ABSTAIN','reason_code':'OMITTED_UNKNOWN_REASON'}]
  print(json.dumps({'score_space':probability_diagnostic('1/2'),'accounting':account_rows(sample),'no_score':curve_admission([],None,False)},indent=2))

if __name__=='__main__':main()
