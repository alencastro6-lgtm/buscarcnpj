"""Lógica de consulta de CNPJ, cache e formatação."""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from pathlib import Path
from urllib import error, request

API_TIMEOUT = 20
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
    conn = sqlite3.connect(DB_FILE)
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
    conn.commit()
    conn.close()


def _load_cache(cnpj: str) -> dict | None:
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT data FROM cache WHERE cnpj = ?", (cnpj,))
        row = cur.fetchone()
        conn.close()
        if row:
            return json.loads(row[0])
    except Exception:
        logging.exception("Erro ao carregar cache")
    return None


def _save_cache(cnpj: str, data: dict) -> None:
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute(
            "INSERT OR REPLACE INTO cache(cnpj,data,updated_at) VALUES(?,?,?)",
            (cnpj, json.dumps(data, ensure_ascii=False), int(time.time())),
        )
        conn.commit()
        conn.close()
    except Exception:
        logging.exception("Erro ao salvar cache")


def _save_history(cnpj: str) -> None:
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("INSERT INTO history(cnpj,ts) VALUES(?,?)", (cnpj, int(time.time())))
        conn.commit()
        conn.close()
    except Exception:
        logging.exception("Erro ao salvar histórico")


def _get_history(limit: int = 10) -> list[str]:
    try:
        conn = sqlite3.connect(DB_FILE)
        cur = conn.cursor()
        cur.execute("SELECT DISTINCT cnpj FROM history ORDER BY ts DESC LIMIT ?", (limit,))
        rows = [r[0] for r in cur.fetchall()]
        conn.close()
        return rows
    except Exception:
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
            }
        erros.append(str(dados.get("message") or "BrasilAPI sem retorno válido"))
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
            }
        erros.append(str(dados.get("message") or "ReceitaWS sem retorno válido"))
    except (error.URLError, error.HTTPError, TimeoutError, ValueError, json.JSONDecodeError) as exc:
        erros.append(f"ReceitaWS: {exc}")

    raise RuntimeError("Falha ao consultar CNPJ. " + " | ".join(erros))
