from ..base import BaseAgent
from ...state import GlobalState
from ...tools.excel_io import read_excel_required
from ...tools.calc_kpis import aging_buckets_cxp, dpo, month_window
from ...tools.schema_validate import validate_with
from typing import Dict, Any

REQUIRED = ["invoice_id","supplier","issue_date","due_date","base_amount","tax","total_amount","paid_amount","payment_date"]
DEFAULT_PATH = "data/cxp/invoices.xlsx"
SCHEMA = "app/schemas/aaav_cxp_schema.json"

class Agent(BaseAgent):
    name = "aaav_cxp"
    role = "operational"

    def handle(self, task, state: GlobalState) -> Dict[str, Any]:
        period = task.get("payload", {}).get("period", state.period)
        path = task.get("payload", {}).get("path", DEFAULT_PATH)
        try:
            start, end, ref_date = month_window(period)
            df = read_excel_required(path, REQUIRED)

            aging = aging_buckets_cxp(df, ref_date)
            kpi_dpo = dpo(df, start, end)
            payload = {"period": period, "aging": aging, "kpi": {"DPO": kpi_dpo}}
            validate_with(SCHEMA, payload)
            return {"agent": self.name, "summary": "CxP calculado", "data": payload}
        except Exception as e:
            return {"agent": self.name, "error": str(e), "needs": {"path": path, "required_cols": REQUIRED}}
