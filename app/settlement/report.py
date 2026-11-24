from collections import Counter
from .inventory import conservation
from .overlap import detect_overlaps
from .receipts import line_items


def reconcile(weights, intake):
    sheets = intake['sheets']
    overlaps = detect_overlaps(weights, intake)
    findings,unmatched = line_items(weights,sheets['receipts'],overlaps)
    stocks = conservation(sheets['stock'],findings,overlaps)
    complete = [row for row in stocks if row['complete']]
    totals = {key:sum(row[key] for row in complete)
              for key in ('opening_g','inbound_g','issued_g','closing_g','difference_g')}
    flags = Counter(row['state'] for row in findings)
    open_states = {'NO_RECEIPT','SIGN_TRUCK','NO_METER','SIGN_DIFF','CONFLICT','OVERLAP_PENDING'}
    return {'stocks':stocks,'totals':totals,'receipts':findings,'unmatched_receipts':unmatched,
            'states':dict(flags),'overlaps':overlaps['groups'],'reprints':overlaps['evidence'],
            'disputed_trucks':overlaps['disputed_trucks'],
            'confirmed_overlap_groups':overlaps['confirmed_groups'],
            'pending_overlap_groups':overlaps['pending_groups'],
            'open_items':sum(n for state,n in flags.items() if state in open_states)
                         +len(unmatched),
            'complete_trucks':len(complete),'held_trucks':len(stocks)-len(complete),
            'unclosed_mass_g':sum(row['confirmed_mass_g'] for row in stocks if not row['complete']),
            'receipt_delta_g':sum(row['variance_g'] for row in findings if row['variance_g'] is not None),
            'row_balance':intake['input']==intake['accepted']+intake['isolated']+intake['duplicate'],
            'conserved':totals['opening_g']+totals['inbound_g']==totals['issued_g']+totals['closing_g']+totals['difference_g']}
