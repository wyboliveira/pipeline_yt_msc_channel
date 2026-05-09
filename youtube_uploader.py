"""
youtube_uploader.py
Módulo de publicação de vídeos via YouTube Data API v3.
Parte do pipeline slowed-reverb-channel.

Autenticação (primeira execução):
    1. Crie um projeto no Google Cloud Console
    2. Ative a YouTube Data API v3
    3. Crie credenciais OAuth 2.0 (Tipo: Aplicativo para computador)
    4. Baixe o arquivo JSON e salve como client_secret.json na raiz do projeto
    5. Adicione no .env: YOUTUBE_CLIENT_SECRET_PATH=client_secret.json
    Na primeira execução, abrirá o navegador para autorizar. O token é salvo
    em youtube_token.json e reutilizado nas próximas execuções.

Uso direto:
    python youtube_uploader.py video.mp4 "Título do Vídeo"
    python youtube_uploader.py video.mp4 "Título" --descricao "Desc" --tags "tag1,tag2"
"""

import os
import sys
import json
import time
import argparse
from pathlib import Path

from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

SCOPES              = ["https://www.googleapis.com/auth/youtube.upload"]
TOKEN_PATH          = "youtube_token.json"
CATEGORIA_MUSICA    = "10"   # Music — https://developers.google.com/youtube/v3/docs/videoCategories
PRIVACIDADE_PADRAO  = "public"
CHUNK_SIZE          = 8 * 1024 * 1024   # 8 MB por chunk (upload resumível)
MAX_RETRIES         = 5


# ---------------------------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------------------------

def _ler_client_secret_path() -> str:
    """Lê o caminho do client_secret.json do .env ou usa o padrão."""
    # Variável de ambiente tem prioridade
    path = os.environ.get("YOUTUBE_CLIENT_SECRET_PATH", "").strip()
    if path:
        return path

    # Tenta ler do .env
    env_path = Path(".env")
    if env_path.exists():
        for linha in env_path.read_text().splitlines():
            if linha.startswith("YOUTUBE_CLIENT_SECRET_PATH="):
                path = linha.split("=", 1)[1].strip().strip('"').strip("'")
                if path:
                    return path

    return "client_secret.json"


def _autenticar() -> Credentials:
    """
    Retorna credenciais OAuth 2.0 válidas.
    - Reutiliza token salvo se ainda válido.
    - Renova automaticamente se expirado.
    - Abre o navegador para autorização na primeira execução.
    """
    creds = None
    token_path = Path(TOKEN_PATH)

    if token_path.exists():
        creds = Credentials.from_authorized_user_file(str(token_path), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("[youtube] Renovando token de acesso...")
            creds.refresh(Request())
        else:
            secret_path = _ler_client_secret_path()
            if not Path(secret_path).exists():
                raise FileNotFoundError(
                    f"Arquivo '{secret_path}' não encontrado.\n"
                    "Baixe as credenciais OAuth 2.0 no Google Cloud Console e\n"
                    "salve como client_secret.json na raiz do projeto.\n\n"
                    "Guia rápido:\n"
                    "  1. console.cloud.google.com → APIs e Serviços → Credenciais\n"
                    "  2. Criar credencial → ID do cliente OAuth → Aplicativo para computador\n"
                    "  3. Baixar JSON → renomear para client_secret.json"
                )

            print("[youtube] Abrindo navegador para autorização...")
            flow = InstalledAppFlow.from_client_secrets_file(secret_path, SCOPES)
            creds = flow.run_local_server(port=0, open_browser=True)

        # Salva token para próximas execuções
        token_path.write_text(creds.to_json())
        print(f"[youtube] Token salvo em: {TOKEN_PATH}")

    return creds


def _fazer_upload(
    youtube,
    video_path: str,
    titulo: str,
    descricao: str,
    tags: list[str],
    privacidade: str,
) -> str:
    """
    Faz upload do vídeo com upload resumível e retorna o video_id.
    Tenta novamente em caso de erros transitórios (5xx).
    """
    body = {
        "snippet": {
            "title":       titulo[:100],
            "description": descricao,
            "tags":        tags,
            "categoryId":  CATEGORIA_MUSICA,
        },
        "status": {
            "privacyStatus":           privacidade,
            "selfDeclaredMadeForKids": False,
        },
    }

    media = MediaFileUpload(
        video_path,
        mimetype="video/mp4",
        chunksize=CHUNK_SIZE,
        resumable=True,
    )

    request = youtube.videos().insert(
        part="snippet,status",
        body=body,
        media_body=media,
    )

    print(f"[youtube] Iniciando upload: {Path(video_path).name}")
    tamanho_mb = Path(video_path).stat().st_size / (1024 * 1024)
    print(f"[youtube] Tamanho       : {tamanho_mb:.1f} MB")

    response    = None
    retry_count = 0
    erros_retry = {500, 502, 503, 504}

    while response is None:
        try:
            status, response = request.next_chunk()
            if status:
                pct = int(status.progress() * 100)
                print(f"[youtube] Progresso     : {pct}%", end="\r")
        except HttpError as e:
            if e.resp.status in erros_retry and retry_count < MAX_RETRIES:
                retry_count += 1
                espera = 2 ** retry_count
                print(f"[youtube] Erro {e.resp.status}, tentativa {retry_count}/{MAX_RETRIES} em {espera}s...")
                time.sleep(espera)
            else:
                raise RuntimeError(
                    f"Erro no upload (HTTP {e.resp.status}):\n{e.content}"
                )

    print()  # nova linha após a barra de progresso
    return response["id"]


# ---------------------------------------------------------------------------
# Função principal
# ---------------------------------------------------------------------------

def publicar_video(
    video_path: str,
    titulo: str,
    descricao: str = "",
    tags: list[str] = None,
    privacidade: str = PRIVACIDADE_PADRAO,
) -> dict:
    """
    Publica um vídeo no YouTube.

    Args:
        video_path:  Caminho para o arquivo MP4.
        titulo:      Título do vídeo.
        descricao:   Descrição completa (suporta emojis e quebras de linha).
        tags:        Lista de tags para o YouTube.
        privacidade: "public", "unlisted" ou "private".

    Returns:
        dict com:
            video_id  — ID do vídeo no YouTube
            url       — URL pública do vídeo
            titulo    — título publicado

    Raises:
        FileNotFoundError: Vídeo ou client_secret.json não encontrado.
        RuntimeError:      Falha no upload.
    """
    if not Path(video_path).exists():
        raise FileNotFoundError(f"Vídeo não encontrado: {video_path}")

    if tags is None:
        tags = []

    creds   = _autenticar()
    youtube = build("youtube", "v3", credentials=creds)

    video_id = _fazer_upload(
        youtube,
        video_path=video_path,
        titulo=titulo,
        descricao=descricao,
        tags=tags,
        privacidade=privacidade,
    )

    url = f"https://www.youtube.com/watch?v={video_id}"
    print(f"[youtube] Publicado     : {url}")

    return {
        "video_id": video_id,
        "url":      url,
        "titulo":   titulo,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Publica um vídeo no YouTube.")
    parser.add_argument("video",      help="Caminho do arquivo MP4")
    parser.add_argument("titulo",     help="Título do vídeo")
    parser.add_argument("--descricao", default="", help="Descrição do vídeo")
    parser.add_argument("--tags",      default="", help="Tags separadas por vírgula")
    parser.add_argument(
        "--privacidade",
        default=PRIVACIDADE_PADRAO,
        choices=["public", "unlisted", "private"],
        help="Privacidade (padrão: public)",
    )
    args = parser.parse_args()

    tags_lista = [t.strip() for t in args.tags.split(",") if t.strip()]

    try:
        resultado = publicar_video(
            video_path=args.video,
            titulo=args.titulo,
            descricao=args.descricao,
            tags=tags_lista,
            privacidade=args.privacidade,
        )
        print(f"\nVídeo publicado com sucesso!")
        print(f"  ID  : {resultado['video_id']}")
        print(f"  URL : {resultado['url']}")
    except Exception as e:
        print(f"\n[ERRO] {e}", file=sys.stderr)
        sys.exit(1)
