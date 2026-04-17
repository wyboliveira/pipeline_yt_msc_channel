"""
pipeline.py
Script principal do canal slowed-reverb-channel.

Fluxo por arquivo:
    inbox/ → [1] gerar imagem → [2] aplicar Ken Burns → [3] combinar áudio+vídeo
           → review/ → aprovação humana → publicar no YouTube
                                        → rejeitar → rejected/

Uso:
    python pipeline.py                  # processa o arquivo mais antigo do /inbox
    python pipeline.py "duhe"           # busca arquivo com nome parecido na inbox
    python pipeline.py "shy martin"     # busca case-insensitive por qualquer parte do nome
"""

import sys
import json
import shutil
import argparse
import subprocess
import traceback
from datetime import datetime
from pathlib import Path

from image_generator  import gerar_imagem
from ken_burns        import aplicar_ken_burns
from metadata_generator import gerar_metadados, NOME_CANAL
from youtube_uploader import publicar_video


# ---------------------------------------------------------------------------
# Configuração de pastas
# ---------------------------------------------------------------------------

DIR_INBOX      = Path("inbox")
DIR_PROCESSING = Path("processing")
DIR_REVIEW     = Path("review")
DIR_REJECTED   = Path("rejected")
DIR_LOGS       = Path("logs")

AUDIO_EXTENSOES = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}

FPS        = 60
RESOLUCAO  = "1920x1080"


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def _notificar_erro(titulo: str, mensagem: str) -> None:
    """Dispara notificação toast do Windows sem dependências extras."""
    script = (
        f"Add-Type -AssemblyName System.Windows.Forms; "
        f"$n = New-Object System.Windows.Forms.NotifyIcon; "
        f"$n.Icon = [System.Drawing.SystemIcons]::Error; "
        f"$n.Visible = $true; "
        f"$n.ShowBalloonTip(8000, '{titulo}', '{mensagem}', "
        f"[System.Windows.Forms.ToolTipIcon]::Error)"
    )
    try:
        subprocess.Popen(
            ["powershell", "-WindowStyle", "Hidden", "-Command", script],
            creationflags=subprocess.CREATE_NO_WINDOW,
        )
    except Exception:
        pass  # notificação é melhor-esforço


def _salvar_log_erro(nome_arquivo: str, erro: str) -> Path:
    """Salva log de erro detalhado em logs/erro_[nome].txt."""
    DIR_LOGS.mkdir(exist_ok=True)
    agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = DIR_LOGS / f"erro_{Path(nome_arquivo).stem}_{agora}.txt"
    log_path.write_text(
        f"Arquivo : {nome_arquivo}\n"
        f"Horário : {agora}\n"
        f"{'=' * 60}\n"
        f"{erro}\n",
        encoding="utf-8",
    )
    return log_path


def _obter_duracao(audio_path: Path) -> int:
    """Retorna a duração do áudio em segundos via ffprobe."""
    cmd = [
        "ffprobe", "-v", "quiet",
        "-print_format", "json",
        "-show_streams",
        str(audio_path),
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(
            f"ffprobe falhou ao ler '{audio_path.name}':\n{resultado.stderr}"
        )

    dados = json.loads(resultado.stdout)
    for stream in dados.get("streams", []):
        duracao = stream.get("duration")
        if duracao:
            return int(float(duracao))

    raise RuntimeError(f"Não foi possível obter a duração de '{audio_path.name}'.")


def _combinar_audio_video(video_path: Path, audio_path: Path, saida: Path) -> None:
    """Combina vídeo animado + áudio em um único MP4 via FFmpeg."""
    cmd = [
        "ffmpeg", "-y",
        "-i", str(video_path),
        "-i", str(audio_path),
        "-c:v", "copy",
        "-c:a", "aac",
        "-b:a", "192k",
        "-shortest",
        str(saida),
    ]
    resultado = subprocess.run(cmd, capture_output=True, text=True)
    if resultado.returncode != 0:
        raise RuntimeError(
            f"FFmpeg falhou ao combinar áudio+vídeo:\n{resultado.stderr[-1500:]}"
        )


def _abrir_pasta(path: Path) -> None:
    """Abre a pasta no Windows Explorer."""
    subprocess.Popen(["explorer", str(path.resolve())])


def _limpar_processing(manter: Path = None) -> None:
    """Remove arquivos temporários da pasta processing/, preservando o arquivo indicado."""
    for f in DIR_PROCESSING.iterdir():
        if manter and f.resolve() == manter.resolve():
            continue
        try:
            f.unlink()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Processamento de um arquivo
# ---------------------------------------------------------------------------

def processar_arquivo(audio_path: Path) -> bool:
    """
    Executa o pipeline completo para um arquivo de áudio.

    Returns:
        True se publicado, False se rejeitado.

    Raises:
        Exception em qualquer erro de processamento.
    """
    nome = audio_path.name
    print(f"\n{'=' * 60}")
    print(f"  Processando: {nome}")
    print(f"{'=' * 60}")

    # Move para processing/
    DIR_PROCESSING.mkdir(exist_ok=True)
    audio_proc = DIR_PROCESSING / nome
    shutil.move(str(audio_path), str(audio_proc))

    try:
        # [1] Metadados (gerado uma vez por música)
        print("\n[1/4] Gerando metadados (Ollama)...")
        meta = gerar_metadados(nome)

        # Edição do nome da música antes de prosseguir
        print(f"\n{'─' * 60}")
        print(f"  Título gerado : {meta['titulo']}")
        print(f"{'─' * 60}")
        print("  Edite o nome da música no formato  Artista - Nome da Música")
        print("  (ex: Queen - Bohemian Rhapsody)  ou Enter para manter:")
        nome_editado = input("  >>> ").strip()
        if nome_editado:
            titulo_antigo  = meta["titulo"]
            meta["titulo"] = f"｜ {nome_editado} ｜ slowed + reverb - vers {NOME_CANAL}"
            meta["descricao"] = meta["descricao"].replace(titulo_antigo, meta["titulo"])
            print(f"  Título atualizado: {meta['titulo']}")

        # Duração do áudio (necessária para o Ken Burns)
        duracao = _obter_duracao(audio_proc)

        # ── Loop de aprovação da imagem ──────────────────────────────────────
        # Gera e mostra a imagem antes de montar o vídeo.
        # Repete até o usuário aprovar ou descartar a música inteira.
        img_meta    = {}
        imagem_path = ""
        tentativa   = 0

        while True:
            tentativa += 1
            if tentativa > 1:
                print(f"\n  Nova imagem (tentativa {tentativa})...")

            print("\n[2/4] Gerando imagem (Leonardo.ai)...")
            imagem_path, img_meta = gerar_imagem(
                destino=str(DIR_PROCESSING / "imagem_gerada.png")
            )

            # Abre a imagem com o visualizador padrão do Windows
            import os as _os
            _os.startfile(str(Path(imagem_path).resolve()))

            print(f"\n{'─' * 60}")
            print(f"  Personagem : {img_meta.get('personagem', '')}")
            print(f"  Cenário    : {img_meta.get('cenario', '')}")
            print(f"  Estilo     : {img_meta.get('estilo', '')}")
            print(f"{'─' * 60}")
            print("\nAvalie a imagem que foi aberta.")
            print("Digite  [s] para aprovar  |  [n] para gerar nova imagem  |  [d] para descartar esta música")
            resposta_img = input(">>> ").strip().lower()

            if resposta_img == "s":
                break                       # imagem aprovada → segue para o vídeo
            elif resposta_img == "d":
                shutil.move(str(audio_proc), str(audio_path))
                _limpar_processing()
                print("\nMúsica descartada. Áudio devolvido ao /inbox.")
                return False
            # qualquer outra resposta (ou "n") → gera nova imagem

        # ── Montagem do vídeo (imagem já aprovada) ───────────────────────────
        print("\n[3/4] Aplicando efeito Ken Burns...")
        video_animado = str(DIR_PROCESSING / "video_animado.mp4")
        aplicar_ken_burns(
            imagem=imagem_path,
            duracao=duracao,
            saida=video_animado,
            efeito_nome=None,
            fps=FPS,
            resolucao=RESOLUCAO,
        )

        print("\n[4/4] Combinando áudio + vídeo...")
        nome_final  = Path(nome).stem + "_final.mp4"
        video_final = DIR_PROCESSING / nome_final
        _combinar_audio_video(
            video_path=Path(video_animado),
            audio_path=audio_proc,
            saida=video_final,
        )

        DIR_REVIEW.mkdir(exist_ok=True)
        video_review = DIR_REVIEW / nome_final
        shutil.move(str(video_final), str(video_review))
        _limpar_processing(manter=audio_proc)

        # ── Review final do vídeo ────────────────────────────────────────────
        print(f"\n{'─' * 60}")
        print(f"  Título : {meta['titulo']}")
        print(f"  Vídeo  : {video_review}")
        print(f"{'─' * 60}")
        _abrir_pasta(DIR_REVIEW)

        print("\nAssista ao vídeo na pasta /review que foi aberta.")
        print("Digite  [s] para publicar  |  [n] para descartar")
        resposta_video = input(">>> ").strip().lower()

        if resposta_video == "s":
            print("\nPublicando no YouTube...")
            resultado = publicar_video(
                video_path=str(video_review),
                titulo=meta["titulo"],
                descricao=meta["descricao"],
                tags=meta["tags"],
            )

            DIR_LOGS.mkdir(exist_ok=True)
            agora    = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_path = DIR_LOGS / f"publicado_{Path(nome).stem}_{agora}.txt"
            log_path.write_text(
                f"Arquivo  : {nome}\n"
                f"Título   : {resultado['titulo']}\n"
                f"Video ID : {resultado['video_id']}\n"
                f"URL      : {resultado['url']}\n"
                f"Horário  : {agora}\n"
                f"\nPrompt da imagem:\n{img_meta.get('prompt_completo', '')}\n",
                encoding="utf-8",
            )
            print(f"\nPublicado: {resultado['url']}")
            print(f"Log salvo: {log_path}")
            _limpar_processing()
            return True

        else:
            DIR_REJECTED.mkdir(exist_ok=True)
            shutil.move(str(video_review), str(DIR_REJECTED / nome_final))
            shutil.move(str(audio_proc), str(audio_path))
            _limpar_processing()
            print("\nVídeo movido para /rejected. Áudio devolvido ao /inbox.")
            return False

    except Exception:
        # Em caso de erro: devolve áudio ao inbox e limpa processing
        try:
            shutil.move(str(audio_proc), str(audio_path))
        except Exception:
            pass
        _limpar_processing()
        raise


# ---------------------------------------------------------------------------
# Loop principal
# ---------------------------------------------------------------------------

def _buscar_audio(busca: str) -> Path | None:
    """
    Retorna o primeiro arquivo do /inbox cujo nome contenha a string de busca
    (case-insensitive). Prioriza correspondências no início do nome.
    Retorna None se nenhum arquivo for encontrado.
    """
    termo = busca.lower()
    candidatos = sorted(
        (f for f in DIR_INBOX.iterdir()
         if f.is_file() and f.suffix.lower() in AUDIO_EXTENSOES),
        key=lambda f: f.stat().st_mtime,
    )

    # Primeiro tenta encontrar no início do nome, depois em qualquer posição
    for prioridade in (
        lambda n: n.startswith(termo),
        lambda n: termo in n,
    ):
        resultado = [f for f in candidatos if prioridade(f.name.lower())]
        if resultado:
            return resultado[0]

    return None


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(
        description="Pipeline OvxrNight — processa um áudio do /inbox.",
        epilog='Exemplo: python pipeline.py "shy martin"',
    )
    parser.add_argument(
        "busca",
        nargs="?",
        default=None,
        help="Texto para buscar um arquivo específico no /inbox (opcional).",
    )
    args = parser.parse_args()

    DIR_INBOX.mkdir(exist_ok=True)

    if args.busca:
        # Busca por nome
        audio_path = _buscar_audio(args.busca)
        if not audio_path:
            print(f'Nenhum arquivo encontrado no /inbox com "{args.busca}".')
            fila = sorted(
                (f for f in DIR_INBOX.iterdir()
                 if f.is_file() and f.suffix.lower() in AUDIO_EXTENSOES),
                key=lambda f: f.stat().st_mtime,
            )
            if fila:
                print("\nArquivos disponíveis no /inbox:")
                for f in fila:
                    print(f"  - {f.name}")
            sys.exit(1)
        print(f'Busca "{args.busca}" → {audio_path.name}')
        restantes = 0
    else:
        # Modo padrão: arquivo mais antigo
        fila = sorted(
            (f for f in DIR_INBOX.iterdir()
             if f.is_file() and f.suffix.lower() in AUDIO_EXTENSOES),
            key=lambda f: f.stat().st_mtime,
        )
        if not fila:
            print("Nenhum arquivo de áudio encontrado em /inbox.")
            print(f"Extensões aceitas: {', '.join(sorted(AUDIO_EXTENSOES))}")
            return
        audio_path = fila[0]
        restantes  = len(fila) - 1

    print(f"Próximo na fila : {audio_path.name}")
    if restantes:
        print(f"Aguardando      : {restantes} arquivo(s) restante(s) na inbox")

    try:
        aprovado = processar_arquivo(audio_path)
        status   = "Publicado" if aprovado else "Rejeitado"
        print(f"\n{'=' * 60}")
        print(f"  {status}: {audio_path.name}")
        if restantes:
            print(f"  Execute novamente para processar o próximo arquivo.")
        print(f"{'=' * 60}")

    except Exception as e:
        erro_completo = traceback.format_exc()
        log_path = _salvar_log_erro(audio_path.name, erro_completo)

        mensagem_curta = str(e)[:100]
        _notificar_erro(
            titulo="Pipeline — Erro",
            mensagem=f"{audio_path.name}: {mensagem_curta}",
        )

        print(f"\n[ERRO] {e}", file=sys.stderr)
        print(f"Log salvo em: {log_path}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
