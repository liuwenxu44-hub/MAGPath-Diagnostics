# Portable diagnostic schema v1

Interfaces for the publicly distributed v0.3.2-candidate software. JSON inputs and TSV universe/accounting
tables use the exact fields below. API accepts Python dictionaries/lists. No
third-party dependency, model fitting, external tool execution or data download.

## Comparison

`diagnose_comparison(left, right, universe, config)`

Each independent result object has nonempty string fields `dataset_id`,
`family_id`, `assembly_id`, `policy_id`, `weighting`, `matching`, `score_event`,
`filter_definition`; arbitrary family/policy identities are accepted.

- `members`: list of `{contig_id: string, length_bp: positive integer}`.
- `target_map`: list of `{submission_id: string, candidate_bin_id: string,
  truth_id: string}`; one target per (submission, candidate).
- `results`: list of `{submission_id: string, method: string, version: string,
  workflow_id: string, score: finite number or decimal string}`. Null and `NA`
  mean legally unavailable, not zero and not agreement. Submission IDs unique.
- Optional `declared_totals`: `{records: nonnegative integer, bp: nonnegative
  integer}` is checked against the supplied membership table.
- `provenance`: `{source_id: nonempty string, sha256: 64 hexadecimal characters}`
  is mandatory for evidence completeness and records source identity only.
  Missing provenance is NOT_VERIFIABLE. A declared digest never proves a
  scientific assertion true and is reported as DECLARED_NOT_AUTHENTICATED.

`universe`: independently provided complete assembly ID/length list with the same
two fields as `members`. Each compared evaluation population may be a subset;
IDs and lengths must match the universe. In contrast, accounting rows must cover
the entire universe. A list is an input assertion, not proof of independent
origin. The CLI records actual file SHA-256 separately.

`config`: `{metric_name: string, direction: "higher" | "lower",
representative_rule: "all" | "lexical_submission_per_method"}`. Representative
selection is lexical submission ID per method, separately for each input.
Neither selection changes the membership population. All result identities and
differences remain reported. Exact finite-decimal score arithmetic; no hidden
score tolerance or hard-coded original families/policies.

Output separates `validity` (`VALID`, `INVALID`, `NOT_VERIFIABLE`) from
`comparability` (`COMPARABLE`, `NOT_DIRECTLY_COMPARABLE`, `NOT_VERIFIABLE`).
`category` is `INVALID`, `INSUFFICIENT_EVIDENCE`, `VALID_NOT_DIRECTLY_COMPARABLE`,
or `VALID_COMPARABLE`. Missing required evidence never produces comparable PASS.
Issues have `code`, `location`, `details`, `severity`. Scope, membership, target
map and same-submission identity differences are not evidence of software error.
Changed finite scores alone are legitimate comparable results. Deleted panel
members remove comparison pairs, not population members. Order invariance and
consistent arbitrary renaming are supported, not semantic alias inference.

Exit 0 can accompany VALID_NOT_DIRECTLY_COMPARABLE; it is not a universal
comparability PASS. Descriptive pair statistics can be emitted even when input
or comparison gates fail; in that situation their presence is not validation
and they are debugging output, not evidence of comparable-method performance.
See OUTPUT_INTERPRETATION_GUIDE.md for the native/generic interface distinction.

Numerical output: `score_differences` list of `{submission_id,left_score,
right_score,delta}` (exact decimal strings), `retained_score_changes` count (null
if any retained score pair is unavailable; `observed_finite_score_changes` and
`unassessable_retained_scores` distinguish observed changes from unavailable data);
`panel` contains `left_ids`, `right_ids`, `retained_ids`, `removed_ids`, `added_ids`,
`deleted_pairs`, `added_pairs`, `retained_pairs`; `pairs` contains real pair
states. `differences` reports fields, population IDs, lengths and target maps.

## Accounting

`diagnose_accounting(rows, universe)`: rows contain `contig_id`, `length_bp`,
`candidate_bin_id`, `assignment_status`, `reason_code`. Statuses are `ASSIGNED`,
`UNBINNED`, `TOOL_ABSTAIN`, `HARD_FAIL_INVALID_OUTPUT`. Only ASSIGNED permits and
requires a nonempty candidate. Known reason mappings:

| Reason | Required status |
|---|---|
| EXPLICIT, EXPLICIT_BIN | ASSIGNED |
| EXPLICIT_UNBINNED | UNBINNED |
| OMITTED_UNKNOWN_REASON, TOOL_ABSTAIN | TOOL_ABSTAIN |
| HARD_FAIL_INVALID_OUTPUT, INVALID_OUTPUT | HARD_FAIL_INVALID_OUTPUT |

Unknown nonempty reasons remain unchanged and NOT_VERIFIABLE, never relabelled
as explicit unbinned. Omitted universe IDs are omissions, not unbinned records.
Outputs `total_records`, `total_bp`, `counts`, `base_pairs`, `reason_rows`, and
explicit `missing_ids`, `unknown_ids`, `length_mismatches`.

## Event numeric diagnosis

`diagnose_event(spec)`: `event` is `BINARY` or `CATEGORICAL`,
`probability_support` maps category labels to finite probabilities, `target` is
one label, `filter_scope` and `matching_definition` are nonempty strings, and
`score_definition` is `BRIER`. BINARY has exactly two labels; CATEGORICAL at least
two. Probabilities lie in [0,1], sum to 1 with absolute tolerance 1e-12. Output
`brier` is sum of squared discrepancies from the one-hot target, a mathematical
check only. Arbitrary event semantics and filter truth cannot be inferred.
The additionally supported `CURRENT_ASSIGNMENT_CORRECTNESS` event requires
exactly `CORRECT` and `INCORRECT` support labels. Candidate IDs plus `UNKNOWN`
are not a binary correctness sample space, even when there are two labels.
Optional `probability_event` must agree with `event` if supplied.

Optional `request_aurc`, `confidence_scores`, `confidence_source`, and
`confidence_frozen_provenance` diagnose ordering evidence. AURC is never computed
here: no validated per-example confidence/outcome series is implemented.
`aurc_status` is `NOT_ESTIMABLE`, `aurc` is null. No scores specifically produces
`NO_CONFIDENCE_SCORES`. Hard assignments or target-derived scores cannot supply
prediction-side confidence.

All claims concern the mechanical consistency of supplied evidence only, not
true host assignment, scientific validity of a declared estimand, expression,
activity, pathogenicity, calibrated uncertainty or external biological validation.
