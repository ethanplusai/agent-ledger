#!/usr/bin/env python3
"""Build a source-only ZIP from the scanned prospective Git publication set."""
import hashlib
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]


def main():
    subprocess.run([sys.executable,str(ROOT/'scripts'/'check_public_tree.py')],cwd=ROOT,check=True)
    paths=subprocess.check_output(['git','ls-files','-z','--cached','--others','--exclude-standard'],cwd=ROOT)
    out=ROOT/'dist';out.mkdir(exist_ok=True)
    archive=out/'agent-ledger-0.1.0.zip'
    with zipfile.ZipFile(archive,'w',compression=zipfile.ZIP_DEFLATED) as bundle:
        for raw in sorted(set(paths.split(b'\0'))):
            if not raw:continue
            relative=raw.decode();path=ROOT/relative
            if not path.is_file() or relative.startswith('dist/'):continue
            entry=zipfile.ZipInfo('agent-ledger-0.1.0/'+relative,(2026,9,12,0,0,0))
            entry.compress_type=zipfile.ZIP_DEFLATED;entry.external_attr=0o100644<<16
            bundle.writestr(entry,path.read_bytes())
    checksum=hashlib.sha256(archive.read_bytes()).hexdigest()
    (out/'SHA256SUMS').write_text(checksum+'  '+archive.name+'\n',encoding='ascii')
    print('Built dist/'+archive.name+' with SHA256SUMS.')


if __name__=='__main__':main()
