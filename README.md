# MAGPath Diagnostics

Equal contig counts do not mean two metagenomic binning evaluations scored the same sequences. MAGPath Diagnostics checks which contigs each result covers and how bins were matched to references before comparing the reported scores. It reads existing results; it does not run a binner or introduce a new accuracy metric.

**[Download MAGPath Diagnostics v0.3.4](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/releases/download/v0.3.4/MAGPath_Diagnostics_v0.3.4.zip)**. This is the software ZIP supplied in Additional file 3 of the manuscript. Its checksum is on the [release page](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/releases/tag/v0.3.4). **Code → Download ZIP** on `main` gives you the [older v0.3.2 code](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/tree/v0.3.2-public.1), not the manuscript version.

## Try a comparison

Extract the ZIP, then open a terminal in `MAGPath_Diagnostics_v0.3.4/`, the folder containing `diagnostic_cli.py`. The example runs with Python 3 (tested with CPython 3.12.3 on Linux) and the standard library. You do not need to install packages, run AMBER, or download data.

```bash
python3 -B diagnostic_cli.py --version
python3 -B diagnostic_cli.py compare \
  --left examples/left.json --right examples/right.json \
  --universe examples/universe.tsv --config examples/config.json
```

The first command prints `0.3.4`. In the synthetic example, both results cover the same two contigs (150 bp). Submission `s1` goes from 0.6 to 0.8, while `s2` stays at 0.7. Look for `"comparability": "COMPARABLE"` and `"STRICT_REVERSAL": 1` in the JSON: the two submissions switch rank on the same contigs. This command compares the supplied scores and bin-to-reference maps; it does not reconstruct the scores from reference assignments.

## Use your own results

| If you want to… | Use |
| --- | --- |
| Compare two sets of scores without assuming their denominators match | `compare`: supply two result JSON files and a separate list of contig IDs and lengths. See the [input formats](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/blob/v0.3.4/INPUT_SCHEMA.md). |
| Account for every contig, including those omitted without a known reason | `account`: check the status and reason recorded for each contig against the full assembly list. An omission alone does not establish that the tool filtered the contig. |
| Check whether a probability refers to the event being scored | `event`: supply the event, target and probabilities. It checks their stated support and calculates the Brier score. It does not estimate probabilities or compute the area under a risk–coverage curve. |
| Check evaluator output against its source records | `artifact`: for AMBER 2.0.8, check six genome-binning fields against the supplied reference and query assignments. To compare two native results, provide both `--spec` and `--reference-spec`. See [supported files and fields](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/blob/v0.3.4/NATIVE_ARTIFACT_SCHEMA.md). |

A native report separates input validity, comparability, numerical agreement and evidence that the job finished. A score can agree with the source records even if a required report is missing. Two valid results can also return `NOT_DIRECTLY_COMPARABLE` with exit code 0. See the [guide to interpreting output](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/blob/v0.3.4/OUTPUT_INTERPRETATION_GUIDE.md).

## License and support

You can run the unmodified software free of charge for noncommercial use, without registration. Modification, commercial use and redistribution require separate written permission, subject to the [license](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/blob/v0.3.4/LICENSE.txt) and [GitHub platform notice](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/blob/v0.3.4/PLATFORM_NOTICE.md). This is not an OSI open-source license. The ZIP contains author-written synthetic examples, not raw benchmark data or AMBER itself. See the [third-party notices](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/blob/v0.3.4/THIRD_PARTY_NOTICES.md).

For questions, [open an issue](https://github.com/liuwenxu44-hub/MAGPath-Diagnostics/issues). Remove private file paths and data from diagnostic output before sharing it.

Copyright © 2026 Wenxu Liu.
