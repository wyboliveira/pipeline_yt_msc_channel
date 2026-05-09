"""
image_generator.py
Módulo de geração de imagem anime/dark via Leonardo.ai API.
Parte do pipeline slowed-reverb-channel.

Fluxo:
    1. Monta um prompt aleatório com tema anime sombrio/épico
    2. Envia para a API do Leonardo (POST /generations)
    3. Faz polling até o status ser COMPLETE
    4. Baixa a imagem gerada e salva localmente

Configuração:
    Crie um arquivo .env na raiz do projeto com:
        LEONARDO_API_KEY=sua_chave_aqui

    Ou exporte a variável de ambiente antes de rodar:
        set LEONARDO_API_KEY=sua_chave_aqui   (Windows CMD)
        $env:LEONARDO_API_KEY="sua_chave"     (PowerShell)

Uso direto:
    python image_generator.py [caminho_saida.png]
"""

import os
import sys
import time
import random
import shutil
import requests
from datetime import datetime
from pathlib import Path


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

API_BASE   = "https://cloud.leonardo.ai/api/rest/v1"
MODEL_ID   = "de7d3faf-762f-48e0-b3b7-9d0ac3a3fcf3"  # Phoenix 1.0 Fast
IMG_WIDTH  = 1472
IMG_HEIGHT = 832
POLL_INTERVAL  = 3   # segundos entre cada checagem de status
POLL_TIMEOUT   = 120 # segundos máximos de espera


# ---------------------------------------------------------------------------
# Banco de variações de prompt
# Cada categoria tem várias opções — combinadas aleatoriamente a cada geração
# ---------------------------------------------------------------------------

PERSONAGENS = [
    # — Guerreiras e combatentes (femininas) —
    "a lone anime warrior girl with silver hair and red eyes",
    "a battle-worn anime knight with cracked armor and glowing wounds",
    "a dark-armored anime valkyrie with broken wings, kneeling in defeat",
    "a fierce anime huntress with amber eyes and a black longbow, shrouded in mist",

    # — Místicas e sobrenaturais (femininas) —
    "an ethereal anime priestess with white robes and closed eyes",
    "a cursed anime oracle wrapped in dark silk, her eyes replaced by glowing runes",
    "an ancient anime sorceress with pretty color hair floating in a void, surrounded by orbiting dark crystals",
    "a pale anime shrine maiden with hollow eyes, holding a lantern that casts no light",

    # — Femininas: beleza misteriosa e serena —
    "a melancholic anime girl with long black hair sitting with her knees to her chest",
    "a serene anime girl with pale skin and violet eyes, floating underwater among black petals",
    "a graceful anime girl with waist-length blonde hair, standing barefoot in shallow dark water",
    "a quiet anime girl with closed eyes and flower petals tangled in her silver hair",
    "an elegant anime woman in a torn black dress, sitting still while ravens circle around her",
    "a dreamy anime girl with long silver lashes, face half-buried in a bouquet of dead roses",

    # — Femininas: sensualidade contida e pureza sombria —
    "a composed anime woman with deep red eyes and bare shoulders, staring into a dark mirror",
    "a mysterious anime femme with a translucent veil obscuring half her face, surrounded by misterious smoke",
    "a pure anime girl in a white burial gown walking through falling black ash, eyes cast downward",
    "an ethereal anime woman with luminous skin and black tears streaming down her face",
    "a lone anime girl with long dark hair covering one eye, holding a traditional mage object",

    # — Masculinos: guerreiros e combatentes —
    "a lone dark anime warrior in tattered black armor, sword resting on his shoulder, walking through ruins",
    "a battle-scarred anime warrior with long dark hair, wearing a torn travelling cloak, staring at the horizon",
    "an exhausted anime soldier with a sword planted in the ground, leaning on it with eyes closed",
    "a stoic anime knight without armor, wrapped in a weathered cloak, one hand resting on a worn sword hilt",
    "a grizzled anime warrior sitting on crumbling stone steps, sharpening a blade with a distant expression",
    "a silent anime ronin standing with his back to the viewer, watching an ember-lit sky",

    # — Masculinos: magos e místicos —
    "a solitary anime mage in long dark robes, surrounded by orbiting spell fragments and arcane dust",
    "a cloaked anime sorcerer with glowing violet runes floating around his outstretched hands",
    "a mysterious anime wanderer in heavy robes, leaning on a gnarled staff, face half-hidden by shadow",
    "a young anime mage with wild silver hair and faintly glowing eyes, surrounded by swirling dark energy",
    "a hooded anime figure with only glowing eyes visible, arcane symbols burning in the air around him",

    # — Masculinos: solitários e melancólicos —
    "a solitary androgynous anime figure with long pale hair, playing a silent violin in the rain",
    "a brooding anime young man with golden eyes, leaning against a cold stone wall in darkness",
    "a silent anime boy with red or black hair and dark feathered wings, sitting on a ruined altar",
    "a weary anime traveler sitting alone at a dying campfire, staring into the embers",
]

POSES_ANGULOS = [
    # — Retratos e close-ups —
    "close-up portrait, face partially in shadow",
    "extreme close-up on the eyes, tears reflecting light",
    "extreme close-up on the lips and chin, shadows cutting across the face",
    "close-up from below the chin, character looking up at falling rain",
    "side profile with eyes closed, hair floating gently sideways",
    "dutch angle close-up, character looking down at their hands",

    # — Poses sentadas e ao chão —
    "overhead shot, character sitting alone in a vast empty space",
    "low wide shot, character lying on a stone floor staring at the ceiling",
    "seated pose, character resting chin on knees, arms wrapped tightly around legs",
    "seated on the edge of a ledge, legs dangling over darkness, gazing into the distance",
    "character sitting cross-legged on the ground, head bowed, hands resting open on their knees",
    "character kneeling on the ground with one hand pressed to the earth, head down",

    # — Poses com gestual de braços e roupas esvoaçantes —
    "full body shot, both arms slightly outstretched, cloak or robes billowing dramatically in the wind",
    "wide shot, character with one arm raised, fingertips extended toward a distant light",
    "mid-shot, character caught mid-turn, hair and robes swirling dramatically around them",
    "three-quarter view, wind blowing hair and clothes violently across the frame",
    "full body, character walking forward slowly with head slightly bowed, cloak trailing behind",
    "wide shot, character standing with both arms extended outward, embracing the emptiness around them",

    # — Planos abertos e afastados —
    "wide shot, seen from behind, facing the horizon",
    "far wide shot, tiny figure alone in a massive desolate landscape",
    "wide shot, character reflected perfectly in a still black pool below",
    "low angle shot, looking up at the character against a stormy sky",
    "three-quarter back view, single light source casting a long shadow ahead",

    # — Outros —
    "mid-shot, dramatic side profile with light coming from one side",
    "over-the-shoulder shot, character gazing into a dark endless corridor",
    "mid-shot from behind, arms slightly open, surrounded by swirling dark mist",
    "waist-up shot, character standing in the rain, eyes open and expressionless",
    "intimate close-up of hands holding something fragile — a petal, a shard, a candle",
    "full body shot, character silhouetted against a cloudy stormy sky",
]

CENARIOS = [
    # — Arquitetura e ruínas —
    "in a ruined gothic cathedral with light streaming through broken stained glass",
    "standing on a crumbling stone bridge over a black abyss",
    "inside an abandoned clocktower with dust and broken gears",
    "in a throne room in ruins, with crows perched on the broken throne",
    "inside a dark library with floating candles and endless shelves of ancient books",
    "in a flooded underground chamber, still water reflecting a single torch",
    "inside a crumbling greenhouse overrun with dark vines and glowing spores",
    "in a collapsed opera house with torn velvet curtains and a broken chandelier",
    "inside a half-sunken stone temple, water on the floor reflecting golden candlelight",
    "at the foot of a massive ancient stone gate, crumbling and overgrown, leading into darkness",

    # — Tavernas e lugares habitados —
    "inside an old tavern at closing time, a single candle burning on an empty table, fog creeping in",
    "in a dimly lit inn corridor, flickering torch on the wall, shadows stretching long",

    # — Natureza sombria e fantástica —
    "in a forest of dead white trees under a sky of ash and falling embers",
    "at the shore of a dark ocean with bioluminescent waves",
    "in a field of black flowers under a sky full of dying stars",
    "in a flooded plain at dusk, dead trees emerging from dark still water as far as the eye can see",
    "beneath a colossal dead tree in a fog-covered meadow, its roots spreading across the ground",
    "on a spiraling stone staircase descending into infinite darkness",
    "inside a mirror maze where every reflection shows a different version of the character",
    "on a floating island fragment drifting through a starless void",

    # — Montanhas, campos e horizontes —
    "on a mountain ridge at dusk, wind blowing hard, distant peaks dissolving into clouds",
    "on a mountain peak above the clouds at twilight, looking down into an endless grey void",
    "in an open field under a sky of ten thousand stars, the only light coming from above",
    "in a vast open plain at night, tall grass moving in the wind, a dim fire dying nearby",
    "at the edge of a cliff overlooking a misty valley with distant warm lights far below",
    "on a rooftop at night, surrounded by a rainy neon-lit city far below",
    "at the center of a frozen lake under aurora borealis in shades of violet and black",
    "at the gate of a burned-down shrine, embers still drifting in the still air",
    "in the middle of a vast desert at night, surrounded by ancient stone monoliths",
    "at the edge of a cliff overlooking an endless sea of clouds lit by a dying red sun",
]

ESTILOS_VISUAIS = [
    "detailed anime art style, cinematic lighting, high contrast",
    "dark fantasy anime illustration, painterly style, muted colors",
    "moody anime art, cel-shaded, deep shadows, rim lighting",
    "epic anime style, dramatic atmosphere, glowing details",
    "melancholic anime aesthetic, soft focus, desaturated palette with single color accent",
    "ethereal anime style, translucent overlays, cool blue and violet tones, dreamy atmosphere",
    "noir anime aesthetic, heavy blacks, sharp contrast, single warm light source",
    "watercolor-inspired anime art, bleeding ink edges, washed-out palette, paper texture",
    "gothic anime illustration, intricate linework, candlelight palette, deep crimson accents",
    "hyper-detailed anime portrait style, subsurface skin lighting, sharp focus on face, blurred background",
]

TOM_ADICIONAL = [
    "feeling of solitude and quiet strength",
    "overwhelming sense of loss and longing",
    "silent resolve before an inevitable battle",
    "the weight of carrying a burden alone",
    "beauty found in destruction and decay",
    "the serenity of someone who has accepted the end",
    "an aching tenderness hidden beneath a cold exterior",
    "the stillness before everything falls apart",
    "a fragile purity that the darkness has not yet touched",
    "the quiet devastation of remembering something irretrievable",
]

SUFIXO_QUALIDADE = (
    "highly detailed face, perfect symmetric eyes, detailed iris, "
    "anatomically correct hands, well-defined fingers, sharp facial features, "
    "detailed lips and mouth, clean linework, masterpiece quality"
)

NEGATIVOS = (
    "blurry, low quality, deformed, extra limbs, bad anatomy, "
    "watermark, text, signature, nsfw, bright colors, happy, cheerful, "
    "childish, chibi, cartoon, western cartoon style, photorealistic, "
    "bad hands, extra fingers, missing fingers, fused fingers, mutated hands, "
    "deformed fingers, bad face, distorted face, asymmetric eyes, crossed eyes, extra fingers"
    "blurry eyes, poorly drawn face, ugly, disfigured, malformed limbs"
)


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _get_api_key() -> str:
    """Lê a API key do ambiente ou do arquivo .env na pasta atual."""
    key = os.environ.get("LEONARDO_API_KEY", "").strip()
    if key:
        return key

    # Tenta ler de um arquivo .env simples
    env_path = Path(".env")
    if env_path.exists():
        for linha in env_path.read_text().splitlines():
            if linha.startswith("LEONARDO_API_KEY="):
                key = linha.split("=", 1)[1].strip().strip('"').strip("'")
                if key:
                    return key

    raise EnvironmentError(
        "Chave de API do Leonardo não encontrada.\n"
        "Crie um arquivo .env na pasta do projeto com:\n"
        "    LEONARDO_API_KEY=sua_chave_aqui\n\n"
        "Ou defina a variável de ambiente:\n"
        "    PowerShell: $env:LEONARDO_API_KEY='sua_chave'\n"
        "    CMD:        set LEONARDO_API_KEY=sua_chave"
    )


def _montar_prompt() -> tuple[str, dict]:
    """
    Sorteia elementos de cada categoria e monta o prompt final.

    Returns:
        (prompt_texto, metadados_das_escolhas)
    """
    personagem   = random.choice(PERSONAGENS)
    pose_angulo  = random.choice(POSES_ANGULOS)
    cenario      = random.choice(CENARIOS)
    estilo       = random.choice(ESTILOS_VISUAIS)
    tom          = random.choice(TOM_ADICIONAL)

    prompt = (
        f"{personagem}, {pose_angulo}, {cenario}, "
        f"{estilo}, {tom}, {SUFIXO_QUALIDADE}"
    )

    meta = {
        "personagem":  personagem,
        "pose_angulo": pose_angulo,
        "cenario":     cenario,
        "estilo":      estilo,
        "tom":         tom,
    }

    return prompt, meta


def _solicitar_geracao(prompt: str, api_key: str) -> str:
    """
    Envia o prompt para a API e retorna o generation_id.

    Raises:
        RuntimeError: se a API retornar erro.
    """
    headers = {
        "accept": "application/json",
        "content-type": "application/json",
        "authorization": f"Bearer {api_key}",
    }

    payload = {
        "modelId":        MODEL_ID,
        "prompt":         prompt,
        "negative_prompt": NEGATIVOS,
        "width":          IMG_WIDTH,
        "height":         IMG_HEIGHT,
        "num_images":     1,
        "alchemy":        True,
        "public":         False,
    }

    resp = requests.post(
        f"{API_BASE}/generations",
        headers=headers,
        json=payload,
        timeout=30,
    )

    if resp.status_code != 200:
        raise RuntimeError(
            f"Erro ao solicitar geração (HTTP {resp.status_code}):\n{resp.text}"
        )

    data = resp.json()
    generation_id = data.get("sdGenerationJob", {}).get("generationId")
    if not generation_id:
        raise RuntimeError(f"generation_id não encontrado na resposta:\n{data}")

    return generation_id


def _aguardar_conclusao(generation_id: str, api_key: str) -> str:
    """
    Faz polling até a geração completar e retorna a URL da imagem.

    Raises:
        RuntimeError: se a geração falhar ou o timeout for atingido.
        TimeoutError: se o timeout for atingido.
    """
    headers = {
        "accept": "application/json",
        "authorization": f"Bearer {api_key}",
    }

    url = f"{API_BASE}/generations/{generation_id}"
    inicio = time.time()

    while True:
        elapsed = time.time() - inicio
        if elapsed > POLL_TIMEOUT:
            raise TimeoutError(
                f"Timeout de {POLL_TIMEOUT}s atingido aguardando geração {generation_id}"
            )

        resp = requests.get(url, headers=headers, timeout=15)
        if resp.status_code != 200:
            raise RuntimeError(
                f"Erro ao consultar geração (HTTP {resp.status_code}):\n{resp.text}"
            )

        data  = resp.json().get("generations_by_pk", {})
        status = data.get("status", "PENDING")

        print(f"[image_gen] Status: {status} ({elapsed:.0f}s)")

        if status == "COMPLETE":
            imagens = data.get("generated_images", [])
            if not imagens:
                raise RuntimeError("Geração completa mas nenhuma imagem retornada.")
            return imagens[0]["url"]

        if status == "FAILED":
            raise RuntimeError(f"Geração falhou: {data}")

        time.sleep(POLL_INTERVAL)


def _baixar_imagem(url: str, destino: str) -> str:
    """
    Baixa a imagem da URL e salva no destino.

    Returns:
        Caminho do arquivo salvo.
    """
    resp = requests.get(url, timeout=60, stream=True)
    resp.raise_for_status()

    Path(destino).parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "wb") as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return destino


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def gerar_imagem(destino: str = None) -> tuple[str, dict]:
    """
    Gera uma imagem anime/dark via Leonardo.ai e salva localmente.

    Args:
        destino: Caminho para salvar a imagem. Se None, salva como
                 'processing/imagem_gerada.png' relativo à pasta atual.

    Returns:
        (caminho_arquivo, metadados_do_prompt)

    Raises:
        EnvironmentError: API key não configurada.
        RuntimeError:     Falha na geração ou download.
        TimeoutError:     Timeout aguardando a geração.
    """
    if destino is None:
        destino = str(Path("processing") / "imagem_gerada.png")

    api_key = _get_api_key()

    # 1. Montar prompt
    prompt, meta = _montar_prompt()
    print(f"[image_gen] Prompt gerado:")
    print(f"            {prompt}")
    print(f"[image_gen] Enviando para Leonardo.ai...")

    # 2. Solicitar geração
    generation_id = _solicitar_geracao(prompt, api_key)
    print(f"[image_gen] Generation ID: {generation_id}")

    # 3. Aguardar conclusão com polling
    print(f"[image_gen] Aguardando conclusão (até {POLL_TIMEOUT}s)...")
    image_url = _aguardar_conclusao(generation_id, api_key)
    print(f"[image_gen] Imagem disponível: {image_url}")

    # 4. Baixar imagem
    print(f"[image_gen] Baixando imagem para: {destino}")
    _baixar_imagem(image_url, destino)

    tamanho_kb = Path(destino).stat().st_size / 1024
    print(f"[image_gen] Concluído: {destino} ({tamanho_kb:.0f} KB)")

    # 5. Salvar cópia em assets/images/ com timestamp
    assets_dir = Path("assets/images")
    assets_dir.mkdir(parents=True, exist_ok=True)
    timestamp  = datetime.now().strftime("%Y%m%d_%H%M%S")
    copia_path = assets_dir / f"gerada_{timestamp}.png"
    shutil.copy2(destino, copia_path)
    print(f"[image_gen] Cópia salva : {copia_path}")

    meta["prompt_completo"] = prompt
    meta["generation_id"]   = generation_id
    meta["image_url"]       = image_url

    return destino, meta


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    destino = sys.argv[1] if len(sys.argv) > 1 else None

    try:
        arquivo, meta = gerar_imagem(destino)
        print(f"\nImagem salva em: {arquivo}")
        print(f"\nElementos do prompt:")
        for k, v in meta.items():
            if k not in ("prompt_completo", "generation_id", "image_url"):
                print(f"  {k:<14}: {v}")
    except Exception as e:
        print(f"\n[ERRO] {e}", file=sys.stderr)
        sys.exit(1)
