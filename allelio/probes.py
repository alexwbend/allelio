"""Conservative opt-in custom-probe recovery from an explicitly supplied mapping."""
import gzip
import json
import re
from dataclasses import replace
from pathlib import Path
from allelio.parsers.base import ParsedVariants, detect_format


def load_mapping(path):
    value=json.loads(Path(path).read_text())
    if not isinstance(value,dict) or value.get('schema')!='allelio-probes/1':
        raise ValueError('Unsupported probe mapping schema.')
    for field in ('source','version','license','source_url'):
        if not isinstance(value.get(field),str) or not value[field].strip():
            raise ValueError('Probe mapping requires source, version, license and source_url provenance.')
    if value.get('product')!='23andme-raw' or value.get('assembly') not in ('GRCh37','GRCh38') or value.get('strand')!='+':
        raise ValueError('Only explicitly declared 23andme-raw, GRCh37/38, plus-strand mappings are supported.')
    if not isinstance(value.get('entries'),list): raise ValueError('Mapping entries must be a list.')
    for row in value['entries']:
        if not isinstance(row,dict) or not re.fullmatch(r'i\d+',str(row.get('probe',''))) or not re.fullmatch(r'rs\d+',str(row.get('rsid',''))):
            raise ValueError('Mapping entries need internal probe IDs and explicit rsIDs.')
        if type(row.get('position')) is not int or row['position']<=0 or row.get('chromosome') not in [str(n) for n in range(1,23)]+['X','Y']:
            raise ValueError('Mapping entries need positive coordinates and supported chromosomes.')
        if any(not isinstance(row.get(k),str) or not row[k] for k in ('ref','alt')):
            raise ValueError('Mapping entries need explicit REF and ALT.')
    return value


def input_context(path):
    """Read declarations, not filenames or a presumed build for all array files."""
    products=set(); builds=set()
    opener=gzip.open if str(path).endswith('.gz') else open
    with opener(path,'rt') as source:
        for line in source:
            if not line.startswith('#'):
                if line.strip(): break
                continue
            if '23andMe' in line or line.strip()=='# Allelio product: 23andme-raw': products.add('23andme-raw')
            builds.update('GRCh'+n for n in re.findall(r'(?:GRCh|[Bb]uild\s+)(37|38)\b',line))
    return (next(iter(products)) if len(products)==1 else None,
            next(iter(builds)) if len(builds)==1 else None)


def recover_probes(variants, path, mapping, db):
    product,build=input_context(path)
    context_ok=detect_format(str(path))=='23andme' and product==mapping['product'] and build==mapping['assembly']
    by_probe={}
    for row in mapping['entries']: by_probe.setdefault(row['probe'],[]).append(row)
    output=[]
    for variant in variants:
        if not variant.rsid.startswith('i'):
            output.append(variant);continue
        rows=by_probe.get(variant.rsid,[])
        recovery={'original_probe':variant.rsid,'observed_genotype':variant.genotype,
                  'source':mapping['source'],'version':mapping['version'],
                  'assembly':build,'status':'unresolved','reason':None,'identity':None}
        reason=None; identity=None
        if not context_ok: reason='missing_or_conflicting_product_build'
        elif not rows: reason='probe_not_mapped'
        elif len({(r['rsid'],r['chromosome'],r['position'],r['ref'],r['alt']) for r in rows})!=1:
            reason='conflicting_mapping'; recovery['status']='conflicting'
        else:
            row=rows[0]; ref,alt=row['ref'],row['alt']
            if len(ref)!=1 or len(alt)!=1 or ref not in 'ACGT' or alt not in 'ACGT' or ref==alt:
                reason='unsupported_alleles'
            elif {ref,alt} in ({'A','T'},{'C','G'}): reason='strand_ambiguous'
            elif variant.chromosome!=row['chromosome'] or variant.position!=row['position']: reason='coordinate_mismatch'
            elif len(variant.genotype) not in (1,2) or not set(variant.genotype)<=set(ref+alt): reason='allele_mismatch'
            else:
                identity={'rsid':row['rsid'],'assembly':build,'chromosome':row['chromosome'],
                          'position':row['position'],'ref':ref,'alt':alt}
                # Require an unambiguous installed source anchor. Multiple
                # locations/alleles are outside this first bounded recovery path.
                anchors={(r.get('assembly'),r.get('chromosome'),r.get('position_vcf'),r.get('ref_allele'),r.get('alt_allele'))
                         for r in db.lookup_rsid(row['rsid'])['clinvar']}
                if anchors!={(build,row['chromosome'],row['position'],ref,alt)}:
                    reason='reference_identity_unresolved'
                else:
                    recovery.update(status='recovered',reason='explicit_mapping_and_reference_match',identity=identity)
                    output.append(replace(variant,rsid=row['rsid'],probe_recovery=recovery));continue
        recovery['reason']=reason
        output.append(replace(variant,probe_recovery=recovery))
    return ParsedVariants(output,getattr(variants,'audit',None))
