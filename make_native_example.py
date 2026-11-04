"""Create a new, clearly synthetic native-shaped TSV example; never run AMBER."""
import argparse
import hashlib
import json
from pathlib import Path


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output', required=True)
    a = p.parse_args()
    out = Path(a.output)
    # Fresh only: never overwrite a user directory or mix generations.
    out.mkdir(parents=True, exist_ok=False)
    files = {
        'truth.tsv': '@Version:0.9.0\n@SampleID:synthetic\n@@SEQUENCEID\tBINID\tLENGTH\na\tG1\t40\nb\tG1\t30\nc\tG2\t30\n',
        'query.tsv': '@Version:0.9.0\n@SampleID:synthetic\n@@SEQUENCEID\tBINID\na\tX\nc\tX\nb\tY\n',
        'results.tsv': 'Sample\tTool\tbinning type\taccuracy_bp\tpercentage_of_assigned_bps\tprecision_weighted_bp\nsynthetic\tquery\tgenome\t0.7\t1.0\t0.7\n',
        'receipt.json': json.dumps({'exit_code': 0, 'source': 'AUTHOR_CREATED_SYNTHETIC_NATIVE_SHAPED_FIXTURE_NOT_AMBER_EXECUTION'}, indent=2) + '\n',
    }
    for name, content in files.items():
        with (out / name).open('x', encoding='utf-8', newline='') as f:
            f.write(content)
    def descriptor(name):
        return dict(path=name, sha256=hashlib.sha256((out / name).read_bytes()).hexdigest())
    scope = dict(dataset_id='synthetic', family_id='synthetic', assembly_id='synthetic',
                 policy_id='min0', weighting='BASE_PAIRS', matching='MANY_TO_ONE',
                 score_event='DECLARED_CORRECT_ASSIGNMENT', filter_definition='minimum_length_0')
    manifest = dict(adapter='AMBER_RESULTS_V2_0_8', source=descriptor('results.tsv'),
        selector={'Sample': 'synthetic', 'Tool': 'query', 'binning type': 'genome'},
        metrics=['accuracy_bp', 'percentage_of_assigned_bps', 'precision_weighted_bp'], scope=scope,
        minimum_length=0, witnesses=dict(truth=descriptor('truth.tsv'), query=descriptor('query.tsv')),
        process=dict(receipt=descriptor('receipt.json'), required_artifacts=[descriptor('results.tsv')]))
    with (out / 'manifest.json').open('x', encoding='utf-8') as f:
        f.write(json.dumps(manifest, indent=2) + '\n')
    with (out / 'README.md').open('x', encoding='utf-8') as f:
        f.write('# Author-created synthetic native-shaped example\n\nNot output from an AMBER run. '
                'Truth mass=100, query bin X matches G1 mass40 and Y matches G1 mass30: '
                'accuracy=precision=.7, assigned fraction=1.0.\n\n'
                'Run from the software directory: `python -B diagnostic_cli.py artifact --spec '
                + str(out / 'manifest.json') + '`\n')
    print(out / 'manifest.json')


if __name__ == '__main__':
    main()
