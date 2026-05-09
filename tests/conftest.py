"""
Fixtures compartilhadas entre todos os módulos de teste.
"""
import sys
from pathlib import Path

# Garante que o diretório raiz está no path para importar os módulos do projeto
ROOT = Path(__file__).parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pytest


@pytest.fixture
def tmp_dirs(tmp_path: Path) -> Path:
    """Cria a estrutura de diretórios do pipeline em um diretório temporário."""
    for d in ("inbox", "processing", "review", "rejected", "logs", "assets/images"):
        (tmp_path / d).mkdir(parents=True)
    return tmp_path


@pytest.fixture
def dummy_audio(tmp_dirs: Path) -> Path:
    """Cria um arquivo de áudio fictício no inbox."""
    f = tmp_dirs / "inbox" / "Artista - Musica Teste.mp3"
    f.write_bytes(b"\xff\xfb" + b"\x00" * 128)   # cabeçalho MP3 mínimo
    return f


@pytest.fixture
def dummy_image(tmp_path: Path) -> Path:
    """Cria um PNG mínimo válido (1x1 pixel preto)."""
    img = tmp_path / "imagem_gerada.png"
    # PNG mínimo válido (1x1 px, gerado a partir de bytes conhecidos)
    png_bytes = (
        b"\x89PNG\r\n\x1a\n"                         # assinatura
        b"\x00\x00\x00\rIHDR"                         # chunk IHDR
        b"\x00\x00\x00\x01\x00\x00\x00\x01"           # 1x1
        b"\x08\x02\x00\x00\x00\x90wS\xde"             # bit depth, color type
        b"\x00\x00\x00\x0cIDATx\x9cc\xf8\x0f\x00"    # IDAT mínimo
        b"\x00\x01\x01\x00\x18\xdd\x8d\xb4"
        b"\x00\x00\x00\x00IEND\xaeB`\x82"             # IEND
    )
    img.write_bytes(png_bytes)
    return img
