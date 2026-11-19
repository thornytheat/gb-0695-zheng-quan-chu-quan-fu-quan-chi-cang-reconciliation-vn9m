from pathlib import Path
RULE_VERSION = "2026.11.19.1"
TITLE = '证券除权复权与持仓对账'
SHORT = 'equity-adjust'
MODULES = ['行动接收', '证券映射', '权益登记', '除权因子', '持仓重算', '现金对账', '修订回放', '客户合并']
HEADERS = ['record', 'kind', 'security', 'alias', 'event_date', 'record_date', 'ex_date', 'price', 'cash', 'bonus', 'rights', 'rights_price', 'shares', 'version', 'reported_cash']
OPTIONAL_HEADERS = ['client', 'account']
SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "operations.csv"
MULTI_SAMPLE = Path(__file__).resolve().parent.parent / "sample_data" / "multi_account.csv"
LIMIT = 10000
