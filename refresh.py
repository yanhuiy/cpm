#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""增量刷新框架（骨架）。

数据流：data.json（唯一主数据） --export_data.py--> data.js（前端）--<script>--> index.html

刷新策略（数据变化频率低，采用增量而非全量重构）：
  - 输入一批"新增/变更"的项目/政策（由 fetch_latest() 从爬虫或 AI 检索返回）。
  - 按 id 主键匹配：
      * 已存在且业务字段有变化 -> 更新字段，并刷新 updatedAt 为当日。
      * 已存在但无变化       -> 跳过。
      * 不存在               -> 追加，createdAt 记为当日，updatedAt 置 null。
  - 合并后写回 data.json，并调用 export_data.py 重新生成 data.js。

AI 检索接入：fetch_latest() 采用「Tavily 实时检索 + DeepSeek 结构化抽取」生成增量。
  依赖：pip install requests
  环境变量：DEEPSEEK_API_KEY（必填）、TAVILY_API_KEY（推荐，提供最新资讯）、DEEPSEEK_MODEL 等
  运行：python refresh.py --run 执行一次完整刷新
"""

import datetime
import json
import os
import sys
import time

import export_data

try:
    import requests
except ImportError:
    requests = None

# ============ AI 检索配置（环境变量注入，密钥勿写入代码） ============
DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '').strip()
DEEPSEEK_BASE = os.environ.get('DEEPSEEK_BASE', 'https://api.deepseek.com').rstrip('/')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')
TAVILY_API_KEY = os.environ.get('TAVILY_API_KEY', '').strip()
SEARCH_TOP_K = int(os.environ.get('SEARCH_TOP_K', '5'))        # 每个关键词取前 N 条
SEARCH_MAX_DOCS = int(os.environ.get('SEARCH_MAX_DOCS', '20'))  # 单轮最多资料条数
BACKFILL_SLEEP = float(os.environ.get('BACKFILL_SLEEP', '1'))   # 回填时时间片之间的间隔秒数
TYPE_LIST = ['超算中心', '智算中心', '运营商IDC', '通用·云']
STAGE_LIST = ['已建成', '在建', '规划']
VENDOR_LIST = ['昇腾', 'NVIDIA', '寒武纪', '海光', '阿里', '百度', '混合', '其他']

BASE = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE, 'data.json')

TYPE_CODE = {'超算中心': 'hpc', '智算中心': 'aic', '运营商IDC': 'idc', '通用·云': 'clu'}

# 给模型的 JSON 输出契约（与 data.json 字段一致）
_SCHEMA = """{"projects": [{"name": "项目全称", "province": "省份简称如陕西", "city": "地市如西安市",
"district": "区县/园区", "type": "超算中心|智算中心|运营商IDC|通用·云", "stage": "已建成|在建|规划",
"scaleText": "规模文字如 峰值180PFlops / 存储100PB", "aiP": 5000, "hpcP": null, "racks": null,
"vendor": "智算专用:昇腾|NVIDIA|寒武纪|海光|阿里|百度|混合|其他,其余填null", "year": 2025,
"announced": "2026-08", "estimated": false, "coord": [109, 34.16], "intro": "一句话简介",
"source": "https://原文", "sourceName": "出处"}], "policies": [{"title": "政策全称",
"level": "国家级|省级|市级", "region": "全国或省份简称", "publisher": "发布单位", "date": "2026-08",
"category": "算力|人工智能", "content": "要点", "link": "https://原文"}]}
规则：aiP(智算,P)/hpcP(超算,PFlops)/racks(IDC与通用·云,架)三选一按type填其余填null；
coord需在东经73~135北纬18~54内；规模无确切数字时estimated填true；source/link没有就填空串；不许编造。"""


def _normalize_project(data, raw, name2id):
    """校验并归一化一条项目；不合法返回 None。"""
    key = _norm_name(raw.get('name'))
    if not key:
        return None
    province = _match_province(data, raw.get('province'))
    if not province or raw.get('type') not in TYPE_LIST or raw.get('stage') not in STAGE_LIST:
        return None
    coord = raw.get('coord') or []
    try:
        lng, lat = float(coord[0]), float(coord[1])
    except (TypeError, ValueError, IndexError):
        return None
    if not (73 <= lng <= 135 and 18 <= lat <= 54):
        return None
    typ = raw['type']
    aiP = _clean_num(raw.get('aiP')) if typ == '智算中心' else None
    hpcP = _clean_num(raw.get('hpcP')) if typ == '超算中心' else None
    racks = _clean_num(raw.get('racks')) if typ in ('运营商IDC', '通用·云') else None
    vendor = raw.get('vendor') if typ == '智算中心' and raw.get('vendor') in VENDOR_LIST else None
    scale_text = (raw.get('scaleText') or '').strip()
    if not scale_text:
        if hpcP:
            scale_text = '峰值%.0fPFlops' % hpcP
        elif aiP:
            scale_text = 'AI算力%.0fP' % aiP
        elif racks:
            scale_text = '机架约%.0f架' % racks
    year = None
    try:
        y = int(raw.get('year') or 0)
        if 2000 <= y <= 2100:
            year = y
    except (TypeError, ValueError):
        pass
    p = {'name': (raw.get('name') or '').strip(), 'province': province,
         'city': (raw.get('city') or '').strip() or None,
         'district': (raw.get('district') or '').strip() or None,
         'type': typ, 'stage': raw['stage'], 'scaleText': scale_text,
         'level': _compute_level({'type': typ, 'aiP': aiP, 'hpcP': hpcP, 'racks': racks}),
         'aiP': aiP, 'hpcP': hpcP, 'racks': racks, 'vendor': vendor,
         'year': year, 'announced': (raw.get('announced') or '').strip() or None,
         'estimated': bool(raw.get('estimated')), 'coord': [lng, lat],
         'intro': (raw.get('intro') or '').strip() or None,
         'source': (raw.get('source') or '').strip() or '',
         'sourceName': (raw.get('sourceName') or '').strip() or ''}
    if key in name2id:
        p['id'] = name2id[key]  # 命中已有项目 -> 走更新而非新增
    return p


def _normalize_policy(data, raw, title2id):
    """校验并归一化一条政策；不合法返回 None。"""
    key = _norm_name(raw.get('title'))
    if not key:
        return None
    level = raw.get('level') or ''
    if '国家' in level:
        level = '国家级'
    elif '市' in level:
        level = '市级'
    else:
        level = '省级'
    region = (raw.get('region') or '').strip()
    if region != '全国':
        region = _match_province(data, region) or region
    q = {'title': (raw.get('title') or '').strip(), 'level': level,
         'region': region or '全国', 'publisher': (raw.get('publisher') or '').strip() or None,
         'date': (raw.get('date') or '').strip() or None,
         'category': (raw.get('category') or '').strip() or '算力',
         'content': (raw.get('content') or '').strip() or None,
         'link': (raw.get('link') or '').strip() or ''}
    if key in title2id:
        q['id'] = title2id[key]
    return q

# 合并时忽略的元字段（id 用于匹配，时间戳由框架维护）
_META_KEYS = ('id', 'createdAt', 'updatedAt')


def load():
    with open(DATA_PATH, encoding='utf-8') as f:
        return json.load(f)


def save(data):
    with open(DATA_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _date():
    return datetime.date.today().isoformat()


def _next_id(data, p):
    """为没有 id 的新项目按 {adcode}-{type}-{三位序号} 生成语义主键。"""
    ad = {x['s']: x['adcode'] for x in data['constants']['PROVINCES']}.get(
        p.get('province'), '000000')
    tc = TYPE_CODE.get(p.get('type'), 'oth')
    prefix = '%s-%s-' % (ad, tc)
    seq = 0
    for it in data['projects']:
        did = it.get('id', '')
        if did.startswith(prefix):
            try:
                seq = max(seq, int(did.rsplit('-', 1)[-1]))
            except ValueError:
                pass
    return '%s%03d' % (prefix, seq + 1)


def _business_fields(item):
    """取业务字段（剔除元字段），用于比较是否有实质变更。"""
    return {k: v for k, v in item.items() if k not in _META_KEYS}


def _upsert(data, incoming, key, gen_id):
    """按主键增量合并一批记录，返回 (新增数, 更新数)。"""
    by_id = {it['id']: it for it in data[key]}
    today = _date()
    added = updated = 0
    for it in incoming:
        it = dict(it)
        iid = it.get('id')
        if not iid:
            iid = gen_id(data, it)
            it['id'] = iid
        if iid in by_id:
            old = by_id[iid]
            if _business_fields(old) != _business_fields(it):
                old.update(_business_fields(it))
                old['updatedAt'] = today
                updated += 1
        else:
            it.setdefault('createdAt', today)
            it.setdefault('updatedAt', None)
            data[key].append(it)
            by_id[iid] = it
            added += 1
    return added, updated


def refresh(incoming):
    """合并一批增量数据，更新元信息，写回并重新导出。"""
    data = load()
    pa, pu = _upsert(data, incoming.get('projects', []), 'projects',
                     gen_id=lambda d, p: p.get('id') or _next_id(d, p))
    aa, au = _upsert(data, incoming.get('policies', []), 'policies',
                     gen_id=lambda d, p: 'pol-%03d' % (len(d['policies']) + 1))
    # 政策 id 用简单递增；若 incoming 已带 id 则沿用（见 _upsert）

    if pa or pu or aa or au:
        data['meta']['updatedAt'] = _date()
        save(data)
    export_data.main()

    print('项目：新增 %d / 更新 %d | 政策：新增 %d / 更新 %d' % (pa, pu, aa, au))
    return {'projects_added': pa, 'projects_updated': pu,
            'policies_added': aa, 'policies_updated': au}


def _post_json(url, payload, headers, timeout=60):
    """POST JSON 并解析响应；失败抛异常由调用方兜底。"""
    if requests is None:
        raise RuntimeError('缺少 requests 库，请先执行：pip install requests')
    r = requests.post(url, json=payload, headers=headers, timeout=timeout)
    r.raise_for_status()
    return r.json()


def _search_tavily(query):
    """Tavily 实时检索，返回 [{title,url,content}, ...]。"""
    body = {'api_key': TAVILY_API_KEY, 'query': query, 'topic': 'news',
            'search_depth': 'basic', 'max_results': SEARCH_TOP_K,
            'time_range': 'month'}
    return _post_json('https://api.tavily.com/search', body,
                      headers={'Content-Type': 'application/json'}).get('results', [])


def _search_all(queries):
    """依次检索各关键词，聚合去重并截断，控制单轮资料量。"""
    docs, seen = [], set()
    for q in queries:
        try:
            for r in _search_tavily(q):
                u = r.get('url', '')
                if u not in seen:
                    seen.add(u)
                    docs.append({'title': r.get('title', ''), 'url': u,
                                 'content': (r.get('content') or '')[:600]})
        except Exception as e:
            print('[fetch_latest] 检索失败(%s)：%s' % (q, e))
        if len(docs) >= SEARCH_MAX_DOCS:
            break
    return docs[:SEARCH_MAX_DOCS]


def _build_queries(period):
    """按指定时间片（'2026年' 或 '2026年09月'）生成检索关键词（覆盖项目与政策两类）。"""
    return ['算力中心 建成 投运 %s' % period, '智算中心 开工 投产 %s' % period,
            '超算中心 上线 扩容 %s' % period, '东数西算 枢纽 数据中心 %s' % period,
            '算力 人工智能 政策 发布 %s' % period]


def _chat_json(system, user, max_tokens=6000):
    """调用 DeepSeek 对话接口，强制 json_object 输出。"""
    body = {'model': DEEPSEEK_MODEL, 'temperature': 0.1,
            'response_format': {'type': 'json_object'}, 'max_tokens': max_tokens,
            'messages': [{'role': 'system', 'content': system},
                         {'role': 'user', 'content': user}]}
    data = _post_json(DEEPSEEK_BASE + '/chat/completions', body,
                      headers={'Authorization': 'Bearer ' + DEEPSEEK_API_KEY,
                               'Content-Type': 'application/json'})
    return data['choices'][0]['message']['content']


def _parse_json_loose(c):
    """容忍模型偶尔用 ```json 代码块包裹输出。"""
    c = c.strip()
    if c.startswith('```'):
        c = c.strip('`').strip()
        if c.startswith('json'):
            c = c[4:].strip()
    return json.loads(c)


def _norm_name(s):
    return (s or '').replace(' ', '').replace('\u3000', '').lower()


def _clean_num(v):
    try:
        f = float(v)
        return f if f > 0 else None
    except (TypeError, ValueError):
        return None


def _match_province(data, s):
    """把模型给的省份写法归一化为 PROVINCES 简称，无法识别返回 None。"""
    s = (s or '').strip().replace('省', '').replace('自治区', '') \
         .replace('壮族', '').replace('回族', '').replace('维吾尔', '')
    for p in data['constants']['PROVINCES']:
        if s == p['s'] or s == p['full']:
            return p['s']
    return None


def _compute_level(p):
    """按规模数值映射气泡等级 1-5。"""
    t = p.get('type')
    if t == '超算中心':
        v, steps = p.get('hpcP') or 0, ((200, 5), (100, 4), (50, 3), (10, 2))
    elif t in ('运营商IDC', '通用·云'):
        v, steps = p.get('racks') or 0, ((50000, 5), (20000, 4), (5000, 3), (1000, 2))
    else:
        v, steps = p.get('aiP') or 0, ((10000, 5), (5000, 4), (1000, 3), (300, 2))
    for n, lv in steps:
        if v >= n:
            return lv
    return 1


def _extract(data, docs):
    """构建 Prompt -> DeepSeek 抽取 -> 归一化，返回 {'projects': [...], 'policies': [...]}。"""
    today = datetime.date.today().isoformat()
    last = data['meta'].get('updatedAt') or data['meta'].get('monthlyNewCutoff') or '2020-01-01'
    names = [_norm_name(p['name']) for p in data['projects']]
    titles = [_norm_name(p['title']) for p in data['policies']]
    name2id = {n: p['id'] for n, p in zip(names, data['projects']) if p.get('id')}
    title2id = {t: p['id'] for t, p in zip(titles, data['policies']) if p.get('id')}

    if docs:
        docs_text = '\n\n'.join(
            '[%d] %s\n来源：%s\n%s' % (i + 1, d['title'], d['url'], d['content'])
            for i, d in enumerate(docs))
    else:
        docs_text = '（无外部检索资料，请基于自身知识回答，注意知识有截止时间，不确定勿编造）'

    system = ('你是「全国算力中心看板」的资料采集助手。根据检索资料和自身知识，抽取自 %s 以来'
              '【新增建成/开工/投产/规划公示】的算力中心项目，以及【新发布】的算力/AI 相关政策。'
              '只返回一个 JSON 对象，不要输出任何解释文字，格式为：\n%s' % (last, _SCHEMA))
    user = ('今天日期：%s\n上次数据更新：%s\n\n【检索资料】\n%s\n\n'
            '【已有项目名称】（避免重复，命中视为同一条，仅当状态/规模等变化时才作为更新返回）\n%s\n\n'
            '【已有政策标题】（避免重复）\n%s\n\n'
            '请严格按字段规则输出增量 JSON；确实没有新信息时输出 {"projects": [], "policies": []}。'
            % (today, last, docs_text,
               '、'.join(sorted(set(names))[:300]), '、'.join(sorted(set(titles))[:100])))

    raw = None
    for attempt in (1, 2):
        try:
            raw = _parse_json_loose(_chat_json(system, user))
            break
        except Exception as e:
            print('[fetch_latest] 第 %d 次抽取失败：%s' % (attempt, e))
            if attempt == 2:
                return {'projects': [], 'policies': []}

    out = {'projects': [], 'policies': []}
    for it in raw.get('projects', []):
        p = _normalize_project(data, it, name2id)
        if p:
            out['projects'].append(p)
    for it in raw.get('policies', []):
        q = _normalize_policy(data, it, title2id)
        if q:
            out['policies'].append(q)
    return out


def _iter_months(start, end):
    """按月份遍历 [start, end]（YYYY-MM 字符串，含端点）。"""
    y0, m0 = (int(x) for x in start.split('-'))
    y1, m1 = (int(x) for x in end.split('-'))
    while (y0, m0) <= (y1, m1):
        yield '%d年%02d月' % (y0, m0)
        m0 += 1
        if m0 == 13:
            y0, m0 = y0 + 1, 1


def _iter_years(start, end):
    """按年份遍历 [start, end]（取起止的年份，含端点）。"""
    for y in range(int(start.split('-')[0]), int(end.split('-')[0]) + 1):
        yield '%d年' % y


def _dedupe(entries):
    """按名称/标题去重：同名保留最后一次出现（时间靠后的状态通常更新）。"""
    seen_p, seen_q = {}, {}
    ps, qs = [], []
    for p in entries['projects']:
        k = _norm_name(p.get('name'))
        if k in seen_p:
            ps[seen_p[k]] = p
        else:
            seen_p[k] = len(ps)
            ps.append(p)
    for q in entries['policies']:
        k = _norm_name(q.get('title'))
        if k in seen_q:
            qs[seen_q[k]] = q
        else:
            seen_q[k] = len(qs)
            qs.append(q)
    entries['projects'] = ps
    entries['policies'] = qs


def fetch_backfill(start='2020-01', end='2026-08', monthly=False):
    """批量回填历史数据：按年（默认）/按月遍历检索+抽取，去重后返回合并增量。

    用法：python refresh.py --backfill 2020-01 2026-08           # 按年（默认）
          python refresh.py --backfill 2020-01 2026-08 --monthly  # 按月
    提示：未配置 TAVILY_API_KEY 时退化为纯模型知识模式。
    """
    if not DEEPSEEK_API_KEY:
        print('[backfill] 未配置 DEEPSEEK_API_KEY，无法回填。')
        return {'projects': [], 'policies': []}
    data = load()
    periods = list(_iter_months(start, end)) if monthly else list(_iter_years(start, end))
    if not periods:
        print('[backfill] 起始时间晚于结束时间，请检查参数。')
        return {'projects': [], 'policies': []}
    unit = '月' if monthly else '年'
    total = {'projects': [], 'policies': []}
    print('[backfill] 将按%s遍历 %d 个时间片（%s ~ %s）……' % (
        unit, len(periods), periods[0], periods[-1]))
    for i, period in enumerate(periods, 1):
        docs = _search_all(_build_queries(period)) if TAVILY_API_KEY else []
        entries = _extract(data, docs)
        total['projects'].extend(entries['projects'])
        total['policies'].extend(entries['policies'])
        print('[backfill] %02d/%d %s：项目 %d / 政策 %d（累计 %d / %d）' % (
            i, len(periods), period, len(entries['projects']), len(entries['policies']),
            len(total['projects']), len(total['policies'])))
        if i < len(periods):
            time.sleep(BACKFILL_SLEEP)
    _dedupe(total)
    print('[backfill] 去重后：项目 %d 条 / 政策 %d 条' % (
        len(total['projects']), len(total['policies'])))
    return total


def fetch_latest():
    """AI 检索实现：Tavily 实时检索 -> DeepSeek 结构化抽取 -> 归一化增量。

    环境变量：
      DEEPSEEK_API_KEY  必填（https://platform.deepseek.com）
      TAVILY_API_KEY    可选但推荐（https://tavily.com，免费约1000次/月）；
                        未配置时退化为纯模型知识模式（时效性较弱）。
    返回 {"projects": [...], "policies": [...]}，字段与 data.json 对应。
    """
    if not DEEPSEEK_API_KEY:
        print('[fetch_latest] 未配置 DEEPSEEK_API_KEY，本次跳过刷新。')
        return {'projects': [], 'policies': []}
    data = load()

    ym = '%d年%02d月' % (datetime.date.today().year, datetime.date.today().month)
    docs = []
    if TAVILY_API_KEY:
        docs = _search_all(_build_queries(ym))
        print('[fetch_latest] 实时检索到资料 %d 条' % len(docs))
    else:
        print('[fetch_latest] 未配置 TAVILY_API_KEY，使用纯模型知识模式（时效性有限）。')

    entries = _extract(data, docs)
    print('[fetch_latest] 模型产出：项目 %d 条 / 政策 %d 条' % (
        len(entries['projects']), len(entries['policies'])))
    return entries


if __name__ == '__main__':
    d = load()
    print('当前数据：项目 %d 条 / 政策 %d 条 / 版本 %s' % (
        len(d['projects']), len(d['policies']), d['meta'].get('version')))
    if '--run' in sys.argv:
        print('开始 AI 检索刷新……')
        result = refresh(fetch_latest())
        print('刷新完成：%s' % result)
    elif '--backfill' in sys.argv:
        pos = sys.argv.index('--backfill')
        start = sys.argv[pos + 1] if len(sys.argv) > pos + 1 else '2020-01'
        end = sys.argv[pos + 2] if len(sys.argv) > pos + 2 else '2026-08'
        if '-' not in start or '-' not in end:
            start, end = '2020-01', '2026-08'
        monthly = '--monthly' in sys.argv
        print('开始历史回填（%s ~ %s，按%s）……' % (start, end, '月' if monthly else '年'))
        result = refresh(fetch_backfill(start, end, monthly=monthly))
        print('回填完成：%s' % result)
    else:
        print('运行 python refresh.py --run 执行一次完整刷新；')
        print('      python refresh.py --backfill [起始月] [结束月] 批量回填历史数据（默认按年）。')