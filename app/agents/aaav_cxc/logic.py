from ..base import BaseAgent
from ...state import GlobalState
from ...tools.excel_io import read_excel_required
from ...tools.calc_kpis import aging_buckets_cxc, dso, month_window
from ...tools.schema_validate import validate_with
from typing import Dict, Any
import pandas as pd

REQUIRED = ["invoice_id","customer","issue_date","due_date","amount","paid_amount","payment_date"]
DEFAULT_PATH = "data/cxc/invoices.xlsx"
SCHEMA = "app/schemas/aaav_cxc_schema.json"

class Agent(BaseAgent):
    name = "aaav_cxc"
    role = "operational"

    def handle(self, task: Dict[str, Any], state: GlobalState) -> Dict[str, Any]:
        period = task.get("payload", {}).get("period", state.period)
        path = task.get("payload", {}).get("path", DEFAULT_PATH)
        try:
            start, end, ref_date = month_window(period)
            df = read_excel_required(path, REQUIRED)

            aging = aging_buckets_cxc(df, ref_date)
            kpi_dso = dso(df, start, end)
            payload = {
                "period": period,
                "aging": aging,
                "kpi": {"DSO": kpi_dso},
                "incidents": []
            }
            validate_with(SCHEMA, payload)
            return {"agent": self.name, "summary": "CxC calculado", "data": payload}
        except Exception as e:
            return {"agent": self.name, "error": str(e), "needs": {"path": path, "required_cols": REQUIRED}}
