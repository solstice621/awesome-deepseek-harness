#!/usr/bin/env python3
"""Check textbook structure, local links, pinned sources, ranges and optional source hashes.
No network, upstream builds or model calls. Run the teaching tests separately.
"""
import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]

def links(text):
    text = re.sub(r'^```.*?^```[^\n]*$', '', text, flags=re.M|re.S)
    return (re.findall(r'\[[^\]\n]*\]\(([^\s)]+)(?:\s+"[^"]*")?\)',text)
            + re.findall(r'^\[[^\]]+\]:\s*(\S+)',text,flags=re.M))

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--sources-root',type=Path)
    args=p.parse_args()
    errors=[]
    lock=json.loads((ROOT/'source-lock.json').read_text())
    evidence=json.loads((ROOT/'evidence.json').read_text())
    repos={r['repository']:r for r in lock['repositories']}
    source_files={(x['project'],x['path']):x for x in lock['source_files']}
    chapters=sorted((ROOT/'chapters').glob('*.md'))
    if [int(x.name[:2]) for x in chapters]!=list(range(1,29)):
        errors.append('Expected exactly chapters 01 through 28')
    toc=(ROOT/'README.md').read_text()
    source_links=0
    local_links=0
    for chapter in chapters:
        text=chapter.read_text()
        if not text.startswith("# "):errors.append(f"Chapter must start with its title: {chapter.name}")
        if f'chapters/{chapter.name}' not in toc:errors.append(f'Missing TOC: {chapter.name}')
        if not re.search('练习|习题',text):errors.append(f'Missing exercises: {chapter.name}')
        if not re.search('答案|参考|思路',text):errors.append(f'Missing answer guidance: {chapter.name}')
        if not chapter.name.startswith('28-'):
            for r in repos:
                if f'https://github.com/{r}/blob/' not in text:
                    errors.append(f'Missing project mapping: {chapter.name}: {r}')
    markdown_files=sorted(ROOT.rglob('*.md'))
    for md in markdown_files:
        for target in links(md.read_text()):
            u=urlsplit(target.strip('<>'))
            if u.scheme or u.netloc:
                if u.netloc!='github.com':continue
                parts=u.path.lstrip('/').split('/')
                if len(parts)<5 or parts[2]!='blob':continue
                repo='/'.join(parts[:2])
                if repo not in repos:continue
                r=repos[repo]
                sha=parts[3]
                path=unquote('/'.join(parts[4:]))
                if sha!=r['commit']:errors.append(f'Unpinned/wrong commit: {md.name}: {target}')
                key=(r['id'],path)
                if key not in source_files:
                    errors.append(f'Cited source not inventoried: {md.name}: {path}')
                    continue
                if u.fragment:
                    m=re.fullmatch(r'L(\d+)(?:-L(\d+))?',u.fragment)
                    if m:
                        a=int(m[1]);b=int(m[2] or m[1])
                        if not 1<=a<=b<=source_files[key]['line_count']:
                            errors.append(f'Out of range citation: {md.name}: {target}')
                source_links+=1
            else:
                if not u.path:continue
                dest=(md.parent/unquote(u.path)).resolve()
                if not dest.exists():errors.append(f'Broken local link: {md.relative_to(ROOT)} -> {target}')
                local_links+=1
    for e in evidence:
        key=(e['project'],e['path'])
        if key not in source_files:errors.append(f'Evidence lacks source: {key}');continue
        a,b=e['lines']
        if not 1<=a<=b<=source_files[key]['line_count']:errors.append(f'Invalid evidence range: {e}')
        if not (ROOT/'chapters'/e['chapter']).is_file():errors.append(f'Evidence chapter absent: {e["chapter"]}')
        if e['kind'] not in {'code','test','doc'}:errors.append(f'Invalid evidence kind: {e["kind"]}')
    if lock['evidence_count']!=len(evidence):errors.append('Evidence count mismatch')
    if lock['source_file_count']!=len(source_files):errors.append('Source count mismatch')
    if args.sources_root:
        ids={r['id']:r for r in repos.values()}
        for (project,path),entry in source_files.items():
            local=args.sources_root/ids[project]['source_directory']/path
            if not local.is_file():errors.append(f'Source file absent: {project}/{path}');continue
            if hashlib.sha256(local.read_bytes()).hexdigest()!=entry['sha256']:
                errors.append(f'Source hash mismatch: {project}/{path}')
    report={'chapters':len(chapters),'markdown_files':len(markdown_files),
            'evidence_entries':len(evidence),'source_files':len(source_files),
            'source_links_checked':source_links,'local_links_checked':local_links,
            'source_hashes_checked':len(source_files) if args.sources_root else 0,
            'errors':errors}
    print(json.dumps(report,ensure_ascii=False,indent=2))
    return bool(errors)

if __name__=='__main__':sys.exit(main())
