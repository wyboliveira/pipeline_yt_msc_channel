"""
pinterest_uploader.py
Módulo de arquivamento de imagens no Pinterest via Pinterest API v5.
Parte do pipeline slowed-reverb-channel.

Objetivo:
    Esvaziar o histórico local de `assets/images/` subindo cada imagem como
    um pin em um board fixo da sua conta. A imagem local só é apagada após o
    pin ser criado com sucesso (mesma invariante do pipeline: nunca remove o
    dado sem confirmar o destino).

Autenticação (primeira execução):
    1. Crie um app em https://developers.pinterest.com/apps/
    2. Anote o App ID e o App secret
    3. Em "Redirect URIs" do app, adicione EXATAMENTE:  http://localhost:8085/
    4. No .env adicione:
           PINTEREST_APP_ID=...
           PINTEREST_APP_SECRET=...
           PINTEREST_BOARD_ID=...            # id do board de destino
           # opcional (padrão abaixo):
           # PINTEREST_REDIRECT_URI=http://localhost:8085/
    Na primeira execução abrirá o navegador para autorizar. O token é salvo em
    pinterest_token.json e renovado automaticamente nas próximas execuções.

    Para descobrir o board_id, após autenticar rode:
        python pinterest_uploader.py --listar-boards

Uso direto:
    python pinterest_uploader.py --flush          # sobe assets/images/ e limpa
    python pinterest_uploader.py --listar-boards
    python pinterest_uploader.py --reauth
"""

import os
import sys
import json
import time
import base64
import argparse
import threading
import webbrowser
from pathlib import Path
from urllib.parse import urlencode, urlparse, parse_qs
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

AUTH_URL      = "https://www.pinterest.com/oauth/"
TOKEN_URL     = "https://api.pinterest.com/v5/oauth/token"
API_BASE      = "https://api.pinterest.com/v5"
SCOPES        = "boards:read,pins:write"
TOKEN_PATH    = "pinterest_token.json"
ASSETS_DIR    = "assets/images"
DEFAULT_REDIRECT = "http://localhost:8085/"
REQUEST_TIMEOUT  = 30


# ---------------------------------------------------------------------------
# Leitura de configuração (.env / ambiente)
# ---------------------------------------------------------------------------

def _ler_env(chave: str, padrao: str = "") -> str:
    """Lê uma chave do ambiente ou do arquivo .env (ambiente tem prioridade)."""
    valor = os.environ.get(chave, "").strip()
    if valor:
        return valor

    env_path = Path(".env")
    if env_path.exists():
        for linha in env_path.read_text(encoding="utf-8").splitlines():
            if linha.startswith(f"{chave}="):
                return linha.split("=", 1)[1].strip().strip('"').strip("'")

    return padrao


def _config() -> dict:
    """Retorna app_id, app_secret, board_id e redirect_uri."""
    return {
        "app_id":       _ler_env("PINTEREST_APP_ID"),
        "app_secret":   _ler_env("PINTEREST_APP_SECRET"),
        "board_id":     _ler_env("PINTEREST_BOARD_ID"),
        "redirect_uri": _ler_env("PINTEREST_REDIRECT_URI", DEFAULT_REDIRECT),
    }


# ---------------------------------------------------------------------------
# OAuth 2.0
# ---------------------------------------------------------------------------

class _OAuthHandler(BaseHTTPRequestHandler):
    """Captura o ?code= do redirect do Pinterest em uma única requisição."""
    code = None
    erro = None

    def do_GET(self):
        params = parse_qs(urlparse(self.path).query)
        _OAuthHandler.code = (params.get("code") or [None])[0]
        _OAuthHandler.erro = (params.get("error") or [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = ("Autorizacao concluida. Pode fechar esta aba."
               if _OAuthHandler.code else
               f"Falha na autorizacao: {_OAuthHandler.erro}")
        self.wfile.write(f"<html><body><h3>{msg}</h3></body></html>".encode("utf-8"))

    def log_message(self, *args):
        pass  # silencia o log padrão do http.server


def _trocar_code_por_token(code: str, cfg: dict) -> dict:
    """Troca o authorization code por access/refresh token."""
    resp = requests.post(
        TOKEN_URL,
        auth=(cfg["app_id"], cfg["app_secret"]),
        data={
            "grant_type":   "authorization_code",
            "code":         code,
            "redirect_uri": cfg["redirect_uri"],
        },
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao obter token (HTTP {resp.status_code}): {resp.text}")
    return resp.json()


def _autorizar_no_navegador(cfg: dict) -> dict:
    """Fluxo OAuth completo: abre o navegador e captura o code via servidor local."""
    if not cfg["app_id"] or not cfg["app_secret"]:
        raise RuntimeError(
            "PINTEREST_APP_ID / PINTEREST_APP_SECRET ausentes.\n"
            "Crie um app em https://developers.pinterest.com/apps/ e configure o .env."
        )

    parsed = urlparse(cfg["redirect_uri"])
    host   = parsed.hostname or "localhost"
    port   = parsed.port or 80

    _OAuthHandler.code = None
    _OAuthHandler.erro = None
    servidor = HTTPServer((host, port), _OAuthHandler)

    auth_link = AUTH_URL + "?" + urlencode({
        "client_id":     cfg["app_id"],
        "redirect_uri":  cfg["redirect_uri"],
        "response_type": "code",
        "scope":         SCOPES,
    })
    print(f"[pinterest] Abrindo navegador para autorização...")
    webbrowser.open(auth_link)

    servidor.handle_request()   # bloqueia até o redirect chegar
    servidor.server_close()

    if _OAuthHandler.erro:
        raise RuntimeError(f"Autorização negada: {_OAuthHandler.erro}")
    if not _OAuthHandler.code:
        raise RuntimeError("Nenhum authorization code recebido.")

    token = _trocar_code_por_token(_OAuthHandler.code, cfg)
    _salvar_token(token)
    print(f"[pinterest] Token salvo em: {TOKEN_PATH}")
    return token


def _salvar_token(token: dict) -> None:
    """Persiste o token com o instante de expiração calculado."""
    expires_in = int(token.get("expires_in", 0))
    dados = {
        "access_token":  token["access_token"],
        "refresh_token": token.get("refresh_token", ""),
        "expires_at":    time.time() + expires_in - 60,  # margem de 60s
        "scope":         token.get("scope", SCOPES),
    }
    Path(TOKEN_PATH).write_text(json.dumps(dados, indent=2), encoding="utf-8")


def _renovar_token(refresh_token: str, cfg: dict) -> dict:
    """Renova o access token usando o refresh token."""
    resp = requests.post(
        TOKEN_URL,
        auth=(cfg["app_id"], cfg["app_secret"]),
        data={"grant_type": "refresh_token", "refresh_token": refresh_token},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao renovar token (HTTP {resp.status_code}): {resp.text}")
    token = resp.json()
    # Pinterest pode não devolver um novo refresh_token — preserva o atual.
    token.setdefault("refresh_token", refresh_token)
    _salvar_token(token)
    return token


def _access_token_valido() -> str:
    """
    Retorna um access token válido.
    Reutiliza o token salvo, renova se expirado, ou dispara o fluxo OAuth.
    """
    cfg        = _config()
    token_path = Path(TOKEN_PATH)

    if token_path.exists():
        dados = json.loads(token_path.read_text(encoding="utf-8"))
        if dados.get("expires_at", 0) > time.time():
            return dados["access_token"]
        if dados.get("refresh_token"):
            print("[pinterest] Renovando access token...")
            return _renovar_token(dados["refresh_token"], cfg)["access_token"]

    return _autorizar_no_navegador(cfg)["access_token"]


# ---------------------------------------------------------------------------
# API
# ---------------------------------------------------------------------------

def listar_boards() -> list[dict]:
    """Lista os boards da conta autenticada (id + nome)."""
    token = _access_token_valido()
    resp  = requests.get(
        f"{API_BASE}/boards",
        headers={"Authorization": f"Bearer {token}"},
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Falha ao listar boards (HTTP {resp.status_code}): {resp.text}")
    return [{"id": b["id"], "name": b.get("name", "")} for b in resp.json().get("items", [])]


def criar_pin(imagem_path: str, board_id: str, titulo: str = "", token: str = None) -> str:
    """
    Cria um pin a partir de uma imagem local (enviada em base64).

    Args:
        imagem_path: Caminho do PNG/JPG local.
        board_id:    Board de destino.
        titulo:      Título opcional do pin.
        token:       Access token já obtido (evita reautenticar a cada pin).

    Returns:
        O id do pin criado.
    """
    if token is None:
        token = _access_token_valido()

    caminho   = Path(imagem_path)
    ext       = caminho.suffix.lower()
    content_type = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"
    dados_b64 = base64.b64encode(caminho.read_bytes()).decode("ascii")

    body = {
        "board_id": board_id,
        "media_source": {
            "source_type":  "image_base64",
            "content_type": content_type,
            "data":         dados_b64,
        },
    }
    if titulo:
        body["title"] = titulo[:100]

    resp = requests.post(
        f"{API_BASE}/pins",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
        timeout=REQUEST_TIMEOUT,
    )
    if resp.status_code != 201:
        raise RuntimeError(f"Falha ao criar pin (HTTP {resp.status_code}): {resp.text}")
    return resp.json()["id"]


def flush_assets(
    board_id: str = None,
    assets_dir: str = ASSETS_DIR,
    minimo: int = 0,
    log=print,
) -> dict:
    """
    Sobe todas as imagens de `assets_dir` como pins e apaga cada uma após
    sucesso. A imagem só é removida localmente quando o pin é confirmado.

    Args:
        board_id:   Board de destino (padrão: PINTEREST_BOARD_ID do .env).
        assets_dir: Pasta com as imagens.
        minimo:     Se > 0, só executa quando houver pelo menos N imagens.
        log:        Callback de log (recebe uma string por linha).

    Returns:
        dict com: total, enviadas, falhas, ignorado (bool).
    """
    cfg      = _config()
    board_id = board_id or cfg["board_id"]
    if not board_id:
        raise RuntimeError("PINTEREST_BOARD_ID não definido. Configure o board de destino no .env.")

    pasta   = Path(assets_dir)
    imagens = sorted(
        p for p in pasta.glob("*")
        if p.suffix.lower() in (".png", ".jpg", ".jpeg")
    ) if pasta.exists() else []

    total = len(imagens)
    if minimo > 0 and total < minimo:
        log(f"[pinterest] {total} imagem(ns) — abaixo do mínimo de {minimo}. Nada a fazer.")
        return {"total": total, "enviadas": 0, "falhas": 0, "ignorado": True}

    if total == 0:
        log("[pinterest] Nenhuma imagem em assets/images/. Nada a fazer.")
        return {"total": 0, "enviadas": 0, "falhas": 0, "ignorado": False}

    token = _access_token_valido()
    log(f"[pinterest] Arquivando {total} imagem(ns) no board {board_id}...")

    enviadas = 0
    falhas   = 0
    for img in imagens:
        try:
            pin_id = criar_pin(str(img), board_id, titulo=img.stem, token=token)
            img.unlink()  # só apaga após o pin confirmado
            enviadas += 1
            log(f"[pinterest] OK {img.name} → pin {pin_id}")
        except Exception as e:
            falhas += 1
            log(f"[pinterest] FALHOU {img.name}: {e}")

    log(f"[pinterest] Concluído: {enviadas} enviada(s), {falhas} falha(s).")
    return {"total": total, "enviadas": enviadas, "falhas": falhas, "ignorado": False}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Arquiva imagens no Pinterest.")
    parser.add_argument("--flush", action="store_true", help="Sobe assets/images/ e limpa a pasta")
    parser.add_argument("--listar-boards", action="store_true", help="Lista os boards da conta")
    parser.add_argument("--reauth", action="store_true", help="Refaz a autenticação OAuth")
    parser.add_argument("--minimo", type=int, default=0, help="Mínimo de imagens para o flush")
    args = parser.parse_args()

    try:
        if args.reauth:
            Path(TOKEN_PATH).unlink(missing_ok=True)
            _autorizar_no_navegador(_config())
            print("Autenticação concluída.")
        elif args.listar_boards:
            for b in listar_boards():
                print(f"  {b['id']}  {b['name']}")
        elif args.flush:
            flush_assets(minimo=args.minimo)
        else:
            parser.print_help()
    except Exception as e:
        print(f"\n[ERRO] {e}", file=sys.stderr)
        sys.exit(1)
