import sqlite3, json, os, time
from pathlib import Path
from app.errors import DomainError
from app.publish import lines_of
SCHEMA=[
 'CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, payload TEXT NOT NULL, revision INTEGER NOT NULL DEFAULT 1, decision TEXT NOT NULL DEFAULT "待复核")',
 # 已确认台账独立于批次内容，便于晚到批次只比对、不回写。
 'CREATE TABLE IF NOT EXISTS confirmed_meta(key TEXT PRIMARY KEY, run_id TEXT NOT NULL, decided_at TEXT NOT NULL)',
 'CREATE TABLE IF NOT EXISTS confirmed_lines(run_id TEXT NOT NULL, client TEXT NOT NULL, account TEXT NOT NULL, security TEXT NOT NULL, ex_date TEXT NOT NULL, added_shares TEXT NOT NULL, cash TEXT NOT NULL, PRIMARY KEY(account,security,ex_date))',
]
def connection():
    path=Path(os.environ.get('APP_DB','data/runs.sqlite3'));path.parent.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(path);db.row_factory=sqlite3.Row
    for statement in SCHEMA: db.execute(statement)
    return db
def save(result):
    with connection() as db:
        ident=result['manifest']['run_id'];row=db.execute('SELECT payload,revision,decision FROM runs WHERE id=?',(ident,)).fetchone()
        if row: return {**json.loads(row['payload']), 'revision':row['revision'], 'decision':row['decision'], 'reused':True}
        db.execute('INSERT INTO runs(id,payload) VALUES (?,?)',(ident,json.dumps(result,ensure_ascii=False)))
    return {**result,'revision':1,'decision':'待复核','reused':False}
def get_run(ident):
    with connection() as db: row=db.execute('SELECT payload,revision,decision FROM runs WHERE id=?',(ident,)).fetchone()
    if row is None: raise DomainError('NOT_FOUND','批次不存在',404)
    return {**json.loads(row['payload']),'revision':row['revision'],'decision':row['decision']}
def latest():
    with connection() as db: row=db.execute('SELECT payload,revision,decision FROM runs ORDER BY rowid DESC LIMIT 1').fetchone()
    return {**json.loads(row['payload']),'revision':row['revision'],'decision':row['decision']} if row else None
def history():
    with connection() as db: return [dict(r) for r in db.execute('SELECT id,revision,decision FROM runs ORDER BY rowid DESC')]
def confirmed():
    # 已确认结果是一个不可变快照；只有复核通过的新批次才会整体替换它。
    with connection() as db:
        meta=db.execute("SELECT run_id FROM confirmed_meta WHERE key='confirmed'").fetchone()
        if meta is None: return {'run_id':None,'lines':[]}
        lines=[dict(r) for r in db.execute('SELECT client,account,security,ex_date,added_shares,cash FROM confirmed_lines ORDER BY client,account,security,ex_date')]
    return {'run_id':meta['run_id'],'lines':lines}
def review(ident, revision, decision, ledger=None):
    if decision not in ('通过','退回'): raise DomainError('DECISION','复核动作无效')
    with connection() as db:
        row=db.execute('SELECT payload,revision,decision FROM runs WHERE id=?',(ident,)).fetchone()
        if row is None: raise DomainError('NOT_FOUND','批次不存在',404)
        changed=db.execute('UPDATE runs SET revision=revision+1,decision=? WHERE id=? AND revision=?',(decision,ident,revision)).rowcount
        if not changed: raise DomainError('VERSION','版本已变化，请重新载入',409)
        if decision=='通过':
            # 主键即业务键：重放同一批或同一账户只覆盖对应行，不会重复累加。
            if ledger is None: ledger=lines_of(json.loads(row['payload']))
            db.execute('DELETE FROM confirmed_lines')
            db.executemany('INSERT INTO confirmed_lines(run_id,client,account,security,ex_date,added_shares,cash) VALUES (?,?,?,?,?,?,?)',
                [(ident,line['client'],line['account'],line['security'],line['ex_date'],line['added_shares'],line['cash']) for line in ledger])
            db.execute("INSERT INTO confirmed_meta(key,run_id,decided_at) VALUES ('confirmed',?,?) ON CONFLICT(key) DO UPDATE SET run_id=excluded.run_id,decided_at=excluded.decided_at",
                (ident,time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime())))
    return {'revision':revision+1,'decision':decision}
