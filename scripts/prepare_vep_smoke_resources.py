#!/usr/bin/env python3
"""Prepare pinned local VEP resources without executing experimental inputs."""
import argparse
import gzip
import hashlib
import io
import json
import os
from pathlib import Path, PurePosixPath
import subprocess
import tarfile

COMMIT = 'f479099e2a9cd86887a48cf5c293fd7a208ddfb9'
IMAGE = 'ensemblorg/ensembl-vep@sha256:d0c0ab9697f10f5c8b2c5f65cf51ad9e60254161c02a414db3c85f37ecfa620d'
SOURCE_SHA = '401c50c126e04254ec34993fe5a3c0ba122fa3631114135b1dd5d3ef889f5d42'
VOLUME = 'allelio-vep-cache-v1'


def require(condition):
    if not condition:
        raise ValueError('Pinned VEP resource verification failed; retain local artifacts for inspection.')


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1048576), b''): digest.update(block)
    return digest.hexdigest()


def docker(context, args, **kwargs):
    return subprocess.run(['docker', '--context', context] + args, check=True, capture_output=True, **kwargs)


def cache_inventory(context):
    result = docker(context, ['run', '--rm', '--network', 'none', '--read-only', '--cap-drop', 'ALL',
        '--security-opt', 'no-new-privileges', '--mount', 'type=volume,src='+VOLUME+',dst=/cache,readonly',
        '--entrypoint', '/bin/sh', IMAGE, '-c',
        'test -z "$(find /cache -type l -print)" && find /cache -type f -exec sha256sum {} \\;'])
    return {line.split(None, 1)[1].removeprefix('/cache/'): line.split(None, 1)[0]
            for line in result.stdout.decode().splitlines()}


def verify_image_archive(path):
    """Verify OCI descriptors and every retained blob, not just an inventory label."""
    with tarfile.open(path) as archive:
        index = json.load(archive.extractfile('index.json'))
        expected = IMAGE.split('@')[1]
        require([r['digest'] for r in index['manifests']] == [expected])
        manifest = json.load(archive.extractfile('blobs/sha256/'+expected.split(':')[1]))
        for descriptor in [manifest['config']] + manifest['layers']:
            require(archive.getmember('blobs/sha256/'+descriptor['digest'].split(':')[1]).isfile())
        for member in archive:
            if member.name.startswith('blobs/sha256/') and member.isfile():
                digest = hashlib.sha256()
                with archive.extractfile(member) as source:
                    for block in iter(lambda: source.read(1048576), b''): digest.update(block)
                require(digest.hexdigest() == member.name.split('/')[-1])
        return manifest['config']['digest']


def prepare(root, context):
    root = Path(root).resolve()
    require(not any((p/'.git').exists() for p in (root,*root.parents)))
    source = root / 'ensembl-vep-f479099e.tar.gz'
    image_archive = root / 'vep-116.3-arm64.tar'
    target = root / 'cache-84-GRCh38.tar.gz'
    require(not target.exists() and not (root/'runtime.json').exists())
    existing = subprocess.run(['docker','--context',context,'volume','inspect',VOLUME],capture_output=True)
    require(existing.returncode != 0)
    require(sha(source) == SOURCE_SHA and image_archive.is_file())
    image_config_digest = verify_image_archive(image_archive)
    prefix = 'ensembl-vep-'+COMMIT+'/t/testdata/cache/homo_sapiens/84_GRCh38/'
    inventory = {}
    with tarfile.open(source) as incoming, target.open('xb') as raw, gzip.GzipFile(fileobj=raw, mode='wb', filename='', mtime=0) as zipped, tarfile.open(fileobj=zipped, mode='w') as outgoing:
        for member in incoming:
            if not member.name.startswith(prefix) or member.isdir(): continue
            relative = PurePosixPath(member.name[len(prefix):])
            require(member.isfile() and '..' not in relative.parts and not relative.is_absolute())
            data = incoming.extractfile(member).read()
            name = 'homo_sapiens/84_GRCh38/' + relative.as_posix()
            info = tarfile.TarInfo(name); info.size = len(data); info.mode = 0o644; info.mtime = 0
            outgoing.addfile(info, io.BytesIO(data))
            inventory[name] = hashlib.sha256(data).hexdigest()
    require(inventory and 'homo_sapiens/84_GRCh38/info.txt' in inventory)
    (root/'cache-inventory.json').write_text(json.dumps(inventory,sort_keys=True,indent=2)+'\n')
    inspect = json.loads(docker(context, ['image','inspect',IMAGE]).stdout)[0]
    require(inspect['Architecture'] == 'arm64' and inspect['Os'] == 'linux')
    require(IMAGE in inspect['RepoDigests'])
    help_result = docker(context, ['run','--rm','--network','none','--read-only','--tmpfs','/tmp:rw,noexec,nosuid,size=64m',
        '--cap-drop','ALL','--security-opt','no-new-privileges',IMAGE,'vep','--help'])
    require(b'ensembl-vep          : 116.3' in help_result.stdout)
    (root/'version-help.txt').write_bytes(help_result.stdout)
    docker(context,['volume','create',VOLUME])
    with target.open('rb') as cache:
        docker(context,['run','--rm','-i','--network','none','--read-only','--user','0',
            '--mount','type=volume,src='+VOLUME+',dst=/cache','--entrypoint','tar',IMAGE,'-xzf','-','-C','/cache'],stdin=cache)
    require(cache_inventory(context) == inventory)
    metadata = {'image':IMAGE,'image_id':inspect['Id'],'image_config_digest':image_config_digest,'architecture':'linux/arm64','vep_version':'116.3',
                'source_commit':COMMIT,'cache_version':'84_GRCh38','cache_inventory_sha256':sha(root/'cache-inventory.json'),
                'resources':[
                    {'kind':'software','path':image_archive.name,'sha256':sha(image_archive),'version':'VEP116.3 linux/arm64; '+IMAGE},
                    {'kind':'cache','path':target.name,'sha256':sha(target),'version':'upstream sparse test cache 84_GRCh38; '+COMMIT}]}
    (root/'runtime.json').write_text(json.dumps(metadata,indent=2)+'\n')
    print('Pinned image, complete software archive and exact sparse-cache inventory verified.')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--resources',type=Path,required=True)
    parser.add_argument('--docker-context',required=True)
    args = parser.parse_args(); os.umask(0o077)
    prepare(args.resources,args.docker_context)
