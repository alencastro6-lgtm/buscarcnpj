
"""Consulta de CNPJ para apoiar cadastro de clientes."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import logging
import time
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog
from urllib import error, request
from concurrent.futures import ThreadPoolExecutor


API_TIMEOUT = 20
DB_FILE = Path(__file__).parent / "cnpj_cache.db"
LOG_FILE = Path(__file__).parent / "app.log"

# logging
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


class ConsultaCNPJApp:
    CAMPOS = [
        ("cnpj", "CNPJ"),
        ("razao_social", "Razão social"),
        ("nome_fantasia", "Nome fantasia"),
        ("situacao", "Situação"),
        ("data_situacao", "Data situação"),
        ("natureza_juridica", "Natureza jurídica"),
        ("porte", "Porte"),
        ("capital_social", "Capital social"),
        ("atividade_principal", "Atividade principal"),
        ("telefone_1", "Telefone 1"),
        ("telefone_2", "Telefone 2"),
        ("email", "E-mail"),
        ("cep", "CEP"),
        ("logradouro", "Logradouro"),
        ("numero", "Número"),
        ("complemento", "Complemento"),
        ("bairro", "Bairro"),
        ("municipio", "Município"),
        ("uf", "UF"),
    ]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Consulta de CNPJ")
        self.root.geometry("950x700")
        self.root.minsize(840, 560)

        self.cnpj_var = tk.StringVar()
        self.msg_var = tk.StringVar(value="Digite o CNPJ e clique em Consultar.")
        self.campos_vars = {chave: tk.StringVar() for chave, _ in self.CAMPOS}

        # executor para chamadas em background e DB init
        self.executor = ThreadPoolExecutor(max_workers=2)
        _init_db()

        self._montar_tela()

        # spinner control
        self._spinner_running = False
        self._spinner_pos = 0

    def _montar_tela(self) -> None:
        topo = ttk.Frame(self.root, padding=12)
        topo.pack(fill="x")

        ttk.Label(topo, text="CNPJ:").pack(side="left")
        self.cnpj_entry = ttk.Entry(topo, textvariable=self.cnpj_var, width=24)
        self.cnpj_entry.pack(side="left", padx=(8, 8))
        self.cnpj_entry.bind("<KeyRelease>", self._on_cnpj_change)
        self.cnpj_entry.bind("<Return>", self.consultar)
        self.cnpj_entry.bind("<FocusOut>", self._on_cnpj_change)
        self.cnpj_entry.focus_set()

        self.consultar_btn = ttk.Button(topo, text="Consultar", command=self.consultar)
        self.consultar_btn.pack(side="left", padx=(0, 8))
        self.limpar_btn = ttk.Button(topo, text="Limpar", command=self.limpar)
        self.limpar_btn.pack(side="left")
        self.salvar_txt_btn = ttk.Button(topo, text="Salvar TXT", command=self.salvar_txt)
        self.salvar_txt_btn.pack(side="left", padx=(8, 0))
        self.copiar_tudo_btn = ttk.Button(topo, text="Copiar tudo", command=self.copiar_tudo)
        self.copiar_tudo_btn.pack(side="left", padx=(8, 0))

        # histórico
        ttk.Label(topo, text="Histórico:").pack(side="left", padx=(12, 4))
        self.history_cb = ttk.Combobox(topo, values=_get_history(), width=18)
        self.history_cb.pack(side="left")
        self.history_cb.bind("<<ComboboxSelected>>", self._on_history_selected)

        # status label (mensagens e spinner)
        self.status_label = ttk.Label(self.root, textvariable=self.msg_var, padding=(12, 0))
        self.status_label.pack(fill="x")

        wrapper = ttk.Frame(self.root, padding=(12, 8, 12, 12))
        wrapper.pack(fill="both", expand=True)

        canvas = tk.Canvas(wrapper, highlightthickness=0)
        scrollbar = ttk.Scrollbar(wrapper, orient="vertical", command=canvas.yview)
        self.form_frame = ttk.Frame(canvas)

        self.form_frame.bind(
            "<Configure>",
            lambda _e: canvas.configure(scrollregion=canvas.bbox("all")),
        )

        canvas.create_window((0, 0), window=self.form_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)

        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        for idx, (chave, titulo) in enumerate(self.CAMPOS):
            ttk.Label(self.form_frame, text=f"{titulo}:").grid(row=idx, column=0, padx=(0, 8), pady=5, sticky="w")
            entry = ttk.Entry(self.form_frame, textvariable=self.campos_vars[chave], width=78)
            entry.grid(row=idx, column=1, padx=(0, 8), pady=5, sticky="we")
            entry.configure(state="readonly")
            ttk.Button(
                self.form_frame,
                text="Copiar",
                width=10,
                command=lambda c=chave, t=titulo: self.copiar_campo(c, t),
            ).grid(row=idx, column=2, padx=(0, 2), pady=5)

        self.form_frame.columnconfigure(1, weight=1)

    def _on_cnpj_change(self, _event=None) -> None:
        valor_atual = self.cnpj_var.get()
        cursor_atual = self.cnpj_entry.index(tk.INSERT)
        qtd_digitos_antes_cursor = len(_apenas_digitos(valor_atual[:cursor_atual]))

        valor_formatado = _formatar_cnpj(valor_atual)
        if valor_atual != valor_formatado:
            self.cnpj_var.set(valor_formatado)

        novo_cursor = _cursor_por_qtd_digitos(valor_formatado, qtd_digitos_antes_cursor)
        self.cnpj_entry.icursor(novo_cursor)

    def limpar(self) -> None:
        self.cnpj_var.set("")
        for var in self.campos_vars.values():
            var.set("")
        self.msg_var.set("Campos limpos.")

    def copiar_campo(self, chave: str, titulo: str) -> None:
        valor = _formatar_para_copia(chave, self.campos_vars[chave].get())
        if not valor:
            self.msg_var.set(f"{titulo} está vazio.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(valor)
        self.msg_var.set(f"{titulo} copiado.")

    def salvar_txt(self) -> None:
        linhas: list[str] = []
        for chave, titulo in self.CAMPOS:
            valor = str(self.campos_vars[chave].get() or "")
            linhas.append(f"{titulo}: {valor}")

        # Verifica se há algum dado
        dados_existem = any(line.split(": ", 1)[1].strip() for line in linhas)
        if not dados_existem:
            self.msg_var.set("Nenhum dado disponível para salvar.")
            return

        cnpj_limpo = _apenas_digitos(self.campos_vars.get("cnpj").get() or "")
        nome_inicial = f"cnpj_{cnpj_limpo}" if cnpj_limpo else "cnpj_dados"

        caminho = filedialog.asksaveasfilename(
            defaultextension=".txt",
            filetypes=[("Text files", "*.txt")],
            initialfile=f"{nome_inicial}.txt",
            title="Salvar dados do CNPJ",
        )
        if not caminho:
            return

        try:
            with open(caminho, "w", encoding="utf-8") as fp:
                fp.write("\n".join(linhas))
            self.msg_var.set(f"Dados salvos em {os.path.basename(caminho)}.")
        except Exception as exc:
            self.msg_var.set(f"Erro ao salvar: {exc}")



    def copiar_tudo(self) -> None:
        partes = []
        for chave, titulo in self.CAMPOS:
            valor = str(self.campos_vars[chave].get() or "")
            partes.append(f"{titulo}: {valor}")
        texto = "\n".join(partes)
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        self.msg_var.set("Todos os campos copiados.")

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for w in (
            self.consultar_btn,
            self.limpar_btn,
            self.salvar_txt_btn,
            self.copiar_tudo_btn,
        ):
            try:
                w.configure(state=state)
            except Exception:
                pass

    def _start_spinner(self) -> None:
        if self._spinner_running:
            return
        self._spinner_running = True
        self._spinner_pos = 0
        self._spinner_step()

    def _spinner_step(self) -> None:
        if not self._spinner_running:
            return
        chars = ["|", "/", "-", "\\"]
        ch = chars[self._spinner_pos % len(chars)]
        self.msg_var.set(f"Consultando... {ch}")
        self._spinner_pos += 1
        self.root.after(200, self._spinner_step)

    def _stop_spinner(self) -> None:
        self._spinner_running = False

    def _on_history_selected(self, _ev=None) -> None:
        sel = self.history_cb.get()
        if sel:
            self.cnpj_var.set(_formatar_cnpj(sel))
            self.consultar()

    def _consultar_background(self, cnpj_digits: str) -> dict:
        # checar cache
        cached = _load_cache(cnpj_digits)
        if cached:
            logging.info(f"Cache hit: {cnpj_digits}")
            return cached

        # tentar consultar com retries
        last_exc = None
        for attempt in range(3):
            try:
                dados = consultar_cnpj(cnpj_digits)
                _save_cache(cnpj_digits, dados)
                _save_history(cnpj_digits)
                return dados
            except Exception as exc:
                logging.exception("Erro na consulta")
                last_exc = exc
                time.sleep(1 + attempt * 2)
        raise last_exc

    def _on_consulta_done(self, dados: dict | None, exc: Exception | None) -> None:
        self._stop_spinner()
        self._set_busy(False)
        if exc:
            self.msg_var.set(str(exc))
            return

        dados["cnpj"] = _formatar_cnpj(str(dados.get("cnpj") or ""))
        dados["cep"] = _formatar_cep(str(dados.get("cep") or ""))
        dados["telefone_1"] = _formatar_telefone(str(dados.get("telefone_1") or ""))
        dados["telefone_2"] = _formatar_telefone(str(dados.get("telefone_2") or ""))

        for chave, _titulo in self.CAMPOS:
            self.campos_vars[chave].set(str(dados.get(chave, "") or ""))

        # atualizar histórico combobox
        try:
            self.history_cb.configure(values=_get_history())
        except Exception:
            pass

        self.msg_var.set("Consulta concluída. Use os botões Copiar/Salvar para exportar.")

    def consultar(self, _event=None) -> None:
        cnpj = self.cnpj_var.get()
        cnpj_digits = _apenas_digitos(cnpj)
        if not validar_cnpj(cnpj_digits):
            self.msg_var.set("CNPJ inválido. Verifique e tente novamente.")
            return

        self.msg_var.set("Iniciando consulta...")
        self._set_busy(True)
        future = self.executor.submit(self._consultar_background, cnpj_digits)
        self._start_spinner()

        def _when_done(fut):
            try:
                res = fut.result()
                self.root.after(0, lambda: self._on_consulta_done(res, None))
            except Exception as e:
                self.root.after(0, lambda: self._on_consulta_done(None, e))

        future.add_done_callback(_when_done)


def main() -> None:
    root = tk.Tk()
    ConsultaCNPJApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
