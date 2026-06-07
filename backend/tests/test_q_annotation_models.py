from models import CalculadoraHistorico, QuestaoAnotacao


def test_annotation_model_uses_expected_table_and_index():
    assert QuestaoAnotacao.__tablename__ == "questao_anotacoes"
    columns = set(QuestaoAnotacao.__table__.columns.keys())
    assert {
        "id",
        "usuario_id",
        "caderno_id",
        "questao_id",
        "canvas_json",
        "strikes_json",
        "created_at",
        "updated_at",
    }.issubset(columns)
    index_names = {index.name for index in QuestaoAnotacao.__table__.indexes}
    assert "uq_questao_anotacoes_scope" in index_names


def test_calculator_history_model_uses_expected_table():
    assert CalculadoraHistorico.__tablename__ == "calculadora_historico"
    columns = set(CalculadoraHistorico.__table__.columns.keys())
    assert {
        "id",
        "usuario_id",
        "caderno_id",
        "questao_id",
        "expression",
        "result",
        "created_at",
    }.issubset(columns)
