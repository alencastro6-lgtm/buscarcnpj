"""Consulta de CNPJ para apoiar cadastro de clientes."""

from __future__ import annotations

import logging
import os
import re
import time
import webbrowser
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
    consultar_cep,
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
    CAMPOS_CEP = [
        ("cep", "CEP"),
        ("logradouro", "Logradouro"),
        ("complemento", "Complemento"),
        ("bairro", "Bairro"),
        ("localidade", "Localidade"),
        ("uf", "UF"),
        ("ddd", "DDD"),
        ("ibge", "IBGE"),
        ("gia", "GIA"),
        ("siafi", "SIAFI"),
    ]

    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Consulta de CNPJ")
        self.root.geometry("1120x680")
        self.root.minsize(1040, 620)
        try:
            self.root.state("zoomed")
        except tk.TclError:
            self.root.attributes("-zoomed", True)

        self.cnpj_var = tk.StringVar()
        self.cep_var = tk.StringVar()
        self.msg_var = tk.StringVar(value="Digite o CNPJ e clique em Consultar.")
        self.campos_vars = {chave: tk.StringVar() for chave, _ in self.CAMPOS}
        self.cep_vars = {
            "cep": tk.StringVar(),
            "logradouro": tk.StringVar(),
            "complemento": tk.StringVar(),
            "bairro": tk.StringVar(),
            "localidade": tk.StringVar(),
            "uf": tk.StringVar(),
            "ddd": tk.StringVar(),
            "ibge": tk.StringVar(),
            "gia": tk.StringVar(),
            "siafi": tk.StringVar(),
        }
        self.consulta_em_andamento = False
        self.cnpj_consultando = ""
        self.consulta_cep_em_andamento = False
        self.cep_consultando = ""

        self.executor = ThreadPoolExecutor(max_workers=2)
        _init_db()

        self._configurar_estilo()
        self._montar_tela()

        self._spinner_running = False
        self._spinner_pos = 0

    def _configurar_estilo(self) -> None:
        self.root.configure(bg="#f4f6f8")
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background="#f4f6f8")
        style.configure("Top.TFrame", background="#e9eef3")
        style.configure("Panel.TFrame", background="#ffffff")
        style.configure("Top.TLabel", background="#e9eef3", foreground="#1f2933")
        style.configure("Panel.TLabelframe", background="#ffffff", padding=(12, 8))
        style.configure(
            "Panel.TLabelframe.Label",
            background="#f4f6f8",
            foreground="#1f2933",
            font=("", 10, "bold"),
        )
        style.configure("TLabel", background="#f4f6f8", foreground="#1f2933")
        style.configure("Field.TLabel", background="#ffffff", foreground="#52606d")
        style.configure("Status.TLabel", background="#dde6ef", foreground="#1f2933")
        style.configure("TButton", padding=(8, 4))
        style.configure("TEntry", padding=(4, 3))
        style.configure("TCombobox", padding=(4, 3))
        style.configure("Small.TLabel", background="#e9eef3", foreground="#4b5563", font=("", 9))

    def _montar_tela(self) -> None:
        self.status_label = ttk.Label(
            self.root,
            textvariable=self.msg_var,
            padding=(12, 7),
            style="Status.TLabel",
        )
        self.status_label.pack(fill="x")

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True)

        tab_cnpj = ttk.Frame(notebook, padding=(0, 0))
        tab_cep = ttk.Frame(notebook, padding=(0, 0))
        notebook.add(tab_cnpj, text="CNPJ")
        notebook.add(tab_cep, text="CEP")

        self._montar_tela_cnpj(tab_cnpj)
        self._montar_tela_cep(tab_cep)

    def _montar_tela_cnpj(self, parent: ttk.Frame) -> None:
        topo = ttk.Frame(parent, padding=(12, 10), style="Top.TFrame")
        topo.pack(fill="x")
        topo.columnconfigure(4, weight=1)

        ttk.Label(topo, text="CNPJ:", style="Top.TLabel").grid(row=0, column=0, sticky="w")
        self.cnpj_entry = ttk.Entry(topo, textvariable=self.cnpj_var, width=24)
        self.cnpj_entry.grid(row=0, column=1, sticky="w", padx=(8, 8))
        self.cnpj_entry.bind("<KeyRelease>", self._on_cnpj_change)
        self.cnpj_entry.bind("<Return>", self.consultar)
        self.cnpj_entry.bind("<FocusOut>", self._on_cnpj_change)
        self.cnpj_entry.focus_set()

        self.colar_btn = ttk.Button(topo, text="Colar", command=self.colar_cnpj)
        self.colar_btn.grid(row=0, column=2, padx=(0, 6))
        self.consultar_btn = ttk.Button(topo, text="Consultar", command=self.consultar)
        self.consultar_btn.grid(row=0, column=3, padx=(0, 6))
        self.limpar_btn = ttk.Button(topo, text="Limpar", command=self.limpar)
        self.limpar_btn.grid(row=0, column=5, padx=(18, 6))
        self.salvar_txt_btn = ttk.Button(topo, text="Salvar TXT", command=self.salvar_txt)
        self.salvar_txt_btn.grid(row=0, column=6, padx=(0, 6))
        self.copiar_tudo_btn = ttk.Button(topo, text="Copiar tudo", command=self.copiar_tudo)
        self.copiar_tudo_btn.grid(row=0, column=7, padx=(0, 14))

        ttk.Label(topo, text="Histórico:", style="Top.TLabel").grid(row=0, column=8, sticky="e", padx=(0, 4))
        self.history_cb = ttk.Combobox(topo, values=self._history_values(), width=18)
        self.history_cb.grid(row=0, column=9, sticky="w")
        self.history_cb.bind("<<ComboboxSelected>>", self._on_history_selected)

        self.limpar_historico_btn = ttk.Button(
            topo,
            text="Limpar histórico",
            command=self.limpar_historico,
        )
        self.limpar_historico_btn.grid(row=0, column=10, padx=(8, 0))

        conteudo = ttk.Frame(parent, padding=(12, 10, 12, 12))
        conteudo.pack(fill="both", expand=True)
        conteudo.columnconfigure(0, weight=3, uniform="main")
        conteudo.columnconfigure(1, weight=2, uniform="main")
        conteudo.rowconfigure(0, weight=1)
        conteudo.rowconfigure(1, weight=1)

        empresa = ttk.LabelFrame(conteudo, text="Empresa", style="Panel.TLabelframe")
        empresa.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 8))
        contato = ttk.LabelFrame(conteudo, text="Contato", style="Panel.TLabelframe")
        contato.grid(row=0, column=1, sticky="nsew", padx=(8, 0), pady=(0, 8))
        endereco = ttk.LabelFrame(conteudo, text="Endereço", style="Panel.TLabelframe")
        endereco.grid(row=1, column=1, sticky="nsew", padx=(8, 0), pady=(8, 0))

        self._montar_secao(empresa, self.SECOES[0][1], colunas=2, largura=30)
        self._montar_secao(contato, self.SECOES[1][1], colunas=1, largura=34)
        self._montar_secao(endereco, self.SECOES[2][1], colunas=1, largura=34)

    def _montar_tela_cep(self, parent: ttk.Frame) -> None:
        container = ttk.Frame(parent, padding=(12, 10, 12, 12))
        container.pack(fill="both", expand=True)

        topo = ttk.Frame(container, padding=(0, 0, 0, 10), style="Top.TFrame")
        topo.pack(fill="x")
        topo.columnconfigure(4, weight=1)

        ttk.Label(topo, text="CEP / Endereço:", style="Top.TLabel").grid(row=0, column=0, sticky="w")
        self.cep_entry = ttk.Entry(topo, textvariable=self.cep_var, width=40)
        self.cep_entry.grid(row=0, column=1, sticky="w", padx=(8, 8))
        self.cep_entry.bind("<KeyRelease>", self._on_cep_change)
        self.cep_entry.bind("<Return>", self.buscar_cep)
        self.cep_entry.bind("<FocusOut>", self._on_cep_change)

        ttk.Label(topo, text="Informe CEP ou endereço (UF/Cidade/Logradouro)", style="Small.TLabel").grid(row=1, column=1, sticky="w", padx=(8, 8))

        self.buscar_cep_btn = ttk.Button(topo, text="Buscar CEP", command=self.buscar_cep)
        self.buscar_cep_btn.grid(row=0, column=2, padx=(0, 6))
        self.limpar_cep_btn = ttk.Button(topo, text="Limpar", command=self.limpar_cep)
        self.limpar_cep_btn.grid(row=0, column=3, padx=(0, 6))
        self.copiar_tudo_cep_btn = ttk.Button(topo, text="Copiar tudo", command=self.copiar_tudo_cep)
        self.copiar_tudo_cep_btn.grid(row=0, column=4, padx=(16, 0))

        panel = ttk.LabelFrame(container, text="Dados do endereço", style="Panel.TLabelframe")
        panel.pack(fill="both", expand=True)

        for linha, (chave, titulo) in enumerate(self.CAMPOS_CEP):
            ttk.Label(panel, text=f"{titulo}:", style="Field.TLabel").grid(
                row=linha,
                column=0,
                sticky="w",
                padx=(0, 8),
                pady=4,
            )
            entry = ttk.Entry(panel, textvariable=self.cep_vars[chave], width=38)
            entry.grid(row=linha, column=1, sticky="ew", padx=(0, 6), pady=4)
            entry.configure(state="readonly")
            ttk.Button(
                panel,
                text="Copiar",
                width=8,
                command=lambda c=chave, t=titulo: self.copiar_campo_cep(c, t),
            ).grid(row=linha, column=2, sticky="w", pady=4)
            panel.columnconfigure(1, weight=1)

    def _montar_secao(
        self,
        frame: ttk.LabelFrame,
        campos: list[tuple[str, str]],
        colunas: int,
        largura: int,
    ) -> None:
        for coluna in range(colunas):
            base = coluna * 3
            frame.columnconfigure(base + 1, weight=1)

        linha = 0
        coluna = 0
        for chave, titulo in campos:
            if chave in ("razao_social", "atividade_principal") and colunas > 1:
                if coluna:
                    linha += 1
                    coluna = 0
                ttk.Label(frame, text=f"{titulo}:", style="Field.TLabel").grid(
                    row=linha,
                    column=0,
                    sticky="w",
                    padx=(0, 6),
                    pady=4,
                )
                entry = ttk.Entry(frame, textvariable=self.campos_vars[chave])
                entry.grid(row=linha, column=1, columnspan=(colunas * 3) - 2, sticky="ew", padx=(0, 6), pady=4)
                entry.configure(state="readonly")
                self._montar_acoes_campo(frame, linha, (colunas * 3) - 1, chave, titulo)
                linha += 1
                coluna = 0
                continue

            base = coluna * 3
            padx_label = (0 if coluna == 0 else 14, 6)
            ttk.Label(frame, text=f"{titulo}:", style="Field.TLabel").grid(
                row=linha,
                column=base,
                sticky="w",
                padx=padx_label,
                pady=4,
            )
            entry = ttk.Entry(frame, textvariable=self.campos_vars[chave], width=largura)
            entry.grid(row=linha, column=base + 1, sticky="ew", padx=(0, 6), pady=4)
            entry.configure(state="readonly")
            self._montar_acoes_campo(frame, linha, base + 2, chave, titulo)
            coluna += 1
            if coluna >= colunas:
                linha += 1
                coluna = 0

    def _montar_acoes_campo(
        self,
        frame: ttk.LabelFrame,
        linha: int,
        coluna: int,
        chave: str,
        titulo: str,
    ) -> None:
        acoes = ttk.Frame(frame, style="Panel.TFrame")
        acoes.grid(row=linha, column=coluna, sticky="e", pady=4)
        ttk.Button(
            acoes,
            text="Copiar",
            width=7,
            command=lambda c=chave, t=titulo: self.copiar_campo(c, t),
        ).pack(side="left")
        if chave in ("telefone_1", "telefone_2"):
            ttk.Button(
                acoes,
                text="WhatsApp",
                width=10,
                command=lambda c=chave, t=titulo: self.abrir_whatsapp(c, t),
            ).pack(side="left", padx=(4, 0))

    def _history_values(self) -> list[str]:
        return [_formatar_cnpj(cnpj) for cnpj in _get_history()]

    def _on_cep_change(self, _event=None) -> None:
        valor_atual = self.cep_var.get()
        if any(ch.isalpha() for ch in valor_atual) or "/" in valor_atual or "," in valor_atual:
            return

        cursor_atual = self.cep_entry.index(tk.INSERT)
        qtd_digitos_antes_cursor = len(_apenas_digitos(valor_atual[:cursor_atual]))

        valor_formatado = _formatar_cep(valor_atual)
        if valor_atual != valor_formatado:
            self.cep_var.set(valor_formatado)

        novo_cursor = _cursor_por_qtd_digitos(valor_formatado, qtd_digitos_antes_cursor)
        self.cep_entry.icursor(novo_cursor)

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

    def limpar_cep(self) -> None:
        self.cep_var.set("")
        for var in self.cep_vars.values():
            var.set("")
        self.msg_var.set("Campos de CEP limpos.")

    def colar_cnpj(self) -> None:
        try:
            texto = self.root.clipboard_get()
        except tk.TclError:
            self.msg_var.set("Área de transferência vazia.")
            return

        cnpj_digits = _apenas_digitos(texto)
        if len(cnpj_digits) < 14:
            self.msg_var.set("Nenhum CNPJ com 14 dígitos encontrado para colar.")
            return

        self.cnpj_var.set(_formatar_cnpj(cnpj_digits[:14]))
        self.cnpj_entry.icursor(tk.END)
        self.msg_var.set("CNPJ colado.")

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

    def copiar_campo_cep(self, chave: str, titulo: str) -> None:
        valor = self.cep_vars[chave].get()
        if not valor:
            self.msg_var.set(f"{titulo} está vazio.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(valor)
        self.msg_var.set(f"{titulo} copiado.")

    def copiar_tudo_cep(self) -> None:
        texto = "\n".join(self._linhas_cep())
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        self.msg_var.set("Dados do CEP copiados.")

    def _linhas_cep(self) -> list[str]:
        return [f"{titulo}: {self.cep_vars[chave].get()}" for chave, titulo in self.CAMPOS_CEP]

    def buscar_cep(self, _event=None) -> None:
        cep = self.cep_var.get().strip()
        if not cep:
            self.msg_var.set("Informe um CEP ou endereço para buscar.")
            return

        if self.consulta_cep_em_andamento:
            if self.cep_consultando == cep:
                self.msg_var.set("Esta consulta já está em andamento.")
            else:
                self.msg_var.set("Aguarde a consulta atual terminar.")
            return

        self.consulta_cep_em_andamento = True
        self.cep_consultando = cep
        self._set_cep_busy(True)
        self.msg_var.set("Consultando CEP...")
        future = self.executor.submit(self._consultar_cep_sincrono, cep)

        def _when_done(fut):
            try:
                res = fut.result()
                self.root.after(0, lambda res=res: self._on_cep_done(res, None))
            except Exception as e:
                self.root.after(0, lambda e=e: self._on_cep_done(None, e))

        future.add_done_callback(_when_done)

    def _on_cep_done(self, dados: dict | None, exc: Exception | None) -> None:
        self._set_cep_busy(False)
        self.consulta_cep_em_andamento = False
        cep_consultado = self.cep_consultando
        self.cep_consultando = ""

        if exc:
            self.msg_var.set(str(exc))
            return
        if not dados:
            self.msg_var.set("Nenhum dado retornado para este CEP.")
            return

        self._preencher_cep(dados)
        self.msg_var.set(f"CEP {dados.get('cep', cep_consultado)} consultado com sucesso.")

    def _preencher_cep(self, dados: dict) -> None:
        for chave, _titulo in self.CAMPOS_CEP:
            self.cep_vars[chave].set(str(dados.get(chave, "") or ""))

    def _set_cep_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (
            self.cep_entry,
            self.buscar_cep_btn,
            self.limpar_cep_btn,
            self.copiar_tudo_cep_btn,
        ):
            try:
                widget.configure(state=state)
            except tk.TclError:
                pass

    def _consultar_cep_sincrono(self, cep_digits: str) -> dict:
        try:
            return consultar_cep(cep_digits)
        except Exception as exc:
            logging.exception("Erro na consulta de CEP")
            raise

    def abrir_whatsapp(self, chave: str, titulo: str) -> None:
        telefone = self._telefone_whatsapp(self.campos_vars[chave].get())
        if not telefone:
            self.msg_var.set(f"{titulo} não parece ter DDD.")
            return

        if self._abrir_link_whatsapp(telefone):
            self.msg_var.set(f"WhatsApp aberto para {titulo}.")
        else:
            self.msg_var.set("Não foi possível abrir o WhatsApp instalado.")

    def _telefone_whatsapp(self, valor: str) -> str | None:
        grupos = re.findall(r"\d+", valor or "")
        candidatos: list[str] = []

        for grupo in grupos:
            digitos = grupo[2:] if grupo.startswith("55") else grupo
            if len(digitos) in (10, 11):
                candidatos.append(digitos)

        for inicio in range(len(grupos) - 2):
            partes = grupos[inicio : inicio + 3]
            if partes[0] == "55" and inicio + 3 < len(grupos):
                partes = grupos[inicio + 1 : inicio + 4]
            if len(partes[0]) != 2:
                continue
            digitos = "".join(partes)
            if len(digitos) in (10, 11):
                candidatos.append(digitos)

        for tamanho in (11, 10):
            for candidato in candidatos:
                if len(candidato) == tamanho:
                    return f"55{candidato}"
        return None

    def _abrir_link_whatsapp(self, telefone: str) -> bool:
        app_url = f"whatsapp://send?phone={telefone}"
        web_url = f"https://wa.me/{telefone}"
        try:
            os.startfile(app_url)
            return True
        except (AttributeError, OSError):
            return webbrowser.open(web_url)

    def salvar_txt(self) -> None:
        linhas = self._linhas_cnpj()

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
        texto = "\n".join(self._linhas_cnpj())
        self.root.clipboard_clear()
        self.root.clipboard_append(texto)
        self.msg_var.set("Todos os campos copiados.")

    def _linhas_cnpj(self) -> list[str]:
        return [f"{titulo}: {self.campos_vars[chave].get() or ''}" for chave, titulo in self.CAMPOS]

    def _set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        for widget in (
            self.colar_btn,
            self.consultar_btn,
            self.limpar_btn,
            self.salvar_txt_btn,
            self.copiar_tudo_btn,
            self.history_cb,
            self.limpar_historico_btn,
        ):
            try:
                widget.configure(state=state)
            except tk.TclError:
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
        self._preencher_cnpj(dados)

        try:
            self._atualizar_historico()
        except tk.TclError:
            pass

        if origem == "cache":
            self.msg_var.set("Dados carregados do cache.")
        elif origem:
            self.msg_var.set(f"Consulta concluída. Fonte: {origem}.")
        else:
            self.msg_var.set("Consulta concluída.")

    def _preencher_cnpj(self, dados: dict) -> None:
        dados_formatados = dict(dados)
        dados_formatados["cnpj"] = _formatar_cnpj(str(dados_formatados.get("cnpj") or ""))
        dados_formatados["cep"] = _formatar_cep(str(dados_formatados.get("cep") or ""))
        dados_formatados["telefone_1"] = _formatar_telefone(str(dados_formatados.get("telefone_1") or ""))
        dados_formatados["telefone_2"] = _formatar_telefone(str(dados_formatados.get("telefone_2") or ""))

        for chave, _titulo in self.CAMPOS:
            self.campos_vars[chave].set(str(dados_formatados.get(chave, "") or ""))

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
