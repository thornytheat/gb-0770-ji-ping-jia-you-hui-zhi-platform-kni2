from app.bundles import sample_set


def test_archive_keeps_deduction_basis_and_rerun_deducts_once(client):
    first = client.post('/api/shifts', json={'sample': 'dirty'})
    assert first.status_code == 201
    batch = first.json['batch']
    # 同批复跑不重复扣库存：批次复用、合计一致
    repeat = client.post('/api/shifts', json={'sample': 'dirty'})
    assert repeat.status_code == 200 and repeat.json == dict(first.json, reused=True)

    archived = client.get('/api/shifts/' + batch).json['stages']['balance']
    merged = next(g for g in archived['overlaps'] if g['status'] == 'CONFIRMED')
    assert merged['tickets'] == ['T01', 'DUP1', 'DUP2'] and merged['evidence'] == [2]
    truck = next(s for s in archived['stocks'] if s['truck'] == 'FT-12')
    assert truck['issued_g'] == 191600 and truck['difference_g'] == 1400
    # 两张原票都留档可查
    receipts = {row['ticket']: row for row in archived['receipts']}
    assert receipts['DUP1']['state'] == 'MERGED_DUPLICATE' and receipts['DUP2']['keeper'] == 'T01'
    # 争议车只列已确认发油、不出盈亏
    disputed = next(s for s in archived['stocks'] if s['truck'] == 'FT-18')
    assert disputed['disputed'] and disputed['difference_g'] is None and disputed['confirmed_mass_g'] == 88000


def test_optional_reprints_channel_accepted_over_api(client):
    bundle = {key: raw.decode() for key, raw in sample_set('dirty').items()}
    response = client.post('/api/balance', json=bundle)
    assert response.status_code == 200
    assert response.json['confirmed_overlap_groups'] == 1
    # 去掉重打凭据后重叠组转为待核
    bundle.pop('reprints')
    held = client.post('/api/balance', json=bundle).json
    assert held['confirmed_overlap_groups'] == 0 and held['pending_overlap_groups'] == 2


def test_bundle_with_unknown_channel_is_rejected(client):
    bundle = {key: raw.decode() for key, raw in sample_set('dirty').items()}
    bundle['rogue'] = 'x'
    assert client.post('/api/intake', json=bundle).status_code == 422
