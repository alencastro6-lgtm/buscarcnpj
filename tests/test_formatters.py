from cnpj_service import _apenas_digitos, _formatar_cnpj, validar_cnpj


def test_apenas_digitos():
    assert _apenas_digitos("12a3-45") == "12345"


def test_formatar_cnpj():
    assert _formatar_cnpj("12345678000195") == "12.345.678/0001-95"


def test_validar_cnpj():
    assert validar_cnpj("11444777000161") is True
    assert validar_cnpj("00000000000000") is False
    assert validar_cnpj("123") is False
