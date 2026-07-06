import json
import sqlite3
import time
from unittest.mock import patch

import pytest

import cnpj_service
from cnpj_service import consultar_cnpj, consultar_cep, validar_cnpj


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


def test_consultar_cep_mapeia_dados_basicos():
    cep_response = {
        "cep": "01000-000",
        "street": "Rua Teste",
        "complement": "Sala 1",
        "neighborhood": "Centro",
        "city": "São Paulo",
        "state": "SP",
        "ddd": "11",
        "service": "viacep",
        "ibge": "3550308",
        "gia": "1004",
        "siafi": "7107",
    }

    with patch("cnpj_service._get_json", return_value=cep_response):
        resultado = consultar_cep("01000000")

    assert resultado["cep"] == "01000-000"
    assert resultado["logradouro"] == "Rua Teste"
    assert resultado["bairro"] == "Centro"
    assert resultado["localidade"] == "São Paulo"
    assert resultado["uf"] == "SP"
    assert resultado["ddd"] == "11"


def test_consultar_cep_fallback_viacep_quando_brasilapi_falha():
    viacep_response = {
        "cep": "01000-000",
        "logradouro": "Praça da Sé",
        "bairro": "Sé",
        "localidade": "São Paulo",
        "uf": "SP",
    }

    with patch("cnpj_service._get_json", side_effect=[TimeoutError("timeout"), viacep_response]):
        resultado = consultar_cep("01000000")

    assert resultado["logradouro"] == "Praça da Sé"
    assert resultado["service"] == "ViaCEP"


def test_consultar_cep_inexistente_retorna_erro_descritivo():
    with patch("cnpj_service._get_json", side_effect=[{"message": "não encontrado"}, {"erro": True}, {"status": 404}]):
        with pytest.raises(RuntimeError, match="Falha ao consultar CEP"):
            consultar_cep("01000000")


def test_consultar_cep_por_endereco_retornando_cep():
    busca_endereco_response = [
        {
            "cep": "01310-100",
            "logradouro": "Avenida Paulista",
            "complemento": "",
            "bairro": "Bela Vista",
            "localidade": "São Paulo",
            "uf": "SP",
            "ddd": "11",
            "ibge": "3550308",
            "gia": "1004",
            "siafi": "7107",
        }
    ]

    with patch("cnpj_service._get_json", return_value=busca_endereco_response):
        resultado = consultar_cep("SP, São Paulo, Avenida Paulista")

    assert resultado["cep"] == "01310-100"
    assert resultado["logradouro"] == "Avenida Paulista"
    assert resultado["localidade"] == "São Paulo"
    assert resultado["uf"] == "SP"
    assert resultado["service"] == "ViaCEP"


def test_consultar_cep_por_endereco_formato_invalido_gera_erro():
    with pytest.raises(ValueError, match="formato UF, Cidade e Logradouro"):
        consultar_cep("Avenida Paulista")


def test_consultar_cnpj_resposta_invalida_nao_quebra_com_attribute_error():
    with patch("cnpj_service._get_json", side_effect=[[], []]):
        with pytest.raises(RuntimeError, match="BrasilAPI sem retorno válido.*ReceitaWS sem retorno válido"):
            consultar_cnpj("11444777000161")


def test_cache_carrega_apenas_quando_valido(tmp_path, monkeypatch):
    monkeypatch.setattr(cnpj_service, "DB_FILE", tmp_path / "cache.db")
    cnpj_service._init_db()
    cnpj_service._save_cache("11444777000161", {"razao_social": "Empresa"})

    assert cnpj_service._load_cache("11444777000161") == {"razao_social": "Empresa"}


def test_cache_expirado_nao_e_usado(tmp_path, monkeypatch):
    monkeypatch.setattr(cnpj_service, "DB_FILE", tmp_path / "cache.db")
    cnpj_service._init_db()
    antigo = int(time.time()) - cnpj_service.CACHE_TTL_SECONDS - 1

    with sqlite3.connect(cnpj_service.DB_FILE) as conn:
        conn.execute(
            "INSERT INTO cache(cnpj,data,updated_at) VALUES(?,?,?)",
            ("11444777000161", json.dumps({"razao_social": "Antiga"}), antigo),
        )

    assert cnpj_service._load_cache("11444777000161") is None


def test_cache_corrompido_nao_quebra_app(tmp_path, monkeypatch):
    monkeypatch.setattr(cnpj_service, "DB_FILE", tmp_path / "cache.db")
    cnpj_service._init_db()

    with sqlite3.connect(cnpj_service.DB_FILE) as conn:
        conn.execute(
            "INSERT INTO cache(cnpj,data,updated_at) VALUES(?,?,?)",
            ("11444777000161", "{json", int(time.time())),
        )

    assert cnpj_service._load_cache("11444777000161") is None


def test_consultar_cep_fallback_awesome_api_quando_outras_falham():
    """Testa fallback para AwesomeAPI quando BrasilAPI e ViaCEP falham."""
    awesome_response = {
        "cep": "01000000",
        "address": "Rua Teste",
        "district": "Centro",
        "city": "São Paulo",
        "state": "SP",
        "status": 200,
    }

    with patch("cnpj_service._get_json", side_effect=[
        TimeoutError("timeout"),
        {"erro": True},
        awesome_response
    ]):
        resultado = consultar_cep("01000000")

    assert resultado["logradouro"] == "Rua Teste"
    assert resultado["bairro"] == "Centro"
    assert resultado["service"] == "AwesomeAPI"


def test_consultar_cep_mescla_dados_de_multiplas_apis():
    """Testa mescla de dados quando uma API tem bairro incompleto."""
    brasilapi_response = {
        "cep": "01000-000",
        "street": "Rua Teste",
        "neighborhood": "",  # Sem bairro
        "city": "São Paulo",
        "state": "SP",
        "ibge": "3550308",
    }

    viacep_response = {
        "cep": "01000-000",
        "logradouro": "Rua Teste",
        "bairro": "Centro",  # BrasilAPI não tinha
        "localidade": "São Paulo",
        "uf": "SP",
        "siafi": "7107",
    }

    with patch("cnpj_service._get_json", side_effect=[brasilapi_response, viacep_response]):
        resultado = consultar_cep("01000000")

    assert resultado["bairro"] == "Centro"
    assert resultado["logradouro"] == "Rua Teste"
    assert resultado["siafi"] == "7107"


def test_consultar_cep_busca_complementar_bairro():
    """Testa busca complementar de bairro quando está vazio."""
    primeira_resposta = {
        "cep": "01000000",
        "street": "Avenida Paulista",
        "neighborhood": "",  # Sem bairro
        "city": "São Paulo",
        "state": "SP",
    }

    segunda_resposta = {
        "erro": True,  # ViaCEP não tem
    }

    # Resposta para busca complementar
    busca_complementar = [
        {
            "cep": "01000000",
            "bairro": "Bela Vista",
            "ibge": "3550308",
        }
    ]

    with patch("cnpj_service._get_json", side_effect=[
        primeira_resposta,
        segunda_resposta,
        {"status": 404},  # AwesomeAPI também falha
        busca_complementar  # Busca complementar encontra bairro
    ]):
        resultado = consultar_cep("01000000")

    assert resultado["bairro"] == "Bela Vista"
    assert resultado["logradouro"] == "Avenida Paulista"
