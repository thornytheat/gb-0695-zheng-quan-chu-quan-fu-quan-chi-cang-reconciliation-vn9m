from app.numeric import number
def test_security_leading_zero(ctx): # TRAP-08
    assert ctx['actions'][0]['canonical']=='000001'
def test_large_id_unchanged(ctx): # TRAP-09
    assert ctx['positions'][0]['record']=='9007199254741001'
def test_fullwidth_decimal(): # TRAP-06
    assert number('１,２３４.５')==number('1234.5')
def test_conflicting_action_removed(ctx): # TRAP-14
    assert all(a['canonical']!='000003' for a in ctx['actions'])
def test_latest_action_chosen(ctx): # TRAP-25
    assert ctx['actions'][0]['version']=='2'
def test_older_action_retained(ctx):assert len(ctx['action_history'])==1
def test_missing_shares_isolated(ctx):assert any(q['原因码']=='MISSING' for q in ctx['quarantine'])


def _multi():
    from app.config import MULTI_SAMPLE
    from app.pipeline import calculate
    return MULTI_SAMPLE.read_text(encoding='utf-8-sig')

def test_optional_attribution_columns_keep_legacy_defaults(ctx):
    assert all(p['account_key']==p['record'] and p['client_key']==p['account_key'] for p in ctx['positions'])

def test_multi_account_attribution_parsed():
    from app.pipeline import calculate
    result=calculate(_multi())
    pairs={(p['client_key'],p['account_key']) for p in result['positions']}
    assert ('C0001','7001') in pairs and ('C0003','7005') in pairs

def test_same_day_two_clients_isolated():
    from app.pipeline import calculate
    base=_multi();target=[line for line in base.splitlines() if line.startswith('P1001')][0]
    changed=base.replace(target,target.replace(',C0001,7001',',C0009,7001'),1)
    result=calculate(changed)
    assert [q['原因码'] for q in result['quarantine']]==['ATTRIBUTION_CONFLICT','ATTRIBUTION_CONFLICT']

def test_cross_snapshot_client_drift_isolated():
    from app.pipeline import calculate
    base=_multi();target=[line for line in base.splitlines() if line.startswith('P1005')][0]
    changed=base.replace(target,target.replace(',C0003,7005',',C0008,7005'))
    result=calculate(changed)
    assert {q['原因'] for q in result['quarantine']}=={'同一账户跨快照归属多个客户'}

def test_unknown_optional_column_rejected():
    import pytest
    from app.errors import DomainError
    from app.pipeline import calculate
    base=_multi().replace('client,account','client,account,owner',1)
    with pytest.raises(DomainError):calculate(base)
