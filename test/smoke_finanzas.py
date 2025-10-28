# tests/smoke_finanzas.py  (ejecútalo con `python -m tests.smoke_finanzas`)
from sqlalchemy import func
from app.database import SessionLocal
from app.models import FacturaCXP, FacturaCXC
from app.repo_finanzas_db import FinanzasRepoDB

db = SessionLocal()
try:
    n_cxp = db.query(func.count(FacturaCXP.id_cxp)).scalar()
    n_cxc = db.query(func.count(FacturaCXC.id_cxc)).scalar()
    print("CxP visibles:", n_cxp, "| CxC visibles:", n_cxc)
finally:
    db.close()

repo = FinanzasRepoDB()
print("CxP balance ago-2025:", repo.cxp_balance_by_month(2025, 8))
print("DPO ago-2025:", repo.dpo(2025, 8))
print("CxC balance ago-2025:", repo.cxc_balance_by_month(2025, 8))
print("DSO ago-2025:", repo.dso(2025, 8))
print("Aging CxC hoy:", repo.cxc_aging())
