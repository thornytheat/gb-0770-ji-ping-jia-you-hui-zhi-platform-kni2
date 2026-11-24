def test_balance_has_tank_scales_and_real_receipt_flags(client):
    shown=client.get('/').get_data(as_text=True)
    assert '罐车收发双账' in shown and '1.400 kg' in shown and 'gauge-fill' in shown
    feature=client.get('/ops/readings').get_data(as_text=True)
    assert '仪表回卷证据' in feature and '真实回卷' in feature


def test_overlap_workbench_shows_merge_and_dispute(client):
    shown=client.get('/').get_data(as_text=True)
    assert '同车时间重叠票组' in shown
    assert '同一笔发油 · 只扣一次' in shown and '凭据不足 · 留待核' in shown
    assert '争议待核' in shown and '重打凭据采信账' in shown
    # 两张被合并的原票仍可在明细中查到
    assert 'DUP1' in shown and 'DUP2' in shown
    clean=client.get('/?sample=clean').get_data(as_text=True)
    assert '首尾相接照常核算' in clean or '同车时间重叠票组' in clean
