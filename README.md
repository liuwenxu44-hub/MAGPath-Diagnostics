# MAGPath Diagnostics

An evidence-scoped diagnostic layer for comparing metagenomic binning evaluations.
It checks whether reported differences concern the same evaluated contigs,
denominators and targets, and distinguishes valid numbers from an incomplete job.
It complements evaluators such as AMBER; it is not a binner, a new evaluation
metric, a probability estimator or a biological validation method.

## Version and installation

This public distribution packages **v0.3.2-candidate**. The four Python modules
are unchanged from that candidate; publication updates documentation and licensing,
not algorithms or scientific results. The publication tag is `v0.3.2-public.1`.

Download the source from this repository's Releases page, or use **Code → Download
ZIP**, extract it and open a terminal in the extracted source directory. Use
Python 3; the recorded test environment was CPython 3.12.3 on Linux x86_64.
The runtime uses only the Python standard library. No pip installation, AMBER,
binner or reference database is required for the bundled synthetic examples.
`ENVIRONMENT.json` records that historical test environment, not a newly run test
or a bundled environment installer.

```bash
python -B diagnostic_cli.py --help
python -B diagnostic_cli.py --version
python -B diagnostic_cli.py compare --left examples/left.json --right examples/right.json --universe examples/universe.tsv --config examples/config.json
python -B diagnostic_cli.py account --records examples/account.tsv --universe examples/universe.tsv
python -B diagnostic_cli.py event --spec examples/event.json
```

For a self-contained native-shaped example:

```bash
python -B make_native_example.py --output new_example_directory
```

Use a new output directory, then follow its README commands. This generator creates
author-written synthetic artifacts; it does not run AMBER or download research
data. It does not reproduce the original native-tool executions.

## Supply your own results

- `compare`: two independently supplied result JSON files plus an independent
  contig-ID/length universe. See [INPUT_SCHEMA.md](INPUT_SCHEMA.md).
- `account`: reconcile assignment records and reasons against the entire universe.
- `event`: check a declared event, probability support and Brier calculation.
- `artifact`: read supported native result files and available independent
  witnesses. For two native results supply both `--spec` and `--reference-spec`.
  See [NATIVE_ARTIFACT_SCHEMA.md](NATIVE_ARTIFACT_SCHEMA.md).

`diagnostic_cli.py` is the portable entry point. `alignment_diagnostics.py` also
retains an earlier bounded posthoc helper with predefined family/policy labels;
that helper is not the general-purpose input interface.

## Interpret the output

Read the diagnostic fields, not only the exit code. Native artifact reports
separate input validity, comparability, numerical consistency and process/artifact
completeness. Equal contig counts and bp totals do not establish equal membership.
A valid number need not mean a reporting job completed. Missing witnesses cannot
verify a scientific assertion. Generic and native interfaces have different
supported checks, as described in [OUTPUT_INTERPRETATION_GUIDE.md](OUTPUT_INTERPRETATION_GUIDE.md).

Exit 0 may accompany legitimate noncomparability; it is not universal PASS.
Exit 2 signals invalid input/numerical inconsistency, and exit 3 signals unverified
evidence or an incomplete process. `synthetic-demo` does not combine its nested
reports into a diagnostic exit status. AURC is **not computed** by this version.
No output establishes true host assignment, biological activity or clinical risk.
Generated receipts can contain your local input paths and selected input fields;
review them before sharing them publicly.

## Version history and scope

The v0.3.1 repair added duplicate-header names and one-based column locations to
existing TSV rejection messages. It was informed by an observed validation case;
later replays are regression checks, not new holdout evidence. The v0.3.2 repair
guards string-only adapter handling: missing/null/non-string adapters retain the
structured unsupported-adapter refusal instead of raising `AttributeError`.
Neither repair changes the numerical or matching definitions. This publication
does not add a new human trial, fresh independent validation or new experiments.

This is the diagnostic software distribution, not the complete research archive.
It contains no raw CAMI data, sequencing data, retired labels, private validation
answers, participant records, AMBER distribution or third-party software bundle.

## License and support

Copyright © 2026 Wenxu Liu. Available without charge for noncommercial use under
the [MAGPath Diagnostics Noncommercial No-Modification License 1.0](LICENSE.txt).
No registration, individual permission request or material-transfer agreement is
needed for permitted use. Modification, commercial use, sublicensing and onward
distribution otherwise require separate written permission. This is a custom
restricted-use license, **not an OSI open-source license**.

Public GitHub hosting also carries the platform rights described in
[PLATFORM_NOTICE.md](PLATFORM_NOTICE.md), including viewing and forking through
GitHub. These are distinct from a general permission to modify or commercially
use the software. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) and
[SOURCE_INVENTORY.tsv](SOURCE_INVENTORY.tsv).

Questions may be raised through this repository's Issues page. Do not include
private datasets, credentials or personal information in an issue. No support
response time is promised. No published manuscript DOI is assigned here.
