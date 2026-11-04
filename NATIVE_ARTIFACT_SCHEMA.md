# Native artifact manifest — v0.3.2-candidate

Run `python -B diagnostic_cli.py artifact --spec manifest.json`. The implementation
uses the Python standard library and writes JSON to stdout only. Relative paths
are resolved against the manifest directory. Existing compare/account/event
interfaces retain their v1 schema. Unknown cached values are never used.

Every file descriptor is `{ "path": "relative/or/absolute/path", "sha256":
"64 hexadecimal characters" }`. The declared digest is compared with actual
bytes and both are reported. Missing digests cannot establish verified evidence;
a syntactically valid digest alone is not authentication. Do not create a digest
after changing a file and call it a check against an earlier frozen generation.

## AMBER v2.0.8 results.tsv

```json
{
  "adapter": "AMBER_RESULTS_V2_0_8",
  "source": {"path": "results.tsv", "sha256": "REPLACE_WITH_ACTUAL_SHA256"},
  "selector": {"Sample": "sample", "Tool": "query", "binning type": "genome"},
  "metrics": ["accuracy_bp", "accuracy_seq", "percentage_of_assigned_bps",
              "percentage_of_assigned_seqs", "precision_weighted_bp", "precision_weighted_seq"],
  "scope": {
    "dataset_id": "synthetic", "family_id": "synthetic", "assembly_id": "assembly",
    "policy_id": "minimum_length_0", "weighting": "BASE_PAIRS",
    "matching": "MANY_TO_ONE", "score_event": "DECLARED_CORRECT_ASSIGNMENT",
    "filter_definition": "minimum_length_0"
  },
  "minimum_length": 0,
  "witnesses": {
    "truth": {"path": "truth.tsv", "sha256": "REPLACE_WITH_ACTUAL_SHA256"},
    "query": {"path": "query.tsv", "sha256": "REPLACE_WITH_ACTUAL_SHA256"}
  },
  "process": {
    "receipt": {"path": "receipt.json", "sha256": "REPLACE_WITH_ACTUAL_SHA256"},
    "required_artifacts": [{"path": "results.tsv", "sha256": "REPLACE_WITH_ACTUAL_SHA256"}],
    "logs": []
  }
}
```

Source is the actual AMBER TSV, not a JSON summary carrying cached AMBER values.
Selector must identify exactly one source row. Only the six listed fields and
genome-level results are supported. Assignment percentages are fractions, not
0–100 percentages. Recall, F1, ARI and other native fields are not substituted
with an accuracy calculation: selecting unsupported semantics returns
NOT_VERIFIABLE. No AMBER, binner or dependency installation is performed.

Truth/query use a single-sample Biobox table with `@SampleID:sample`, header
`@@SEQUENCEID<TAB>BINID<TAB>LENGTH` for truth and
`@@SEQUENCEID<TAB>BINID` for query. Truth LENGTH is a positive integer. Optional
query LENGTH must agree with truth. Truth is the supplied independent universe;
all query IDs must exist in truth, including IDs excluded by the minimum length.
SampleID must match selected source Sample. Contig and bin IDs must be nonempty.
Minimum length is an inclusive nonnegative integer threshold. No other AMBER
filter is reconstructed. Query omissions are preserved, not assigned a causal
reason or relabelled explicit unbinned. Empty query is permitted, but precision
with zero assigned denominator is undefined. Empty filtered universe cannot
verify ratios. Duplicate hard assignments are rejected even if exact repeats;
subtypes are SAME_BIN_REPEAT and CONFLICTING_ASSIGNMENT. This intentionally
strict workflow contract is not a claim that AMBER cannot accept multiple bins.

For each candidate bin, bp and sequence overlaps independently choose their
largest truth overlap. Lexical truth ID breaks ties. Accuracy divides the sum
of these maxima by filtered truth bp or records; precision divides by assigned
bp or records. These two maps can differ. Aggregate agreement is a mechanical
witness check, not authentic biological truth or host-assignment validation.

## Existing BER decomposition TSV

Use adapter `BER_DECOMPOSITION_V1`, source `decomposition_by_submission.tsv`,
selector `{ "family_id": "family", "submission_id": "submission" }`, and
metrics selected from `U_bp`, `I_bp`, `correct_bp_A`, `correct_bp_B`,
`correct_bp_C`, `a_A`, `a_B`, `a_C`, `f_A`, `f_B`, `f_C`.

Witness descriptor keys:

- `overlaps`: TSV fields family_id, submission_id, candidate_bin, truth_target,
  U_bp, I_bp, U_records, I_records; one row per bin/target. Nonnegative integers,
  I mass/records cannot exceed U, positive-length record constraints apply.
- `mappings`: TSV fields family_id, submission_id, candidate_bin, map_U, map_I.
  Existing additional fields are retained at source but not silently verified.
  Empty-on-I bins use empty map_I. All selected overlap bins require map rows.
- `universe`, `members`: separate TSVs with contig_id (or record_id), length_bp,
  optionally family_id. Members must be a length-consistent subset of universe.
  Their sums provide independent U and I denominators. The I witness is the
  original frozen intersection, never recomputed from a selected method panel.
- Optional `scope_identity`: existing family-level U_bp/I_bp scope TSV. These
  totals are checked but never replace an independent universe membership file.

Without universe or member witnesses, conditional aggregate arithmetic is still
shown, using the source's explicitly labelled denominator declaration where
needed. Missing membership evidence prevents global VERIFIED; the global state
is NOT_VERIFIABLE unless an observed numerical mismatch takes precedence under
the input-error gate. Never
fabricate U membership from an aggregate bp value. Overlap verification checks
sufficient aggregate totals, maps, integer constraints and I record conservation;
it does not establish the provenance of each contig-to-overlap assignment.
A uses U map/U denominator; B uses U map/I denominator; C uses I map/I denominator.
a = correct/denominator; f = 2*correct/(denominator+correct). No new estimand,
optimization rule, population intersection or scientific ranking is introduced.

## Receipts, comparison and output

Receipt is a JSON object with integer `exit_code`. A nonzero exit means source
process incomplete, not automatic invalidation of finite numeric outputs.
`required_artifacts` is a nonempty supplied closed list. Missing declared files
or mismatched actual hashes make completeness INCOMPLETE. Missing receipt/list
is NOT_VERIFIABLE. Optional `logs` descriptors are read and hashed; basename
stdout/stderr is also reconciled with receipt stdout_sha256/stderr_sha256 when
those keys exist. Hashes do not authenticate job/result association. Time expiry
and origin authentication are unsupported; no timestamp implies freshness.

Scope requires the same eight nonempty declaration fields as compare. Optional
`reference_scope` contains those eight fields; differences produce
NOT_DIRECTLY_COMPARABLE when higher-priority input/evidence gates do not require
NOT_VERIFIABLE, without making syntactically valid inputs invalid.
Scope declarations and their scientific meanings are not authenticated. Adapter
numeric semantics above do not change when arbitrary scope labels are supplied.
Single-artifact output explicitly states `comparison_scope=SINGLE_ARTIFACT_NO_PEER`;
COMPARABLE there means local comparison-admissibility within the inputs,
required witnesses and declarations this implementation checked, not merely
coherent declarations and not a verified comparison with an unprovided peer.
Numerical MISMATCH or process INCOMPLETE can coexist with that structural state;
read all four axes and the overall status. This is a prospective v0.3.2 wording
clarification, not a revision of old case expectations. For an actual pair, use `artifact --spec
left.json --reference-spec right.json`. Each manifest is read independently and
resolved against its own directory. Pair output embeds left/right audits and
compares computed order-invariant universe/evaluation ID+length fingerprints,
scope declarations, selected native fields and same-submission target maps.
Changing actual membership with identical scope labels is still a difference.
If either membership witness is absent, pair comparability is NOT_VERIFIABLE.
Changed finite source values alone are not a comparability failure.

Four separate output axes:

- input_validity: VALID or INVALID (file/schema/membership checks).
- comparability: COMPARABLE, NOT_DIRECTLY_COMPARABLE or NOT_VERIFIABLE.
- source_numerical_verification: VERIFIED_AGAINST_SUPPLIED_WITNESS, MISMATCH or
  NOT_VERIFIABLE. Absolute numeric tolerance is explicitly 1e-12.
- process_artifact_completeness: COMPLETE, INCOMPLETE or NOT_VERIFIABLE.

`source_fields` records actual source path, actual hash, one-based TSV line,
selector and column, raw observed value, parsed value, recomputed value, delta
and per-field status. A field can have conditional overlap agreement while the
global numerical gate remains NOT_VERIFIABLE because independent U is absent.
`source_files` contains actual byte identities for every read artifact.
Issues include code, location, actual details, dimension and severity.
Duplicate TSV header rejection includes actual `observed_header`,
`header_line=1`, and `duplicate_columns` with exact field names and one-based
column `positions`; malformed headers are still rejected, never repaired silently.
Legacy umbrella `validity/category` yields exit 2 for invalid input or numerical
mismatch, exit 3 for incomplete evidence/process, exit 0 only for otherwise valid
complete evidence (including legitimate scope differences). COMPLETE is only
within the supplied inventory, never a claim that all possible native outputs
or an external publication release are complete.
