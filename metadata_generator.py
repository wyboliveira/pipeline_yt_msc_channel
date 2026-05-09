"""
metadata_generator.py
Módulo de geração de metadados para o pipeline slowed-reverb-channel.
Gera título, descrição e tags a partir do nome do arquivo de áudio.

Uso direto:
    python metadata_generator.py bohemian_rhapsody.mp3
    python metadata_generator.py "D:/inbox/my song.wav"
"""

import sys
import random
import re
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

NOME_CANAL   = "OvxrNight"

# Pool de tags YouTube (plain text, pode ter espaço)
TAG_POOL = [
    "slowed reverb", "slowed songs", "reverb music", "slowed and reverbed",
    "dark music", "dark aesthetic", "dark anime", "dark vibes", "dark chill",
    "dark ambient", "dark house", "dark beats",
    "chill music", "chill vibes", "chill house", "chill girl",
    "anime music", "anime girl", "anime aesthetic", "anime art",
    "lofi music", "lo fi", "lofi chill", "lofi beats",
    "ambient music", "atmospheric music", "ambient chill",
    "night music", "night vibes", "nocturnal music",
    "sad music", "emotional music", "melancholic music", "introspective music",
    "relaxing music", "soothing music", "dreamy music", "ethereal music",
    "moody music", "moody vibes", "moody aesthetic",
    "deep house", "house music", "underground music",
    "bass music", "bass vibes",
    "slowedreverb", "animegirl", "darkchill", "darkmusic", "chillmusic",
    "lofimusic", "darkambient", "chillvibes", "animeaesthetic",
    "housemusic", "deephouse", "darkgirl", "gloomypop",
]

# Pool de hashtags para a descrição (sem espaços, formato #tag)
HASHTAG_POOL = [
    "#slowedreverb", "#slowed", "#reverb", "#sloweddown",
    "#anime", "#animegirl", "#animegirls", "#animeaesthetic", "#animeart",
    "#darkmusic", "#darkaesthetic", "#darkchill", "#darkambient", "#darkvibes",
    "#darkgirl", "#darkanime", "#darkhouse",
    "#chillmusic", "#chillvibes", "#chillgirl", "#chillhouse",
    "#lofi", "#lofimusic", "#lofichill", "#lofibeats",
    "#ambient", "#ambientmusic", "#atmospheric",
    "#housemusic", "#deephouse", "#darkbeats",
    "#nightmusic", "#nightvibes", "#nocturnal",
    "#sadmusic", "#emotional", "#melancholic", "#introspective",
    "#relaxing", "#soothing", "#dreamy", "#ethereal",
    "#moody", "#moodmusic", "#moodygirl",
    "#bass", "#underground", "#gothic", "#cinematic",
    "#animegirl", "#darkgirl", "#aestheticgirl",
]

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
    """
    nome_musica = _limpar_nome_arquivo(nome_arquivo)

    print(f"[metadata] Gerando metadados para: {nome_musica}")

    titulo   = f"｜ {nome_musica} ｜ slowed + reverb - vers {NOME_CANAL}"
    creditos = f"🎵 {nome_musica} — todos os direitos reservados aos respectivos criadores."
    tags     = random.sample(TAG_POOL, 10)
    hashtags = " ".join(random.sample(HASHTAG_POOL, 7))

    descricao = DESCRICAO_TEMPLATE.format(
        titulo=titulo,
        creditos=creditos,
        hashtags=hashtags,
    )

    resultado = {
        "titulo":      titulo,
        "nome_musica": nome_musica,
        "descricao":   descricao,
        "tags":        tags,
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
