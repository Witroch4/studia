from models import CalculadoraHistorico, QuestaoAnotacao


def test_annotation_model_uses_expected_table_and_index():
    assert QuestaoAnotacao.__tablename__ == "questao_anotacoes"
    columns = set(QuestaoAnotacao.__table__.columns.keys())
    assert columns == {
        "id",
        "usuario_id",
        "usuario_uid",
        "caderno_id",
        "questao_id",
        "canvas_json",
        "strikes_json",
        "created_at",
        "updated_at",
    }
    # Escopo por usuário real (usuario_uid), não mais single-tenant.
    index = next(
        index
        for index in QuestaoAnotacao.__table__.indexes
        if index.name == "uq_questao_anotacoes_scope_uid"
    )
    assert index.unique is True
    assert len(index.expressions) == 3


def test_calculator_history_model_uses_expected_table():
    assert CalculadoraHistorico.__tablename__ == "calculadora_historico"
    columns = set(CalculadoraHistorico.__table__.columns.keys())
    assert columns == {
        "id",
        "usuario_id",
        "usuario_uid",
        "caderno_id",
        "questao_id",
        "expression",
        "result",
        "created_at",
    }
