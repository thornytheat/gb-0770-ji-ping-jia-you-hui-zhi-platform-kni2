from app.diagnostics import detail


def line_items(weights, sheet, overlaps):
    receipts = {row['data']['ticket']:row for row in sheet['rows']}
    conflicts = {}
    for row in sheet['quarantine']:
        if row['code']=='CONFLICT':
            conflicts[row['data']['ticket']] = row['related']
    compared = []
    for row in weights:
        ticket,truck = row['ticket'],row['truck']
        signed = receipts.pop(ticket,None)
        standard = row['standard']
        variance = None
        role = overlaps['roles'].get(ticket)
        overlap_code = role['role'] if role else None
        if row['fault']:
            status = row['fault']['code']
        elif overlap_code == 'OVERLAP_PENDING':
            status = 'OVERLAP_PENDING'
        elif overlap_code == 'MERGED_DUPLICATE':
            status = 'MERGED_DUPLICATE'
        elif ticket in conflicts:
            status = 'CONFLICT'
        elif signed is None:
            status = 'NO_RECEIPT'
        elif signed['data']['truck'] != truck:
            status = 'SIGN_TRUCK'
        else:
            variance = signed['data']['signed_g'] - standard['mass_g']
            status = 'SIGN_DIFF' if abs(variance)>standard['allowance_g'] else 'MATCH'
        component = role['component'] if role else None
        compared.append({'ticket':ticket,'truck':truck,'ticket_line':row['line'],'state':status,
                         'reason':detail(status)['note'] if status not in ('MATCH','MERGED_DUPLICATE')
                         else ('误差带内' if status=='MATCH' else detail('MERGED_DUPLICATE')['note']),
                         'overlap_status':overlap_code,
                         'overlap_group':component['tickets'] if component else None,
                         'keeper':component['keeper'] if component else None,
                         'reprint_lines':component['evidence'] if component and component['status']=='CONFIRMED' else None,
                         'signed_g':signed['data']['signed_g'] if signed else None,
                         'receipt_lines':[signed['line']] if signed else conflicts.get(ticket,[]),
                         'document':signed['data']['document'] if signed else None,
                         'meter_g':standard['mass_g'] if standard else None,
                         'allowance_g':standard['allowance_g'] if standard else None,'variance_g':variance})
    unmatched = [dict(detail('NO_METER'),ticket=key,truck=row['data']['truck'],line=row['line'],
                      signed_g=row['data']['signed_g'],document=row['data']['document']) for key,row in receipts.items()]
    return compared,unmatched
