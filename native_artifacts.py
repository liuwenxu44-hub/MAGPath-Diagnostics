"""Narrow native-file reconciliation, not an AMBER implementation or truth audit.

All observed numbers come from the actual selected TSV field. SHA-256 binds bytes
to a supplied declaration, never authenticates provenance or scientific meaning.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, InvalidOperation, localcontext
from pathlib import Path
import hashlib
import json
import csv
import re

from diagnostic_cli import (SCOPE_FIELDS, VERSION, file_identity, nonempty,
                            read_json, read_tsv, report, validate_tsv_header)

TOLERANCE = Decimal('1e-12')
AMBER_FIELDS = ('accuracy_bp', 'accuracy_seq', 'percentage_of_assigned_bps',
                'percentage_of_assigned_seqs', 'precision_weighted_bp',
                'precision_weighted_seq')
BER_FIELDS = ('U_bp', 'I_bp', 'correct_bp_A', 'correct_bp_B', 'correct_bp_C',
              'a_A', 'a_B', 'a_C', 'f_A', 'f_B', 'f_C')


def membership_fingerprint(members):
    """Order-invariant identity from loaded IDs AND lengths, not declared labels."""
    if members is None or any(value is None for value in members.values()):
        return None
    digest = hashlib.sha256()
    digest.update(b'[')
    for i, cid in enumerate(sorted(members)):
        if i:
            digest.update(b',')
        pair = json.dumps([cid, str(int(members[cid]))], ensure_ascii=False,
                          separators=(',', ':')).encode('utf-8')
        digest.update(pair)
    digest.update(b']')
    return dict(records=len(members), bp=str(sum(int(n) for n in members.values())),
                id_length_sha256=digest.hexdigest(),
                canonicalisation='UTF8_JSON_SORTED_ID_DECIMAL_INTEGER_LENGTH_PAIRS')


def add(out, code, location, details, dimension='input', severity='ERROR'):
    out['issues'].append(dict(code=code, location=location, details=details,
                              dimension=dimension, severity=severity))


def missing(out, location, detail, dimension='evidence'):
    add(out, 'MISSING_EVIDENCE', location, detail, dimension, 'INSUFFICIENT_EVIDENCE')


def numeric(value, out, location, integral=False, positive=False):
    if value is None or value in ('', 'NA'):
        missing(out, location, 'Finite numeric value unavailable.')
        return None
    try:
        if isinstance(value, bool):
            raise ValueError('Boolean is not a numeric value.')
        n = Decimal(str(value))
        if not n.is_finite():
            raise ValueError('Nonfinite number.')
        if integral and (n != n.to_integral_value() or n < (1 if positive else 0)):
            raise ValueError('Expected positive integer.' if positive else 'Expected nonnegative integer.')
        return n
    except (InvalidOperation, ValueError, TypeError) as exc:
        add(out, 'INVALID_NUMBER', location, dict(value=value, reason=str(exc)))
        return None


def load_file(descriptor, role, base, out, fmt='tsv', process=False):
    dimension = 'process' if process else 'input'
    if descriptor is None:
        missing(out, role, 'File declaration absent.', 'process' if process else 'evidence')
        return None, None
    if not isinstance(descriptor, dict) or not nonempty(descriptor.get('path')):
        add(out, 'INVALID_FILE_DECLARATION', role, 'Expected path and sha256.', dimension)
        return None, None
    path = Path(descriptor['path'])
    if not path.is_absolute():
        path = base / path
    expected = descriptor.get('sha256')
    if expected is None:
        missing(out, role + '.sha256', 'Expected byte digest absent.',
                'process' if process else 'evidence')
    elif not isinstance(expected, str) or not re.fullmatch('[a-fA-F0-9]{64}', expected):
        add(out, 'INVALID_SHA256', role + '.sha256', {'observed': expected}, dimension)
    try:
        identity = file_identity(path)
        identity.update(role=role, declared_sha256=expected,
                        hash_status='MATCH' if isinstance(expected, str) and
                        expected.lower() == identity['sha256'] else 'NOT_VERIFIABLE' if
                        expected is None else 'MISMATCH')
        out['source_files'].append(identity)
        if expected is not None and identity['hash_status'] == 'MISMATCH':
            add(out, 'SOURCE_HASH_MISMATCH', role + '.sha256',
                dict(declared=expected, actual=identity['sha256'], path=str(path)), dimension)
        data = (read_json(path) if fmt == 'json' else read_biobox(path) if fmt == 'biobox'
                else None if fmt == 'bytes' else read_tsv(path))
        return data, identity
    except OSError as exc:
        if role.startswith('witnesses.'):
            missing(out, role, dict(path=str(path), reason=str(exc),
                                   missing_witness_not_malformed_input=True))
        else:
            add(out, 'REQUIRED_ARTIFACT_UNAVAILABLE' if process else 'INPUT_READ_ERROR', role,
                dict(path=str(path), reason=str(exc)), dimension)
        return None, None
    except (ValueError, TypeError) as exc:
        add(out, 'REQUIRED_ARTIFACT_UNAVAILABLE' if process else 'INPUT_READ_ERROR', role,
            dict(path=str(path), reason=str(exc), **getattr(exc, 'details', {})), dimension)
        return None, None


def read_biobox(path):
    fields, rows, sample = None, [], None
    with Path(path).open(encoding='utf-8') as handle:
        for line_no, raw in enumerate(handle, 1):
            line = raw.rstrip('\r\n')
            if line.startswith('@SampleID:'):
                if sample is not None:
                    raise ValueError('MULTIPLE_SAMPLE_DECLARATIONS')
                sample = line.split(':', 1)[1]
            elif line.startswith('@@'):
                if fields is not None:
                    raise ValueError('MULTIPLE_BIOBOX_HEADERS')
                fields = line[2:].split('\t')
                if len(set(fields)) != len(fields) or not {'SEQUENCEID', 'BINID'} <= set(fields):
                    raise ValueError('INVALID_BIOBOX_HEADER')
            elif line and not line.startswith(('@', '#')):
                values = line.split('\t')
                if fields is None or len(values) != len(fields):
                    raise ValueError('INVALID_BIOBOX_WIDTH_OR_HEADER:line=' + str(line_no))
                rows.append(dict(zip(fields, values), _line=line_no))
    if fields is None:
        raise ValueError('MISSING_BIOBOX_HEADER')
    return dict(sample_id=sample, rows=rows, fields=fields)


def select(rows, selector, out, role, unique=False):
    if rows is None:
        return []
    selected = [(i + 2, row) for i, row in enumerate(rows)
                if all(row.get(k) == v for k, v in selector.items())]
    if unique and len(selected) != 1:
        add(out, 'SOURCE_SELECTOR_NOT_UNIQUE', role,
            dict(selector=selector, matched_rows=len(selected)))
    return selected


def check_scope(spec, out):
    scope = spec.get('scope')
    if not isinstance(scope, dict):
        missing(out, 'scope', 'Eight explicit scope declarations required.', 'comparability')
        scope = {}
    for key in SCOPE_FIELDS:
        if not nonempty(scope.get(key)):
            missing(out, 'scope.' + key, 'Nonempty scope declaration required.', 'comparability')
    out['scope'] = scope
    reference = spec.get('reference_scope')
    if reference is not None:
        if not isinstance(reference, dict):
            add(out, 'INVALID_REFERENCE_SCOPE', 'reference_scope', 'Expected object.')
        else:
            for key in SCOPE_FIELDS:
                if not nonempty(reference.get(key)):
                    missing(out, 'reference_scope.' + key, 'Reference scope absent.', 'comparability')
                elif nonempty(scope.get(key)) and reference[key] != scope[key]:
                    add(out, 'SCOPE_DIFFERENCE', 'scope.' + key,
                        dict(observed=scope[key], reference=reference[key]),
                        'comparability', 'COMPARABILITY')


def process_audit(spec, base, out):
    process = spec.get('process')
    out['process_exit_code'] = None
    if process is None:
        missing(out, 'process', 'No source execution receipt or closed required-artifact list.', 'process')
        return
    if not isinstance(process, dict):
        add(out, 'INVALID_PROCESS_DECLARATION', 'process', 'Expected object.', 'process')
        return
    receipt, identity = load_file(process.get('receipt'), 'process.receipt', base, out, 'json', True)
    if receipt is not None:
        code = receipt.get('exit_code') if isinstance(receipt, dict) else None
        if not isinstance(code, int) or isinstance(code, bool):
            add(out, 'INVALID_PROCESS_EXIT_CODE', 'process.receipt.exit_code', code, 'process')
        else:
            out['process_exit_code'] = code
            if code != 0:
                add(out, 'SOURCE_PROCESS_FAILED', 'process.receipt.exit_code',
                    dict(exit_code=code, numeric_results_not_automatically_invalid=True), 'process')
    artifacts = process.get('required_artifacts')
    if not isinstance(artifacts, list) or not artifacts:
        missing(out, 'process.required_artifacts', 'Explicit nonempty required artifact inventory absent.', 'process')
    else:
        for i, descriptor in enumerate(artifacts):
            load_file(descriptor, f'process.required_artifacts[{i}]', base, out, 'bytes', True)
    logs = process.get('logs', [])
    if not isinstance(logs, list):
        add(out, 'INVALID_PROCESS_LOGS', 'process.logs', 'Expected list.', 'process')
    else:
        for i, descriptor in enumerate(logs):
            _, log_id = load_file(descriptor, f'process.logs[{i}]', base, out, 'bytes', True)
            if log_id and isinstance(receipt, dict):
                key = Path(log_id['path']).stem + '_sha256'
                if key in receipt and receipt[key] != log_id['sha256']:
                    add(out, 'PROCESS_LOG_RECEIPT_MISMATCH', f'process.logs[{i}]',
                        dict(receipt_sha256=receipt[key], actual_sha256=log_id['sha256']), 'process')


def amber_recompute(spec, selector, base, out):
    witnesses = spec.get('witnesses', {})
    truth, _ = load_file(witnesses.get('truth'), 'witnesses.truth', base, out, 'biobox')
    query, _ = load_file(witnesses.get('query'), 'witnesses.query', base, out, 'biobox')
    minimum = numeric(spec.get('minimum_length', 0), out, 'minimum_length', integral=True)
    if truth is None or query is None or minimum is None:
        return {}, False
    minimum = int(minimum)
    for role, data in (('truth', truth), ('query', query)):
        if not nonempty(data['sample_id']):
            missing(out, 'witnesses.' + role + '.SampleID', 'Biobox sample identity missing.')
        elif data['sample_id'] != selector.get('Sample'):
            add(out, 'SAMPLE_IDENTITY_MISMATCH', 'witnesses.' + role + '.SampleID',
                dict(observed=data['sample_id'], source_sample=selector.get('Sample')))
    truth_map = {}
    for row in truth['rows']:
        cid, tid = row['SEQUENCEID'], row['BINID']
        loc = 'witnesses.truth:line=' + str(row['_line'])
        n = numeric(row.get('LENGTH'), out, loc + '.LENGTH', integral=True, positive=True)
        if not nonempty(cid) or not nonempty(tid):
            add(out, 'INVALID_MEMBERSHIP_ID', loc, dict(contig_id=cid, truth_id=tid))
        elif cid in truth_map:
            add(out, 'DUPLICATE_TRUTH_ID', loc, dict(contig_id=cid))
        else:
            truth_map[cid] = (tid, n)
    query_map = {}
    for row in query['rows']:
        cid, bid = row['SEQUENCEID'], row['BINID']
        loc = 'witnesses.query:line=' + str(row['_line'])
        if not nonempty(cid) or not nonempty(bid):
            add(out, 'INVALID_MEMBERSHIP_ID', loc, dict(contig_id=cid, candidate_bin_id=bid))
        elif cid in query_map:
            add(out, 'DUPLICATE_HARD_ASSIGNMENT', loc,
                dict(contig_id=cid, previous_candidate_bin_id=query_map[cid], candidate_bin_id=bid,
                     subtype='SAME_BIN_REPEAT' if query_map[cid] == bid else 'CONFLICTING_ASSIGNMENT'))
        else:
            query_map[cid] = bid
        if cid not in truth_map:
            add(out, 'UNKNOWN_CONTIG_ID', loc, dict(contig_id=cid))
        elif 'LENGTH' in row:
            length = numeric(row['LENGTH'], out, loc + '.LENGTH', integral=True, positive=True)
            if length is not None and truth_map[cid][1] is not None and length != truth_map[cid][1]:
                add(out, 'LENGTH_MISMATCH', loc + '.LENGTH',
                    dict(contig_id=cid, observed=str(length), expected=str(truth_map[cid][1])))
    if any(x['dimension'] == 'input' and x['severity'] == 'ERROR' for x in out['issues']):
        return {}, False
    if any(n is None for _, n in truth_map.values()):
        return {}, False
    uu = {cid: row for cid, row in truth_map.items() if row[1] >= minimum}
    assigned = {cid: bid for cid, bid in query_map.items() if cid in uu}
    denom_bp = sum((n for _, n in uu.values()), Decimal(0))
    if not uu or not denom_bp:
        missing(out, 'witnesses.truth', 'Empty filtered evaluation universe; ratios undefined.')
        return {}, False
    masses = {'bp': defaultdict(lambda: defaultdict(Decimal)),
              'seq': defaultdict(lambda: defaultdict(Decimal))}
    for cid, bid in assigned.items():
        tid, length = uu[cid]
        masses['bp'][bid][tid] += length
        masses['seq'][bid][tid] += 1
    calculated, mappings = {}, {}
    for unit, denominator, assigned_mass in (
            ('bp', denom_bp, sum((uu[cid][1] for cid in assigned), Decimal(0))),
            ('seq', Decimal(len(uu)), Decimal(len(assigned)))):
        mapping = {bid: min(values, key=lambda tid: (-values[tid], tid))
                   for bid, values in masses[unit].items()}
        correct = sum((masses[unit][bid][tid] for bid, tid in mapping.items()), Decimal(0))
        mappings[unit] = mapping
        calculated['accuracy_' + unit] = correct / denominator
        calculated['percentage_of_assigned_' + ('bps' if unit == 'bp' else 'seqs')] = assigned_mass / denominator
        calculated['precision_weighted_' + unit] = correct / assigned_mass if assigned_mass else None
    out['reconstruction'] = dict(universe_records=len(uu), universe_bp=str(denom_bp),
        assigned_records=len(assigned), assigned_bp=str(sum((uu[cid][1] for cid in assigned), Decimal(0))),
        omitted_ids=sorted(set(uu) - set(assigned)), excluded_by_length=sorted(set(truth_map) - set(uu)),
        target_maps=mappings, minimum_length=minimum,
        contract='STRICT_SINGLETON_TRUTH_UNIQUE_HARD_ASSIGNMENT_MANY_TO_ONE',
        membership_origin='SUPPLIED_TRUTH_BIOBOX_NOT_ORIGIN_AUTHENTICATED')
    out['reconstruction']['membership_fingerprints'] = dict(
        universe=membership_fingerprint({cid: row[1] for cid, row in truth_map.items()}),
        evaluated=membership_fingerprint({cid: row[1] for cid, row in uu.items()}))
    return calculated, True


def members_file(descriptor, role, family, base, out):
    # U can contain millions of IDs. Hash the declared bytes, then parse once
    # into the ID-length map without retaining a second list of row dictionaries.
    _, identity = load_file(descriptor, role, base, out, 'bytes')
    if identity is None:
        return None
    members = {}
    try:
        with Path(identity['path']).open(encoding='utf-8', newline='') as handle:
            reader = csv.DictReader(handle, delimiter='\t')
            validate_tsv_header(reader.fieldnames)
            for line, row in enumerate(reader, 2):
                if None in row or None in row.values():
                    raise ValueError('INVALID_TSV_WIDTH:line=' + str(line))
                if 'family_id' in row and row['family_id'] != family:
                    continue
                cid = row.get('contig_id', row.get('record_id'))
                n = numeric(row.get('length_bp'), out, f'{role}:line={line}.length_bp', integral=True, positive=True)
                if not nonempty(cid):
                    add(out, 'INVALID_MEMBERSHIP_ID', f'{role}:line={line}', {'contig_id': cid})
                elif cid in members:
                    add(out, 'DUPLICATE_CONTIG_ID', f'{role}:line={line}', {'contig_id': cid})
                else:
                    members[cid] = None if n is None else int(n)
    except OSError as exc:
        missing(out, role, dict(path=identity['path'], reason=str(exc),
                               missing_witness_not_malformed_input=True))
        return None
    except (ValueError, TypeError) as exc:
        add(out, 'INPUT_READ_ERROR', role,
            dict(path=identity['path'], reason=str(exc), **getattr(exc, 'details', {})))
        return None
    if not members:
        missing(out, role, 'Empty selected membership witness.')
    return members


def ber_recompute(spec, selector, source, base, out):
    w = spec.get('witnesses', {})
    family = selector.get('family_id')
    uu = members_file(w.get('universe'), 'witnesses.universe', family, base, out)
    ii = members_file(w.get('members'), 'witnesses.members', family, base, out)
    if uu is not None and ii is not None:
        for cid, n in ii.items():
            if cid not in uu:
                add(out, 'UNKNOWN_CONTIG_ID', 'witnesses.members', {'contig_id': cid})
            elif n != uu[cid]:
                add(out, 'LENGTH_MISMATCH', 'witnesses.members',
                    dict(contig_id=cid, observed=str(n), expected=str(uu[cid])))
    overlaps, _ = load_file(w.get('overlaps'), 'witnesses.overlaps', base, out)
    mapping_rows, _ = load_file(w.get('mappings'), 'witnesses.mappings', base, out)
    selected = select(overlaps, selector, out, 'witnesses.overlaps')
    selected_maps = select(mapping_rows, selector, out, 'witnesses.mappings')
    if not selected:
        missing(out, 'witnesses.overlaps', 'No overlap rows match declared source selector.')
        return {}, False
    mass = defaultdict(dict)
    for line, row in selected:
        bid, tid = row.get('candidate_bin'), row.get('truth_target')
        if not nonempty(bid) or not nonempty(tid):
            add(out, 'INVALID_OVERLAP_ID', f'witnesses.overlaps:line={line}', row)
            continue
        vals = [numeric(row.get(k), out, f'witnesses.overlaps:line={line}.{k}', integral=True)
                for k in ('U_bp', 'I_bp', 'U_records', 'I_records')]
        if tid in mass[bid]:
            add(out, 'DUPLICATE_OVERLAP', f'witnesses.overlaps:line={line}',
                dict(candidate_bin=bid, truth_target=tid))
        elif all(v is not None for v in vals):
            u, i, un, inn = vals
            if i > u or inn > un or (u == 0) != (un == 0) or (i == 0) != (inn == 0) or u < un or i < inn:
                add(out, 'INVALID_OVERLAP_MASS', f'witnesses.overlaps:line={line}', row)
            mass[bid][tid] = (u, i, un, inn)
    if any(not vals for vals in mass.values()):
        return {}, False
    maps_u = {bid: min(vals, key=lambda tid: (-vals[tid][0], tid)) for bid, vals in mass.items()}
    maps_i = {bid: min(vals, key=lambda tid: (-vals[tid][1], tid))
              for bid, vals in mass.items() if sum(v[1] for v in vals.values()) > 0}
    seen_maps = set()
    for line, row in selected_maps:
        bid = row.get('candidate_bin')
        if bid in seen_maps:
            add(out, 'DUPLICATE_TARGET_MAP', f'witnesses.mappings:line={line}', {'candidate_bin': bid})
        seen_maps.add(bid)
        for field, expected in (('map_U', maps_u.get(bid)), ('map_I', maps_i.get(bid, ''))):
            if row.get(field) != expected:
                add(out, 'TARGET_MAP_MISMATCH', f'witnesses.mappings:line={line}.{field}',
                    dict(candidate_bin=bid, observed=row.get(field), recomputed=expected), 'numerical')
    if set(mass) != seen_maps:
        missing(out, 'witnesses.mappings',
                dict(missing_bins=sorted(set(mass) - seen_maps), extra_bins=sorted(seen_maps - set(mass))))
    denominators = {}
    for key, members in (('U_bp', uu), ('I_bp', ii)):
        if members is not None and all(n is not None for n in members.values()):
            denominators[key] = sum(members.values(), Decimal(0))
        else:
            denominators[key] = numeric(source.get(key), out, 'source.' + key)
    if any(v is None or v <= 0 for v in denominators.values()):
        missing(out, 'denominators', 'Positive U and I denominator required.')
        return {}, False
    correct = dict(A=sum((mass[b][t][0] for b, t in maps_u.items()), Decimal(0)),
                   B=sum((mass[b][t][1] for b, t in maps_u.items()), Decimal(0)),
                   C=sum((mass[b][t][1] for b, t in maps_i.items()), Decimal(0)))
    for key, j, witness in (('U_bp', 0, uu), ('I_bp', 1, ii)):
        total = sum((v[j] for rows in mass.values() for v in rows.values()), Decimal(0))
        if total > denominators[key] or (key == 'I_bp' and total != denominators[key]):
            add(out, 'OVERLAP_DENOMINATOR_MISMATCH', 'witnesses.overlaps.' + key,
                dict(overlap_bp=str(total), denominator_bp=str(denominators[key])), 'numerical')
        if witness is not None:
            records = sum((v[j + 2] for rows in mass.values() for v in rows.values()), Decimal(0))
            if records > len(witness) or (key == 'I_bp' and records != len(witness)):
                add(out, 'OVERLAP_RECORDS_MISMATCH', 'witnesses.overlaps.' + key,
                    dict(overlap_records=str(records), witness_records=len(witness)), 'numerical')
    calculated = dict(denominators)
    for stage, c in correct.items():
        d = denominators['U_bp' if stage == 'A' else 'I_bp']
        calculated['correct_bp_' + stage] = c
        calculated['a_' + stage] = c / d
        calculated['f_' + stage] = 2 * c / (d + c)
    out['reconstruction'] = dict(correct_bp={k: str(v) for k, v in correct.items()},
        denominators={k: str(v) for k, v in denominators.items()},
        universe_records=None if uu is None else len(uu), members_records=None if ii is None else len(ii),
        target_maps=dict(U=maps_u, I=maps_i),
        witness_level='AGGREGATE_OVERLAP_RECONCILIATION_NOT_CONTIG_ASSIGNMENT_ORIGIN_VERIFICATION',
        denominator_origin=dict(U='INDEPENDENT_SUPPLIED_MEMBERSHIP' if uu is not None else 'SOURCE_DECLARATION_ONLY',
                                I='INDEPENDENT_SUPPLIED_MEMBERSHIP' if ii is not None else 'SOURCE_DECLARATION_ONLY'))
    out['reconstruction']['membership_fingerprints'] = dict(
        universe=membership_fingerprint(uu), evaluated=membership_fingerprint(ii))
    scope_rows, _ = (load_file(w.get('scope_identity'), 'witnesses.scope_identity', base, out)
                     if w.get('scope_identity') is not None else (None, None))
    for line, row in select(scope_rows, {'family_id': family}, out, 'witnesses.scope_identity', unique=scope_rows is not None):
        for key, expected in denominators.items():
            value = numeric(row.get(key), out, f'witnesses.scope_identity:line={line}.{key}')
            if value is not None and value != expected:
                add(out, 'SCOPE_TOTAL_MISMATCH', f'witnesses.scope_identity:line={line}.{key}',
                    dict(observed=str(value), recomputed=str(expected)), 'numerical')
    return calculated, uu is not None and ii is not None and bool(selected_maps)


def finish_native(out):
    errors = [x for x in out['issues'] if x['severity'] == 'ERROR']
    input_errors = [x for x in errors if x['dimension'] == 'input']
    evidence_missing = [x for x in out['issues'] if x['dimension'] == 'evidence']
    comp = [x for x in out['issues'] if x['dimension'] == 'comparability']
    process = [x for x in out['issues'] if x['dimension'] == 'process']
    out['input_validity'] = 'INVALID' if input_errors else 'VALID'
    out['comparability'] = ('NOT_VERIFIABLE' if input_errors or evidence_missing or any(
        x['severity'] == 'INSUFFICIENT_EVIDENCE' for x in comp) else
        'NOT_DIRECTLY_COMPARABLE' if comp else 'COMPARABLE')
    statuses = [f['status'] for f in out['source_fields']]
    out['source_numerical_verification'] = ('NOT_VERIFIABLE' if input_errors else
        'MISMATCH' if 'MISMATCH' in statuses or any(x['dimension'] == 'numerical' for x in errors) else
        'NOT_VERIFIABLE' if not statuses or 'NOT_VERIFIABLE' in statuses or evidence_missing or
        not out.get('independent_witness_complete', False) else 'VERIFIED_AGAINST_SUPPLIED_WITNESS')
    out['process_artifact_completeness'] = ('INCOMPLETE' if any(x['severity'] == 'ERROR' for x in process)
        else 'NOT_VERIFIABLE' if process else 'COMPLETE')
    invalid = bool(input_errors) or out['source_numerical_verification'] == 'MISMATCH'
    incomplete = (out['source_numerical_verification'] == 'NOT_VERIFIABLE' or
                  out['process_artifact_completeness'] != 'COMPLETE' or out['comparability'] == 'NOT_VERIFIABLE')
    out['validity'] = 'INVALID' if invalid else 'NOT_VERIFIABLE' if incomplete else 'VALID'
    out['category'] = ('INVALID' if invalid else 'INSUFFICIENT_EVIDENCE' if incomplete else
        'VALID_NOT_DIRECTLY_COMPARABLE' if out['comparability'] == 'NOT_DIRECTLY_COMPARABLE' else 'VALID_COMPARABLE')
    return out


def diagnose_artifact(spec, base=Path('.')):
    out = report('artifact')
    out.update(source_files=[], source_fields=[], absolute_numeric_tolerance=str(TOLERANCE),
               source_identity_verification='ACTUAL_BYTES_VS_SUPPLIED_HASH_NOT_AUTHENTICATED',
               independent_witness_complete=False)
    out['comparison_scope'] = 'SINGLE_ARTIFACT_NO_PEER'
    out['limitations'].extend([
        'Receipt/source association and closed artifact inventory are supplied declarations, not authenticated process provenance.',
        'AMBER numerical reconstruction supports six genome-level accuracy/assignment/precision fields only, strict unique hard assignments, positive integer lengths and minimum-length filtering.',
        'BER reconstruction verifies aggregate overlaps and declared many-to-one maps; it does not verify biological truth or contig-to-overlap provenance.'])
    if not isinstance(spec, dict):
        add(out, 'INVALID_MANIFEST', 'spec', 'Expected object.')
        return finish_native(out)
    base = Path(base)
    check_scope(spec, out)
    process_audit(spec, base, out)
    adapter = spec.get('adapter')
    out['adapter'] = adapter
    if adapter not in ('AMBER_RESULTS_V2_0_8', 'BER_DECOMPOSITION_V1'):
        missing(out, 'adapter', 'Unsupported native adapter; no metric semantics inferred.')
        return finish_native(out)
    selector = spec.get('selector')
    keys = ('Sample', 'Tool', 'binning type') if adapter.startswith('AMBER') else ('family_id', 'submission_id')
    if not isinstance(selector, dict) or any(not nonempty(selector.get(k)) for k in keys):
        add(out, 'INVALID_SOURCE_SELECTOR', 'selector', {'required_keys': list(keys)})
        return finish_native(out)
    if adapter.startswith('AMBER') and selector.get('binning type') != 'genome':
        missing(out, 'selector.binning type', 'Only genome-level metrics have implemented semantics.')
        return finish_native(out)
    if not isinstance(spec.get('witnesses', {}), dict):
        add(out, 'INVALID_WITNESSES', 'witnesses', 'Expected file-descriptor object.')
        return finish_native(out)
    rows, identity = load_file(spec.get('source'), 'source', base, out)
    selected = select(rows, selector, out, 'source', unique=True)
    if len(selected) != 1:
        return finish_native(out)
    line, row = selected[0]
    supported = AMBER_FIELDS if adapter.startswith('AMBER') else BER_FIELDS
    metrics = spec.get('metrics')
    if not isinstance(metrics, list) or not metrics or any(not isinstance(k, str) for k in metrics) or len(set(metrics)) != len(metrics):
        add(out, 'INVALID_METRIC_SELECTION', 'metrics', 'Nonempty unique field-name list required.')
        return finish_native(out)
    with localcontext() as context:
        context.prec = 60
        calculated, independent = (amber_recompute(spec, selector, base, out) if adapter.startswith('AMBER')
                                  else ber_recompute(spec, selector, row, base, out))
        out['independent_witness_complete'] = independent
        for field in metrics:
            locator = dict(path=identity['path'], sha256=identity['sha256'],
                           row=line, column=field, selector=selector)
            entry = dict(field=field, locator=locator, observed_raw=row.get(field),
                         observed=None, recomputed=None, delta=None, status='NOT_VERIFIABLE')
            out['source_fields'].append(entry)
            if field not in supported:
                missing(out, 'source.' + field, 'Native field semantics not implemented; never substituted.')
                continue
            if field not in row:
                add(out, 'MISSING_SOURCE_COLUMN', 'source.' + field, {'field': field})
                continue
            observed = numeric(row[field], out, 'source.' + field)
            expected = calculated.get(field)
            entry['observed'] = None if observed is None else str(observed)
            entry['recomputed'] = None if expected is None else str(expected)
            if observed is not None and expected is not None:
                delta = observed - expected
                entry.update(delta=str(delta), status='VERIFIED_AGAINST_SUPPLIED_WITNESS'
                             if abs(delta) <= TOLERANCE else 'MISMATCH')
                if entry['status'] == 'MISMATCH':
                    add(out, 'SOURCE_NUMERICAL_MISMATCH', 'source.' + field,
                        dict(locator=locator, observed=str(observed), recomputed=str(expected), delta=str(delta)),
                        'numerical')
            elif expected is None:
                missing(out, 'source.' + field, 'Independent recomputation unavailable or ratio undefined.')
    return finish_native(out)


def diagnose_artifact_pair(left_spec, right_spec, left_base=Path('.'), right_base=Path('.')):
    """Compare actual independently read native evidence, not scope labels alone."""
    left = diagnose_artifact(left_spec, left_base)
    right = diagnose_artifact(right_spec, right_base)
    out = report('artifact-pair')
    out.update(left=left, right=right, comparison_scope='TWO_ACTUAL_NATIVE_ARTIFACTS',
               differences=[], source_field_differences=[])
    def difference(field, a, b):
        if a != b:
            out['differences'].append(dict(field=field, left=a, right=b))
    for field in SCOPE_FIELDS:
        difference('scope.' + field, left.get('scope', {}).get(field), right.get('scope', {}).get(field))
    difference('adapter', left.get('adapter'), right.get('adapter'))
    lf = left.get('reconstruction', {}).get('membership_fingerprints', {})
    rf = right.get('reconstruction', {}).get('membership_fingerprints', {})
    membership_verified = all(lf.get(k) is not None and rf.get(k) is not None for k in ('universe', 'evaluated'))
    for key in ('universe', 'evaluated'):
        if lf.get(key) is not None and rf.get(key) is not None:
            difference('actual_membership.' + key, lf[key], rf[key])
    # Maps belong to a scored submission. Different submissions are legitimate
    # alternatives, not intrinsically a changed target map for the same identity.
    lsel = left_spec.get('selector', {}) if isinstance(left_spec, dict) else {}
    rsel = right_spec.get('selector', {}) if isinstance(right_spec, dict) else {}
    # Keep unsupported-adapter refusals from the single-artifact audits; their
    # adapter value may be absent, null or non-string, not a string to inspect.
    left_adapter = left.get('adapter')
    is_amber = isinstance(left_adapter, str) and left_adapter.startswith('AMBER')
    same_submission = (lsel.get('Tool') == rsel.get('Tool') if is_amber
                       else lsel.get('submission_id') == rsel.get('submission_id'))
    if same_submission:
        difference('actual_target_maps', left.get('reconstruction', {}).get('target_maps'),
                   right.get('reconstruction', {}).get('target_maps'))
    lvalues = {x['field']: x for x in left.get('source_fields', [])}
    rvalues = {x['field']: x for x in right.get('source_fields', [])}
    difference('selected_native_fields', sorted(lvalues), sorted(rvalues))
    for key in sorted(set(lvalues) & set(rvalues)):
        a, b = lvalues[key], rvalues[key]
        av, bv = a.get('observed'), b.get('observed')
        with localcontext() as ctx:
            ctx.prec = 60
            delta = str(Decimal(bv) - Decimal(av)) if av is not None and bv is not None else None
        out['source_field_differences'].append(dict(field=key, left=av, right=bv, delta=delta,
            left_locator=a['locator'], right_locator=b['locator']))
    out['input_validity'] = 'INVALID' if any(x['input_validity'] == 'INVALID' for x in (left, right)) else 'VALID'
    numerical = [x['source_numerical_verification'] for x in (left, right)]
    out['source_numerical_verification'] = ('MISMATCH' if 'MISMATCH' in numerical else 'NOT_VERIFIABLE'
        if 'NOT_VERIFIABLE' in numerical else 'VERIFIED_AGAINST_SUPPLIED_WITNESS')
    process = [x['process_artifact_completeness'] for x in (left, right)]
    out['process_artifact_completeness'] = ('INCOMPLETE' if 'INCOMPLETE' in process else
        'NOT_VERIFIABLE' if 'NOT_VERIFIABLE' in process else 'COMPLETE')
    out['comparability'] = ('NOT_VERIFIABLE' if not membership_verified or any(
        x['comparability'] == 'NOT_VERIFIABLE' for x in (left, right)) else
        'NOT_DIRECTLY_COMPARABLE' if out['differences'] or any(
        x['comparability'] == 'NOT_DIRECTLY_COMPARABLE' for x in (left, right)) else 'COMPARABLE')
    invalid = out['input_validity'] == 'INVALID' or out['source_numerical_verification'] == 'MISMATCH'
    missing_evidence = out['comparability'] == 'NOT_VERIFIABLE' or out['source_numerical_verification'] == 'NOT_VERIFIABLE' or out['process_artifact_completeness'] != 'COMPLETE'
    out['validity'] = 'INVALID' if invalid else 'NOT_VERIFIABLE' if missing_evidence else 'VALID'
    out['category'] = ('INVALID' if invalid else 'INSUFFICIENT_EVIDENCE' if missing_evidence else
        'VALID_NOT_DIRECTLY_COMPARABLE' if out['comparability'] == 'NOT_DIRECTLY_COMPARABLE' else 'VALID_COMPARABLE')
    out['limitations'].append('Population equality uses order-invariant ID/length fingerprints computed from the loaded witnesses, not declared scope labels. No biological truth or process-origin authentication is implied.')
    return out
