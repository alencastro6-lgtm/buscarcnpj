"""Lógica de consulta de CNPJ, cache e formatação."""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import time
from pathlib import Path
from urllib import error, request
from urllib.parse import quote

API_TIMEOUT = 20
CACHE_TTL_SECONDS = 30 * 24 * 60 * 60
DB_FILE = Path(__file__).parent / "cnpj_cache.db"
LOG_FILE = Path(__file__).parent / "app.log"

logging.basicConfig(
    filename=str(LOG_FILE),
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
)


def _apenas_digitos(texto: str) -> str:
    return "".join(ch for ch in str(texto or "") if ch.isdigit())


def _formatar_cnpj(texto: str) -> str:
    digitos = _apenas_digitos(texto)[:14]
    if not digitos:
        return ""
    if len(digitos) <= 2:
        return digitos
    if len(digitos) <= 5:
        return f"{digitos[:2]}.{digitos[2:]}"
    if len(digitos) <= 8:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:]}"
    if len(digitos) <= 12:
        return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:]}"
    return f"{digitos[:2]}.{digitos[2:5]}.{digitos[5:8]}/{digitos[8:12]}-{digitos[12:14]}"


def _formatar_cep(texto: str) -> str:
    digitos = _apenas_digitos(texto)[:8]
    if len(digitos) <= 5:
        return digitos
    return f"{digitos[:5]}-{digitos[5:8]}"


def _formatar_telefone(texto: str) -> str:
    digitos = _apenas_digitos(texto)
    if len(digitos) == 11:
        return f"({digitos[:2]}) {digitos[2:7]}-{digitos[7:11]}"
    if len(digitos) == 10:
        return f"({digitos[:2]}) {digitos[2:6]}-{digitos[6:10]}"
    if len(digitos) > 11:
        base = digitos[:11]
        ramal = digitos[11:]
        return f"({base[:2]}) {base[2:7]}-{base[7:11]} ramal {ramal}"
    return texto or ""


def _cursor_por_qtd_digitos(texto_formatado: str, qtd_digitos: int) -> int:
    if qtd_digitos <= 0:
        return 0

    contador = 0
    for idx, ch in enumerate(texto_formatado):
        if ch.isdigit():
            contador += 1
            if contador >= qtd_digitos:
                return idx + 1
    return len(texto_formatado)


def _formatar_para_copia(chave: str, valor: str) -> str:
    if chave in ("cnpj", "cep", "telefone_1", "telefone_2"):
        return _apenas_digitos(valor)
    return valor


def validar_cnpj(cnpj: str) -> bool:
    c = _apenas_digitos(cnpj)
    if len(c) != 14:
        return False
    if c == c[0] * 14:
        return False

    def calc(digs: str) -> int:
        soma = 0
        peso = len(digs) - 7
        for ch in digs:
            soma += int(ch) * peso
            peso -= 1
            if peso < 2:
                peso = 9
        resto = soma % 11
        return 0 if resto < 2 else 11 - resto

    n1 = calc(c[:12])
    n2 = calc(c[:12] + str(n1))
    return c[-2:] == f"{n1}{n2}"


def _init_db() -> None:
    with sqlite3.connect(DB_FILE) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS cache(
                cnpj TEXT PRIMARY KEY,
                data TEXT,
                updated_at INTEGER
            )
            """
        )
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS history(
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                cnpj TEXT,
                ts INTEGER
            )
            """
        )


def _load_cache(cnpj: str) -> dict | None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute("SELECT data, updated_at FROM cache WHERE cnpj = ?", (cnpj,))
            row = cur.fetchone()
        if row:
            if _cache_expirado(int(row[1] or 0)):
                return None
            return json.loads(row[0])
    except (sqlite3.Error, ValueError, TypeError, json.JSONDecodeError):
        logging.exception("Erro ao carregar cache")
    return None


def _cache_expirado(updated_at: int, agora: int | None = None) -> bool:
    if updated_at <= 0:
        return True
    referencia = int(time.time()) if agora is None else agora
    return referencia - updated_at > CACHE_TTL_SECONDS


def _save_cache(cnpj: str, data: dict) -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute(
                "INSERT OR REPLACE INTO cache(cnpj,data,updated_at) VALUES(?,?,?)",
                (cnpj, json.dumps(data, ensure_ascii=False), int(time.time())),
            )
    except (sqlite3.Error, TypeError):
        logging.exception("Erro ao salvar cache")


def _save_history(cnpj: str) -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute("INSERT INTO history(cnpj,ts) VALUES(?,?)", (cnpj, int(time.time())))
    except sqlite3.Error:
        logging.exception("Erro ao salvar histórico")


def _clear_history() -> None:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute("DELETE FROM history")
    except sqlite3.Error:
        logging.exception("Erro ao limpar histórico")
        raise


def _get_history(limit: int = 10) -> list[str]:
    try:
        with sqlite3.connect(DB_FILE) as conn:
            cur = conn.cursor()
            cur.execute(
                """
                SELECT cnpj
                FROM history
                GROUP BY cnpj
                ORDER BY MAX(ts) DESC
                LIMIT ?
                """,
                (limit,),
            )
            return [r[0] for r in cur.fetchall()]
    except sqlite3.Error:
        logging.exception("Erro ao ler histórico")
    return []


def _get_json(url: str) -> dict:
    req = request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )
    with request.urlopen(req, timeout=API_TIMEOUT) as resp:
        conteudo = resp.read().decode("utf-8")
        return json.loads(conteudo)


def _consultar_cep_por_numero(cep_limpo: str) -> dict:
    """Consulta CEP com múltiplas APIs para garantir dados completos, incluindo bairro."""
    erros: list[str] = []
    resultado: dict = {}
    
    # Tenta BrasilAPI primeiro
    try:
        dados = _get_json(f"https://brasilapi.com.br/api/cep/v1/{cep_limpo}")
        if isinstance(dados, dict) and not dados.get("message"):
            resultado = {
                "cep": _formatar_cep(str(dados.get("cep") or cep_limpo)),
                "logradouro": dados.get("street") or dados.get("logradouro") or "",
                "complemento": dados.get("complement") or dados.get("complemento") or "",
                "bairro": dados.get("neighborhood") or dados.get("bairro") or "",
                "localidade": dados.get("city") or dados.get("localidade") or "",
                "uf": dados.get("state") or dados.get("uf") or "",
                "ddd": str(dados.get("ddd") or ""),
                "ibge": str(dados.get("ibge") or ""),
                "gia": str(dados.get("gia") or ""),
                "siafi": str(dados.get("siafi") or ""),
                "service": "BrasilAPI",
            }
            if resultado.get("bairro"):
                return resultado
        else:
            mensagem = dados.get("message") if isinstance(dados, dict) else "BrasilAPI sem retorno válido"
            erros.append(f"BrasilAPI: {mensagem}")
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"BrasilAPI: {exc}")

    # Tenta ViaCEP se BrasilAPI não retornou ou faltam dados
    try:
        dados = _get_json(f"https://viacep.com.br/ws/{cep_limpo}/json/")
        if isinstance(dados, dict) and not dados.get("erro"):
            dados_viacep = {
                "cep": _formatar_cep(str(dados.get("cep") or cep_limpo)),
                "logradouro": dados.get("logradouro") or "",
                "complemento": dados.get("complemento") or "",
                "bairro": dados.get("bairro") or "",
                "localidade": dados.get("localidade") or "",
                "uf": dados.get("uf") or "",
                "ddd": str(dados.get("ddd") or ""),
                "ibge": str(dados.get("ibge") or ""),
                "gia": str(dados.get("gia") or ""),
                "siafi": str(dados.get("siafi") or ""),
                "service": "ViaCEP",
            }
            # Mescla com resultado anterior, preenchendo campos vazios
            if not resultado:
                resultado = dados_viacep
            else:
                for chave, valor in dados_viacep.items():
                    if not resultado.get(chave) and valor:
                        resultado[chave] = valor
            if resultado.get("bairro"):
                return resultado
        else:
            mensagem = dados.get("message") if isinstance(dados, dict) else "ViaCEP sem retorno válido"
            erros.append(f"ViaCEP: {mensagem or 'CEP não localizado'}")
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"ViaCEP: {exc}")

    # Tenta OpenCEP (API alternativa confiável)
    try:
        dados = _get_json(f"https://cep.awesomeapi.com.br/json/{cep_limpo}")
        if isinstance(dados, dict) and not dados.get("status") or dados.get("status") == 200:
            dados_openapi = {
                "cep": _formatar_cep(str(dados.get("cep") or cep_limpo)),
                "logradouro": dados.get("address") or dados.get("logradouro") or "",
                "complemento": dados.get("complemento") or "",
                "bairro": dados.get("district") or dados.get("bairro") or "",
                "localidade": dados.get("city") or dados.get("localidade") or "",
                "uf": dados.get("state") or dados.get("uf") or "",
                "ddd": str(dados.get("ddd") or ""),
                "ibge": str(dados.get("ibge") or ""),
                "gia": str(dados.get("gia") or ""),
                "siafi": str(dados.get("siafi") or ""),
                "service": "AwesomeAPI",
            }
            # Mescla dados
            if not resultado:
                resultado = dados_openapi
            else:
                for chave, valor in dados_openapi.items():
                    if not resultado.get(chave) and valor:
                        resultado[chave] = valor
            if resultado.get("bairro"):
                return resultado
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"AwesomeAPI: {exc}")

    # Se encontrou dados parciais, tenta busca complementar por bairro
    if resultado and not resultado.get("bairro") and resultado.get("logradouro") and resultado.get("localidade"):
        try:
            resultado.update(_buscar_bairro_complementar(resultado))
        except Exception as exc:
            erros.append(f"Busca complementar: {exc}")

    # Retorna resultado se encontrado dados
    if resultado and resultado.get("logradouro"):
        return resultado

    raise RuntimeError("Falha ao consultar CEP. " + " | ".join(erros) if erros else "CEP não localizado em nenhuma API.")


def _buscar_bairro_complementar(dados: dict) -> dict:
    """Tenta preencher o bairro usando busca por endereço."""
    complemento = dados.copy()
    
    # Se não tem bairro, tenta buscar via endereço completo
    uf = dados.get("uf", "")
    localidade = dados.get("localidade", "")
    logradouro = dados.get("logradouro", "")
    
    if not uf or not localidade or not logradouro:
        return complemento
    
    try:
        # Tenta ViaCEP com endereço para obter bairro
        url = f"https://viacep.com.br/ws/{quote(uf)}/{quote(localidade)}/{quote(logradouro)}/json/"
        dados_busca = _get_json(url)
        
        if isinstance(dados_busca, list) and dados_busca:
            primeiro = dados_busca[0]
            if primeiro.get("bairro"):
                complemento["bairro"] = primeiro.get("bairro")
                complemento["ibge"] = str(primeiro.get("ibge") or complemento.get("ibge", ""))
                complemento["siafi"] = str(primeiro.get("siafi") or complemento.get("siafi", ""))
    except Exception:
        pass
    
    return complemento


def consultar_cep_por_endereco(endereco: str) -> dict:
    """Consulta CEP por endereço com suporte a múltiplas APIs e preenchimento automático de bairro."""
    partes = [p.strip() for p in re.split(r"[,-/]", endereco) if p.strip()]
    if len(partes) < 3:
        raise ValueError("Informe o endereço no formato UF, Cidade e Logradouro.")

    uf = partes[0].upper()
    cidade = partes[1]
    logradouro = " ".join(partes[2:])
    if len(uf) != 2 or not uf.isalpha():
        raise ValueError("Informe a UF com dois caracteres no endereço.")

    resultado: dict = {}
    erros: list[str] = []

    # Tenta ViaCEP (mais confiável para busca por endereço)
    try:
        url = f"https://viacep.com.br/ws/{quote(uf)}/{quote(cidade)}/{quote(logradouro)}/json/"
        dados_lista = _get_json(url)
        if isinstance(dados_lista, list) and dados_lista:
            resultado_temp = dados_lista[0]
            resultado = {
                "cep": _formatar_cep(str(resultado_temp.get("cep") or "")),
                "logradouro": resultado_temp.get("logradouro") or "",
                "complemento": resultado_temp.get("complemento") or "",
                "bairro": resultado_temp.get("bairro") or "",
                "localidade": resultado_temp.get("localidade") or "",
                "uf": resultado_temp.get("uf") or "",
                "ddd": str(resultado_temp.get("ddd") or ""),
                "ibge": str(resultado_temp.get("ibge") or ""),
                "gia": str(resultado_temp.get("gia") or ""),
                "siafi": str(resultado_temp.get("siafi") or ""),
                "service": "ViaCEP",
            }
            if resultado.get("bairro"):
                return resultado
        elif isinstance(dados_lista, dict) and dados_lista.get("erro"):
            erros.append("ViaCEP: Endereço não localizado.")
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"ViaCEP: {exc}")

    # Se ViaCEP não encontrou ou faltam dados, tenta BrasilAPI
    if not resultado:
        try:
            # BrasilAPI usa formato diferente para busca por endereço
            url = f"https://brasilapi.com.br/api/cep/v1/{quote(logradouro)}"
            dados = _get_json(url)
            if isinstance(dados, dict) and not dados.get("message"):
                resultado = {
                    "cep": _formatar_cep(str(dados.get("cep") or "")),
                    "logradouro": dados.get("street") or dados.get("logradouro") or "",
                    "complemento": dados.get("complement") or dados.get("complemento") or "",
                    "bairro": dados.get("neighborhood") or dados.get("bairro") or "",
                    "localidade": dados.get("city") or dados.get("localidade") or "",
                    "uf": dados.get("state") or dados.get("uf") or "",
                    "ddd": str(dados.get("ddd") or ""),
                    "ibge": str(dados.get("ibge") or ""),
                    "gia": str(dados.get("gia") or ""),
                    "siafi": str(dados.get("siafi") or ""),
                    "service": "BrasilAPI",
                }
        except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
            erros.append(f"BrasilAPI: {exc}")

    if resultado and resultado.get("bairro"):
        return resultado
    elif resultado and resultado.get("logradouro"):
        return resultado

    raise RuntimeError("Endereço não encontrado. " + " | ".join(erros) if erros else "Nenhuma API retornou dados válidos.")


def consultar_cep(cep: str) -> dict:
    consulta = str(cep or "").strip()
    if not consulta:
        raise ValueError("Informe um CEP com 8 dígitos ou um endereço no formato UF/Cidade/Logradouro.")

    cep_limpo = _apenas_digitos(consulta)
    if consulta.replace("-", "").isdigit() and len(cep_limpo) == 8:
        return _consultar_cep_por_numero(cep_limpo)

    return consultar_cep_por_endereco(consulta)


def consultar_cnpj(cnpj: str) -> dict:
    cnpj_limpo = _apenas_digitos(cnpj)
    if len(cnpj_limpo) != 14:
        raise ValueError("Informe um CNPJ com 14 dígitos.")

    erros: list[str] = []
    try:
        dados = _get_json(f"https://brasilapi.com.br/api/cnpj/v1/{cnpj_limpo}")
        if isinstance(dados, dict) and not dados.get("message"):
            return {
                "cnpj": dados.get("cnpj") or cnpj_limpo,
                "razao_social": dados.get("razao_social") or "",
                "nome_fantasia": dados.get("nome_fantasia") or "",
                "situacao": dados.get("descricao_situacao_cadastral") or "",
                "data_situacao": dados.get("data_situacao_cadastral") or "",
                "natureza_juridica": dados.get("natureza_juridica") or "",
                "porte": dados.get("porte") or "",
                "capital_social": str(dados.get("capital_social") or ""),
                "atividade_principal": dados.get("cnae_fiscal_descricao") or "",
                "telefone_1": dados.get("ddd_telefone_1") or "",
                "telefone_2": dados.get("ddd_telefone_2") or "",
                "email": dados.get("email") or "",
                "cep": dados.get("cep") or "",
                "logradouro": dados.get("logradouro") or "",
                "numero": dados.get("numero") or "",
                "complemento": dados.get("complemento") or "",
                "bairro": dados.get("bairro") or "",
                "municipio": dados.get("municipio") or "",
                "uf": dados.get("uf") or "",
                "_origem": "BrasilAPI",
            }
        mensagem = dados.get("message") if isinstance(dados, dict) else "BrasilAPI sem retorno válido"
        erros.append(str(mensagem))
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"BrasilAPI: {exc}")

    try:
        dados = _get_json(f"https://www.receitaws.com.br/v1/cnpj/{cnpj_limpo}")
        if isinstance(dados, dict) and dados.get("status") != "ERROR":
            atividade_principal = ""
            if isinstance(dados.get("atividade_principal"), list) and dados["atividade_principal"]:
                atividade_principal = dados["atividade_principal"][0].get("text", "")

            return {
                "cnpj": dados.get("cnpj") or cnpj_limpo,
                "razao_social": dados.get("nome") or "",
                "nome_fantasia": dados.get("fantasia") or "",
                "situacao": dados.get("situacao") or "",
                "data_situacao": dados.get("data_situacao") or "",
                "natureza_juridica": dados.get("natureza_juridica") or "",
                "porte": dados.get("porte") or "",
                "capital_social": str(dados.get("capital_social") or ""),
                "atividade_principal": atividade_principal,
                "telefone_1": dados.get("telefone") or "",
                "telefone_2": "",
                "email": dados.get("email") or "",
                "cep": dados.get("cep") or "",
                "logradouro": dados.get("logradouro") or "",
                "numero": dados.get("numero") or "",
                "complemento": dados.get("complemento") or "",
                "bairro": dados.get("bairro") or "",
                "municipio": dados.get("municipio") or "",
                "uf": dados.get("uf") or "",
                "_origem": "ReceitaWS",
            }
        mensagem = dados.get("message") if isinstance(dados, dict) else "ReceitaWS sem retorno válido"
        erros.append(str(mensagem))
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"ReceitaWS: {exc}")

    raise RuntimeError("Falha ao consultar CNPJ. " + " | ".join(erros))
