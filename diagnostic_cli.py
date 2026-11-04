"""Bounded portable mechanical diagnostics; synthetic and post-hoc evidence only.

No score recomputation from raw biology, confidence creation, external tool calls,
scientific truth authentication, model fitting, or third-party dependencies.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import itertools
import json
import re
from collections import Counter
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path

VERSION = '0.3.2-candidate'
SCOPE_FIELDS = ('dataset_id', 'family_id', 'assembly_id', 'policy_id',
                'weighting', 'matching', 'score_event', 'filter_definition')
STATUSES = {'ASSIGNED', 'UNBINNED', 'TOOL_ABSTAIN', 'HARD_FAIL_INVALID_OUTPUT'}
REASON_STATUS = {
    'EXPLICIT': 'ASSIGNED', 'EXPLICIT_BIN': 'ASSIGNED',
    'EXPLICIT_UNBINNED': 'UNBINNED', 'OMITTED_UNKNOWN_REASON': 'TOOL_ABSTAIN',
    'TOOL_ABSTAIN': 'TOOL_ABSTAIN', 'INVALID_OUTPUT': 'HARD_FAIL_INVALID_OUTPUT',
    'HARD_FAIL_INVALID_OUTPUT': 'HARD_FAIL_INVALID_OUTPUT',
}


def issue(out, code, location, details, severity='ERROR'):
    out['issues'].append(dict(code=code, location=location, details=details,
                              severity=severity))


def report(kind):
    return dict(interface=kind, schema_version='1', candidate_version=VERSION,
                evidence_role='POSTHOC_EXPLANATORY_DIAGNOSTIC', issues=[],
                verification_scope='MECHANICAL_CONSISTENCY_OF_SUPPLIED_EVIDENCE_ONLY',
                provenance_verification='DECLARED_NOT_AUTHENTICATED',
                limitations=['Declared filters, identities, provenance and scientific '
                             'meaning are not authenticated. No host-assignment '
                             'accuracy or biological activity is established.'])


def finish(out):
    kinds = {x['severity'] for x in out['issues']}
    invalid = 'ERROR' in kinds
    missing = 'INSUFFICIENT_EVIDENCE' in kinds
    different = 'COMPARABILITY' in kinds
    out['validity'] = 'INVALID' if invalid else 'NOT_VERIFIABLE' if missing else 'VALID'
    out['comparability'] = ('NOT_VERIFIABLE' if invalid or missing else
                            'NOT_DIRECTLY_COMPARABLE' if different else 'COMPARABLE')
    out['category'] = ('INVALID' if invalid else 'INSUFFICIENT_EVIDENCE' if missing else
                       'VALID_NOT_DIRECTLY_COMPARABLE' if different else 'VALID_COMPARABLE')
    return out


def nonempty(value):
    return isinstance(value, str) and bool(value.strip())


def text_field(obj, field, location, out):
    value = obj.get(field)
    if value is None or value == '':
        issue(out, 'MISSING_EVIDENCE', location, 'Required declaration is absent.',
              'INSUFFICIENT_EVIDENCE')
        return None
    if not nonempty(value):
        issue(out, 'INVALID_STRING', location, 'Expected nonempty string.')
        return None
    return value


def number(value, location, out, allow_na=False):
    if value is None or (isinstance(value, str) and value == 'NA'):
        issue(out, 'SCORE_UNAVAILABLE' if allow_na else 'MISSING_EVIDENCE', location,
              'No finite numeric value is available.', 'INSUFFICIENT_EVIDENCE')
        return None
    if isinstance(value, bool):
        issue(out, 'INVALID_NUMBER', location, 'Boolean is not a numeric observation.')
        return None
    try:
        n = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        issue(out, 'INVALID_NUMBER', location, 'Expected decimal-compatible number.')
        return None
    if not n.is_finite():
        issue(out, 'NONFINITE_NUMBER', location, 'NaN and infinity cannot be compared.')
        return None
    return n


def integer(value, location, out, positive=True):
    n = number(value, location, out)
    if n is None:
        return None
    if n != n.to_integral_value() or n < (1 if positive else 0):
        issue(out, 'INVALID_CONTIG_LENGTH' if positive else 'INVALID_COUNT', location,
              'Expected positive integer.' if positive else 'Expected nonnegative integer.')
        return None
    return int(n)


def records(value, location, out, require_nonempty=False):
    if value is None:
        issue(out, 'MISSING_EVIDENCE', location, 'Required evidence table is absent.',
              'INSUFFICIENT_EVIDENCE')
        return None
    if not isinstance(value, list):
        issue(out, 'INVALID_TABLE', location, 'Expected list of records.')
        return None
    if require_nonempty and not value:
        issue(out, 'EMPTY_EVIDENCE', location, 'Empty table cannot support evaluation.',
              'INSUFFICIENT_EVIDENCE')
    good = []
    for i, row in enumerate(value):
        if not isinstance(row, dict):
            issue(out, 'INVALID_RECORD', f'{location}[{i}]', 'Expected object.')
        else:
            good.append((i, row))
    return good


def membership(value, location, out):
    rr = records(value, location, out, require_nonempty=True)
    if rr is None:
        return None
    result = {}
    for i, row in rr:
        loc = f'{location}[{i}]'
        cid = text_field(row, 'contig_id', loc + '.contig_id', out)
        length = integer(row.get('length_bp'), loc + '.length_bp', out)
        if cid is None:
            continue
        if cid in result:
            issue(out, 'DUPLICATE_CONTIG_ID', loc + '.contig_id', {'contig_id': cid})
        else:
            result[cid] = length
    return result


def reconcile_members(members, universe, location, out, complete=False, input_rows=None):
    if members is None or universe is None:
        return dict(missing_ids=None, unknown_ids=None, length_mismatches=None)
    missing = sorted(set(universe) - set(members)) if complete else []
    unknown = sorted(set(members) - set(universe))
    lengths = [dict(contig_id=cid, observed=members[cid], expected=universe[cid])
               for cid in sorted(set(members) & set(universe))
               if members[cid] is not None and universe[cid] is not None
               and members[cid] != universe[cid]]
    for cid in missing:
        issue(out, 'OMITTED_CONTIG_ID', location, {'contig_id': cid})
    # Preserve the actual row/field address rather than only an aggregate table
    # address. Do not infer row order from the sorted ID set.
    positions = {}
    for i, row in enumerate(input_rows if isinstance(input_rows, list) else []):
        if isinstance(row, dict) and nonempty(row.get('contig_id')):
            positions.setdefault(row['contig_id'], i)
    def address(cid, field):
        return f'{location}[{positions[cid]}].{field}' if cid in positions else location
    for cid in unknown:
        issue(out, 'UNKNOWN_CONTIG_ID', address(cid, 'contig_id'), {'contig_id': cid})
    for row in lengths:
        issue(out, 'LENGTH_MISMATCH', address(row['contig_id'], 'length_bp'), row)
    return dict(missing_ids=missing, unknown_ids=unknown, length_mismatches=lengths)


def check_provenance(obj, side, out):
    p = obj.get('provenance')
    if p is None:
        issue(out, 'MISSING_EVIDENCE', side + '.provenance',
              'Source identity declaration absent.', 'INSUFFICIENT_EVIDENCE')
    elif not isinstance(p, dict):
        issue(out, 'INVALID_PROVENANCE', side + '.provenance', 'Expected object.')
    else:
        text_field(p, 'source_id', side + '.provenance.source_id', out)
        digest = text_field(p, 'sha256', side + '.provenance.sha256', out)
        if digest is not None and not re.fullmatch(r'[a-fA-F0-9]{64}', digest):
            issue(out, 'INVALID_SHA256', side + '.provenance.sha256',
                  'Expected 64 hexadecimal characters; no authentication is implied.')


def parse_result(obj, side, universe, out):
    if not isinstance(obj, dict):
        issue(out, 'INVALID_RESULT', side, 'Expected result object.')
        obj = {}
    for field in SCOPE_FIELDS:
        text_field(obj, field, side + '.' + field, out)
    check_provenance(obj, side, out)
    members = membership(obj.get('members'), side + '.members', out)
    reconcile_members(members, universe, side + '.members', out, input_rows=obj.get('members'))
    if 'declared_totals' in obj:
        dt = obj['declared_totals']
        if not isinstance(dt, dict):
            issue(out, 'INVALID_DECLARED_TOTALS', side + '.declared_totals', 'Expected object.')
        elif members is not None and all(v is not None for v in members.values()):
            actual = dict(records=len(members), bp=sum(members.values()))
            for field, value in actual.items():
                declared = integer(dt.get(field), side + '.declared_totals.' + field,
                                   out, positive=False)
                if declared is not None and declared != value:
                    issue(out, 'DECLARED_TOTAL_MISMATCH', side + '.declared_totals.' + field,
                          dict(declared=declared, actual=value))
    rr = records(obj.get('results'), side + '.results', out, require_nonempty=True)
    result_rows = {}
    for i, row in rr or []:
        loc = f'{side}.results[{i}]'
        sid = text_field(row, 'submission_id', loc + '.submission_id', out)
        for field in ('method', 'version', 'workflow_id'):
            text_field(row, field, loc + '.' + field, out)
        score = number(row.get('score'), loc + '.score', out, allow_na=True)
        if sid is None:
            continue
        if sid in result_rows:
            issue(out, 'DUPLICATE_SUBMISSION_ID', loc + '.submission_id', {'submission_id': sid})
        else:
            result_rows[sid] = {**row, '_score': score}
    tr = records(obj.get('target_map'), side + '.target_map', out)
    target_map = None if tr is None else {}
    for i, row in tr or []:
        loc = f'{side}.target_map[{i}]'
        fields = [text_field(row, f, loc + '.' + f, out)
                  for f in ('submission_id', 'candidate_bin_id', 'truth_id')]
        if any(v is None for v in fields):
            continue
        sid, bid, tid = fields
        key = (sid, bid)
        if sid not in result_rows:
            issue(out, 'UNKNOWN_MAP_SUBMISSION', loc + '.submission_id', {'submission_id': sid})
        if key in target_map:
            issue(out, 'DUPLICATE_TARGET_MAP', loc, {'submission_id': sid, 'candidate_bin_id': bid})
        else:
            target_map[key] = tid
    if target_map is not None:
        mapped = {key[0] for key in target_map}
        for sid in sorted(set(result_rows) - mapped):
            issue(out, 'MISSING_EVIDENCE', side + '.target_map',
                  {'submission_id': sid, 'reason': 'No target mappings provided for scored submission.'},
                  'INSUFFICIENT_EVIDENCE')
    return obj, members, result_rows, target_map


def select_panel(rows, rule):
    if rule != 'lexical_submission_per_method':
        return set(rows)
    selected, seen = set(), set()
    for sid in sorted(rows):
        method = rows[sid].get('method')
        if method not in seen:
            selected.add(sid)
            seen.add(method)
    return selected


def decimal_text(value):
    return str(value)


def exact_delta(a, b):
    # Decimal's default 28-digit context can erase small real changes.
    exponents = [x.as_tuple().exponent for x in (a, b)]
    most = max(x.adjusted() for x in (a, b))
    with localcontext() as ctx:
        ctx.prec = max(28, most - min(exponents) + 4)
        return b - a


def diagnose_comparison(left: dict, right: dict, universe: list[dict] | None,
                        config: dict) -> dict:
    out = report('compare')
    if not isinstance(config, dict):
        issue(out, 'INVALID_CONFIG', 'config', 'Expected configuration object.')
        config = {}
    text_field(config, 'metric_name', 'config.metric_name', out)
    direction = text_field(config, 'direction', 'config.direction', out)
    rule = text_field(config, 'representative_rule', 'config.representative_rule', out)
    if direction is not None and direction not in ('higher', 'lower'):
        issue(out, 'INVALID_DIRECTION', 'config.direction', direction)
    if rule is not None and rule not in ('all', 'lexical_submission_per_method'):
        issue(out, 'INVALID_REPRESENTATIVE_RULE', 'config.representative_rule', rule)
    out['config'] = config
    uu = membership(universe, 'universe', out)
    left, lm, lr, lt = parse_result(left, 'left', uu, out)
    right, rm, rr, rt = parse_result(right, 'right', uu, out)
    differences = []
    for field in SCOPE_FIELDS:
        if nonempty(left.get(field)) and nonempty(right.get(field)) and left[field] != right[field]:
            d = dict(field=field, left=left[field], right=right[field])
            differences.append(d)
            issue(out, 'SCOPE_DIFFERENCE', field, d, 'COMPARABILITY')
    if lm is not None and rm is not None:
        d = dict(field='members', removed_ids=sorted(set(lm) - set(rm)),
                 added_ids=sorted(set(rm) - set(lm)),
                 length_changes=[dict(contig_id=c, left=lm[c], right=rm[c])
                                 for c in sorted(set(lm) & set(rm)) if lm[c] != rm[c]])
        if d['removed_ids'] or d['added_ids'] or d['length_changes']:
            differences.append(d)
            issue(out, 'MEMBERSHIP_DIFFERENCE', 'members', d, 'COMPARABILITY')
    all_common = set(lr) & set(rr)
    for sid in sorted(all_common):
        for field in ('method', 'version', 'workflow_id'):
            a, b = lr[sid].get(field), rr[sid].get(field)
            if nonempty(a) and nonempty(b) and a != b:
                d = dict(field=field, submission_id=sid, left=a, right=b)
                differences.append(d)
                issue(out, 'IDENTITY_DIFFERENCE', 'results.' + sid + '.' + field,
                      d, 'COMPARABILITY')
    if lt is not None and rt is not None:
        keys = {k for k in set(lt) | set(rt) if k[0] in all_common}
        d = [dict(submission_id=k[0], candidate_bin_id=k[1],
                  left=lt.get(k), right=rt.get(k)) for k in sorted(keys) if lt.get(k) != rt.get(k)]
        if d:
            differences.append(dict(field='target_map', changes=d))
            issue(out, 'TARGET_MAP_DIFFERENCE', 'target_map', d, 'COMPARABILITY')
    li, ri = select_panel(lr, rule), select_panel(rr, rule)
    common = li & ri
    lp, rp = set(itertools.combinations(sorted(li), 2)), set(itertools.combinations(sorted(ri), 2))
    out['panel'] = dict(left_ids=sorted(li), right_ids=sorted(ri), retained_ids=sorted(common),
                        removed_ids=sorted(li - ri), added_ids=sorted(ri - li),
                        deleted_pairs=len(lp - rp), added_pairs=len(rp - lp), retained_pairs=len(lp & rp),
                        deleted_pair_ids=[list(p) for p in sorted(lp - rp)],
                        added_pair_ids=[list(p) for p in sorted(rp - lp)],
                        population_recomputed=False)
    out['input_submission_differences'] = dict(removed_ids=sorted(set(lr) - set(rr)),
                                              added_ids=sorted(set(rr) - set(lr)))
    if not common:
        issue(out, 'NO_COMMON_SUBMISSIONS', 'results', 'No selected paired submission remains.',
              'INSUFFICIENT_EVIDENCE')
    score_diffs = []
    for sid in sorted(all_common):
        a, b = lr[sid]['_score'], rr[sid]['_score']
        score_diffs.append(dict(submission_id=sid,
                                left_score=None if a is None else decimal_text(a),
                                right_score=None if b is None else decimal_text(b),
                                delta=None if a is None or b is None else decimal_text(exact_delta(a, b)),
                                retained_in_selected_panel=sid in common))
    out['score_differences'] = score_diffs
    finite_common = {s for s in common if lr[s]['_score'] is not None and rr[s]['_score'] is not None}
    out['unassessable_retained_scores'] = len(common - finite_common)
    out['observed_finite_score_changes'] = sum(lr[s]['_score'] != rr[s]['_score'] for s in finite_common)
    out['retained_score_changes'] = (None if common - finite_common else out['observed_finite_score_changes'])
    pairs, counts = [], Counter()
    sign = 1 if direction == 'higher' else -1
    for a, b in sorted(lp & rp):
        values = (lr[a]['_score'], lr[b]['_score'], rr[a]['_score'], rr[b]['_score'])
        if any(v is None for v in values):
            state, left_order, right_order = 'NOT_VERIFIABLE', None, None
        else:
            la, lb, ra, rb = values
            left_order, right_order = sign * ((la > lb) - (la < lb)), sign * ((ra > rb) - (ra < rb))
            state = ('BOTH_TIE' if left_order == right_order == 0 else
                     'LEFT_TIE_ONLY' if left_order == 0 else 'RIGHT_TIE_ONLY' if right_order == 0 else
                     'STRICT_REVERSAL' if left_order != right_order else 'CONCORDANT')
        counts[state] += 1
        pairs.append(dict(left_submission=a, right_submission=b, state=state,
                          left_order=left_order, right_order=right_order))
    out['pairs'], out['pair_counts'], out['differences'] = pairs, dict(counts), differences
    return finish(out)


def diagnose_accounting(rows, universe):
    out = report('account')
    uu = membership(universe, 'universe', out)
    members = membership(rows, 'rows', out)
    out.update(reconcile_members(members, uu, 'rows', out, complete=True, input_rows=rows))
    rr = records(rows, 'rows', out, require_nonempty=True)
    first_assignments = {}
    for i, row in rr or []:
        cid = row.get('contig_id')
        if not nonempty(cid):
            continue
        if cid in first_assignments:
            previous = first_assignments[cid]
            issue(out, 'DUPLICATE_HARD_ASSIGNMENT', f'rows[{i}].candidate_bin_id',
                  dict(contig_id=cid, previous_candidate_bin_id=previous,
                       candidate_bin_id=row.get('candidate_bin_id'),
                       subtype='SAME_BIN_REPEAT' if previous == row.get('candidate_bin_id')
                       else 'CONFLICTING_ASSIGNMENT'))
        else:
            first_assignments[cid] = row.get('candidate_bin_id')
    counts, bp, reasons = Counter(), Counter(), {}
    for i, row in rr or []:
        loc = f'rows[{i}]'
        status = text_field(row, 'assignment_status', loc + '.assignment_status', out)
        reason = text_field(row, 'reason_code', loc + '.reason_code', out)
        candidate = row.get('candidate_bin_id')
        if candidate is None:
            issue(out, 'MISSING_EVIDENCE', loc + '.candidate_bin_id',
                  'Declare assigned candidate or explicit empty string.', 'INSUFFICIENT_EVIDENCE')
        elif not isinstance(candidate, str):
            issue(out, 'INVALID_STRING', loc + '.candidate_bin_id', 'Expected string, empty if not assigned.')
        if status is not None and status not in STATUSES:
            issue(out, 'UNDECLARED_ASSIGNMENT_STATUS', loc + '.assignment_status', status)
        elif status is not None and isinstance(candidate, str) and (status == 'ASSIGNED') != bool(candidate.strip()):
            issue(out, 'STATUS_CANDIDATE_CONFLICT', loc + '.candidate_bin_id',
                  dict(assignment_status=status, candidate_bin_id=candidate))
        if reason is not None:
            if reason in REASON_STATUS:
                if status is not None and status != REASON_STATUS[reason]:
                    issue(out, 'STATUS_REASON_CONFLICT', loc + '.reason_code',
                          dict(assignment_status=status, reason_code=reason,
                               reason_requires_status=REASON_STATUS[reason]))
            else:
                issue(out, 'UNKNOWN_REASON', loc + '.reason_code', {'reason_code': reason},
                      'INSUFFICIENT_EVIDENCE')
        length = members.get(row.get('contig_id')) if members is not None else None
        if status in STATUSES and length is not None:
            counts[status] += 1
            bp[status] += length
            key = (status, reason)
            n, mass = reasons.get(key, (0, 0))
            reasons[key] = (n + 1, mass + length)
    out.update(total_records=len(rows) if isinstance(rows, list) else None,
               total_bp=sum(v for v in members.values() if v is not None) if members is not None else None,
               counts=dict(counts), base_pairs=dict(bp),
               totals_status='OBSERVED_TABLE_ONLY_NOT_PROOF_OF_COMPLETENESS',
               reason_rows=[dict(status=s, recorded_reason=r, records=n, bp=b,
                                 reason_interpretation='UNKNOWN_PRESERVED' if r not in REASON_STATUS or r == 'OMITTED_UNKNOWN_REASON' else 'DECLARED_REASON_ONLY')
                            for (s, r), (n, b) in sorted(reasons.items(), key=lambda x: str(x[0]))])
    return finish(out)


def diagnose_event(spec):
    out = report('event')
    out.update(brier=None, aurc=None, aurc_status='NOT_ESTIMABLE')
    if not isinstance(spec, dict):
        issue(out, 'INVALID_EVENT_SPEC', 'spec', 'Expected object.')
        return finish(out)
    event = text_field(spec, 'event', 'event', out)
    target = text_field(spec, 'target', 'target', out)
    for field in ('filter_scope', 'matching_definition', 'score_definition'):
        text_field(spec, field, field, out)
    known_events = ('BINARY', 'CATEGORICAL', 'CURRENT_ASSIGNMENT_CORRECTNESS')
    if event is not None and event not in known_events:
        issue(out, 'UNSUPPORTED_EVENT_SEMANTICS', 'event', event, 'INSUFFICIENT_EVIDENCE')
    if spec.get('score_definition') not in (None, '', 'BRIER'):
        issue(out, 'UNSUPPORTED_SCORE_DEFINITION', 'score_definition', spec['score_definition'],
              'INSUFFICIENT_EVIDENCE')
    if 'probability_event' in spec and spec['probability_event'] != event:
        issue(out, 'EVENT_PROBABILITY_SPACE_CONFLICT', 'probability_event',
              dict(event=event, probability_event=spec['probability_event']))
    support = spec.get('probability_support')
    values = {}
    if support is None:
        issue(out, 'MISSING_EVIDENCE', 'probability_support', 'Numeric support absent.',
              'INSUFFICIENT_EVIDENCE')
    elif not isinstance(support, dict):
        issue(out, 'INVALID_PROBABILITY_SUPPORT', 'probability_support', 'Expected label-to-probability object.')
    else:
        if ((event in ('BINARY', 'CURRENT_ASSIGNMENT_CORRECTNESS') and len(support) != 2)
                or (event == 'CATEGORICAL' and len(support) < 2)):
            issue(out, 'EVENT_SUPPORT_CONFLICT', 'probability_support',
                  dict(event=event, support_labels=list(support)))
        if event == 'CURRENT_ASSIGNMENT_CORRECTNESS' and set(support) != {'CORRECT', 'INCORRECT'}:
            issue(out, 'EVENT_SUPPORT_CONFLICT', 'probability_support',
                  'Correctness event requires CORRECT/INCORRECT outcomes, not candidate+UNKNOWN categories.')
        for label, value in support.items():
            if not nonempty(label):
                issue(out, 'INVALID_SUPPORT_LABEL', 'probability_support', 'Labels must be nonempty strings.')
            n = number(value, 'probability_support.' + str(label), out)
            if n is not None:
                values[label] = n
        if target is not None and target not in support:
            issue(out, 'TARGET_OUTSIDE_SUPPORT', 'target', dict(target=target, support_labels=list(support)))
        if len(values) == len(support):
            with localcontext() as ctx:
                ctx.prec = max(50, sum(len(v.as_tuple().digits) for v in values.values()) + 10)
                total = sum(values.values(), Decimal(0))
                offending = [dict(label=label, value=str(value))
                             for label, value in values.items() if value < 0 or value > 1]
                normalisation_valid = abs(total - 1) <= Decimal('1e-12')
                if offending or not normalisation_valid:
                    issue(out, 'INVALID_SIMPLEX', 'probability_support',
                          dict(total=str(total), offending_values=offending,
                               support_bounds_valid=not offending,
                               normalisation_valid=normalisation_valid))
                if not any(x['severity'] in ('ERROR', 'INSUFFICIENT_EVIDENCE') for x in out['issues']):
                    out['brier'] = decimal_text(sum((p - Decimal(label == target)) ** 2 for label, p in values.items()))
    if spec.get('request_aurc'):
        scores = spec.get('confidence_scores')
        if not scores:
            issue(out, 'NO_CONFIDENCE_SCORES', 'confidence_scores',
                  'Hard assignments do not supply confidence ordering.', 'INSUFFICIENT_EVIDENCE')
        elif not isinstance(scores, list):
            issue(out, 'INVALID_CONFIDENCE_SCORES', 'confidence_scores', 'Expected list.')
        else:
            for i, value in enumerate(scores):
                number(value, f'confidence_scores[{i}]', out)
            if spec.get('confidence_source') != 'PREDICTION_SIDE':
                issue(out, 'INVALID_CONFIDENCE_SOURCE', 'confidence_source',
                      'Confidence must be prediction-side, never target-derived or bin mass.')
            if spec.get('confidence_frozen_provenance') is not True:
                issue(out, 'MISSING_EVIDENCE', 'confidence_frozen_provenance',
                      'Frozen ordering provenance absent.', 'INSUFFICIENT_EVIDENCE')
            issue(out, 'AURC_OUTCOMES_UNAVAILABLE', 'request_aurc',
                  'No validated per-example confidence/outcome interface; AURC not implemented.',
                  'INSUFFICIENT_EVIDENCE')
    return finish(out)


def read_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError('DUPLICATE_JSON_KEY:' + key)
            result[key] = value
        return result
    with Path(path).open(encoding='utf-8') as handle:
        return json.load(handle, parse_float=Decimal, object_pairs_hook=unique)


class TSVHeaderError(ValueError):
    """Invalid TSV header with the actual duplicate fields and column locations."""
    def __init__(self, fields):
        columns = list(fields or [])
        counts = Counter(columns)
        self.details = dict(header_line=1, observed_header=columns,
            duplicate_columns=[dict(column=column,
                positions=[i + 1 for i, value in enumerate(columns) if value == column])
                for column in dict.fromkeys(columns) if counts[column] > 1])
        super().__init__('INVALID_TSV_HEADER')


def validate_tsv_header(fields):
    if not fields or len(set(fields)) != len(fields):
        raise TSVHeaderError(fields)


def read_tsv(path):
    with Path(path).open(encoding='utf-8', newline='') as handle:
        reader = csv.DictReader(handle, delimiter='\t')
        validate_tsv_header(reader.fieldnames)
        rows = list(reader)
        if any(None in row or None in row.values() for row in rows):
            raise ValueError('INVALID_TSV_WIDTH')
        return rows


def file_identity(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b''):
            digest.update(chunk)
    return dict(path=str(Path(path).resolve()), sha256=digest.hexdigest())


def synthetic_demo():
    from copy import deepcopy
    source = dict(dataset_id='synthetic_dataset', family_id='custom_family', assembly_id='asm_synthetic',
                  policy_id='declared_policy', weighting='BASE_PAIRS', matching='MANY_TO_ONE',
                  score_event='DECLARED_CORRECT_ASSIGNMENT', filter_definition='all_declared_members',
                  provenance=dict(source_id='hand_authored_synthetic_fixture', sha256='0' * 64),
                  members=[dict(contig_id='c1', length_bp=100), dict(contig_id='c2', length_bp=50)],
                  target_map=[dict(submission_id='s1', candidate_bin_id='bin1', truth_id='t1'),
                              dict(submission_id='s2', candidate_bin_id='bin2', truth_id='t1')],
                  results=[dict(submission_id='s1', method='alpha', version='1', workflow_id='wf1', score='0.6'),
                           dict(submission_id='s2', method='beta', version='2', workflow_id='wf2', score='0.7')])
    right = deepcopy(source)
    right['results'][0]['score'] = '0.8'
    config = dict(metric_name='synthetic_score', direction='higher', representative_rule='all')
    comparison = diagnose_comparison(source, right, source['members'], config)
    comparison['limitations'].append('Demo provenance digest is explicitly synthetic placeholder, not observed file identity.')
    return dict(synthetic=True, comparison=comparison,
                event=diagnose_event(dict(event='BINARY', probability_support={'correct': '.25', 'incorrect': '.75'},
                                         target='incorrect', filter_scope='all', matching_definition='declared',
                                         score_definition='BRIER', request_aurc=True)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--version', action='version', version=VERSION)
    sub = parser.add_subparsers(dest='command', required=True)
    compare = sub.add_parser('compare', help='Compare two independently supplied result JSON files.')
    compare.add_argument('--left', required=True)
    compare.add_argument('--right', required=True)
    compare.add_argument('--universe', help='Independent complete assembly TSV: contig_id,length_bp.')
    compare.add_argument('--config', required=True)
    account = sub.add_parser('account', help='Reconcile assignment TSV against independent universe TSV.')
    account.add_argument('--records', required=True)
    account.add_argument('--universe')
    event = sub.add_parser('event', help='Diagnose explicitly declared numeric event/probability support.')
    event.add_argument('--spec', required=True)
    artifact = sub.add_parser('artifact', help='Read and reconcile declared native artifact files.')
    artifact.add_argument('--spec', required=True)
    artifact.add_argument('--reference-spec', help='Optional second independently read native manifest for actual-file comparison.')
    sub.add_parser('synthetic-demo')
    args = parser.parse_args(argv)
    input_paths = {}
    try:
        if args.command == 'compare':
            input_paths = dict(left=args.left, right=args.right, config=args.config)
            if args.universe:
                input_paths['universe'] = args.universe
            out = diagnose_comparison(read_json(args.left), read_json(args.right),
                                      read_tsv(args.universe) if args.universe else None,
                                      read_json(args.config))
        elif args.command == 'account':
            input_paths = dict(records=args.records)
            if args.universe:
                input_paths['universe'] = args.universe
            out = diagnose_accounting(read_tsv(args.records), read_tsv(args.universe) if args.universe else None)
        elif args.command == 'artifact':
            from native_artifacts import diagnose_artifact, diagnose_artifact_pair
            input_paths = dict(spec=args.spec)
            if args.reference_spec:
                input_paths['reference_spec'] = args.reference_spec
                out = diagnose_artifact_pair(read_json(args.spec), read_json(args.reference_spec),
                    Path(args.spec).resolve().parent, Path(args.reference_spec).resolve().parent)
            else:
                out = diagnose_artifact(read_json(args.spec), Path(args.spec).resolve().parent)
        elif args.command == 'event':
            input_paths = dict(spec=args.spec)
            out = diagnose_event(read_json(args.spec))
        else:
            out = synthetic_demo()
        out['input_files'] = {key: file_identity(path) for key, path in input_paths.items()}
        print(json.dumps(out, indent=2, sort_keys=True, allow_nan=False, default=str))
        return 2 if out.get('validity') == 'INVALID' else 3 if out.get('validity') == 'NOT_VERIFIABLE' else 0
    except (OSError, ValueError, TypeError) as exc:
        out = report(args.command)
        issue(out, 'INPUT_READ_ERROR', 'input_files',
              dict(reason=str(exc), **exc.details) if isinstance(exc, TSVHeaderError) else str(exc))
        print(json.dumps(finish(out), indent=2, sort_keys=True, allow_nan=False, default=str))
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
