from unittest.mock import patch

from main import ConsultaCNPJApp


def test_consultar_background_retorna_cache_sem_erro():
    app = ConsultaCNPJApp.__new__(ConsultaCNPJApp)
    cached = {"cnpj": "11444777000161", "razao_social": "Empresa em Cache"}

    with (
        patch("main._load_cache", return_value=cached),
        patch("main._save_history"),
    ):
        resultado = app._consultar_background("11444777000161")

    assert resultado["cnpj"] == cached["cnpj"]
    assert resultado["razao_social"] == cached["razao_social"]
    assert resultado["_origem"] == "cache"
