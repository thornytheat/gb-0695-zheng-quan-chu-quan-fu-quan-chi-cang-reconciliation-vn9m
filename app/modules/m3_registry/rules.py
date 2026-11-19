from app.domain import day

def apply(ctx):
    rows=[];eligible=[];selected=set()
    for action in ctx['actions']:
        matching=[p for p in ctx['positions'] if p['canonical']==action['canonical'] and day(p['event_date'])<=day(action['record_date'])]
        # 每个账户只取登记日前最后一笔快照，避免同一账户多日快照重复计权。
        latest={}
        for p in matching:
            prior=latest.get(p['account_key'])
            if prior is None or (p['event_date'],p['行号'])>(prior['event_date'],prior['行号']): latest[p['account_key']]=p
        for p in sorted(latest.values(),key=lambda x:(x['client_key'],x['account_key'],x['record'])):
            eligible.append({'position':p,'action':action});selected.add((p['record'],p['event_date']))
            rows.append({'客户':p['client_key'],'账户':p['account_key'],'持仓记录':p['record'],'证券':p['canonical'],'资格':'有登记权益','股份':p['shares'],'行动':action['record']})
    for p in ctx['positions']:
        if (p['record'],p['event_date']) not in selected:
            rows.append({'客户':p['client_key'],'账户':p['account_key'],'持仓记录':p['record'],'证券':p['canonical'],'资格':'无登记权益','股份':p['shares'],'行动':''})
    ctx['eligible']=eligible
    return {'rows':rows,'metrics':[['有权益',len(eligible),'条'],['无权益',sum(r['资格']=='无登记权益' for r in rows),'条'],['登记日',' / '.join(sorted({a['record_date'] for a in ctx['actions']})),'']]}
