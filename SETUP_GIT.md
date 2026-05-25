# Instruções para enviar para GitHub/GitLab

## Passo 1: Criar repositório online
- GitHub: https://github.com/new
- GitLab: https://gitlab.com/projects/new

## Passo 2: Inicializar e fazer push local

Execute estes comandos na pasta do projeto:

```powershell
cd c:\Users\User\Downloads\BUSCAR_CNPJ

# Inicializar git
git init
git add .
git commit -m "Initial commit: BUSCAR_CNPJ app"

# Adicionar repositório remoto (substitua URL)
git remote add origin https://github.com/seu-usuario/buscar-cnpj.git

# Fazer push para main/master
git branch -M main
git push -u origin main
```

## Estrutura do repositório

```
BUSCAR_CNPJ/
├── main.py              # Aplicação principal
├── README.md            # Documentação
├── requirements.txt     # Dependências
├── .gitignore          # Arquivos ignorados pelo git
├── run_projeto.bat     # Script para executar no Windows
├── tests/              # Testes unitários
│   └── test_formatters.py
├── dist/               # Executável gerado (não enviado ao git)
│   └── BUSCAR_CNPJ.exe
└── .github/
    └── workflows/      # CI/CD
        └── python-app.yml
```

## Executável

O arquivo `dist/BUSCAR_CNPJ.exe` pode ser executado direto sem Python instalado.
