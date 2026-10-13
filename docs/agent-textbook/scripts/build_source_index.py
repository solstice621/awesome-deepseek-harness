#!/usr/bin/env python3
"""Regenerate source lock and indexes from evidence.json and fixed source trees."""
import argparse
import hashlib
import json
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOS = {
    'codex': ('openai/codex', 'a9b0815167c27ab13719dd12d13b63e02b70d221', 'codex'),
    'opencode': ('anomalyco/opencode', '60a212c0769acd96b446acbadeb790486830f91d', 'opencode'),
    'dsh': ('deepseek-ai/deepseek-harness', 'd743267388641bc76f17c45ce8b4c231aed1d32c', 'deepseek-harness'),
}

def source_url(project, path, lines=None):
    name, sha, _ = REPOS[project]
    url = f'https://github.com/{name}/blob/{sha}/{path}'
    return url + (f'#L{lines[0]}-L{lines[1]}' if lines else '')

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--sources-root', type=Path, required=True)
    args = parser.parse_args()
    evidence = json.loads((ROOT / 'evidence.json').read_text())
    grouped = defaultdict(list)
    for item in evidence:
        grouped[(item['project'], item['path'])].append(item)
    source_files = []
    index = ['# 源码证据索引', '', '[教材目录](../README.md)', '',
             '下列记录对应固定提交的选定阅读范围。每条论断的章节、符号、范围、类型与说明保存在 [evidence.json](../evidence.json)。文件 SHA-256 用于核对下载内容；哈希和有效行号不能代替语义复核。', '',
             '本索引区分代码、官方文档与测试文件。测试文件被阅读不等于本轮运行通过；本地教学实验有单独记录。未将“未检索到”写成整个项目缺少某项能力。', '']
    for project in REPOS:
        name, sha, dirname = REPOS[project]
        index += [f'## {name}', '', f'固定提交：`{sha}`。', '', '| 文件与符号 | 已读行范围 | 章节 | 类型 |', '|---|---|---|---|']
        for (proj, path), items in sorted(grouped.items()):
            if proj != project:
                continue
            local = args.sources_root / f'{dirname}-{sha}' / path
            raw = local.read_bytes()
            length = len(raw.decode('utf-8').splitlines())
            for item in items:
                a, b = item['lines']
                assert 1 <= a <= b <= length, (item, length)
            ranges = sorted(set(tuple(i['lines']) for i in items))
            chapters = sorted(set(i['chapter'] for i in items))
            kinds = sorted(set(i['kind'] for i in items))
            source_files.append({'project':project,'path':path,'sha256':hashlib.sha256(raw).hexdigest(),
                                 'line_count':length,'read_ranges':[list(r) for r in ranges],
                                 'chapters':chapters,'kinds':kinds})
            range_links = ', '.join(f'[{a}–{b}]({source_url(project,path,(a,b))})' for a,b in ranges)
            chapter_links = ', '.join(f'[{c[:2]}](../chapters/{c})' for c in chapters)
            symbols = ', '.join(dict.fromkeys(i['symbol'] for i in items))
            safe_symbols = symbols.replace('|','/').replace('\n',' ')[:230]
            index.append(f'| [{path}]({source_url(project,path)})<br>{safe_symbols} | {range_links} | {chapter_links} | {", ".join(kinds)} |')
        index += ['']
    index.insert(6, f'统计：**{len(source_files)} 个不同上游文件，{len(evidence)} 条阅读证据**。重复使用同一文件不重复计数。')
    (ROOT/'appendices/source-index.md').write_text('\n'.join(index).rstrip()+'\n')
    lock = {'schema_version':1,'research_date':'2026-10-13','language':'zh-CN',
            'scope':'28 chapter source-grounded curriculum; selected source reading, not a repository audit',
            'chapter_count':28,'evidence_count':len(evidence),'source_file_count':len(source_files),
            'repositories':[{'id':k,'repository':v[0],'commit':v[1],'source_directory':f'{v[2]}-{v[1]}'} for k,v in REPOS.items()],
            'evidence':'evidence.json','source_files':source_files,
            'validation':{'upstream_builds_executed':False,'upstream_tests_executed':False,
                          'real_model_calls_executed':False,'upstream_benchmarks_executed':False,
                          'sandbox_security_tests_executed':False,'teaching_lab_results':'VALIDATION.md'}}
    (ROOT/'source-lock.json').write_text(json.dumps(lock,ensure_ascii=False,indent=2)+'\n')
    coverage = ['# 主题与三个项目的对应关系','','[教材目录](../README.md)','',
                '按问题选择章节，再进入代表性源码入口。表格表示本书实际定位与讨论的机制，不是功能成熟度评分；“有入口”不等于全部分支已经验证。完整阅读范围见[源码证据索引](source-index.md)。','',
                '| 章与主题 | Codex | OpenCode | DeepSeek Harness |','|---|---|---|---|']
    for chapter in sorted((ROOT/'chapters').glob('*.md')):
        if chapter.name.startswith('28-'):continue
        title = chapter.read_text().splitlines()[0].lstrip('# ').strip()
        cells = [f'[{title}](../chapters/{chapter.name})']
        for project in REPOS:
            found = [i for i in evidence if i['chapter']==chapter.name and i['project']==project]
            assert found, (chapter.name,project)
            chosen = next((i for i in found if i['kind']=='code'),found[0])
            label = chosen['symbol'].replace('|','/').replace('\n',' ')
            cells.append(f'[{label}]({source_url(project,chosen["path"],chosen["lines"])})')
        coverage.append('| '+' | '.join(cells)+' |')
    coverage += ['', '第 28 章提供本地模拟实验，将上述机制压缩为可理解的教学系统；它不是三个上游项目的共同实现或基准测试。', '',
                 '## 相对于原有八专题的扩展', '',
                 '原有材料按每个项目的 loop、context、tools、streaming、extension、orchestration、persistence、observability 八题组织。新主线在此基础上独立讲授任务建模与部分可观测、模型协议基础、规划与验证、检索与长期记忆、skills 与配置、重试与幂等、提示注入、服务部署、扩展契约和综合实验，并把权限、沙箱、并发、取消与事件交付拆成可分别学习的问题。', '',
                 '这种组织允许读者先理解问题，再比较三种实现；不要求三项目对每个问题采用同一名称、模块边界或默认配置。']
    (ROOT/'appendices/coverage-map.md').write_text('\n'.join(coverage)+'\n')
    print(f'{len(evidence)} evidence entries; {len(source_files)} source files; 27 x 3 mapped chapters')

if __name__ == '__main__':main()
