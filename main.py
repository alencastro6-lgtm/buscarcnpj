
"""Consulta de CNPJ para apoiar cadastro de clientes."""

from __future__ import annotations

import os
import tkinter as tk
from tkinter import ttk, filedialog
from concurrent.futures import ThreadPoolExecutor

from cnpj_service import (
    _apenas_digitos,
    _formatar_cnpj,
    _formatar_cep,
    _formatar_telefone,
    _cursor_por_qtd_digitos,
    _formatar_para_copia,
    validar_cnpj,
    _init_db,
    _get_history,
    _load_cache,
    _save_cache,
    _save_history,
    consultar_cnpj,
)


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
