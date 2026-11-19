from decimal import Decimal
from copy import deepcopy
from app.pipeline import calculate
from app.config import MULTI_SAMPLE
from app.domain import allocate_whole
from app.modules.m8_consolidation.rules import apply as consolidate
from app.publish import evaluate

def test_whole_unit_allocation_conserves():
    amounts={'a':Decimal('15.0'),'b':Decimal('15.15'),'c':Decimal('15.9')}
    result=allocate_whole(amounts)
    # 合计 46.05 向下取整为 46：先各取整得 45，余 1 股给余数最大的 c。
    assert sum(result.values())==46 and result['c']==16 and result['b']==15

def test_single_account_client_defaults(ctx):
    stage=ctx['stages']['8']
    assert stage['metrics'][0][1]==19
    assert all(r['账户']==r['持仓记录'] and r['客户']==r['账户'] for r in stage['rows'])

def test_client_total_uses_combined_holding(multi_ctx):
    stage=multi_ctx['stages']['8']
    c1=[r for r in stage['clients'] if r['客户']=='C0001'][0]
    # 逐账户取整 15+15+16=46；按客户合计 315*0.15=47.25 向下取整得 47。
    assert c1['客户新增股份']=='47' and c1['登记新增股份']=='46' and c1['股份差异']=='1'

def test_client_cash_residual(multi_ctx):
    c1=[r for r in multi_ctx['stages']['8']['clients'] if r['客户']=='C0001'][0]
    # 315*0.131=41.265 四舍五入 41.27；逐账户登记 13.10+13.36+14.80=41.26。
    assert c1['客户分红_CNY']=='41.27' and c1['登记分红_CNY']=='41.26' and c1['现金差异_CNY']=='0.01'

def test_allocation_sums_to_client(multi_ctx):
    stage=multi_ctx['stages']['8']
    for client in stage['clients']:
        rows=[r for r in stage['rows'] if r['客户']==client['客户']]
        assert sum(Decimal(r['分摊新增股份']) for r in rows)==Decimal(client['客户新增股份'])
        assert sum(Decimal(r['分摊分红_CNY']) for r in rows)==Decimal(client['客户分红_CNY'])

def test_residual_lands_on_documented_account(multi_ctx):
    row=[r for r in multi_ctx['stages']['8']['rows'] if r['账户']=='7003'][0]
    # 7003 的送转零碎余数 0.95 最大，现金分数余数也最大，同时承接 1 股与 0.01 元尾差。
    assert row['股份调整']=='1' and row['现金调整_CNY']=='0.01'

def test_account_moved_to_other_client_is_blocked(multi_ctx):
    # 已确认台账里 7002 属于 C0009；现批次显示 C0001，必须阻断并列出变更。
    confirmed={'run_id':'prev','lines':[{'client':'C0009','account':'7002','security':'000001','ex_date':'2026-11-18','added_shares':'15','cash':'13.23'}]}
    state=evaluate(multi_ctx,confirmed)
    assert 'ATTRIBUTION_CHANGED:7002' in state['blockers']
    assert state['status']=='不可发布'
    assert state['attribution_changes'][0]=={'账户':'7002','证券':'000001','除权日':'2026-11-18','原客户':'C0009','现客户':'C0001'}
    moved=[d for d in state['diff'] if d['账户']=='7002'][0]
    assert moved['类型']=='归属变更' and moved['新客户']=='C0001'

def test_acknowledged_attribution_is_publishable(multi_ctx):
    confirmed={'run_id':'prev','lines':[{'client':'C0009','account':'7002','security':'000001','ex_date':'2026-11-18','added_shares':'15','cash':'13.23'}]}
    state=evaluate(multi_ctx,confirmed,acknowledged=['ATTRIBUTION_CHANGED:7002'])
    assert state['blockers']==[] and state['publishable'] is True

def test_late_snapshot_not_double_counted(multi_ctx):
    stage=multi_ctx['stages']['8']
    assert not any(r['持仓记录']=='P1006' for r in stage['rows'])
    assert [r['账户'] for r in stage['rows'] if r['客户']=='C0003']==['7005']

def test_publish_requires_review(multi_ctx):
    state=evaluate(multi_ctx)
    assert state['publishable'] is True and state['status']=='待复核' and state['needs_review']

def test_publish_blocks_on_structural_issue(ctx):
    c=deepcopy(ctx)
    c['stages']['8']['publish']={'publishable':False,'status':'不可发布','blockers':['ATTRIBUTION_CONFLICT:7005']}
    assert evaluate(c)['status']=='不可发布'
    assert evaluate(c)['publishable'] is False

def test_cash_allocation_with_target_matches_client_total():
    from app.domain import allocate_cents
    amounts={'7001':Decimal('13.100'),'7002':Decimal('13.231'),'7003':Decimal('13.886')}
    result=allocate_cents(amounts,target=4022)
    assert sum(result.values())==Decimal('40.22')
    assert set(result)==set(amounts)

def test_client_fraction_retained_in_summary(multi_ctx):
    c1=[r for r in multi_ctx['stages']['8']['clients'] if r['客户']=='C0001'][0]
    # 47.25 股新增中取整 47 股，0.25 股作为客户层面零碎股保留，不四舍五入成整股。
    assert c1['客户零碎股']=='0.25'

def test_allocation_adjustments_only_on_documented_accounts(multi_ctx):
    rows=multi_ctx['stages']['8']['rows']
    adjusted=[r['账户'] for r in rows if r['股份调整']!='0' or r['现金调整_CNY']!='0.00']
    assert adjusted==['7003']
