# OvxrNight — slowed-reverb-channel

Canal automatizado no YouTube com foco em músicas **slowed & reverb**.
O fluxo combina uma etapa manual (escolha da música) com um pipeline Python que gera imagem, anima, combina com áudio e publica.

**Nome do canal:** OvxrNight

---

## 1. Links Importantes

| Serviço | Link | Uso |
|---|---|---|
| Leonardo.ai Console | https://app.leonardo.ai | Ver gerações, créditos, galeria |
| Leonardo.ai API Docs | https://docs.leonardo.ai | Referência da API |
| Google Cloud Console | https://console.cloud.google.com | Gerenciar credenciais OAuth do YouTube |
| YouTube Studio | https://studio.youtube.com | Gerenciar o canal OvxrNight |
| Ollama | https://ollama.ai | Modelos locais instalados |
| FFmpeg | https://ffmpeg.org/download.html | Processamento de vídeo (deve estar no PATH) |
| slowed+reverb studio | https://slowedandreverb.studio | Aplicar efeito nas músicas (etapa manual) |

---

## 2. Fluxo Geral

### Etapa Manual
1. Escolher a música e aplicar efeito slowed+reverb em **slowedandreverb.studio**
2. Salvar o arquivo de áudio (MP3/WAV) na pasta `/inbox`
3. Abrir a interface: `python gui.py`

### Etapa Automatizada (via GUI web)

```
inbox/ (arquivo selecionado na fila)
  │
  ├─[1] metadata_generator  → título, descrição, tags  (Ollama local)
  │      └─ edição manual do título na interface
  │
  ├─[2] image_generator     → imagem anime/dark 16:9   (Leonardo.ai API)
  │      └─ REVIEW DA IMAGEM
  │           ├─ Aprovar     → segue para o vídeo
  │           ├─ Nova Imagem → gera outra (áudio preservado)
  │           └─ Descartar   → áudio volta ao /inbox
  │
  ├─[3] ken_burns           → vídeo animado 1920x1080  (FFmpeg)
  ├─[4] FFmpeg              → combinar áudio + vídeo
  │
  └─ review/  ← abrir /review para assistir
       ├─ Publicar  → YouTube Data API v3
       └─ Descartar → rejected/ + áudio volta ao /inbox
```

> **Regra:** o áudio só é removido permanentemente do `/inbox` quando publicado com aprovação. Em qualquer rejeição ou erro, o arquivo retorna ao `/inbox`.

---

## 3. Interface Gráfica (GUI Web)

A interface roda localmente via **FastAPI + WebSocket + Tailwind CSS**.
Ao iniciar, abre automaticamente em `http://localhost:8000`.

```powershell
python gui.py
```

### Painéis

| Painel | Conteúdo |
|---|---|
| **Esquerda** | Queue Management — fila do inbox (clicável), botão de adicionar arquivo, Real-Time Log |
| **Centro** | Active Workspace — edição de metadados, review de imagem, preview de vídeo |
| **Direita** | Pipeline Monitoring — status das 4 etapas, histórico Published/Rejected |

### Protocolo WebSocket

**Servidor → Cliente:**

| Mensagem | Campos | Descrição |
|---|---|---|
| `log` | `msg` | Linha de log em tempo real |
| `step` | `index` (0-3), `status` | Atualiza badge de etapa |
| `meta_ready` | `titulo`, `descricao`, `tags` | Metadados prontos para edição |
| `img_ready` | `personagem`, `cenario`, `estilo` | Imagem gerada, aguarda decisão |
| `vid_ready` | `path`, `name` | Vídeo pronto, aguarda decisão |
| `done_ok` | `url` | Pipeline concluído com sucesso |
| `done_ko` | `msg` | Erro ou rejeição pelo usuário |
| `queue_update` | `items` | Inbox atualizado |
| `history_update` | `published`, `rejected` | Histórico atualizado |

**Cliente → Servidor:**

| Mensagem | Campos | Descrição |
|---|---|---|
| `start` | `index` | Inicia pipeline no arquivo selecionado |
| `confirm_titulo` | `titulo` | Confirma/substitui o título gerado |
| `img_decision` | `decision` (`s`/`n`/`d`) | Aprovar / Nova / Descartar imagem |
| `vid_decision` | `decision` (`s`/`n`) | Publicar / Rejeitar vídeo |

### Rotas HTTP

| Rota | Método | Descrição |
|---|---|---|
| `/` | GET | Serve a interface HTML |
| `/api/queue` | GET | Lista arquivos no inbox |
| `/api/history` | GET | Published + Rejected |
| `/img/current` | GET | Imagem gerada atual (cache-buster via `?t=`) |
| `/api/open-review` | POST | Abre pasta `/review` no Explorer |
| `/api/open-video` | POST | Abre vídeo específico no player padrão |
| `/api/pick-file` | POST | Dialog nativo (PowerShell) para adicionar áudio ao inbox |
| `/api/shutdown` | POST | Encerra o servidor |

---

## 4. Instalação

### Dependências Python

```powershell
pip install fastapi "uvicorn[standard]" requests \
    google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### Ferramentas externas

- **FFmpeg** — baixar em ffmpeg.org e adicionar ao PATH
- **Ollama** — instalar e baixar o modelo: `ollama pull qwen3:1.7b`

### Arquivo `.env`

```env
LEONARDO_API_KEY=sua_chave_aqui
YOUTUBE_CLIENT_SECRET_PATH=client_secret.json
```

> A chave do Leonardo é obtida em **app.leonardo.ai → API Access → Create New Key**
> O `client_secret.json` é obtido no **Google Cloud Console → Credenciais → OAuth 2.0**

---

## 5. Estrutura de Pastas

```
slowed-reverb-channel/
│
├── README.md               ← documentação do projeto
├── pyproject.toml          ← configuração do pytest
├── .env                    ← chaves de API (nunca commitar)
├── client_secret.json      ← credencial OAuth YouTube (nunca commitar)
├── youtube_token.json      ← token OAuth gerado na 1ª execução (nunca commitar)
│
├── gui.py                  ← interface web (FastAPI + WebSocket + Tailwind)
├── pipeline.py             ← orquestração CLI (alternativa sem GUI)
├── image_generator.py      ← geração de imagem via Leonardo.ai
├── ken_burns.py            ← efeitos de vídeo via FFmpeg
├── metadata_generator.py   ← geração de metadados via Ollama
├── youtube_uploader.py     ← upload via YouTube Data API v3
│
├── tests/                  ← suite de testes (pytest)
│   ├── conftest.py
│   ├── test_ken_burns.py
│   ├── test_metadata_generator.py
│   ├── test_image_generator.py
│   ├── test_youtube_uploader.py
│   ├── test_pipeline_worker.py
│   └── test_gui_api.py
│
├── inbox/                  ← colocar os MP3/WAV aqui (fila de entrada)
├── processing/             ← arquivos sendo processados (temporário)
├── review/                 ← vídeo pronto aguardando aprovação
├── rejected/               ← vídeos descartados
├── logs/                   ← logs de publicações
└── assets/
    └── images/             ← cópia de todas as imagens geradas (histórico)
```

---

## 6. Testes

```powershell
# Executar todos os testes
python -m pytest

# Com cobertura
pip install pytest-cov
python -m pytest --cov --cov-report=term-missing
```

**144 testes** cobrindo todos os módulos:

| Arquivo | Módulo | Testes |
|---|---|---|
| `test_ken_burns.py` | Efeitos de vídeo | Funções puras, EFEITOS_POR_NOME, subprocess mockado |
| `test_metadata_generator.py` | Geração de metadados | Limpeza de nomes, parsing JSON, fallbacks, Ollama mock |
| `test_image_generator.py` | Geração de imagem | Banco de prompts, API mock, timeout, chave ausente |
| `test_youtube_uploader.py` | Upload YouTube | Credenciais, FileNotFound, upload mock, retry |
| `test_pipeline_worker.py` | Worker do pipeline | Events, cancel, fluxo aprovação/descarte/cancelamento |
| `test_gui_api.py` | Rotas HTTP da GUI | Todos os endpoints, helpers, isolamento por tmp_path |

---

## 7. Módulos

### `gui.py` — Interface web

Serve em `http://localhost:8000`, abre o browser automaticamente.
Usa `threading.Event` para sincronizar decisões do usuário com o worker em background.
Thread-safety garantida via `asyncio.run_coroutine_threadsafe` no `ConnectionManager`.

---

### `image_generator.py` — Geração de imagem

**Modelo:** Phoenix 1.0 Fast (`de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3`)
**Formato:** 1472×832 (16:9)

**Banco de variações — 2.958.000 combinações:**

| Categoria | Qtd |
|---|---|
| Personagens | 34 |
| Poses / ângulos | 29 |
| Cenários | 36 |
| Estilos visuais | 10 |
| Tons emocionais | 10 |

Cópia automática em `assets/images/gerada_[timestamp].png` após cada geração.

---

### `ken_burns.py` — Efeito de vídeo

Gera MP4 1920×1080 @ 60fps a partir de imagem estática via FFmpeg zoompan.

**9 efeitos:**

| Efeito | Ciclo | Descrição |
|---|---|---|
| `zoom_in` | único | Zoom lento para fora |
| `zoom_out` | único | Zoom abre — loop perfeito |
| `pan_esquerda` | único | Pan direita→esquerda |
| `pan_direita` | único | Pan esquerda→direita |
| `diagonal_melancolico` | único | Pan diagonal suave |
| `pulsacao` | 6s | Zoom 1.0→1.12→1.0 via seno |
| `pulsacao_pan` | zoom 2s + pan 4s | Pulsação + oscilação lateral |
| `zoom_snap` | 10s | Heartbeat: cresce e snapa |
| `oscilacao` | zoom 6s + pan 10s | Zoom + deriva lateral hipnótica |

**RGB Split** por padrão: aberração cromática a cada 8s por 0.25s.

---

### `metadata_generator.py` — Geração de metadados

Usa **Ollama local** (`qwen3:1.7b`) — sem custo de API.

**Formato do título:**
```
｜ Artista - Nome da Música ｜ slowed + reverb - vers OvxrNight
```

Saída: `{ titulo, descricao, tags }` pronto para o YouTube.

---

### `youtube_uploader.py` — Publicação

**YouTube Data API v3** com OAuth 2.0.
Token salvo em `youtube_token.json` — autorização apenas na 1ª execução.
Upload resumível em chunks de 8 MB com retry automático em erros 5xx (máx. 5 tentativas).
Custo: ~1.600 unidades por upload (cota: 10.000/dia).

**Configuração (única vez):**
1. **console.cloud.google.com** → criar projeto → ativar YouTube Data API v3
2. Criar credencial **OAuth 2.0 → Aplicativo para computador**
3. Baixar JSON → salvar como `client_secret.json`
4. Adicionar e-mail como **usuário de teste** na tela de consentimento

---

## 8. Contexto do Canal

- **Nome:** OvxrNight
- **Tema:** músicas slowed & reverb com estética anime dark fantasy
- **Tom visual:** melancolia + poder épico
- **Personagens:** equilibrado entre femininas (beleza misteriosa, serena) e masculinos (guerreiros, magos, solitários)

---

## 9. Status dos Módulos

- [x] `gui.py` — interface web completa (FastAPI + WebSocket + Tailwind)
- [x] `ken_burns.py` — completo e testado
- [x] `image_generator.py` — completo e testado
- [x] `metadata_generator.py` — completo e testado
- [x] `youtube_uploader.py` — completo e testado
- [x] `pipeline.py` — completo (alternativa CLI)
- [x] `tests/` — 144 testes, 100% passando
