from unittest.mock import patch

from main import ConsultaCNPJApp


class VarFake:
    def __init__(self, value=""):
        self.value = value

    def get(self):
        return self.value

    def set(self, value):
        self.value = value


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


def test_telefone_whatsapp():
    app = ConsultaCNPJApp.__new__(ConsultaCNPJApp)

    assert app._telefone_whatsapp("(11) 99999-8888") == "5511999998888"
    assert app._telefone_whatsapp("55 11 99999-8888") == "5511999998888"
    assert app._telefone_whatsapp("5511999998888") == "5511999998888"
    assert app._telefone_whatsapp("(67) 9829-1632") == "556798291632"
    assert app._telefone_whatsapp("(11) 3333-4444 / (11) 98888-7777") == "5511988887777"
    assert app._telefone_whatsapp("1234567") is None


def test_linhas_cnpj_monta_texto_dos_campos():
    app = ConsultaCNPJApp.__new__(ConsultaCNPJApp)
    app.campos_vars = {chave: VarFake("") for chave, _titulo in app.CAMPOS}
    app.campos_vars["cnpj"].set("11.444.777/0001-61")
    app.campos_vars["razao_social"].set("Empresa Teste")

    linhas = app._linhas_cnpj()

    assert "CNPJ: 11.444.777/0001-61" in linhas
    assert "Razão social: Empresa Teste" in linhas


def test_preencher_cnpj_formata_campos_principais():
    app = ConsultaCNPJApp.__new__(ConsultaCNPJApp)
    app.campos_vars = {chave: VarFake("") for chave, _titulo in app.CAMPOS}

    app._preencher_cnpj(
        {
            "cnpj": "11444777000161",
            "cep": "01000000",
            "telefone_1": "11999998888",
            "telefone_2": "1133334444",
        }
    )

    assert app.campos_vars["cnpj"].get() == "11.444.777/0001-61"
    assert app.campos_vars["cep"].get() == "01000-000"
    assert app.campos_vars["telefone_1"].get() == "(11) 99999-8888"
    assert app.campos_vars["telefone_2"].get() == "(11) 3333-4444"


def test_preencher_cep_e_linhas_cep():
    app = ConsultaCNPJApp.__new__(ConsultaCNPJApp)
    app.cep_vars = {chave: VarFake("") for chave, _titulo in app.CAMPOS_CEP}

    app._preencher_cep({"cep": "01000-000", "logradouro": "Praça da Sé", "uf": "SP"})

    assert app.cep_vars["logradouro"].get() == "Praça da Sé"
    assert "UF: SP" in app._linhas_cep()
