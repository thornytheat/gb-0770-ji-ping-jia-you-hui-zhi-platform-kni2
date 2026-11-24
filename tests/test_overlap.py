from app.bundles import sample_set
from app.shift import compute


def group(report, *tickets):
    balance = report['balance'] if 'balance' in report else report
    wanted = set(tickets)
    return next(g for g in balance['overlaps'] if set(g['tickets']) == wanted)


def receipt(dirty, ticket):
    return next(r for r in dirty['balance']['receipts'] if r['ticket'] == ticket)


def test_confirmed_reprint_books_one_fueling_but_keeps_both_tickets(dirty):
    merged = group(dirty, 'T01', 'DUP1', 'DUP2')
    assert merged['status'] == 'CONFIRMED' and merged['keeper'] == 'T01'
    assert merged['merged'] == ['DUP1', 'DUP2'] and merged['evidence'] == [2]
    keeper, dup1, dup2 = (receipt(dirty, t) for t in ('T01', 'DUP1', 'DUP2'))
    assert keeper['overlap_status'] == 'KEEPER' and dup1['state'] == 'MERGED_DUPLICATE'
    # 两张原票都能查到，且都指向同一保留票和重打凭据行
    for row in (dup1, dup2):
        assert row['keeper'] == 'T01' and row['reprint_lines'] == [2]
        assert row['overlap_group'] == ['T01', 'DUP1', 'DUP2']


def test_confirmed_group_deducts_inventory_only_once(dirty):
    truck = next(s for s in dirty['balance']['stocks'] if s['truck'] == 'FT-12')
    # 三张票各 80000g，合并后只按保留票扣一次，差额维持 1400g
    assert truck['issued_g'] == 191600 and truck['difference_g'] == 1400 and truck['complete']


def test_overlap_without_reliable_evidence_is_held_even_when_signed(dirty):
    pending = group(dirty, 'S01', 'DUP3', 'DUP4')
    assert pending['status'] == 'PENDING' and pending['keeper'] is None
    for ticket in ('S01', 'DUP3', 'DUP4'):
        row = receipt(dirty, ticket)
        assert row['state'] == 'OVERLAP_PENDING' and row['signed_g'] is not None
    assert dirty['balance']['disputed_trucks'] == ['FT-18']


def test_disputed_truck_lists_confirmed_fuel_but_no_profit_or_loss(dirty):
    truck = next(s for s in dirty['balance']['stocks'] if s['truck'] == 'FT-18')
    assert truck['disputed'] and not truck['complete']
    assert truck['difference_g'] is None
    # 已确认发油仍列在工作台（含待核三票 88000g），但不参与库存合计
    assert truck['confirmed_mass_g'] == 88000 and truck['issued_g'] == 16000
    assert truck not in [s for s in dirty['balance']['stocks'] if s['complete']]


def test_touching_end_and_start_is_not_overlap():
    files = sample_set('clean')
    text = files['tickets'].decode()
    text += 'A01,FT-12,2026-11-22T04:20:00Z,2026-11-22T04:30:00Z,510,520,normal,JET-A1,800,kg/m3,15\n'
    text += 'A02,FT-12,2026-11-22T04:30:00Z,2026-11-22T04:40:00Z,520,530,normal,JET-A1,800,kg/m3,15\n'
    files['tickets'] = text.encode()
    balance = compute(files)['balance']
    assert all(set(g['tickets']) != {'A01', 'A02'} for g in balance['overlaps'])
    assert all(r['overlap_status'] is None for r in balance['receipts'] if r['ticket'] in ('A01', 'A02'))


def test_partial_reprint_covering_does_not_confirm_whole_group():
    files = {k: bytearray(v) for k, v in sample_set('dirty').items()}
    # 凭据只覆盖 DUP1;DUP2，组内还有与之重叠的 T01，整组不能确认
    files['reprints'] = b'reprint,truck,tickets,document\nRP-01,FT-12,DUP1;DUP2,R12-DUP\n'
    balance = compute(dict(files))['balance']
    assert group(balance, 'T01', 'DUP1', 'DUP2')['status'] == 'PENDING'
    assert 'FT-12' in balance['disputed_trucks']


def test_reprint_pointing_at_unknown_ticket_is_quarantined_as_evidence_fault():
    files = sample_set('dirty')
    files['reprints'] = ('reprint,truck,tickets,document\n'
                         'RP-09,FT-12,T01;GHOST,R12-X\n').encode()
    balance = compute(files)['balance']
    slip = next(s for s in balance['reprints'] if s['reprint'] == 'RP-09')
    assert slip['usable'] is False and slip['fault']['code'] == 'EVIDENCE'
    assert group(balance, 'T01', 'DUP1', 'DUP2')['status'] == 'PENDING'


def test_reprint_truck_mismatch_is_not_reliable():
    files = sample_set('dirty')
    files['reprints'] = ('reprint,truck,tickets,document\n'
                         'RP-09,FT-18,T01;DUP1,R12-X\n').encode()
    balance = compute(files)['balance']
    slip = next(s for s in balance['reprints'] if s['reprint'] == 'RP-09')
    assert slip['fault']['code'] == 'EVIDENCE' and group(balance, 'T01', 'DUP1', 'DUP2')['status'] == 'PENDING'


def test_chained_reprints_together_confirm_one_group():
    files = sample_set('dirty')
    # 两张凭据分别覆盖 (T01,DUP1) 与 (DUP1,DUP2)，连通且覆盖全组才算确认
    files['reprints'] = ('reprint,truck,tickets,document\n'
                         'RP-1,FT-12,T01;DUP1,R-A\n'
                         'RP-2,FT-12,DUP1;DUP2,R-B\n').encode()
    balance = compute(files)['balance']
    merged = group(balance, 'T01', 'DUP1', 'DUP2')
    assert merged['status'] == 'CONFIRMED' and merged['keeper'] == 'T01'
    assert merged['evidence'] == [2, 3]
    # 去掉一张凭据后连通性/覆盖不足，回到待核
    files['reprints'] = ('reprint,truck,tickets,document\n'
                         'RP-1,FT-12,T01;DUP1,R-A\n').encode()
    held = compute(files)['balance']
    assert group(held, 'T01', 'DUP1', 'DUP2')['status'] == 'PENDING'


def test_header_only_reprints_channel_is_diagnosed_like_other_channels():
    from app.intake.evidence import channel_report
    import pytest
    from app.diagnostics import RampError
    with pytest.raises(RampError) as exc:
        channel_report('reprints', 'reprint,truck,tickets,document\n'.encode())
    assert exc.value.code == 'HEADER_ONLY'


def test_malformed_reprint_member_list_is_quarantined():
    from app.intake.evidence import channel_report
    raw = b'reprint,truck,tickets,document\nRP-1,FT-12,T01,R\n'
    report = channel_report('reprints', raw)
    assert report['accepted'] == 0 and report['reasons'] == {'MALFORMED': 1}


def test_reprint_channel_is_optional_and_blank_sheet_is_safe():
    files = {key: value for key, value in sample_set('dirty').items() if key != 'reprints'}
    balance = compute(files)['balance']
    assert balance['reprints'] == []
    assert group(balance, 'T01', 'DUP1', 'DUP2')['status'] == 'PENDING'


def test_same_window_on_different_trucks_is_not_one_group():
    files = sample_set('clean')
    text = files['tickets'].decode()
    text += 'B01,FT-12,2026-11-22T05:00:00Z,2026-11-22T05:10:00Z,530,540,normal,JET-A1,800,kg/m3,15\n'
    text += 'B02,FT-18,2026-11-22T05:00:00Z,2026-11-22T05:10:00Z,130,140,normal,JET-A1,800,kg/m3,15\n'
    files['tickets'] = text.encode()
    balance = compute(files)['balance']
    ids = {ticket for g in balance['overlaps'] for ticket in g['tickets']}
    assert 'B01' not in ids and 'B02' not in ids


def test_reprint_duplicates_and_conflicts_follow_intake_rules():
    from app.intake.evidence import channel_report
    raw = b'reprint,truck,tickets,document\nRP-1,FT-12,T01;DUP1,R\nRP-1,FT-12,T01;DUP1,R\n'
    report = channel_report('reprints', raw)
    assert report['accepted'] == 1 and report['duplicate'] == 1
    clashing = b'reprint,truck,tickets,document\nRP-1,FT-12,T01;DUP1,R\nRP-1,FT-12,T01;DUP2,R\n'
    conflict = channel_report('reprints', clashing)
    assert conflict['accepted'] == 0 and conflict['reasons'] == {'CONFLICT': 2}
