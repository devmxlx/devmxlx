#!/usr/bin/env python3
"""Export aggregate language bytes from accessible project source files using scc."""
import argparse
from datetime import datetime, timezone
import json
from pathlib import Path
import subprocess

EXTENSIONS = 'ts,tsx,js,jsx,mjs,cjs,html,htm,css,scss,sass,less,sql,py,rs,go,sh,bash,c,cc,cpp,h,hpp,cs,java,kt,kts,swift,m,mm,php,rb,lua,vue,svelte,astro,dart,ex,exs,erl,hrl,hs,r,scala,clj,cljs,pl,pm,ps1,psm1,bat,cmd,zig,sol,prisma,graphql,gql'
EXCLUDED_DIRS = '.git,.hg,.svn,node_modules,vendor,Pods,Carthage,.gradle,.expo,.cxx,.cache,.next,.next-dev,.next-site-qa,.next-collective-test,dist,build,output,artifacts,verification,reference-screenshots,_extract,.shots,.vercel,tmp,target,.venv,venv,__pycache__,.turbo,coverage,.codex,.claude,.agents'
ALIASES = {'TypeScript Typings':'TypeScript', 'TypeScript JSX':'TypeScript', 'TSX':'TypeScript', 'JavaScript JSX':'JavaScript', 'JSX':'JavaScript', 'BASH':'Shell', 'Bash':'Shell', 'Shell Script':'Shell'}


def unique_roots(values):
    paths = sorted({Path(value).resolve() for value in values}, key=lambda value: len(value.parts))
    result = []
    for path in paths:
        if not path.is_dir():
            raise ValueError('A requested project directory is unavailable')
        if not any(path == other or other in path.parents for other in result):
            result.append(path)
    return result


def sanitize(rows, project_count, now, imported_content):
    totals = {}
    for row in rows:
        name = ALIASES.get(row['Name'], row['Name'])
        if not isinstance(name, str) or not name or len(name) > 80:
            raise ValueError('Invalid language label')
        values = {key:row[source] for key,source in [('bytes','Bytes'),('files','Count'),('code_lines','Code')]}
        if any(type(value) is not int or value < 0 for value in values.values()):
            raise ValueError('Invalid language count')
        if not values['bytes'] or not values['code_lines']:
            continue
        item = totals.setdefault(name, {'name':name, 'bytes':0, 'files':0, 'code_lines':0})
        for key, value in values.items():
            item[key] += value
    languages = sorted(totals.values(), key=lambda item:(-item['bytes'],item['name']))
    return {'version':1, 'metric':'source_file_bytes', 'tool':'scc 4.1.0',
            'scanned_at':now.isoformat(timespec='seconds'), 'project_count':project_count,
            'file_count':sum(item['files'] for item in languages),
            'code_lines':sum(item['code_lines'] for item in languages),
            'imported_content_included':imported_content,
            'languages':languages}


def scan(executable, roots, imported_content=False):
    paths = unique_roots(roots)
    command = [str(executable), '--format','json','--no-cocomo','--no-complexity',
               '--no-config','--no-gen','--no-min','--no-gitignore','--no-duplicates','--include-ext',EXTENSIONS,
               '--exclude-dir',EXCLUDED_DIRS,
               '--exclude-file','next-env.d.ts,package-lock.json,Cargo.lock,yarn.lock,pnpm-lock.yaml',
               '--not-match',r'\.min\.(?:js|css)$']
    if not imported_content:
        command += ['--not-match',r'/(?:bibliothek/inhalt|zusammenfassungen/inhalt)/']
    result = subprocess.run(command+[str(path) for path in paths], check=True, capture_output=True,text=True)
    return sanitize(json.loads(result.stdout),len(paths),datetime.now(timezone.utc),imported_content)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--scc',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--include-imported-content',action='store_true')
    parser.add_argument('roots',nargs='+')
    args = parser.parse_args()
    data = scan(args.scc.resolve(),args.roots,args.include_imported_content)
    args.output.write_text(json.dumps(data,indent=2)+'\n')
    # This output and the saved snapshot contain no private project/file identifiers.
    print(json.dumps({'projects':data['project_count'],'files':data['file_count'],
                      'code_lines':data['code_lines'],'languages':data['languages']}))


if __name__ == '__main__':
    main()
