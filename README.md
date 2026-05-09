# OvxrNight — slowed-reverb-channel

Canal automatizado no YouTube com foco em músicas **slowed & reverb**.
O fluxo combina uma etapa manual (escolha e processamento da música) com um pipeline Python que gera imagem, anima, combina com áudio e publica no YouTube.

**Canal:** [OvxrNight](https://www.youtube.com/@OvxrNight)

---

## Visão Geral

A interface web roda localmente e guia cada etapa com aprovação manual nas decisões críticas — imagem gerada e vídeo final. Tudo que pode ser automatizado, é. Tudo que exige curadoria, para e espera.

```
Música (manual)  →  Metadados (local)  →  Imagem (Leonardo.ai)
                                              ↓ aprovação
                                         Vídeo (FFmpeg Ken Burns)
                                              ↓ aprovação
                                         YouTube (Data API v3)
```

---

## Instalação

### 1. Dependências Python

```bash
pip install fastapi "uvicorn[standard]" requests \
    google-api-python-client google-auth-oauthlib google-auth-httplib2
```

### 2. Ferramentas externas

- **FFmpeg** — [ffmpeg.org/download.html](https://ffmpeg.org/download.html) → adicionar ao PATH

### 3. Variáveis de ambiente

Criar `.env` na raiz do projeto:

```env
LEONARDO_API_KEY=sua_chave_aqui
```

> Chave obtida em **app.leonardo.ai → API Access → Create New Key**

### 4. Credenciais do YouTube (uma vez)

1. [console.cloud.google.com](https://console.cloud.google.com) → criar projeto → ativar **YouTube Data API v3**
2. Credenciais → **OAuth 2.0 → Aplicativo para computador** → baixar JSON
3. Salvar como `client_secret.json` na raiz do projeto
4. Na tela de consentimento OAuth, adicionar seu e-mail como **usuário de teste**

Na primeira execução, uma janela de autorização abrirá no browser. O token é salvo em `youtube_token.json` — as execuções seguintes não precisam de nova autorização.

---

## Como usar

### Etapa manual

1. Aplicar efeito slowed+reverb na música em [slowedandreverb.studio](https://slowedandreverb.studio)
2. Salvar o arquivo MP3/WAV na pasta `inbox/`

### Etapa automatizada

```bash
python gui.py
```

A interface abre automaticamente em `http://localhost:8000`.

1. Selecionar o arquivo na fila e clicar em **Start**
2. Revisar e ajustar o título gerado → **Confirmar**
3. Avaliar a imagem gerada → **Aprovar** / **Nova imagem** / **📂 Escolher** (abre `assets/images/` para usar imagem própria)
4. Assistir o vídeo → **Publicar** / **Rejeitar**

> **Regra de segurança:** o áudio só é removido do `inbox/` quando publicado com sucesso. Em qualquer rejeição ou erro, o arquivo retorna automaticamente à fila.

---

## Estrutura de Pastas

```
slowed-reverb-channel/
│
├── gui.py                  ← interface web (FastAPI + WebSocket + Tailwind)
├── pipeline.py             ← worker do pipeline (chamado pela GUI)
├── image_generator.py      ← geração de imagem via Leonardo.ai
├── ken_burns.py            ← efeito de vídeo via FFmpeg
├── metadata_generator.py   ← geração de metadados (local, sem IA)
├── youtube_uploader.py     ← upload via YouTube Data API v3
│
├── tests/                  ← suite de testes (pytest)
├── pyproject.toml          ← configuração do pytest
│
├── inbox/                  ← colocar os MP3/WAV aqui (fila de entrada)
├── processing/             ← em processamento (temporário)
├── review/                 ← vídeo aguardando aprovação
├── rejected/               ← vídeos descartados
├── logs/                   ← logs de publicações
└── assets/images/          ← histórico de todas as imagens geradas
```

Arquivos **nunca commitar:** `.env`, `client_secret.json`, `youtube_token.json`

---

## Módulos

### `image_generator.py`
Gera imagens 1472×832 (16:9) via **Leonardo.ai Phoenix 1.0 Fast**.
Banco de variações com personagens, cenários, estilos e tons emocionais — estética anime dark fantasy.
Cópia automática salva em `assets/images/` após cada geração.

### `ken_burns.py`
Produz MP4 1920×1080 @ 60fps a partir de imagem estática usando **FFmpeg zoompan**.
9 efeitos disponíveis: zoom in/out, pans, pulsação, oscilação e mais.
RGB Split (aberração cromática) aplicado periodicamente por padrão.

### `metadata_generator.py`
Gera título, descrição e tags **localmente, sem IA e sem custo de API**.
Formato do título: `｜ Artista - Música ｜ slowed + reverb - vers OvxrNight`

Tags e hashtags são **embaralhadas a cada geração** a partir de dois pools curados (58 tags YouTube + 51 hashtags de descrição), garantindo variedade entre vídeos sem repetição de combinações.

**Convenção de nome de arquivo:** salvar os áudios no formato `Artista - Nome da Música (qualidade)-slowedandreverbstudio.mp3`.
O separador ` - ` entre artista e música é preservado no título. Tags como `(128 kbps)`, `(Official Video)`, `(Youtube)` são removidas automaticamente.

### `youtube_uploader.py`
Upload via **YouTube Data API v3** com OAuth 2.0.
Upload resumível em chunks de 8 MB com retry automático em erros 5xx (máx. 5 tentativas).
Cota: ~1.600 unidades por upload (limite diário: 10.000 unidades).

---

## Testes

```bash
python -m pytest                          # todos os testes
python -m pytest --cov --cov-report=term-missing  # com cobertura
```

148 testes cobrindo todos os módulos — sem chamadas reais a APIs externas.

---

## Links

| Serviço | Link |
|---|---|
| Leonardo.ai Console | https://app.leonardo.ai |
| Google Cloud Console | https://console.cloud.google.com |
| YouTube Studio | https://studio.youtube.com |
| slowed+reverb studio | https://slowedandreverb.studio |
