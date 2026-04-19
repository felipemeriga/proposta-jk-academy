# Gerador de Proposta JK Academy

Aplicação web simples que serve o formulário e devolve o PDF pronto.
Funciona em qualquer navegador — o usuário final não precisa instalar nada.

## Estrutura

```
Template Proposta.pdf   # template com placeholders {campo}
fonts/                  # Montserrat (Bold / Regular / ExtraLight)
substituir_campos.py    # lógica de substituição (pymupdf)
app.py                  # servidor FastAPI que usa substituir_campos
formulario.html         # formulário web (POSTa no /gerar)
requirements.txt        # dependências Python
Dockerfile              # imagem para hosting
render.yaml             # blueprint para Render.com
```

## Rodar localmente

```bash
pip install -r requirements.txt
uvicorn app:app --reload
```

Abra `http://localhost:8000`, preencha os campos e clique em **Gerar PDF**.

## Deploy (recomendado: Render.com)

1. Suba esta pasta num repositório Git (GitHub, GitLab, etc).
2. Acesse [render.com](https://render.com) e faça login com o GitHub.
3. **New → Blueprint** e aponte para o repositório.
   O arquivo `render.yaml` já está configurado.
4. Aguarde o build. No final, você terá uma URL tipo
   `https://proposta-kacademy.onrender.com` para compartilhar com o time.

O free tier do Render adormece o serviço após ~15 min sem uso e leva
alguns segundos para acordar na primeira requisição seguinte. Se isso
incomodar, o plano Starter (≈ US$ 7/mês) mantém sempre ativo.

### Alternativas

- **Fly.io**: `fly launch` (detecta o Dockerfile automaticamente).
- **Railway**: *New project → Deploy from GitHub repo*.
- **Docker em VPS próprio**: `docker build -t proposta . && docker run -p 8000:8000 proposta`.

## Atualizar o template

Se o desenho do PDF mudar, basta substituir o `Template Proposta.pdf`
e redeploy — os placeholders `{nome}` continuam funcionando.

## Adicionar novos campos

1. Coloque `{novo_campo}` no PDF (Montserrat-Bold, Regular ou ExtraLight).
2. Adicione um input correspondente em `formulario.html` e inclua a chave
   na lista `fields`.
3. Não precisa tocar no Python — o script identifica placeholders
   dinamicamente.
