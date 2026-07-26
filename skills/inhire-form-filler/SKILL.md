---
name: "inhire-form-filler"
description: "Preenchedor inHire que lê dados de um arquivo Markdown."
---

# Skill: Preenchedor inHire via Script Python (v2)

## Procedimento:
Quando precisar se candidatar a uma vaga da plataforma **inHire**:

1. Identifique a URL da vaga enviada pelo usuário.
2. Certifique-se de que o arquivo `/home/rodrigo/web/JobSpy/assets/dados_candidatura.md` contenha os dados formatados (chave:valor) e o arquivo `/home/rodrigo/web/JobSpy/assets/curriculo.pdf` esteja disponível.
3. Execute o comando de shell nativo abaixo substituindo a URL da vaga:

```bash
python3 ./scripts/fill/inhire.py --url "<URL_DA_VAGA>" --data "/home/rodrigo/web/JobSpy/assets/dados_candidatura.md" --resume "/home/rodrigo/web/JobSpy/assets/curriculo.pdf"
```

O script lerá automaticamente os dados do arquivo de markdown e preencherá os campos correspondentes no formulário inHire.
