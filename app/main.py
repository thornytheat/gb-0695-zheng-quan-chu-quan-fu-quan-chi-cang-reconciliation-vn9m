from flask import Flask, request, jsonify, Response
import csv,io
from app.errors import DomainError
from app.reader import decode
from app.pipeline import calculate
from app.publish import decorate, lines_of, evaluate
from app.store import save, latest, history, review, get_run, confirmed
from app.web import bp as web

from app.modules.m1_receiving.handler import bp as bp1
from app.modules.m2_mapping.handler import bp as bp2
from app.modules.m3_registry.handler import bp as bp3
from app.modules.m4_factors.handler import bp as bp4
from app.modules.m5_holdings.handler import bp as bp5
from app.modules.m6_cash.handler import bp as bp6
from app.modules.m7_revisions.handler import bp as bp7
from app.modules.m8_consolidation.handler import bp as bp8
app=Flask(__name__)
app.config['MAX_CONTENT_LENGTH']=5*1024*1024
app.json.ensure_ascii=False
@app.template_filter('display')
def display(value):
    import re
    from decimal import Decimal
    text=str(value)
    if re.fullmatch(r'-?[0-9]+\.[0-9]+',text):
        return format(Decimal(text),'.4f').rstrip('0').rstrip('.')
    return text
@app.template_filter('amount')
def amount(value):
    from decimal import Decimal,InvalidOperation
    try:return format(Decimal(str(value)),'.2f')
    except (InvalidOperation,ValueError):return str(value)
app.register_blueprint(web)
app.register_blueprint(bp1)
app.register_blueprint(bp2)
app.register_blueprint(bp3)
app.register_blueprint(bp4)
app.register_blueprint(bp5)
app.register_blueprint(bp6)
app.register_blueprint(bp7)
app.register_blueprint(bp8)
@app.before_request
def validate_request_object():
    if request.method!='POST': return None
    if request.files:
        if request.path!='/api/run' or 'file' not in request.files:
            raise DomainError('REQUEST','上传必须使用file字段',400)
        return None
    if not request.is_json:
        raise DomainError('REQUEST','请求须为JSON对象或CSV文件',400)
    if not isinstance(request.get_json(silent=True),dict):
        raise DomainError('REQUEST','请求内容必须为JSON对象',400)
@app.errorhandler(DomainError)
def domain_error(error): return jsonify({'code':error.code,'message':error.message}),error.status
@app.errorhandler(413)
def too_big(error): return jsonify({'code':'LIMIT','message':'文件超过5MB'}),413
@app.route('/health')
def health(): return {'status':'ok'}
@app.route('/api/run',methods=['POST'])
def run():
    if request.files:
        raw=request.files['file'].read();text=decode(raw)
    else:
        payload=request.get_json(silent=True) or {};text=payload.get('csv')
    result=save(calculate(text))
    return jsonify(decorate(result,confirmed()))
@app.route('/api/runs/<ident>')
def run_detail(ident): return jsonify(decorate(get_run(ident),confirmed()))
@app.route('/api/history')
def runs(): return jsonify(history())
@app.route('/api/publish')
def publish_state():
    ident=request.args.get('run_id');result=get_run(ident) if ident else (latest() or save(calculate()))
    if '8' not in result.get('stages',{}):
        raise DomainError('NOT_FOUND','批次不含客户合并结果',409)
    return jsonify(decorate(result,confirmed())['stages']['8']['release'])
@app.route('/api/review',methods=['POST'])
def decide():
    body=request.get_json(silent=True) or {}
    try: version=int(body.get('revision',0))
    except (ValueError,TypeError): raise DomainError('VERSION','版本必须为整数')
    ident=body.get('id');decision=body.get('decision')
    if decision not in ('通过','退回'): raise DomainError('DECISION','复核动作无效')
    acknowledge=body.get('acknowledge') or []
    if not isinstance(acknowledge,list) or any(not isinstance(x,str) for x in acknowledge):
        raise DomainError('REQUEST','acknowledge 必须为账户字符串数组',400)
    result=get_run(ident)
    state=evaluate(result,confirmed(),decision)
    known={'ATTRIBUTION_CHANGED:'+c['账户'] for c in state['attribution_changes']}
    unknown=[code for code in acknowledge if code not in known]
    if unknown: raise DomainError('ACK','仅可确认已列出的归属变更：'+'，'.join(unknown),422)
    state=evaluate(result,confirmed(),decision,acknowledge)
    if decision=='通过' and state['blockers']:
        raise DomainError('PUBLISH','存在阻断项，不能发布：'+'，'.join(state['blockers']),409)
    if decision=='退回' and state['confirmed_run_id']==ident:
        # 已发布批次不能被单方面退回而让台账指向一个已退回批次；只能由新批次覆盖。
        raise DomainError('PUBLISH','该批次为当前已确认结果，请提交新批次复核覆盖',409)
    # 通过即固化分摊结果；归属变更必须逐账户显式确认后才写入台账。
    ledger=lines_of(result) if decision=='通过' else None
    return jsonify(review(ident,version,decision,ledger))
@app.route('/api/evidence.csv')
def evidence():
    result=get_run(request.args['run_id']) if request.args.get('run_id') else (latest() or save(calculate()));out=io.StringIO(newline='')
    rows=[]
    for index,stage in result['stages'].items():
        rows.extend({'阶段':index,**r} for r in stage['rows'])
        # 客户合并阶段同时导出客户合计，便于复核客户总数与尾差。
        rows.extend({'阶段':index+'-客户',**r} for r in stage.get('clients',[]))
    rows.extend({'阶段':'隔离',**r} for r in result['quarantine'])
    # 证据只记录批次内容；发布状态依已确认台账随时间变化，不写入证据以保证不可变。
    publish=result.get('stages',{}).get('8',{}).get('publish')
    if publish:
        rows.append({'阶段':'8-发布','内部校验':'通过' if publish['publishable'] else '阻断',
                     '客户总数':len(result['stages']['8'].get('clients',[])),
                     '阻断项':'；'.join(publish.get('blockers',[])) or '无'})
    fields=list(dict.fromkeys(['阶段','run_id','规则版本']+[k for r in rows for k in r]))
    writer=csv.DictWriter(out,fieldnames=fields);writer.writeheader()
    for row in rows: writer.writerow({'run_id':result['manifest']['run_id'],'规则版本':result['manifest']['rule_version'],**row})
    return Response('﻿'+out.getvalue(),mimetype='text/csv',headers={'Content-Disposition':'attachment; filename=evidence.csv'})
if __name__=='__main__': app.run(host='0.0.0.0',port=8000)
