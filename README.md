# OvxrNight — slowed-reverb-channel
Documento de continuidade do projeto. Cole este arquivo no início de cada sessão com o Claude para retomar de onde paramos.

---

## 1. Objetivo do Projeto

Canal automatizado no YouTube com foco em músicas **slowed & reverb**.
O fluxo combina uma etapa manual (escolha da música) com um pipeline Python que gera imagem, anima, combina com áudio e publica.

**Nome do canal:** OvxrNight

---

## 2. Links Importantes

### Plataformas do projeto
| Serviço | Link | Uso |
|---|---|---|
| Leonardo.ai Console | https://app.leonardo.ai | Ver gerações, créditos, galeria |
| Leonardo.ai API Docs | https://docs.leonardo.ai | Referência da API |
| Google Cloud Console | https://console.cloud.google.com | Gerenciar credenciais OAuth do YouTube |
| YouTube Studio | https://studio.youtube.com | Gerenciar o canal OvxrNight |
| Ollama | https://ollama.ai | Modelos locais instalados |

### Ferramentas e dependências
| Ferramenta | Link | Uso |
|---|---|---|
| FFmpeg | https://ffmpeg.org/download.html | Processamento de vídeo (deve estar no PATH) |
| slowed+reverb studio | https://slowedandreverb.studio | Aplicar efeito nas músicas (etapa manual) |

---

## 3. Fluxo Geral

### Etapa Manual (feita pelo usuário)
1. Escolher a música e aplicar efeito slowed+reverb em **slowedandreverb.studio**
2. Salvar o arquivo de áudio (MP3/WAV) na pasta `/inbox`

### Etapa Automatizada
Comando: `python pipeline.py`

```
inbox/ (arquivo mais antigo, ou busca por nome)
  │
  ├─[1] metadata_generator  → título, descrição, tags  (Ollama local)
  │      └─ edição manual do título  →  Artista - Nome da Música
  │
  ├─[2] image_generator     → imagem anime/dark 16:9   (Leonardo.ai API)
  │      └─ REVIEW DA IMAGEM antes do vídeo
  │           ├─ [s] aprovar → segue para o vídeo
  │           ├─ [n] nova imagem → gera outra (áudio preservado)
  │           └─ [d] descartar música → áudio volta ao /inbox
  │
  ├─[3] ken_burns           → vídeo animado 1920x1080  (FFmpeg)
  ├─[4] FFmpeg              → combinar áudio + vídeo
  │
  └─ review/  ← abre automaticamente no Explorer
       ├─ [s] Publicar → YouTube Data API v3
       └─ [n] Descartar → rejected/ + áudio volta ao /inbox
```

> **Regra:** O áudio só é removido permanentemente do `/inbox` quando o vídeo é **publicado com aprovação**. Em qualquer rejeição ou erro, o arquivo retorna ao `/inbox`.

### Comportamento em caso de erro
- Para imediatamente
- Devolve o áudio ao `/inbox`
- Salva log detalhado em `/logs/erro_[nome]_[timestamp].txt`
- Dispara notificação toast do Windows (sem dependências extras)

---

## 4. Uso via CLI

```powershell
# Processa o arquivo mais antigo do /inbox
python pipeline.py

# Busca e processa um arquivo específico (case-insensitive, qualquer parte do nome)
python pipeline.py "shy martin"
python pipeline.py "Duhe"
python pipeline.py "chelsea"

# Ajuda
python pipeline.py --help
```

---

## 5. Decisões Técnicas

| Ponto | Decisão |
|---|---|
| Sistema operacional | Windows |
| Execução do pipeline | Manual (`python pipeline.py`) |
| Ordem da fila | Arquivo mais antigo do `/inbox` primeiro |
| Busca por nome | Argumento posicional: `python pipeline.py "termo"` |
| Geração de metadados | Ollama local — `qwen3:1.7b` (sem custo de API) |
| Edição do título | Passo manual no terminal antes da geração da imagem |
| Geração de imagem | Leonardo.ai API — Phoenix 1.0 Fast, Alchemy ativado |
| Formato da imagem | 1472×832 (16:9 nativo) |
| Review da imagem | Antes da geração do vídeo — evita desperdício de tempo |
| Efeito de vídeo | FFmpeg — 9 efeitos Ken Burns + RGB Split periódico |
| FPS do vídeo | 60fps |
| Resolução | 1920×1080 (YouTube) |
| Publicação | YouTube Data API v3 (OAuth 2.0, 10.000 unidades/dia) |
| Orquestração | Python puro, sem n8n |

---

## 6. Instalação e Requisitos

### Dependências Python
```powershell
pip install requests google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### Ferramentas externas
- **FFmpeg** — baixar em ffmpeg.org e adicionar ao PATH do Windows
- **Ollama** — instalar e baixar o modelo: `ollama pull qwen3:1.7b`

### Arquivo `.env`
```env
LEONARDO_API_KEY=sua_chave_aqui
YOUTUBE_CLIENT_SECRET_PATH=client_secret.json
```

> A chave do Leonardo é obtida em **app.leonardo.ai → API Access → Create New Key**
> O `client_secret.json` é obtido no **Google Cloud Console → Credenciais → OAuth 2.0**

---

## 7. Estrutura de Pastas

```
slowed-reverb-channel/
│
├── README.md               ← este arquivo
├── .env                    ← chaves de API (nunca commitar)
├── client_secret.json      ← credencial OAuth YouTube (nunca commitar)
├── youtube_token.json      ← token OAuth gerado na 1ª execução (nunca commitar)
│
├── pipeline.py             ← script principal
├── image_generator.py      ← geração de imagem via Leonardo.ai
├── ken_burns.py            ← efeitos de vídeo via FFmpeg
├── metadata_generator.py   ← geração de metadados via Ollama
├── youtube_uploader.py     ← upload via YouTube Data API v3
│
├── inbox/                  ← colocar os MP3/WAV aqui (fila de entrada)
├── processing/             ← arquivos sendo processados (temporário)
├── review/                 ← vídeo pronto aguardando aprovação
├── rejected/               ← vídeos descartados
├── logs/                   ← logs de erro e histórico de publicações
└── assets/
    └── images/             ← cópia de todas as imagens geradas (histórico)
```

---

## 8. Módulos

### `pipeline.py` — Script principal

Processa **um arquivo por execução**.

Etapas interativas:
1. Edição do título (formato `Artista - Nome`)
2. Review da imagem gerada (aprovar / nova imagem / descartar)
3. Review do vídeo final (publicar / descartar)

Em todas as rejeições/erros: **áudio volta ao `/inbox`**.

---

### `image_generator.py` — Geração de imagem

**Modelo:** Phoenix 1.0 Fast (`de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3`)
**Modo:** Alchemy ativado (maior qualidade, anatomia melhorada)
**Formato:** 1472×832 (16:9)

**Banco de variações — 2.958.000 combinações:**
| Categoria | Qtd | Destaques |
|---|---|---|
| Personagens | 34 | Guerreiras, místicas, femininas serenas/sensuais, guerreiros masculinos, magos, solitários |
| Poses / ângulos | 29 | Sentadas, braços abertos, roupas esvoaçantes, movimentos artísticos, planos abertos |
| Cenários | 30 | Arquitetura em ruínas, tavernas, montanhas, campos estrelados, horizontes distantes |
| Estilos visuais | 10 | Painterly, noir, watercolor, gothic, hyper-detailed |
| Tons emocionais | 10 | Solidão, perda, serenidade, pureza sombria, silêncio antes do fim |

Cada prompt inclui automaticamente **sufixo de qualidade** (olhos, rosto, mãos, boca).
Após o download, cópia automática em `assets/images/gerada_[timestamp].png`.

---

### `ken_burns.py` — Efeito de vídeo

Gera vídeo MP4 1920×1080 @ 60fps a partir de uma imagem estática.

**9 efeitos disponíveis:**
| Efeito | Ciclo | Descrição |
|---|---|---|
| `zoom_in` | único | Zoom lento para fora |
| `zoom_out` | único | Zoom abre — loop perfeito |
| `pan_esquerda` | único | Pan horizontal direita→esquerda |
| `pan_direita` | único | Pan horizontal esquerda→direita |
| `diagonal_melancolico` | único | Pan diagonal suave |
| `pulsacao` | 6s | Zoom 1.0→1.12→1.0 via seno |
| `pulsacao_pan` | zoom 2s + pan 4s | Pulsação + oscilação lateral |
| `zoom_snap` | 10s | Heartbeat: cresce linearmente e snapa de volta |
| `oscilacao` | zoom 6s + pan 10s | Zoom + deriva lateral lenta e hipnótica |

**RGB Split** ativo por padrão: aberração cromática a cada **8s** por **0.12s**.

---

### `metadata_generator.py` — Geração de metadados

Usa **Ollama local** (`qwen3:1.7b`) — sem custo de API.

**Formato do título gerado:**
```
｜ Artista - Nome da Música ｜ slowed + reverb - vers OvxrNight
```

Output: `{ titulo, descricao, tags }` — pronto para enviar ao YouTube.

---

### `youtube_uploader.py` — Publicação

Usa **YouTube Data API v3** com OAuth 2.0.
Token salvo em `youtube_token.json` — autorização apenas na 1ª execução.
Custo: ~1.600 unidades por upload (cota: 10.000/dia).

**Configuração (única vez):**
1. **console.cloud.google.com** → criar projeto → ativar YouTube Data API v3
2. Criar credencial **OAuth 2.0 → Aplicativo para computador**
3. Baixar JSON → salvar como `client_secret.json`
4. Adicionar seu e-mail como **usuário de teste** na tela de consentimento

---

## 9. Contexto do Canal

- **Nome:** OvxrNight
- **Tema:** músicas slowed & reverb
- **Estética:** anime, dark fantasy, melancólico, épico
- **Personagens:** equilibrado entre femininas (beleza misteriosa, serena, sensualidade contida) e masculinos (guerreiros sombrios, magos místicos, solitários)
- **Tom visual:** melancolia + poder épico (não depressivo, não alegre)
- **Sem:** conteúdo político, publicação sem aprovação explícita do dono

---

## 10. Status dos Módulos

- [x] `ken_burns.py` — completo e testado
- [x] `image_generator.py` — completo e testado
- [x] `metadata_generator.py` — completo e testado
- [x] `youtube_uploader.py` — completo (aguarda `client_secret.json` para teste final)
- [x] `pipeline.py` — completo (aguarda teste de ponta a ponta com YouTube)

---

*Projeto: OvxrNight slowed-reverb-channel — continuar no VS Code com Claude plugin.*
