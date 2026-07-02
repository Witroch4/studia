from app.tasks.ledger import LEDGER_DDL


def test_ddl_concursos_presente_e_splitavel():
    assert "tc_concurso_units" in LEDGER_DDL
    assert "uq_tc_jobs_active_concursos" in LEDGER_DDL
    stmts = "\n".join(l.split("--", 1)[0] for l in LEDGER_DDL.splitlines()).split(";")
    assert all("--" not in s for s in stmts)
