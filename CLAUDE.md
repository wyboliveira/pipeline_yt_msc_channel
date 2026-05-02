# CLAUDE.md — Mapa de referência para o assistente AI

## Stack

- **Backend:** FastAPI + Uvicorn, Python 3.11+
- **Frontend:** HTML inline em `gui.py` (sem arquivos estáticos externos), Tailwind CSS via CDN
- **AI local:** Ollama (`qwen3:1.7b`)
- **APIs externas:** Leonardo.ai (imagem), YouTube Data API v3 (upload OAuth 2.0)
- **Vídeo:** FFmpeg (deve estar no PATH)
- **Testes:** pytest, sem banco real, sem chamadas externas reais (tudo mockado)

---

## Mapa de Arquivos

| Arquivo | Responsabilidade |
|---|---|
| `gui.py` | Servidor FastAPI + template HTML completo inline + WebSocket + rotas HTTP |
| `pipeline.py` | Worker do pipeline (chamado pela GUI em thread separada) |
| `image_generator.py` | Geração de imagem via Leonardo.ai API |
| `ken_burns.py` | Efeito de vídeo via FFmpeg zoompan |
| `metadata_generator.py` | Geração de título/descrição/tags via Ollama |
| `youtube_uploader.py` | Upload para YouTube Data API v3 com OAuth 2.0 |
| `tests/` | Suite pytest — um arquivo por módulo |
| `pyproject.toml` | Configuração do pytest |

### Pastas de dados (não commitar conteúdo)

| Pasta | Uso |
|---|---|
| `inbox/` | Fila de entrada — MP3/WAV aguardando processamento |
| `processing/` | Arquivo sendo processado no momento (temporário) |
| `review/` | Vídeo pronto aguardando decisão do usuário |
| `rejected/` | Vídeos descartados (áudio retorna ao inbox) |
| `assets/images/` | Histórico de todas as imagens geradas |
| `logs/` | Logs de publicações no YouTube |

### Arquivos sensíveis (nunca commitar)

- `.env` — `LEONARDO_API_KEY`
- `client_secret.json` — OAuth 2.0 do Google
- `youtube_token.json` — token gerado na 1ª autorização

---

## Padrões de Código

### Sincronização GUI ↔ Pipeline

Decisões do usuário (aprovar imagem, publicar vídeo) usam `threading.Event`:

```python
# pipeline.py define os eventos
img_event = threading.Event()
img_decision = {"value": None}

# gui.py seta o valor e dispara
img_decision["value"] = "s"
img_event.set()

# pipeline.py aguarda bloqueando a thread do worker
img_event.wait()
decision = img_decision["value"]
```

Nunca usar `asyncio.sleep` para polling de decisão — sempre `Event.wait()`.

### WebSocket — envio thread-safe

O `ConnectionManager` em `gui.py` usa `asyncio.run_coroutine_threadsafe` para enviar mensagens da thread do worker para o loop async do FastAPI:

```python
asyncio.run_coroutine_threadsafe(manager.broadcast(msg), loop)
```

Nunca chamar `await manager.broadcast()` diretamente de dentro de threads síncronas.

### HTML/CSS

O template HTML inteiro vive como string raw em `HTML_TEMPLATE` em `gui.py`.
Não criar arquivos `.html` separados — manter tudo inline.
Paleta de cores definida no `tailwind.config`: `app`, `panel`, `card`, `inp`, `rowsel`, `brd`.

---

## Protocolo WebSocket

### Servidor → Cliente

| Tipo | Campos extras | Momento |
|---|---|---|
| `log` | `msg` | Linha de log em tempo real |
| `step` | `index` (0–3), `status` | Atualiza badge de etapa |
| `meta_ready` | `titulo`, `descricao`, `tags` | Metadados prontos para edição |
| `img_ready` | `personagem`, `cenario`, `estilo` | Imagem gerada — aguarda decisão |
| `vid_ready` | `path`, `name` | Vídeo pronto — aguarda decisão |
| `done_ok` | `url` | Pipeline concluído com sucesso |
| `done_ko` | `msg` | Erro ou rejeição |
| `queue_update` | `items` | Inbox atualizado |
| `history_update` | `published`, `rejected` | Histórico atualizado |

### Cliente → Servidor

| Tipo | Campos extras | Ação |
|---|---|---|
| `start` | `index` | Inicia pipeline no arquivo selecionado |
| `confirm_titulo` | `titulo` | Confirma/edita o título gerado |
| `img_decision` | `decision` (`s`/`n`) | Aprovar / Nova imagem |
| `vid_decision` | `decision` (`s`/`n`) | Publicar / Rejeitar vídeo |

---

## Rotas HTTP

| Rota | Método | Descrição |
|---|---|---|
| `/` | GET | Serve o `HTML_TEMPLATE` |
| `/api/queue` | GET | Lista arquivos no inbox |
| `/api/history` | GET | Published + Rejected |
| `/img/current` | GET | Imagem atual (`?t=` como cache-buster) |
| `/api/open-review` | POST | Abre pasta `/review` no Explorer |
| `/api/open-video` | POST | Abre vídeo específico no player padrão |
| `/api/pick-file` | POST | Dialog nativo via PowerShell para adicionar áudio |
| `/api/pick-image` | POST | Dialog nativo para escolher imagem — abre em `assets/images/`, copia para `processing/imagem_gerada.png` |
| `/api/shutdown` | POST | Encerra o servidor |

---

## Invariantes importantes

- O áudio só é removido do `inbox/` quando publicado com sucesso. Qualquer erro, rejeição ou cancelamento **retorna o arquivo ao inbox**.
- `processing/` deve ficar vazio ao final de qualquer fluxo (inclusive erros).
- O pipeline roda em thread separada — nunca bloquear o loop asyncio do FastAPI.
- Testes usam `tmp_path` do pytest para isolamento total — nunca ler/escrever nas pastas reais.

---

## Testes

```bash
python -m pytest          # todos os testes
python -m pytest -x       # para no primeiro erro
python -m pytest --cov    # com cobertura (requer pytest-cov)
```

Um arquivo de teste por módulo. Mocks via `unittest.mock.patch`. Sem chamadas reais a Ollama, Leonardo ou YouTube.
