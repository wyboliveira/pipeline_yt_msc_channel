"""
ken_burns.py
Módulo de efeito Ken Burns / pulsação para o pipeline slowed-reverb-channel.
Recebe uma imagem, aplica um efeito de movimento suave e gera um vídeo MP4
em loop perfeito no formato YouTube (1920x1080 @ 60fps).

Uso direto:
    python ken_burns.py <imagem> [duracao_segundos] [saida.mp4] [nome_efeito]

Exemplos:
    python ken_burns.py arte.png 180
    python ken_burns.py arte.png 180 saida.mp4 pulsacao
    python ken_burns.py arte.png 180 saida.mp4 pulsacao_pan
"""

import subprocess
import random
import sys
from pathlib import Path


# ---------------------------------------------------------------------------
# Efeitos disponíveis
# Cada função recebe (frames: int, fps: int) e retorna dict com:
#   nome, z, x, y  (expressões zoompan do FFmpeg)
# ---------------------------------------------------------------------------

def efeito_zoom_in(frames: int, fps: int) -> dict:
    """Zoom lento do centro para fora."""
    return {
        "nome": "zoom_in",
        "z": f"if(lte(on,1),1.0,min(zoom+{0.05/frames:.7f},1.05))",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_zoom_out(frames: int, fps: int) -> dict:
    """Zoom-out lento. Loop perfeito: termina onde começou."""
    step = 0.10 / frames
    return {
        "nome": "zoom_out",
        "z": f"1.10-{step:.7f}*on",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_pan_esquerda(frames: int, fps: int) -> dict:
    """Pan lento da direita para esquerda."""
    step = (0.15 * 1920) / frames
    return {
        "nome": "pan_esquerda",
        "z": "1.15",
        "x": f"if(lte(on,1),(iw-iw/zoom),max(x-{step:.3f},0))",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_pan_direita(frames: int, fps: int) -> dict:
    """Pan lento da esquerda para direita."""
    step = (0.15 * 1920) / frames
    return {
        "nome": "pan_direita",
        "z": "1.15",
        "x": f"if(lte(on,1),0,min(x+{step:.3f},iw-iw/zoom))",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_diagonal_melancolico(frames: int, fps: int) -> dict:
    """Pan diagonal suave. Tom mais sombrio/melancólico."""
    step_x = (0.12 * 1920) / frames
    step_y = (0.08 * 1080) / frames
    return {
        "nome": "diagonal_melancolico",
        "z": "1.12",
        "x": f"if(lte(on,1),0,min(x+{step_x:.3f},iw-iw/zoom))",
        "y": f"if(lte(on,1),0,min(y+{step_y:.3f},ih-ih/zoom))",
    }


def efeito_pulsacao(frames: int, fps: int) -> dict:
    """
    Zoom pulsa a cada 6s — respiração lenta e intensa.
    Vai de 1.0 -> 1.12 -> 1.0.
    """
    ciclo = int(fps * 12)
    return {
        "nome": "pulsacao",
        "z": f"1.0+0.12*sin(PI*(mod(on,{ciclo})/{ciclo}))",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_pulsacao_pan(frames: int, fps: int) -> dict:
    """
    Pulsação a cada 2s + pan lateral oscilatório simultâneo.
    O pan reverte direção a cada ciclo — mais agitado que um pan linear.
    """
    ciclo = int(fps * 4)
    ciclo_pan = int(fps * 8)
    return {
        "nome": "pulsacao_pan",
        "z": f"1.05+0.12*sin(PI*(mod(on,{ciclo})/{ciclo}))",
        "x": f"iw/2-(iw/zoom/2)+80*sin(2*PI*mod(on,{ciclo_pan})/{ciclo_pan})",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_zoom_snap(frames: int, fps: int) -> dict:
    """
    Heartbeat zoom: cresce linearmente de 1.02 até 1.22 em 10s, depois
    snapa de volta instantaneamente. Efeito brusco e repentino.
    """
    ciclo = int(fps * 12)
    return {
        "nome": "zoom_snap",
        "z": f"1.02+0.20*mod(on,{ciclo})/{ciclo}",
        "x": "iw/2-(iw/zoom/2)",
        "y": "ih/2-(ih/zoom/2)",
    }


def efeito_oscilacao(frames: int, fps: int) -> dict:
    """
    Oscilação lenta: zoom pulsa em 6s enquanto a câmera deriva
    suavemente da esquerda para a direita ao longo de 10s e volta.
    Hipnótico, quase como ondas.
    """
    ciclo_z = int(fps * 8)
    ciclo_x = int(fps * 14)
    return {
        "nome": "oscilacao",
        "z": f"1.05+0.12*sin(PI*(mod(on,{ciclo_z})/{ciclo_z}))",
        "x": f"iw/2-(iw/zoom/2)+100*sin(2*PI*mod(on,{ciclo_x})/{ciclo_x})",
        "y": "ih/2-(ih/zoom/2)",
    }


# Registro central
EFEITOS = [
    efeito_zoom_in,
    efeito_zoom_out,
    efeito_pan_esquerda,
    efeito_pan_direita,
    efeito_diagonal_melancolico,
    efeito_pulsacao,
    efeito_pulsacao_pan,
    efeito_zoom_snap,
    efeito_oscilacao,
]

EFEITOS_POR_NOME = {fn(1, 30)["nome"]: fn for fn in EFEITOS}


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def aplicar_ken_burns(
    imagem: str,
    duracao: int = 30,
    saida: str = None,
    efeito_nome: str = None,
    fps: int = 60,
    resolucao: str = "1920x1080",
    rgb_split: bool = True,
    rgb_split_intervalo: float = 8.0,
    rgb_split_duracao: float = 0.25,
) -> str:
    """
    Aplica efeito Ken Burns/pulsação em uma imagem e gera vídeo MP4.

    Args:
        imagem:               Caminho para a imagem de entrada (JPG/PNG).
        duracao:              Duração do vídeo em segundos.
        saida:                Caminho do arquivo de saída. Se None, gera automaticamente.
        efeito_nome:          Nome do efeito. Se None, escolhe aleatoriamente.
        fps:                  Frames por segundo (padrão 60).
        resolucao:            Resolução de saída (padrão 1920x1080).
        rgb_split:            Ativa piscada de aberração cromática (padrão True).
        rgb_split_intervalo:  Segundos entre cada piscada de RGB split (padrão 8s).
        rgb_split_duracao:    Duração de cada piscada em segundos (padrão 0.12s).

    Returns:
        Caminho do vídeo gerado.

    Raises:
        FileNotFoundError: Se a imagem não existir ou FFmpeg não estiver no PATH.
        ValueError:        Se o nome do efeito for inválido.
        RuntimeError:      Se o FFmpeg falhar durante a geração.
    """

    imagem_path = Path(imagem)
    if not imagem_path.exists():
        raise FileNotFoundError(f"Imagem não encontrada: {imagem}")

    # Verificar FFmpeg
    try:
        subprocess.run(["ffmpeg", "-version"], capture_output=True, check=True)
    except FileNotFoundError:
        raise FileNotFoundError(
            "FFmpeg não encontrado no PATH.\n"
            "Baixe em https://ffmpeg.org/download.html e adicione ao PATH do Windows.\n"
            "Após instalar, reinicie o terminal."
        )

    # Definir saída
    if saida is None:
        saida = str(imagem_path.parent / f"{imagem_path.stem}_kenbur.mp4")

    # Selecionar efeito
    frames = duracao * fps

    if efeito_nome:
        if efeito_nome not in EFEITOS_POR_NOME:
            disponiveis = list(EFEITOS_POR_NOME.keys())
            raise ValueError(
                f"Efeito '{efeito_nome}' não existe.\n"
                f"Disponíveis: {disponiveis}"
            )
        efeito_fn = EFEITOS_POR_NOME[efeito_nome]
    else:
        efeito_fn = random.choice(EFEITOS)

    efeito = efeito_fn(frames, fps)

    print(f"[ken_burns] Efeito    : {efeito['nome']}")
    print(f"[ken_burns] Imagem    : {imagem_path.name}")
    print(f"[ken_burns] Duração   : {duracao}s | {fps}fps | {frames} frames")
    print(f"[ken_burns] Resolução : {resolucao}")

    zoompan = (
        f"scale=iw*3:ih*3:flags=lanczos,"
        f"zoompan="
        f"z='{efeito['z']}':"
        f"x='{efeito['x']}':"
        f"y='{efeito['y']}':"
        f"d={frames}:s={resolucao}:fps={fps}"
    )

    if rgb_split:
        glitch = (
            f"rgbashift="
            f"rh=8:rv=0:gh=-5:gv=0:bh=-8:bv=0:edge=smear:"
            f"enable='lt(mod(t,{rgb_split_intervalo}),{rgb_split_duracao})'"
        )
        print(f"[ken_burns] RGB Split : a cada {rgb_split_intervalo}s por {rgb_split_duracao}s")
        filtro = f"{zoompan},{glitch},format=yuv420p"
    else:
        filtro = f"{zoompan},format=yuv420p"

    cmd = [
        "ffmpeg", "-y",
        "-loop", "1",
        "-i", str(imagem_path),
        "-vf", filtro,
        "-t", str(duracao),
        "-c:v", "libx264",
        "-preset", "fast",
        "-crf", "18",
        saida,
    ]

    print(f"[ken_burns] Gerando vídeo... (pode levar alguns segundos)")
    resultado = subprocess.run(cmd, capture_output=True, text=True)

    if resultado.returncode != 0:
        raise RuntimeError(
            f"FFmpeg falhou (código {resultado.returncode}):\n"
            f"{resultado.stderr[-1500:]}"
        )

    tamanho_mb = Path(saida).stat().st_size / (1024 * 1024)
    print(f"[ken_burns] Concluído : {saida} ({tamanho_mb:.1f} MB)")
    return saida


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    nomes = list(EFEITOS_POR_NOME.keys())

    if len(sys.argv) < 2:
        print("Uso: python ken_burns.py <imagem> [duracao_s] [saida.mp4] [efeito]")
        print()
        print("Efeitos disponíveis:")
        for nome in nomes:
            print(f"  {nome}")
        print()
        print("Exemplos:")
        print("  python ken_burns.py arte.png 180")
        print("  python ken_burns.py arte.png 180 saida.mp4 pulsacao")
        print("  python ken_burns.py arte.png 180 saida.mp4 pulsacao_pan")
        sys.exit(0)

    img    = sys.argv[1]
    dur    = int(sys.argv[2]) if len(sys.argv) > 2 else 30
    out    = sys.argv[3]      if len(sys.argv) > 3 else None
    efeito = sys.argv[4]      if len(sys.argv) > 4 else None

    try:
        resultado = aplicar_ken_burns(img, duracao=dur, saida=out, efeito_nome=efeito)
        print(f"\nVídeo salvo em: {resultado}")
    except Exception as e:
        print(f"\n[ERRO] {e}", file=sys.stderr)
        sys.exit(1)
