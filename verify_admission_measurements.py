"""Reconcile saved paired samples, source inputs and median table, no retiming."""
import csv
import argparse
import hashlib
import json
import math
from pathlib import Path
import statistics

ROOT=Path(__file__).resolve().parent
SIZES={'generated':(16,64,256),'cartesian':(8,32,128),'cancellation':(128,512,2048)}
MODES=('target','structural','streaming','factorized')
PHASES=('input','producer','store-authority-copy','prepare','commit','challenge',
        'admit','flush','publish','serve','reentry')

def require(condition,message):
    if not condition:
        raise ValueError(message)

def number(value,message):
    require(type(value) in (int,float) and math.isfinite(value) and value>=0,message)
    return value

def validate(raw,summary,environment,bindings,root=ROOT):
    require(environment['workers']==1 and environment['repeats']==3,'Wrong measurement protocol')
    require(environment['modes']==list(MODES),'Wrong mode inventory')
    require(environment['source_inputs_unchanged'] is True,'Unstable measured source')
    require(environment['measurement_processes']==432 and environment['paired_repetitions']==108,
            'Wrong execution denominator')
    expected={(family,n,mode,repeat) for family,sizes in SIZES.items() for n in sizes
              for mode in MODES for repeat in range(3)}
    require(isinstance(raw,list) and len(raw)==108,'Incomplete sample count')
    groups={}
    seen=set()
    for row in raw:
        require(type(row['n']) is int and type(row['repeat']) is int,'Noninteger sample identity')
        key=(row['family'],row['n'],row['mode'],row['repeat'])
        require(key in expected and key not in seen,'Invalid or duplicate sample identity')
        seen.add(key)
        number(row['checker-time']['checker_ns'],'Invalid checker time')
        for section in ('time','lifecycle'):
            sample=row[section]
            require(sample['accepted_and_served'] is True,'Candidate was not admitted and served')
            number(sample['lifecycle_ns'],'Invalid lifecycle time')
            require(tuple(p['phase'] for p in sample['phases'])==PHASES,'Missing lifecycle phase')
            elapsed=[number(p['elapsed_ns'],'Invalid phase time') for p in sample['phases']]
            require(elapsed==sorted(elapsed) and elapsed[-1]<=sample['lifecycle_ns'],'Unordered lifecycle')
            for p in sample['phases']:
                live=number(p['live_python_bytes'],'Invalid live allocation')
                peak=number(p['peak_python_bytes'],'Invalid peak allocation')
                require(peak>=live,'Peak below live allocation')
            for field in ('authority_rows','candidate_rows','candidate_join_rows'):
                require(type(sample[field]) is int and sample[field]>=0,'Invalid row denominator')
                require(sample[field]==row['time'][field],'Traced/untraced input mismatch')
            number(sample['process_peak_rss_bytes'],'Invalid process peak')
        for field in ('aux_peak_python_bytes','aux_live_python_bytes'):
            number(row['aux'][field],'Invalid auxiliary allocation')
        require(row['aux']['aux_peak_python_bytes']>=row['aux']['aux_live_python_bytes'],
                'Auxiliary peak below live allocation')
        number(row['lifecycle']['lifecycle_peak_python_bytes'],'Invalid lifecycle peak')
        number(row['lifecycle']['lifecycle_live_python_bytes'],'Invalid lifecycle live allocation')
        groups.setdefault(key[:3],[]).append(row)
    require(seen==expected,'Missing workload/mode/repetition')
    require(len(summary)==36,'Incomplete summary')
    summaries=set()
    mapping={'checker_ms':('checker-time','checker_ns',1e6),
             'lifecycle_ms':('time','lifecycle_ns',1e6),
             'aux_peak_python_bytes':('aux','aux_peak_python_bytes',1),
             'lifecycle_peak_python_bytes':('lifecycle','lifecycle_peak_python_bytes',1),
             'lifecycle_live_python_bytes':('lifecycle','lifecycle_live_python_bytes',1),
             'untraced_peak_rss_bytes':('time','process_peak_rss_bytes',1)}
    for row in summary:
        key=(row['family'],int(row['n']),row['mode'])
        require(key in groups and key not in summaries,'Invalid summary identity')
        summaries.add(key)
        require(int(row['repeats'])==3,'Summary repetition mismatch')
        samples=groups[key]
        for field in ('authority_rows','candidate_rows','candidate_join_rows'):
            require(all(s['time'][field]==int(row[field]) for s in samples),'Summary row-count mismatch')
        for field,(section,name,scale) in mapping.items():
            observed=number(float(row[field]),'Invalid summary quantity')
            calculated=statistics.median(s[section][name] for s in samples)/scale
            require(math.isclose(observed,calculated,rel_tol=1e-12,abs_tol=1e-9),'Median mismatch: '+field)
    require(bindings['normalization']=='UTF-8/LF','Unknown source normalization')
    files=bindings['files']
    expected_files={'admission_benchmark.py',*(str(p.relative_to(root)).replace('\\','/')
                       for p in (root/'recovery').glob('*.py')),
                    *(f'inputs/generated-{n}.json' for n in (16,64,256))}
    actual_files={name.replace('\\','/') for name in files}
    require(actual_files==expected_files,'Incomplete measured source/input snapshot')
    for name,expected_digest in files.items():
        path=(root/name.replace('\\','/')).resolve()
        require(path.is_relative_to(root.resolve()),'Source path escapes artifact')
        payload=path.read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8')
        require(hashlib.sha256(payload).hexdigest()==expected_digest,'Measured source/input changed: '+name)
    if 'collection_driver' in bindings:
        driver=bindings['collection_driver']
        require(driver['file']=='collect_admission_measurements.py','Unknown collection driver')
        payload=(root/driver['file']).read_text(encoding='utf-8').replace('\r\n','\n').encode('utf-8')
        require(hashlib.sha256(payload).hexdigest()==driver['digest'],'Collection driver changed')
    return dict(samples=108,combinations=36,measurement_processes=432,source_inputs=len(files),matched=True)

def table_tex(summary):
    lookup={(r['family'],int(r['n']),r['mode']):r for r in summary}
    lines=[r'\begin{table}[t]',r'\centering',r'\caption{Paired admission and recovery costs.}',
           r'\label{tab:lifecycle}',r'\small',
           r'\begin{tabularx}{\textwidth}{@{}L{2.2cm}Y r r r r@{}}',r'\toprule',
           r'Case & Mode & Checker ms & Lifecycle ms & Aux KiB & Peak MiB \\',r'\midrule']
    for family,n,label in (('generated',256,'Generated-256'),('cartesian',128,'Cartesian-128'),
                           ('cancellation',2048,'Cancel-2048')):
        if family!='generated':lines.append(r'\midrule')
        for i,(mode,name) in enumerate(zip(MODES,('SQL-target','Structural','Sorted merge','Factorized'))):
            row=lookup[(family,n,mode)]
            values=(float(row['checker_ms']),float(row['lifecycle_ms']),
                    float(row['aux_peak_python_bytes'])/1024,
                    float(row['lifecycle_peak_python_bytes'])/(1024**2))
            lines.append((label if i==0 else '')+' & '+name+' & '+
                         ' & '.join((f'{values[0]:.2f}',f'{values[1]:.2f}',
                                     f'{values[2]:.2f}',f'{values[3]:.3f}'))+r' \\')
    lines.extend((r'\bottomrule',r'\end{tabularx}',r'\end{table}'))
    return '\n'.join(lines)+'\n'

def verify_saved(paper=None, folder=None, root=ROOT):
    folder=ROOT/'results/admission-paired' if folder is None else Path(folder)
    raw=json.loads((folder/'raw.json').read_text())
    with (folder/'summary.csv').open(newline='') as stream:
        summary=list(csv.DictReader(stream))
    environment=json.loads((folder/'environment.json').read_text())
    bindings=json.loads((folder/'source-inputs.json').read_text())
    result=validate(raw,summary,environment,bindings,root=root)
    if paper is not None:
        require(paper.is_dir(),'Manuscript directory missing')
        (paper/'generated-lifecycle.tex').write_text(table_tex(summary),encoding='utf-8')
    return result

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paper',type=Path,help='Optional existing manuscript directory for the derived table')
    parser.add_argument('--results',type=Path,help='Paired result directory; defaults to the retained adopted run')
    args=parser.parse_args()
    print(json.dumps(verify_saved(args.paper,folder=args.results)))
