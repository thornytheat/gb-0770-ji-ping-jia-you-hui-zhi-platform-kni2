from collections import Counter, defaultdict

from app.diagnostics import RampError, detail
from .reader import rows_from
from .schemas import COLUMNS, OPTIONAL_CHANNELS, convert_fields

IDENTITY = {'stock':lambda data:(data['truck'],data['movement']),
            'reprints':lambda data:data['reprint']}


def channel_report(channel, raw):
    groups = defaultdict(list)
    rejected, repeated = [], []
    count, segments = 0,1
    key_of = IDENTITY.get(channel,lambda data:data['ticket'])
    for line,header,row in rows_from(raw,COLUMNS[channel]):
        if row==header:
            segments += 1
            continue
        count += 1
        try:
            if not any(field.strip() for field in row):
                raise ValueError('BLANK_ROW')
            if len(row)!=len(header):
                raise ValueError('WIDTH')
            data = convert_fields({key:value.strip() for key,value in zip(header,row)},channel)
            groups[key_of(data)].append({'line':line,'data':data,'raw':row})
        except ValueError as exc:
            origin = dict(zip(header,row)) if len(row)==len(header) else {}
            rejected.append(dict(detail(str(exc)),line=line,raw=row,
                                 truck=origin.get('truck','').strip() or None))
    if not count:
        raise RampError('HEADER_ONLY')
    kept = []
    for group in groups.values():
        first,*rest = group
        if any(item['data']!=first['data'] for item in rest):
            related = [item['line'] for item in group]
            rejected.extend(dict(detail('CONFLICT'),line=r['line'],raw=r['raw'],data=r['data'],related=related)
                            for r in group)
        else:
            kept.append(first)
            repeated.extend({'line':item['line'],'kept':first['line']} for item in rest)
    return {'input':count,'accepted':len(kept),'isolated':len(rejected),'duplicate':len(repeated),'segments':segments,
            'rows':kept,'quarantine':sorted(rejected,key=lambda e:e['line']),'repeat_sources':repeated,
            'reasons':dict(Counter(row['code'] for row in rejected))}


def blank_sheet():
    return {'input':0,'accepted':0,'isolated':0,'duplicate':0,'segments':0,
            'rows':[],'quarantine':[],'repeat_sources':[],'reasons':{}}


def admit(files):
    sheets = {}
    for name in COLUMNS:
        if name in OPTIONAL_CHANNELS and name not in files:
            sheets[name] = blank_sheet()
        else:
            sheets[name] = channel_report(name,files[name])
    totals = {key:sum(sheet[key] for sheet in sheets.values()) for key in ('input','accepted','isolated','duplicate')}
    return dict(totals,sheets=sheets)
