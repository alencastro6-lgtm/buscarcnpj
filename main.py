"""Consulta de CNPJ para apoiar cadastro de clientes."""

from __future__ import annotations

import logging
import os
import time
import tkinter as tk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog, ttk

from cnpj_service import (
    _apenas_digitos,
    _clear_history,
    _cursor_por_qtd_digitos,
    _formatar_cep,
    _formatar_cnpj,
    _formatar_para_copia,
    _formatar_telefone,
    _get_history,
    _init_db,
    _load_cache,
    _save_cache,
    _save_history,
    consultar_cnpj,
    validar_cnpj,
)


class ConsultaCNPJApp:
    SECOES = [
        (
            "Empresa",
            [
                ("cnpj", "CNPJ"),
                ("razao_social", "Razão social"),
                ("nome_fantasia", "Nome fantasia"),
                ("situacao", "Situação"),
                ("data_situacao", "Data situação"),
                ("natureza_juridica", "Natureza jurídica"),
                ("porte", "Porte"),
                ("capital_social", "Capital social"),
                ("atividade_principal", "Atividade principal"),
            ],
        ),
        (
            "Contato",
            [
                ("telefone_1", "Telefone 1"),
                ("telefone_2", "Telefone 2"),
                ("email", "E-mail"),
            ],
        ),
        (
            "Endereço",
            [
                ("cep", "CEP"),
                ("logradouro", "Logradouro"),
                ("numero", "Número"),
                ("complemento", "Complemento"),
                ("bairro", "Bairro"),
                ("municipio", "Município"),
                ("uf", "UF"),
            ],
        ),
    ]
    CAMPOS = [campo for _secao, campos in SECOES for campo in campos]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Consulta de CNPJ")
        self.root.geometry("950x700")
        self.root.minsize(840, 560)

        self.cnpj_var = tk.StringVar()
        self.msg_var = tk.StringVar(value="Digite o CNPJ e clique em Consultar.")
        self.campos_vars = {chave: tk.StringVar() for chave, _ in self.CAMPOS}
        self.consulta_em_andamento = False
        self.cnpj_consultando = ""

        self.executor = ThreadPoolExecutor(max_workers=2)
        _init_db()

        self._montar_tela()

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

        ttk.Label(topo, text="Histórico:").pack(side="left", padx=(12, 4))
        self.history_cb = ttk.Combobox(topo, values=self._history_values(), width=18)
        self.history_cb.pack(side="left")
        self.history_cb.bind("<<ComboboxSelected>>", self._on_history_selected)

        self.limpar_historico_btn = ttk.Button(
            topo,
            text="Limpar histórico",
            command=self.limpar_historico,
        )
        self.limpar_historico_btn.pack(side="left", padx=(8, 0))

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

        row = 0
        for secao, campos in self.SECOES:
            ttk.Label(self.form_frame, text=secao, font=("", 10, "bold")).grid(
                row=row,
                column=0,
                columnspan=3,
                padx=(0, 8),
                pady=(12 if row else 0, 4),
                sticky="w",
            )
            row += 1
            for chave, titulo in campos:
                ttk.Label(self.form_frame, text=f"{titulo}:").grid(
                    row=row,
                    column=0,
                    padx=(0, 8),
                    pady=5,
                    sticky="w",
                )
                entry = ttk.Entry(self.form_frame, textvariable=self.campos_vars[chave], width=78)
                entry.grid(row=row, column=1, padx=(0, 8), pady=5, sticky="we")
                entry.configure(state="readonly")
                ttk.Button(
                    self.form_frame,
                    text="Copiar",
                    width=10,
                    command=lambda c=chave, t=titulo: self.copiar_campo(c, t),
                ).grid(row=row, column=2, padx=(0, 2), pady=5)
                row += 1

        self.form_frame.columnconfigure(1, weight=1)

    def _history_values(self) -> list[str]:
        return [_formatar_cnpj(cnpj) for cnpj in _get_history()]

    def _atualizar_historico(self) -> None:
        self.history_cb.configure(values=self._history_values())

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

    def limpar_historico(self) -> None:
        try:
            _clear_history()
            self.history_cb.set("")
            self._atualizar_historico()
            self.msg_var.set("Histórico limpo.")
        except Exception:
            self.msg_var.set("Não foi possível limpar o histórico.")

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
        for widget in (
            self.consultar_btn,
            self.limpar_btn,
            self.salvar_txt_btn,
            self.copiar_tudo_btn,
            self.history_cb,
            self.limpar_historico_btn,
        ):
            try:
                widget.configure(state=state)
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
        cached = _load_cache(cnpj_digits)
        if cached:
            logging.info("Cache hit: %s", cnpj_digits)
            _save_history(cnpj_digits)
            dados = dict(cached)
            dados["_origem"] = "cache"
            return dados

        last_exc: Exception | None = None
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

        raise RuntimeError(
            "Não foi possível consultar agora. Verifique sua conexão ou tente novamente em alguns minutos."
        ) from last_exc

    def _on_consulta_done(self, dados: dict | None, exc: Exception | None) -> None:
        self._stop_spinner()
        self._set_busy(False)
        self.consulta_em_andamento = False
        self.cnpj_consultando = ""
        if exc:
            self.msg_var.set(str(exc))
            return
        if not dados:
            self.msg_var.set("Nenhum dado retornado para este CNPJ.")
            return

        origem = dados.pop("_origem", "")
        dados["cnpj"] = _formatar_cnpj(str(dados.get("cnpj") or ""))
        dados["cep"] = _formatar_cep(str(dados.get("cep") or ""))
        dados["telefone_1"] = _formatar_telefone(str(dados.get("telefone_1") or ""))
        dados["telefone_2"] = _formatar_telefone(str(dados.get("telefone_2") or ""))

        for chave, _titulo in self.CAMPOS:
            self.campos_vars[chave].set(str(dados.get(chave, "") or ""))

        try:
            self._atualizar_historico()
        except Exception:
            pass

        if origem == "cache":
            self.msg_var.set("Dados carregados do cache.")
        elif origem:
            self.msg_var.set(f"Consulta concluída. Fonte: {origem}.")
        else:
            self.msg_var.set("Consulta concluída.")

    def consultar(self, _event=None) -> None:
        cnpj = self.cnpj_var.get()
        cnpj_digits = _apenas_digitos(cnpj)
        if len(cnpj_digits) != 14:
            if len(cnpj_digits) == 11:
                self.msg_var.set(
                    "CNPJ inválido. Esse número tem 11 dígitos; verifique se você não digitou um CPF."
                )
            else:
                self.msg_var.set("CNPJ inválido. Informe 14 dígitos e tente novamente.")
            return
        if not validar_cnpj(cnpj_digits):
            self.msg_var.set("CNPJ inválido. Verifique e tente novamente.")
            return

        if self.consulta_em_andamento:
            if self.cnpj_consultando == cnpj_digits:
                self.msg_var.set("Este CNPJ já está sendo consultado.")
            else:
                self.msg_var.set("Aguarde a consulta atual terminar.")
            return

        self.consulta_em_andamento = True
        self.cnpj_consultando = cnpj_digits
        self.msg_var.set("Iniciando consulta...")
        self._set_busy(True)
        future = self.executor.submit(self._consultar_background, cnpj_digits)
        self._start_spinner()

        def _when_done(fut):
            try:
                res = fut.result()
                self.root.after(0, lambda res=res: self._on_consulta_done(res, None))
            except Exception as e:
                self.root.after(0, lambda e=e: self._on_consulta_done(None, e))

        future.add_done_callback(_when_done)


def main() -> None:
    root = tk.Tk()
    ConsultaCNPJApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
