from decimal import Decimal

def lines_of(result):
    # 发布台账的最小粒度：账户 × 证券 × 除权日；客户是账户的归属属性。
    rows=result.get('stages',{}).get('8',{}).get('rows',[])
    return [{'client':r['客户'],'account':r['账户'],'security':r['证券'],'ex_date':r['除权日'],
             'added_shares':r['分摊新增股份'],'cash':r['分摊分红_CNY']} for r in rows]

def _delta(before,after,prefix=''):
    if before is not None and after is not None:return str(Decimal(after)-Decimal(before))
    return (prefix+after) if after is not None else ('-'+before)

def evaluate(result, confirmed=None, decision=None, acknowledged=()):
    confirmed=confirmed or {'run_id':None,'lines':[]}
    decision=decision if decision is not None else result.get('decision','待复核')
    acknowledged=set(acknowledged or ())
    run_id=result.get('manifest',{}).get('run_id')
    stage=result.get('stages',{}).get('8',{})
    blockers=list(stage.get('publish',{}).get('blockers',[]))
    has_baseline=bool(confirmed.get('run_id'))
    new_lines=lines_of(result)
    new={ (l['account'],l['security'],l['ex_date']):l for l in new_lines }
    old={ (l['account'],l['security'],l['ex_date']):l for l in confirmed.get('lines',[])} if has_baseline else {}
    # 归属以账户为业务键：已确认账户改挂客户时必须显式确认，不能由晚到记录静默覆盖。
    attribution=[]
    for key in sorted(new):
        if key in old and old[key]['client']!=new[key]['client']:
            attribution.append({'账户':key[0],'证券':key[1],'除权日':key[2],'原客户':old[key]['client'],'现客户':new[key]['client']})
    for change in attribution:
        code='ATTRIBUTION_CHANGED:'+change['账户']
        if code not in acknowledged: blockers.append(code)
    diff=[]
    if has_baseline:
        for key in sorted(set(old)|set(new)):
            before,after=old.get(key),new.get(key)
            if before and after and before['added_shares']==after['added_shares'] and before['cash']==after['cash'] and before['client']==after['client']:continue
            moved=bool(before and after and before['client']!=after['client'])
            diff.append({
                '客户':after['client'] if after else before['client'],
                '账户':key[0],'证券':key[1],'除权日':key[2],
                '原客户':before['client'] if before else '—',
                '新客户':after['client'] if after else '—',
                '原分摊股份':before['added_shares'] if before else '—',
                '现分摊股份':after['added_shares'] if after else '—',
                '股份变动':_delta(before['added_shares'] if before else None,after['added_shares'] if after else None,'+'),
                '原分摊现金_CNY':before['cash'] if before else '—',
                '现分摊现金_CNY':after['cash'] if after else '—',
                '现金变动_CNY':_delta(before['cash'] if before else None,after['cash'] if after else None,'+'),
                '类型':'归属变更' if moved else ('新增' if not before else ('撤销' if not after else '调整')),
            })
    blockers=sorted(set(blockers))
    published=decision=='通过' and has_baseline and confirmed.get('run_id')==run_id
    if blockers:status='不可发布'
    elif published:status='已发布'
    else:status='待复核'
    release_clients=sorted({l['client'] for l in new_lines})
    confirmed_clients=sorted({l['client'] for l in confirmed.get('lines',[])}) if has_baseline else []
    return {
        'status':status,
        # 能否发布只看硬性阻断；复核动作本身仍是发布前的必经步骤。
        'publishable':not blockers,
        'approved':decision=='通过',
        'needs_review':not published,
        'blockers':blockers,
        'attribution_changes':attribution,
        'acknowledged':sorted(acknowledged),
        'diff':diff,
        'diff_count':len(diff),
        'client_count':len(release_clients),
        'confirmed_client_count':len(confirmed_clients),
        'clients_added':sorted(set(release_clients)-set(confirmed_clients)),
        'clients_removed':sorted(set(confirmed_clients)-set(release_clients)),
        'has_baseline':has_baseline,
        'confirmed_run_id':confirmed.get('run_id'),
        'reason':('存在阻断项，修正前不可发布' if blockers else
                  ('已复核通过并写入已确认台账' if published else
                   ('与已确认结果有 %d 项差异，需复核确认'%len(diff) if diff else
                    '内部一致；复核通过后可发布'))),
    }

def decorate(result, confirmed=None, decision=None, acknowledged=()):
    if 'stages' not in result or '8' not in result['stages']:return result
    result['stages']['8']['release']=evaluate(result,confirmed,decision,acknowledged)
    return result
