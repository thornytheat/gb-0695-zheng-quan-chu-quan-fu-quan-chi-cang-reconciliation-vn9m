from decimal import Decimal,ROUND_FLOOR,ROUND_HALF_UP
from app.domain import allocate_whole,allocate_cents
from app.numeric import fmt,number

def apply(ctx):
    registered={r['持仓记录']:r for r in ctx['holdings']}
    groups={}
    for item in ctx['eligible']:
        p,a=item['position'],item['action']
        groups.setdefault((p['client_key'],p['canonical'],a['ex_date']),[]).append((p,a))
    rows=[];clients={};blockers=[]
    for key,entries in sorted(groups.items()):
        client,security,ex_date=key
        entries=sorted(entries,key=lambda pair:(pair[0]['account_key'],pair[0]['record']))
        action=entries[0][1]
        shares={};advanced={};theoretical={};registered_added={}
        for p,a in entries:
            record=p['record'];shares[record]=number(p['shares'])
            advanced[record]=shares[record]*(number(a['bonus'])+number(a['rights']))
            theoretical[record]=shares[record]*number(a['cash'])
            registered_added[record]=Decimal(registered[record]['新股份'])-shares[record]
        client_shares=sum(shares.values(),Decimal(0))
        client_added=client_shares*(number(action['bonus'])+number(action['rights']))
        client_whole=client_added.to_integral_value(rounding=ROUND_FLOOR)
        client_cash=(client_shares*number(action['cash'])).quantize(Decimal('0.01'),rounding=ROUND_HALF_UP)
        # 客户合并后按最大余额把尾差分摊回账户；分摊合计恒等于客户总数。
        consolidated_added=allocate_whole(advanced)
        consolidated_cash=allocate_cents(theoretical,target=int(client_cash*100))
        registered_new=sum((registered_added[p['record']] for p,a in entries),Decimal(0))
        registered_cash=sum((Decimal(registered[p['record']]['分红_CNY']) for p,a in entries),Decimal(0))
        allocated_new=Decimal(0);allocated_cash=Decimal(0)
        for p,a in entries:
            record=p['record'];account=p['account_key']
            new=consolidated_added[record];cash=consolidated_cash[record]
            allocated_new+=new;allocated_cash+=cash
            rows.append({
                '客户':client,'账户':account,'持仓记录':record,'证券':security,'除权日':ex_date,
                '原股份':str(int(shares[record])),
                '登记新增股份':str(int(registered_added[record])),
                '分摊新增股份':str(int(new)),
                '登记总股数':str(int(shares[record]+registered_added[record])),
                '分摊总股数':str(int(shares[record]+new)),
                '股份调整':str(int(new-registered_added[record])),
                '登记分红_CNY':fmt(Decimal(registered[record]['分红_CNY']),'0.01'),
                '分摊分红_CNY':fmt(cash,'0.01'),
                '现金调整_CNY':fmt(cash-Decimal(registered[record]['分红_CNY']),'0.01'),
                '零碎调整':str(new-advanced[record]),
            })
        if allocated_new!=client_whole:blockers.append('SHARE_ALLOCATION_MISMATCH:'+client+':'+security+':'+ex_date)
        if allocated_cash!=client_cash:blockers.append('CASH_ALLOCATION_MISMATCH:'+client+':'+security+':'+ex_date)
        summary=clients.setdefault(client,{'客户':client,'账户':set(),'证券':set(),'原股份':Decimal(0),'客户新增股份':Decimal(0),'登记新增股份':Decimal(0),'股份差异':Decimal(0),'客户总股数':Decimal(0),'登记总股数':Decimal(0),'客户分红_CNY':Decimal(0),'登记分红_CNY':Decimal(0),'现金差异_CNY':Decimal(0),'客户零碎股':Decimal(0)})
        for p,a in entries:summary['账户'].add(p['account_key'])
        summary['证券'].add(security)
        summary['原股份']+=client_shares
        summary['客户新增股份']+=client_whole
        summary['登记新增股份']+=registered_new
        summary['股份差异']+=client_whole-registered_new
        summary['客户总股数']+=client_shares+client_whole
        summary['登记总股数']+=client_shares+registered_new
        summary['客户分红_CNY']+=client_cash
        summary['登记分红_CNY']+=registered_cash
        summary['现金差异_CNY']+=client_cash-registered_cash
        summary['客户零碎股']+=client_added-client_whole
    client_rows=[]
    for client in sorted(clients):
        s=clients[client]
        client_rows.append({
            '客户':client,'账户数':str(len(s['账户'])),'证券数':str(len(s['证券'])),
            '原股份':str(int(s['原股份'])),
            '客户新增股份':str(int(s['客户新增股份'])),
            '登记新增股份':str(int(s['登记新增股份'])),
            '客户总股数':str(int(s['客户总股数'])),
            '登记总股数':str(int(s['登记总股数'])),
            '股份差异':str(int(s['股份差异'])),
            '客户分红_CNY':fmt(s['客户分红_CNY'],'0.01'),
            '登记分红_CNY':fmt(s['登记分红_CNY'],'0.01'),
            '现金差异_CNY':fmt(s['现金差异_CNY'],'0.01'),
            '客户零碎股':str(s['客户零碎股']),
        })
    for code in ('ATTRIBUTION_CONFLICT','POSITION_CONFLICT'):
        count=ctx.get('issue_counts',{}).get(code,0)
        if count:blockers.append('%s:%d'%(code,count))
    if ctx.get('balanced') is False:blockers.append('RECORD_CONSERVATION')
    publish={'publishable':not blockers,'status':'可发布' if not blockers else '不可发布','blockers':sorted(set(blockers))}
    ctx['consolidation']={'rows':rows,'clients':client_rows,'publish':publish}
    share_residual=sum(Decimal(r['股份调整']) for r in rows)
    cash_residual=sum(Decimal(r['现金调整_CNY']) for r in rows)
    return {
        'rows':rows,
        'clients':client_rows,
        'publish':publish,
        'metrics':[
            ['客户数',len(client_rows),'户'],
            ['账户分摊',len(rows),'条'],
            ['股份尾差',str(int(share_residual)),'股'],
            ['现金尾差',fmt(cash_residual,'0.01'),'CNY'],
            ['可发布','是' if not blockers else '否',''],
        ],
    }
