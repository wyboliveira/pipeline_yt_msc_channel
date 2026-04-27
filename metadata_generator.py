"""
metadata_generator.py
Módulo de geração de metadados para o pipeline slowed-reverb-channel.
Usa o Ollama local (qwen3:4b) para gerar título, descrição e tags
a partir do nome do arquivo de áudio. Sem custos de API.

Requisito:
    Ollama rodando localmente com o modelo qwen3:4b instalado.
    Instalar modelo: ollama pull qwen3:4b

Uso direto:
    python metadata_generator.py bohemian_rhapsody.mp3
    python metadata_generator.py "D:/inbox/my song.wav"
"""

import sys
import json
import re
import requests
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

OLLAMA_URL   = "http://localhost:11434/api/generate"
MODEL        = "qwen3:1.7b"
NOME_CANAL   = "OvxrNight"

DESCRICAO_TEMPLATE = """\
{titulo}

{creditos}

━━━━━━━━━━━━━━━━━━━━━━━━
🎵 Gostou? Deixa o like e se inscreve no canal.
🔔 Ativa o sino pra não perder os próximos lançamentos.
━━━━━━━━━━━━━━━━━━━━━━━━

{hashtags}
"""


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _checar_ollama() -> None:
    """Verifica se o Ollama está acessível antes de fazer a chamada."""
    try:
        resp = requests.get("http://localhost:11434", timeout=3)
        resp.raise_for_status()
    except Exception:
        raise RuntimeError(
            "Ollama não está acessível em http://localhost:11434\n"
            "Inicie o Ollama e tente novamente."
        )


def _limpar_nome_arquivo(nome_arquivo: str) -> str:
    """
    Extrai um nome de música legível a partir do nome do arquivo.
    Ex: 'Falxce - Space Dawn (128 kbps)-slowedandreverbstudio.mp3' → 'Falxce - Space Dawn'
         'bohemian_rhapsody.mp3'                                    → 'Bohemian Rhapsody'
    O separador ' - ' (com espaços) entre artista e música é preservado.
    """
    nome = Path(nome_arquivo).stem

    # Remove sufixos de slowed/reverb
    sufixos = [
        r"\s*[\(\[]\s*slowed.*?[\)\]]",
        r"\s*[\(\[]\s*reverb.*?[\)\]]",
        r"\s*[\(\[]\s*slow.*?[\)\]]",
        r"\s*-\s*slowed.*$",
        r"\s*-\s*reverb.*$",
    ]
    for sufixo in sufixos:
        nome = re.sub(sufixo, "", nome, flags=re.IGNORECASE)

    # Remove tags em parênteses/colchetes: qualidade de áudio e labels do YouTube
    tags_parenteses = [
        r"\s*[\(\[]\s*\d+\s*kbps\s*[\)\]]",
        r"\s*[\(\[]\s*official\s*(video|audio|mv|music\s*video)?\s*[\)\]]",
        r"\s*[\(\[]\s*youtube\s*[\)\]]",
        r"\s*[\(\[]\s*lyric[s]?\s*[\)\]]",
        r"\s*[\(\[]\s*music\s*video\s*[\)\]]",
        r"\s*[\(\[]\s*visuali[zs]er\s*[\)\]]",
        r"\s*[\(\[]\s*(hd|hq|4k|1080p|720p)\s*[\)\]]",
        r"\s*[\(\[]\s*audio\s*[\)\]]",
        r"\s*[\(\[]\s*full\s*(album|version)?\s*[\)\]]",
        r"\s*[\(\[]\s*ft\.?.*?[\)\]]",
    ]
    for tag in tags_parenteses:
        nome = re.sub(tag, "", nome, flags=re.IGNORECASE)

    # Underscores → espaços (preserva hifens)
    nome = nome.replace("_", " ")

    # Hifens sem espaço ao redor → espaços (separadores de palavra em nomes de arquivo)
    # Preserva ' - ' (espaço-hífen-espaço) como separador artista/música
    nome = re.sub(r"(?<!\s)-(?!\s)", " ", nome)

    # Normaliza espaços e title-case preservando o separador ' - '
    nome = re.sub(r"\s+", " ", nome).strip()
    partes = nome.split(" - ", 1)
    nome = " - ".join(p.strip().title() for p in partes)

    return nome


def _gerar_com_ollama(nome_musica: str) -> dict:
    """
    Chama o Ollama local e retorna dict com titulo, creditos, hashtags, tags.
    """
    prompt = f"""Você é o assistente de um canal do YouTube com estética anime sombria e melancólica.
O canal publica versões "slowed + reverb" de músicas. O tom é épico, melancólico e introspectivo.

Gere os metadados para o vídeo da música: "{nome_musica}"

Retorne SOMENTE este JSON, sem nenhum texto antes ou depois:
{{
  "creditos": "🎵 {nome_musica} — todos os direitos reservados aos respectivos criadores.",
  "hashtags": "#slowedreverb #anime #darkmusic #melancolico #sombrio",
  "tags": ["slowed reverb", "anime music", "dark aesthetic", "dark music", "slowed songs", "reverb music", "emotional music", "lofi", "chill music", "night music"]
}}

IMPORTANTE: o campo "tags" DEVE ser uma lista JSON com exatamente 10 strings genéricas do canal. NÃO inclua o nome da música nas tags. Responda APENAS com o JSON."""

    # stream=True mantém a conexão viva enquanto o modelo gera tokens,
    # evitando ReadTimeout em modelos lentos ou com raciocínio longo (<think>).
    resp = requests.post(
        OLLAMA_URL,
        json={"model": MODEL, "prompt": prompt, "stream": True},
        stream=True,
        timeout=(10, 300),   # (connect, read) — 5 min para geração
    )

    if resp.status_code != 200:
        raise RuntimeError(f"Ollama retornou HTTP {resp.status_code}:\n{resp.text}")

    partes = []
    for linha in resp.iter_lines():
        if not linha:
            continue
        try:
            chunk = json.loads(linha)
        except json.JSONDecodeError:
            continue
        partes.append(chunk.get("response", ""))
        if chunk.get("done"):
            break

    resposta = "".join(partes).strip()

    # Remove bloco de raciocínio <think>...</think> do qwen3
    resposta = re.sub(r"<think>.*?</think>", "", resposta, flags=re.DOTALL).strip()
    resposta = re.sub(r"^```(?:json)?\s*", "", resposta)
    resposta = re.sub(r"\s*```$", "", resposta)

    try:
        dados = json.loads(resposta)
    except json.JSONDecodeError as e:
        raise RuntimeError(
            f"Resposta do Ollama não é JSON válido:\n{resposta}\n\nErro: {e}"
        )

    # Normaliza hashtags: aceita lista ou string
    if isinstance(dados.get("hashtags"), list):
        dados["hashtags"] = " ".join(dados["hashtags"])

    # Fallback para tags ausentes ou no formato errado
    if not isinstance(dados.get("tags"), list):
        dados["tags"] = [
            "slowed reverb", "anime music", "dark aesthetic",
            "dark music", "slowed songs", "reverb music",
            "emotional music", "lofi", "chill music", "night music",
        ]

    # Garante campos obrigatórios
    for chave in ("creditos", "hashtags"):
        if chave not in dados:
            raise RuntimeError(f"Campo '{chave}' ausente na resposta:\n{dados}")

    return dados


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def gerar_metadados(nome_arquivo: str) -> dict:
    """
    Gera título, descrição e tags para um arquivo de áudio.

    Args:
        nome_arquivo: Nome ou caminho do arquivo de áudio
                      (ex: 'bohemian_rhapsody.mp3').

    Returns:
        dict com as chaves:
            titulo    — título formatado para o YouTube
            descricao — descrição completa com créditos, CTA e hashtags
            tags      — lista de strings para o YouTube

    Raises:
        EnvironmentError: API key não configurada.
        RuntimeError:     Falha na chamada à API ou resposta inválida.
    """
    _checar_ollama()
    nome_musica = _limpar_nome_arquivo(nome_arquivo)

    print(f"[metadata] Gerando metadados para: {nome_musica}")
    dados = _gerar_com_ollama(nome_musica)

    # Título montado diretamente — não depende do modelo para isso
    dados["titulo"] = f"｜ {nome_musica} ｜ slowed + reverb - vers {NOME_CANAL}"

    descricao = DESCRICAO_TEMPLATE.format(
        titulo=dados["titulo"],
        creditos=dados["creditos"],
        hashtags=dados["hashtags"],
    )

    resultado = {
        "titulo":      dados["titulo"],
        "nome_musica": nome_musica,
        "descricao":   descricao,
        "tags":        dados["tags"],
    }

    print(f"[metadata] Título     : {resultado['titulo']}")
    print(f"[metadata] Tags ({len(resultado['tags'])})  : {', '.join(resultado['tags'][:5])}...")

    return resultado


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    if len(sys.argv) < 2:
        print("Uso: python metadata_generator.py <arquivo_audio>")
        print()
        print("Exemplos:")
        print("  python metadata_generator.py bohemian_rhapsody.mp3")
        print('  python metadata_generator.py "D:/inbox/my song.wav"')
        sys.exit(0)

    try:
        meta = gerar_metadados(sys.argv[1])

        print("\n" + "=" * 60)
        print("TÍTULO:")
        print(f"  {meta['titulo']}")
        print()
        print("DESCRIÇÃO:")
        print(meta['descricao'])
        print("TAGS:")
        print("  " + ", ".join(meta["tags"]))
    except Exception as e:
        print(f"\n[ERRO] {e}", file=sys.stderr)
        sys.exit(1)
