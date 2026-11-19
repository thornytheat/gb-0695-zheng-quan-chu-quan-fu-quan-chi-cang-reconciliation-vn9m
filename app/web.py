from flask import Blueprint, render_template, request
from app.config import TITLE, MODULES, SHORT, SAMPLE, MULTI_SAMPLE
from app.pipeline import calculate
from app.publish import decorate
from app.store import latest, save, get_run, confirmed
bp=Blueprint('web',__name__)
def loaded(ident=None):
    run=get_run(ident) if ident else latest()
    if run is None: run=save(calculate())
    # 发布状态按当前已确认台账实时评估，不写回批次内容，保证证据不可变。
    return decorate(run,confirmed())
@bp.route('/')
@bp.route('/work/<int:stage>')
def work(stage=1):
    if stage<1 or stage>len(MODULES):
        from flask import abort
        abort(404)
    ident=request.args.get('run_id')
    run=loaded(ident)
    if str(stage) not in run['stages']:
        # 旧批次早于某个模块时不改写历史证据，提示重新提交。
        from flask import abort
        abort(404)
    current=run['stages'][str(stage)]
    return render_template('m'+str(stage)+'.html', title=TITLE, modules=MODULES, short=SHORT, run=run, current=current, stage=stage, sample=SAMPLE.read_text(encoding='utf-8-sig'), multi_sample=MULTI_SAMPLE.read_text(encoding='utf-8-sig') if MULTI_SAMPLE.exists() else '')
