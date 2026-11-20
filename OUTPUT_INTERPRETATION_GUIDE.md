# Read the conclusion, evidence scope and limitations together

This guide describes v0.3.4. Use the companion's separately labelled historical replay for the original validation sets.

Start with the question you actually asked. A correct number can survive a mixed-up receipt. Inspect `receipt_result_binding` before acting on a job: a recorded exit of 0 and the presence of the listed files do not identify their generating run. A conflicting receipt makes the process evidence incomplete; an unbound exit of 0 leaves completion unverified. Neither by itself invalidates a reconstructed number. A matching result digest establishes agreement with the supplied bytes, not the unique origin of identical outputs.

In paired native AMBER output, `sample_comparison` shows the two native sample IDs. Different local namespaces need an explicit shared correspondence; equal contig labels alone are insufficient. `prediction_comparison` distinguishes comparing predictions from replaying one submission. Set both manifests to the same purpose, or give each a stable submission identifier. Changing only a tool display label cannot switch the decision. The native schema below describes the alias format and outcomes.

1. Identify the interface. Generic `compare` is not the native four-axis `artifact` interface. Single-artifact checks do not prove a comparison to an unprovided second result. For actual native peers supply both `--spec` and `--reference-spec`.
2. Read `input_validity` (or generic `validity`), comparability, numerical evidence and process evidence separately. A numerical match does not establish correct scope; matching scope does not establish correct numbers.
3. For interfaces returning an aggregate `validity`, exit 0 can accompany NOT_DIRECTLY_COMPARABLE: inspect the actual conclusion and scope. Exit 2 denotes a detected invalid input/numerical mismatch; exit 3 denotes insufficient evidence. `synthetic-demo` does not aggregate nested reports into its exit code: its exit 0 cannot certify every child diagnostic. A top-level file/JSON error may use a generic error envelope rather than four native axes.
4. `COMPARABLE` on SINGLE_ARTIFACT_NO_PEER means local comparison-admissibility under the inputs/witnesses/declarations actually checked. It is not proof of a second artifact, universally trustworthy provenance, or biological accuracy. Numerical MISMATCH and process INCOMPLETE can coexist with this structural state.
5. Pair counts, reversals, correlations or other descriptive statistics can still be emitted when overall validity/comparability fails. Their presence does not validate their scientific interpretation. Use them as mechanical debugging output only until the relevant input, membership, scope and evidence gates pass. Do not report a rank reversal from invalid or incomparable inputs as a comparable-method performance result.
6. Same row count or bp total does not prove same IDs. Same filter name does not prove same filtered set. Missing universe/witness information cannot be filled by a declaration of the expected answer.

Examples of interpretation:

| Observed native states | Appropriate interpretation |
|---|---|
| VALID, COMPARABLE, VERIFIED_AGAINST_SUPPLIED_WITNESS, COMPLETE; single artifact | Selected fields agree with supplied witnesses and local scope checks passed; no actual peer was compared. |
| VALID, NOT_DIRECTLY_COMPARABLE, VERIFIED_AGAINST_SUPPLIED_WITNESS, COMPLETE; actual pair; exit 0 | Both sides can be legitimate while their evaluation scope differs. Inspect the actual differences, not just exit 0. |
| VALID, COMPARABLE, MISMATCH, COMPLETE; exit 2 | Structural checks did not detect a scope difference, but a selected field or numerical reconstruction consistency check failed. Inspect source_fields and numerical issues; do not use the numbers as validated results. |
| VALID, COMPARABLE, VERIFIED_AGAINST_SUPPLIED_WITNESS, INCOMPLETE; exit 3 | Conditional arithmetic agrees, but supplied process evidence failed. This does not prove the original job itself failed. |
| VALID, NOT_VERIFIABLE, NOT_VERIFIABLE, COMPLETE; exit 3 | File syntax may be legal while required independent evidence is absent. Global numerical verification and comparability were not established; conditional per-field calculations may still be present. |

The four axes are separate dimensions with shared gates, not statistically independent certificates. Every claim remains conditional on the supplied artifacts and implemented formulas. Unsupported adapters must be refused without pretending that their files were validated.

For a pair of AMBER files, read `reference_comparison`. Different labelled reference assignments cannot be made equivalent by matching contig lengths. A changed reference partition and reference-name changes with identical partitions are reported separately. A pure candidate-bin rename leaves a comparable result comparable. If one side cannot supply the required membership, or only aggregates are available, the corresponding reference comparison is unverified.
