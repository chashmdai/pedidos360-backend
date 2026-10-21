"""Explicit, scoped EP3 publication. No cloud operations, credentials printed or global Git changes.

prepare preserves the former workspace Git and creates two independent main
branches. push requires the human-authorized replacement flag, uses the existing
credential manager and force-with-lease only against the two fixed destinations.
"""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import urllib.request

BACKEND=Path(__file__).resolve().parent.parent
WORKSPACE=BACKEND.parent
STATE=Path.home()/'.local/state/pedidos360-ep3/publication'
STATE.mkdir(parents=True,exist_ok=True,mode=0o700)
JOURNAL=STATE/'publication.json'
REPOS={name:WORKSPACE/name for name in ('pedidos360-backend','pedidos360-frontend')}
URLS={name:'https://github.com/chashmdai/'+name+'.git' for name in REPOS}
ENV={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'}

def git(path,*args,input=None,auth=False):
    command=['git','-c','safe.directory='+str(WORKSPACE),'-c','safe.directory='+str(path)]
    if auth:command+=['-c','credential.helper='+str(STATE/'credential-helper'),'-c','credential.interactive=never']
    command+=['-C',str(path),*args]
    return subprocess.check_output(command,input=input,text=True,env=ENV,stderr=subprocess.STDOUT).strip()

def save(state):JOURNAL.write_text(json.dumps(state,indent=2)+'\n');JOURNAL.chmod(0o600)

def move_metadata(source,destination):
    assert source.name=='.git' and source.parent in (WORKSPACE,*REPOS.values())
    assert destination.parent==WORKSPACE and destination.name.startswith('.pedidos360-')
    assert source.is_dir() and not source.is_symlink() and not destination.exists()
    try:os.rename(source,destination)
    except PermissionError:
        def win(path):return 'C:\\'+str(path.relative_to('/mnt/c')).replace('/','\\')
        ps=r'''
$ErrorActionPreference='Stop'
$base=[IO.Path]::GetFullPath('C:\Users\Benja\Documents\cloudnative\ev1')
$src=[IO.Path]::GetFullPath('SOURCE_PATH')
$dst=[IO.Path]::GetFullPath('DESTINATION_PATH')
if(-not $src.StartsWith($base+'\') -or [IO.Path]::GetFileName($src) -ne '.git'){throw 'Invalid source'}
if([IO.Path]::GetDirectoryName($dst) -ne $base -or -not [IO.Path]::GetFileName($dst).StartsWith('.pedidos360-')){throw 'Invalid destination'}
if(Test-Path -LiteralPath $dst){throw 'Backup exists'}
if((Get-Item -LiteralPath $src -Force).Attributes -band [IO.FileAttributes]::ReparsePoint){throw 'Refuse symlink'}
Move-Item -LiteralPath $src -Destination $dst -Force
'''.replace('SOURCE_PATH',win(source)).replace('DESTINATION_PATH',win(destination))
        subprocess.run(['/mnt/c/Windows/System32/WindowsPowerShell/v1.0/powershell.exe','-NoProfile','-NonInteractive',
            '-EncodedCommand',base64.b64encode(ps.encode('utf-16-le')).decode()],check=True,capture_output=True)
    assert destination.is_dir() and not source.exists()

def prepare():
    if JOURNAL.exists():
        state=json.loads(JOURNAL.read_text())
        if state.get('prepared'):
            for name,path in REPOS.items():assert git(path,'remote','get-url','origin')==URLS[name]
            print('Already prepared; preserving existing commits.');return
        assert Path(state['metadataBackup']).is_dir() and not (WORKSPACE/'.git').exists()
        author=git(WORKSPACE,'--git-dir='+state['metadataBackup'],'show','-s','--format=%an')
        email=git(WORKSPACE,'--git-dir='+state['metadataBackup'],'show','-s','--format=%ae')
    else:
        assert WORKSPACE==Path('/mnt/c/Users/Benja/Documents/cloudnative/ev1')
        assert all(path.resolve().parent==WORKSPACE.resolve() and path.is_dir() for path in REPOS.values())
        assert (WORKSPACE/'.git').is_dir() and not (WORKSPACE/'.git').is_symlink()
        for path in REPOS.values():
            assert git(path,'rev-parse','--show-toplevel')==str(WORKSPACE)
            assert not (path/'.git').exists()
        author=git(WORKSPACE,'show','-s','--format=%an').strip()
        email=git(WORKSPACE,'show','-s','--format=%ae').strip()
        state=dict(at=datetime.now(timezone.utc).isoformat(),originalCommit=git(WORKSPACE,'rev-parse','HEAD'),repos={})
        bundle=STATE/'workspace-before-split.bundle'
        git(WORKSPACE,'bundle','create',str(bundle),'--all');git(WORKSPACE,'bundle','verify',str(bundle))
        backup=WORKSPACE/('.pedidos360-root-git-backup-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
        move_metadata(WORKSPACE/'.git',backup)
        state.update(metadataBackup=str(backup),bundleBackup=str(bundle));save(state)
    assert author and re.fullmatch(r'[^\s@]+@[^\s@]+\.[^\s@]+',email)
    for name,path in REPOS.items():
        if name in state['repos']:
            assert git(path,'rev-parse','HEAD')==state['repos'][name]['commit']
            continue
        if (path/'.git').is_dir():
            assert not (path/'.git/HEAD').exists(), 'Refuse to archive an unexpected existing repository'
            move_metadata(path/'.git',WORKSPACE/('.pedidos360-incomplete-'+name+'-git-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')))
        native_dir=STATE/name/'git'
        native_dir.parent.mkdir(parents=True,exist_ok=True)
        git(path,'init','-b','main','--separate-git-dir='+str(native_dir))
        git(path,'config','user.name',author);git(path,'config','user.email',email)
        git(path,'config','core.autocrlf','false');git(path,'config','core.filemode','false')
        git(path,'remote','add','origin',URLS[name])
        assert git(path,'rev-parse','--show-toplevel')==str(path)
        assert git(path,'remote','get-url','--push','origin')==URLS[name]
        git(path,'add','--','.')
        files=git(path,'ls-files','-z').split('\0')
        files=[f for f in files if f]
        assert files and not any(any(part in f.split('/') for part in ('node_modules','target','dist','.git','tmp','.venv')) for f in files)
        assert not any(f.startswith('.env') and f!='.env.example' for f in files)
        assert not any(f.endswith(('.pem','.key','.har','.trace.zip')) or f.endswith('-password') for f in files)
        git(path,'update-index','--chmod=-x','-z','--stdin',input='\0'.join(files)+'\0')
        executable=[f for f in files if f.endswith('.sh') or f=='mvnw']
        if executable:git(path,'update-index','--chmod=+x','--',*executable)
        if name=='pedidos360-backend':
            assert 'docs/EP3_RABBITMQ_EVIDENCIAS.pdf' in files
            assert all(x+'/pom.xml' in files for x in ('bff','catalog-service','orders-service','receipts-service','rabbit-admin-service','messaging-support'))
            assert not any(f.startswith(('pedidos360-frontend/','src/App')) for f in files)
        else:
            assert 'src/App.tsx' in files and 'package-lock.json' in files
            assert not any(f.endswith('pom.xml') or f.startswith('pedidos360-backend/') for f in files)
        git(path,'diff','--cached','--check')
        message='feat(ep3): complete RabbitMQ, real Entra evidence and delivery PDF' if name=='pedidos360-backend' else 'docs(ep3): publish preserved React frontend and verified delivery links'
        git(path,'commit','-m',message)
        assert not git(path,'status','--porcelain')
        state['repos'][name]=dict(path=str(path),gitDirectory=str(native_dir),remote=URLS[name],commit=git(path,'rev-parse','HEAD'),files=len(files))
        save(state);print('PREPARED',name,state['repos'][name]['commit'],flush=True)
    helper=STATE/'credential-helper'
    helper.write_text('#!/bin/sh\ncd /mnt/c/Users/Benja\nexec "/mnt/c/Program Files/Git/mingw64/bin/git-credential-manager.exe" "$@"\n')
    helper.chmod(0o700)
    state['prepared']=True;save(state)

def push(approved):
    assert approved,'The explicit human-authorized replacement flag is required'
    state=json.loads(JOURNAL.read_text());assert state['prepared']
    for name,path in REPOS.items():
        entry=state['repos'][name]
        assert path.resolve().parent==WORKSPACE.resolve()
        assert git(path,'rev-parse','--show-toplevel')==str(path)
        assert git(path,'remote','get-url','--push','origin')==URLS[name]
        assert git(path,'rev-parse','HEAD')==entry['commit'] and not git(path,'status','--porcelain')
        current=git(path,'ls-remote','origin','refs/heads/main',auth=True).split()[0]
        if current==entry['commit']:
            entry['remoteVerified']=True;print('ALREADY PUBLISHED',name,flush=True);continue
        lease='--force-with-lease=refs/heads/main:'+current
        print('PUBLISH',str(path),'->',URLS[name],'main',flush=True)
        git(path,'push','--dry-run',lease,'origin','HEAD:refs/heads/main',auth=True)
        result=git(path,'push',lease,'origin','HEAD:refs/heads/main',auth=True)
        print(result,flush=True)
        assert git(path,'ls-remote','origin','refs/heads/main',auth=True).split()[0]==entry['commit']
        entry.update(replacedMain=current,remoteVerified=True);save(state)
    # Verify public GitHub objects, including exact PDF bytes, without exporting auth.
    for name,path in REPOS.items():
        entry=state['repos'][name]
        sha=entry['commit']
        url=f'https://api.github.com/repos/chashmdai/{name}/git/trees/{sha}?recursive=1'
        request=urllib.request.Request(url,headers={'User-Agent':'Pedidos360-EP3-delivery'})
        with urllib.request.urlopen(request,timeout=30) as response:tree=json.load(response)
        remote_files={r['path']:r['sha'] for r in tree['tree'] if r['type']=='blob'}
        local={}
        for line in git(path,'ls-tree','-r','HEAD').splitlines():
            metadata,file=line.split('\t',1);local[file]=metadata.split()[2]
        assert remote_files==local
        for file in ('README.md','docs/EP3_RABBITMQ_EVIDENCIAS.pdf') if name=='pedidos360-backend' else ('README.md','src/App.tsx'):
            with urllib.request.urlopen(f'https://raw.githubusercontent.com/chashmdai/{name}/{sha}/{file}',timeout=30) as response:remote=response.read()
            assert remote==subprocess.check_output(['git','-c','safe.directory='+str(path),'-C',str(path),'show','HEAD:'+file])
        entry['githubTreeMatches']=True;entry['publicFilesVerified']=True;save(state)
    pdf=BACKEND/'docs/EP3_RABBITMQ_EVIDENCIAS.pdf'
    state.update(complete=True,finishedAt=datetime.now(timezone.utc).isoformat(),pdfSha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),
        pdfUrl='https://github.com/chashmdai/pedidos360-backend/blob/main/docs/EP3_RABBITMQ_EVIDENCIAS.pdf')
    save(state)
    (WORKSPACE/'ENTREGA_EP3_GIT.json').write_text(json.dumps(state,indent=2)+'\n')
    print('VERIFIED both GitHub trees and PDF; receipt:',WORKSPACE/'ENTREGA_EP3_GIT.json',flush=True)

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('action',choices=('prepare','push'))
    parser.add_argument('--approved-replace-main',action='store_true');args=parser.parse_args()
    if args.action=='prepare':prepare()
    else:push(args.approved_replace_main)
