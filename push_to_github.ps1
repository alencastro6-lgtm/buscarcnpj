# Script para fazer push automático para GitHub
# Execute após instalar Git: https://git-scm.com/download/win

param(
    [string]$GitHubUrl = "https://github.com/alencastro6-lgtm/buscarcnpj",
    [string]$Token = "" # Será solicitado se não informado
)

if (-not $Token) {
    $Token = Read-Host "Cole o token de acesso do GitHub"
}

$ProjectPath = "c:\Users\User\Downloads\BUSCAR_CNPJ"

cd $ProjectPath

# Inicializar repositório
Write-Host "Inicializando repositório Git..." -ForegroundColor Green
git init

# Configurar usuário
git config user.name "alencastro6-lgtm"
git config user.email "seu-email@example.com"

# Adicionar todos os arquivos
Write-Host "Adicionando arquivos..." -ForegroundColor Green
git add .

# Fazer commit
Write-Host "Criando commit..." -ForegroundColor Green
git commit -m "Initial commit: BUSCAR_CNPJ app - consulta CNPJ e salva em TXT"

# Adicionar remote (com token na URL)
$RemoteUrl = $GitHubUrl -replace "https://", "https://$($Token)@"
Write-Host "Adicionando repositório remoto..." -ForegroundColor Green
git remote add origin $RemoteUrl

# Renomear branch para main
git branch -M main

# Fazer push
Write-Host "Fazendo push para GitHub..." -ForegroundColor Green
git push -u origin main

Write-Host "✓ Pronto! Repositório enviado com sucesso!" -ForegroundColor Green
Write-Host "Acesse: $GitHubUrl" -ForegroundColor Cyan
