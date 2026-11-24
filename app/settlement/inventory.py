from collections import defaultdict
from app.diagnostics import detail


def conservation(stock, findings, overlaps):
    holding = defaultdict(lambda:defaultdict(list))
    for item in stock['rows']:
        row = item['data']
        holding[row['truck']][row['kind']].append(item)
    held_positions = defaultdict(list)
    for item in stock['quarantine']:
        truck = item['data']['truck'] if 'data' in item else item.get('truck')
        if truck:
            held_positions[truck].append(item['line'])
    # 只按真正参与扣库存的票累加：保留票与正常票计入，合并掉的重复票和待核重叠票不计
    issued = defaultdict(int)
    confirmed_visible = defaultdict(int)
    for finding in findings:
        role = finding['overlap_status']
        mass = finding['meter_g'] or 0
        if role in (None, 'KEEPER'):
            issued[finding['truck']] += mass
        if role != 'MERGED_DUPLICATE':
            confirmed_visible[finding['truck']] += mass
    disputed = set(overlaps['disputed_trucks'])
    result = []
    trucks = sorted(set(holding) | set(issued) | set(confirmed_visible) | set(held_positions) | disputed)
    for truck in trucks:
        entries = holding[truck]
        opening,closing = entries['opening'],entries['closing']
        inbound = sum(row['data']['mass_g'] for row in entries['inbound'])
        issue = issued[truck]
        anchors = len(opening)==len(closing)==1 and not held_positions[truck]
        in_dispute = truck in disputed
        complete = anchors and not in_dispute
        start = opening[0]['data']['mass_g'] if len(opening)==1 else None
        end = closing[0]['data']['mass_g'] if len(closing)==1 else None
        residual = start+inbound-issue-end if complete else None
        if in_dispute:
            fault = detail('OVERLAP_PENDING')
        elif not anchors:
            fault = detail('STOCK_ANCHORS')
        else:
            fault = None
        result.append({'truck':truck,'opening_g':start,'inbound_g':inbound,'issued_g':issue,
                       'confirmed_mass_g':confirmed_visible[truck],'closing_g':end,
                       'difference_g':residual,'complete':complete,'disputed':in_dispute,
                       'fault':fault,
                       'source_lines':sorted(item['line'] for group in entries.values() for item in group),
                       'isolated_lines':held_positions[truck]})
    return result
