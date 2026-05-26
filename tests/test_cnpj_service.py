from unittest.mock import patch

from cnpj_service import consultar_cnpj, validar_cnpj


def test_validar_cnpj_valido():
    assert validar_cnpj("11444777000161") is True


def test_validar_cnpj_invalido():
    assert validar_cnpj("00000000000000") is False
    assert validar_cnpj("123") is False


def test_consultar_cnpj_fallback_receitaws():
    brasilapi_response = ValueError("BrasilAPI indisponível")
    receitaws_response = {
        "status": "OK",
        "cnpj": "11444777000161",
        "nome": "Empresa de Teste LTDA",
        "fantasia": "Teste",
        "situacao": "ATIVA",
        "data_situacao": "01/01/2024",
        "natureza_juridica": "Sociedade Empresária",
        "porte": "DEMAIS",
        "capital_social": 10000,
        "atividade_principal": [{"text": "Atividade de teste"}],
        "telefone": "1133334444",
        "email": "teste@empresa.com.br",
        "cep": "12345678",
        "logradouro": "Rua Teste",
        "numero": "100",
        "complemento": "Sala 1",
        "bairro": "Centro",
        "municipio": "Cidade",
        "uf": "SP",
    }

    with patch("cnpj_service._get_json", side_effect=[brasilapi_response, receitaws_response]):
        resultado = consultar_cnpj("11444777000161")

    assert resultado["razao_social"] == "Empresa de Teste LTDA"
    assert resultado["nome_fantasia"] == "Teste"
    assert resultado["atividade_principal"] == "Atividade de teste"
    assert resultado["telefone_1"] == "1133334444"
