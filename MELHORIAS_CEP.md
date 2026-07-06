# Melhorias na Busca de CEP

## Problema Original
A busca de CEP não estava retornando o bairro de forma confiável, usando apenas duas APIs (BrasilAPI e ViaCEP).

## Soluções Implementadas

### 1. **Múltiplas APIs em Cascata** 🔄
Agora a busca tenta 3 APIs sequencialmente para garantir dados completos:

```
BrasilAPI → ViaCEP → AwesomeAPI
```

- **BrasilAPI**: Primeira tentativa, suporta vários formatos de dados
- **ViaCEP**: Segunda tentativa, API brasileira confiável
- **AwesomeAPI**: Terceira tentativa, API alternativa complementar

### 2. **Mescla Inteligente de Dados** 🔗
Quando uma API retorna dados incompletos, os campos faltantes são preenchidos com dados de outras APIs:

```python
# Exemplo: BrasilAPI sem bairro, ViaCEP com bairro
resultado_final = {
    "logradouro": "Rua Teste",  # De BrasilAPI
    "bairro": "Centro",          # Preenchido por ViaCEP
    "ibge": "3550308"            # De BrasilAPI
}
```

### 3. **Busca Complementar de Bairro** 🔍
Função `_buscar_bairro_complementar()` que:
- Tenta preencher bairro vazio via busca por endereço completo
- Usa a API ViaCEP com UF + Cidade + Logradouro
- Preenche também IBGE e SIAFI quando disponível

### 4. **Busca por Endereço Melhorada** 📍
`consultar_cep_por_endereco()` agora:
- Suporta fallback entre BrasilAPI e ViaCEP
- Retorna dados parciais se houver logradouro
- Melhor tratamento de erros com mensagens descritivas

## Campos Retornados
Todos esses campos estão garantidos ou preenchidos quando possível:

| Campo | Descrição | Fonte |
|-------|-----------|-------|
| `cep` | CEP formatado | Formatado automaticamente |
| `logradouro` | Rua, Avenida, Praça, etc | APIs |
| `complemento` | Sala, Bloco, etc | APIs |
| `bairro` | Bairro do endereço | **Agora mais confiável** |
| `localidade` | Cidade | APIs |
| `uf` | Estado (sigla) | APIs |
| `ddd` | DDD telefônico | APIs |
| `ibge` | Código IBGE | APIs |
| `gia` | Código GIA | APIs |
| `siafi` | Código SIAFI | APIs |
| `service` | API usada | Rastreamento interno |

## Testes Adicionados

```
✅ test_consultar_cep_fallback_awesome_api_quando_outras_falham
✅ test_consultar_cep_mescla_dados_de_multiplas_apis  
✅ test_consultar_cep_busca_complementar_bairro
```

## Exemplo de Uso

### Busca por CEP
```python
from cnpj_service import consultar_cep

resultado = consultar_cep("01310-100")
print(resultado["bairro"])      # "Bela Vista"
print(resultado["logradouro"])  # "Avenida Paulista"
print(resultado["service"])     # Qual API forneceu os dados
```

### Busca por Endereço
```python
resultado = consultar_cep("SP, São Paulo, Avenida Paulista")
print(resultado["cep"])  # "01310-100"
print(resultado["bairro"])  # "Bela Vista"
```

## Performance

- ⚡ Timeout por API: 20 segundos
- 📊 Cache: 30 dias (mesmo comportamento anterior)
- 🔄 Fallback automático: sem latência adicional perceptível

## Compatibilidade

- ✅ Todos os testes anteriores continuam passando
- ✅ Interface de API não mudou
- ✅ Backward compatible com código existente
- ✅ Melhor confiabilidade com zero breaking changes

## Próximas Melhorias Possíveis

1. Adicionar Google Maps API como fallback premium
2. Cache de buscas por endereço complementar
3. Validação de latitude/longitude
4. Integração com base IBGE completa
