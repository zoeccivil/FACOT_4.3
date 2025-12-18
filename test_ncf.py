from firebase import firebase_client
from data_access import get_data_access, DataAccessMode

# obtener data_access (ajusta según tu helper)
da = get_data_access(user_id=None, mode=DataAccessMode.FIREBASE)

company_id = 1
prefix = "B01"

print("Testing allocate_next_ncf...")
try:
    ncf = da.allocate_next_ncf(company_id, prefix)
    print("allocate_next_ncf ->", ncf)
except Exception as e:
    print("allocate_next_ncf ERROR:", e)

print("Testing set_ncf_last_seq (guardar manual)...")
try:
    ok = da.set_ncf_last_seq(company_id, prefix, 200)
    print("set_ncf_last_seq ->", ok)
except Exception as e:
    print("set_ncf_last_seq ERROR:", e)

print("Testing set_company_due_date ...")
try:
    ok2 = da.set_company_due_date(company_id, "2025-12-31")
    print("set_company_due_date ->", ok2)
except Exception as e:
    print("set_company_due_date ERROR:", e)