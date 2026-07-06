# BUSCAR_CNPJ

Aplicativo desktop para consultar CNPJ, validar os dados e exportar resultados para TXT.

## Recursos

- Validação completa de CNPJ
- Interface gráfica com histórico de consultas
- Armazenamento local em SQLite para cache e histórico
- Cache com expiração automática após 30 dias
- Indicação se os dados vieram do cache, BrasilAPI ou ReceitaWS
- Consulta de CEP com fallback entre BrasilAPI e ViaCEP
- Botão para limpar o histórico
- Campos organizados por empresa, contato e endereço
- Exporta dados para arquivo TXT
- Copia campos individuais ou todos de uma vez
- Cliques rápidos com formatação automática de CNPJ

## Instalação

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
```

## Execução

```powershell
python main.py
```

Depois de instalar o projeto em modo editável, também é possível abrir pelo comando:

```powershell
pip install -e .
buscar-cnpj
```

## Gerar executável

O repositório inclui um arquivo `.spec` para PyInstaller:

```powershell
pip install pyinstaller
pyinstaller BUSCAR_CNPJ.spec
```

O executável será gerado em `dist/`.

## Estrutura do projeto

- `main.py` - interface gráfica do aplicativo
- `cnpj_service.py` - validação, cache e chamadas de API
- `tests/` - testes unitários
- `requirements.txt` - dependências do projeto
- `LICENSE` - licença do código

## Testes

```powershell
pytest -q
```

## Observações

- Os arquivos `app.log`, `cnpj_cache.db`, `dist/`, `build/` e `.venv/` não são enviados ao repositório.
- O projeto utiliza duas APIs de fallback para garantir consulta de CNPJ mesmo quando uma fonte estiver fora do ar.
- As consultas de CNPJ e CEP rodam em segundo plano para evitar travamentos na interface.
