"""
gui.py
Interface gráfica do pipeline OvxrNight — CustomTkinter.

Uso:
    python gui.py
"""

import os
import shutil
import subprocess
import threading
import traceback
import queue as _queue
from datetime import datetime
from pathlib import Path
from typing import Optional, Callable

import customtkinter as ctk
from PIL import Image

# ── Tema ──────────────────────────────────────────────────────────────────────
ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("dark-blue")

# ── Cores ──────────────────────────────────────────────────────────────────────
BG_APP     = "#0E1120"
BG_PANEL   = "#151829"
BG_CARD    = "#1C2138"
BG_INPUT   = "#232840"
BG_ROW     = "#181E35"
BG_ROW_SEL = "#1E2A50"
ACCENT     = "#7B5CF0"
ACCENT_HOV = "#6A4EDA"
TEXT_MAIN  = "#E2E8F0"
TEXT_DIM   = "#8892A4"
TEXT_GREEN = "#22C55E"
TEXT_RED   = "#EF4444"
TEXT_AMBER = "#F59E0B"
BORDER     = "#252D48"

# ── Fontes ─────────────────────────────────────────────────────────────────────
F_TITLE  = ("Segoe UI", 20, "bold")
F_H2     = ("Segoe UI", 13, "bold")
F_BODY   = ("Segoe UI", 12)
F_SMALL  = ("Segoe UI", 11)
F_LABEL  = ("Segoe UI", 10, "bold")
F_MONO   = ("Consolas", 10)
F_BADGE  = ("Segoe UI", 9,  "bold")
F_ACCENT = ("Segoe UI", 10, "bold")


# ── Pipeline Worker ────────────────────────────────────────────────────────────

class PipelineWorker(threading.Thread):
    """Executa o pipeline em background. Usa callbacks thread-safe via _post()."""

    def __init__(
        self,
        audio_path: Path,
        post:       Callable,          # fn para enfileirar callbacks na GUI
        on_log:     Callable[[str], None],
        on_step:    Callable[[int, str], None],
        on_meta:    Callable[[dict], None],
        on_img:     Callable[[str, dict], None],
        on_vid:     Callable[[str], None],
        on_done_ok: Callable[[str], None],
        on_done_ko: Callable[[str], None],
    ):
        super().__init__(daemon=True)
        self.audio_path   = audio_path
        self._post        = post
        self._on_log      = on_log
        self._on_step     = on_step
        self._on_meta     = on_meta
        self._on_img      = on_img
        self._on_vid      = on_vid
        self._on_done_ok  = on_done_ok
        self._on_done_ko  = on_done_ko

        self._titulo_editado: str  = ""
        self._decisao_img:    str  = ""
        self._decisao_vid:    str  = ""
        self._cancelled:      bool = False

        self._evt_titulo = threading.Event()
        self._evt_imagem = threading.Event()
        self._evt_video  = threading.Event()

    # API para a GUI enviar decisões
    def set_titulo(self, titulo: str):
        self._titulo_editado = titulo
        self._evt_titulo.set()

    def set_decisao_imagem(self, d: str):
        self._decisao_img = d
        self._evt_imagem.set()

    def set_decisao_video(self, d: str):
        self._decisao_vid = d
        self._evt_video.set()

    def cancel(self):
        self._cancelled = True
        for e in (self._evt_titulo, self._evt_imagem, self._evt_video):
            e.set()

    def _cb(self, fn, *args):
        self._post(lambda: fn(*args))

    def run(self):
        import json as _json
        from image_generator    import gerar_imagem
        from ken_burns           import aplicar_ken_burns
        from metadata_generator  import gerar_metadados, NOME_CANAL
        from youtube_uploader    import publicar_video

        nome           = self.audio_path.name
        DIR_PROCESSING = Path("processing")
        DIR_REVIEW     = Path("review")
        DIR_REJECTED   = Path("rejected")
        DIR_LOGS       = Path("logs")

        DIR_PROCESSING.mkdir(exist_ok=True)
        audio_proc = DIR_PROCESSING / nome
        shutil.move(str(self.audio_path), str(audio_proc))

        def devolver():
            try:
                shutil.move(str(audio_proc), str(self.audio_path))
            except Exception:
                pass

        def limpar(manter=None):
            for f in DIR_PROCESSING.iterdir():
                if manter and f.resolve() == Path(manter).resolve():
                    continue
                try:
                    f.unlink()
                except Exception:
                    pass

        try:
            # [1] Metadados
            self._cb(self._on_step, 0, "running")
            self._cb(self._on_log, f"[1/4] Gerando metadados — {nome}")
            meta = gerar_metadados(nome)
            self._cb(self._on_step, 0, "done")
            self._cb(self._on_log, f"  Título: {meta['titulo']}")
            self._cb(self._on_meta, meta)
            self._evt_titulo.wait()
            if self._cancelled:
                devolver()
                return

            if self._titulo_editado:
                old = meta["titulo"]
                meta["titulo"] = f"｜ {self._titulo_editado} ｜ slowed + reverb - vers {NOME_CANAL}"
                meta["descricao"] = meta["descricao"].replace(old, meta["titulo"])
            self._cb(self._on_log, f"  Título final: {meta['titulo']}")

            # Duração do áudio
            res = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(audio_proc)],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(f"ffprobe: {res.stderr}")
            duracao = 0
            for s in _json.loads(res.stdout).get("streams", []):
                d = s.get("duration")
                if d:
                    duracao = int(float(d))
                    break
            if not duracao:
                raise RuntimeError("Duração do áudio não encontrada.")
            self._cb(self._on_log, f"  Duração: {duracao}s")

            # [2] Imagem — loop de aprovação
            tentativa = 0
            while True:
                tentativa += 1
                self._cb(self._on_step, 1, "running")
                self._evt_imagem.clear()
                self._cb(self._on_log, f"[2/4] Gerando imagem (tentativa {tentativa})...")
                img_path, img_meta = gerar_imagem(
                    destino=str(DIR_PROCESSING / "imagem_gerada.png")
                )
                self._cb(self._on_step, 1, "done")
                self._cb(self._on_log, f"  Personagem: {img_meta.get('personagem','')}")
                self._cb(self._on_log, f"  Cenário   : {img_meta.get('cenario','')}")
                self._cb(self._on_img, img_path, img_meta)
                self._evt_imagem.wait()
                if self._cancelled:
                    devolver()
                    return
                if self._decisao_img == "s":
                    break
                elif self._decisao_img == "d":
                    self._cb(self._on_step, 1, "error")
                    devolver()
                    limpar()
                    self._cb(self._on_log, "  Descartado. Áudio devolvido ao /inbox.")
                    self._cb(self._on_done_ko, "descartado")
                    return

            # [3] Ken Burns
            self._cb(self._on_step, 2, "running")
            self._cb(self._on_log, "[3/4] Aplicando Ken Burns...")
            video_anim = str(DIR_PROCESSING / "video_animado.mp4")
            aplicar_ken_burns(
                imagem=img_path, duracao=duracao, saida=video_anim,
                fps=60, resolucao="1920x1080",
            )
            self._cb(self._on_log, "  Vídeo animado gerado.")

            self._cb(self._on_log, "[4a] Combinando áudio + vídeo...")
            nome_final  = Path(nome).stem + "_final.mp4"
            video_final = DIR_PROCESSING / nome_final
            res = subprocess.run(
                ["ffmpeg", "-y", "-i", str(video_anim), "-i", str(audio_proc),
                 "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                 str(video_final)],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg: {res.stderr[-600:]}")
            self._cb(self._on_step, 2, "done")

            DIR_REVIEW.mkdir(exist_ok=True)
            video_review = DIR_REVIEW / nome_final
            shutil.move(str(video_final), str(video_review))
            limpar(manter=audio_proc)
            self._cb(self._on_log, f"  Vídeo pronto: {video_review.name}")
            self._cb(self._on_vid, str(video_review))

            self._evt_video.wait()
            if self._cancelled:
                devolver()
                return

            if self._decisao_vid != "s":
                DIR_REJECTED.mkdir(exist_ok=True)
                shutil.move(str(video_review), str(DIR_REJECTED / nome_final))
                devolver()
                limpar()
                self._cb(self._on_log, "  Rejeitado. Áudio devolvido ao /inbox.")
                self._cb(self._on_done_ko, "rejeitado")
                return

            # [4] Upload
            self._cb(self._on_step, 3, "running")
            self._cb(self._on_log, "[4/4] Publicando no YouTube...")
            resultado = publicar_video(
                video_path=str(video_review),
                titulo=meta["titulo"],
                descricao=meta["descricao"],
                tags=meta["tags"],
            )
            self._cb(self._on_step, 3, "done")

            DIR_LOGS.mkdir(exist_ok=True)
            agora = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            (DIR_LOGS / f"publicado_{Path(nome).stem}_{agora}.txt").write_text(
                f"Arquivo  : {nome}\nTítulo   : {resultado['titulo']}\n"
                f"Video ID : {resultado['video_id']}\nURL      : {resultado['url']}\n"
                f"Horário  : {agora}\n\nPrompt:\n{img_meta.get('prompt_completo','')}\n",
                encoding="utf-8",
            )
            limpar()
            self._cb(self._on_log, f"  ✓ Publicado: {resultado['url']}")
            self._cb(self._on_done_ok, resultado["url"])

        except Exception:
            err = traceback.format_exc()
            devolver()
            self._cb(self._on_log, f"[ERRO] {err.splitlines()[-1]}")
            self._cb(self._on_done_ko, err.splitlines()[-1])
            for i in range(4):
                self._cb(self._on_step, i, "error")


# ── Widgets auxiliares ────────────────────────────────────────────────────────

def _section_label(parent, text: str) -> ctk.CTkLabel:
    return ctk.CTkLabel(
        parent, text=text.upper(), font=F_ACCENT,
        text_color=ACCENT, anchor="w",
    )


def _divider(parent):
    return ctk.CTkFrame(parent, height=1, fg_color=BORDER, corner_radius=0)


class TrackRow(ctk.CTkFrame):
    """Linha de fila — ícone, índice.nome, data."""

    def __init__(self, parent, index: int, f: Path, selected: bool, **kw):
        bg = BG_ROW_SEL if selected else BG_ROW
        super().__init__(parent, fg_color=bg, corner_radius=4, **kw)

        if selected:
            bar = ctk.CTkFrame(self, width=3, fg_color=ACCENT, corner_radius=0)
            bar.pack(side="left", fill="y", padx=(0, 4))

        icon_color = ACCENT if selected else TEXT_DIM
        ctk.CTkLabel(self, text="♪", font=F_BODY, text_color=icon_color, width=22
                     ).pack(side="left", padx=(6 if not selected else 2, 2), pady=6)

        stem = f.stem
        display = f"{index:02d}. {stem}" if len(stem) <= 26 else f"{index:02d}. {stem[:24]}…"
        ctk.CTkLabel(self, text=display, font=F_SMALL,
                     text_color=TEXT_MAIN if selected else TEXT_DIM, anchor="w"
                     ).pack(side="left", fill="x", expand=True, padx=2)

        date_str = datetime.fromtimestamp(f.stat().st_mtime).strftime("%d/%m/%Y")
        ctk.CTkLabel(self, text=date_str, font=F_SMALL, text_color=TEXT_DIM, width=68
                     ).pack(side="right", padx=6)


class StepRow(ctk.CTkFrame):
    """Linha de status do pipeline — número, nome, badge."""

    CONFIGS = {
        "idle":    (TEXT_DIM,  "PENDING", TEXT_DIM,   "#1E2340", "transparent"),
        "running": (TEXT_MAIN, "ACTIVE",  TEXT_MAIN,  ACCENT,    BG_ROW_SEL),
        "done":    (TEXT_MAIN, "OK",      TEXT_GREEN,  "#153020", "transparent"),
        "error":   (TEXT_RED,  "ERROR",   TEXT_RED,   "#301515", "transparent"),
    }

    def __init__(self, parent, number: int, label: str, **kw):
        super().__init__(parent, fg_color="transparent", corner_radius=4, **kw)
        self.columnconfigure(0, weight=1)
        self.columnconfigure(1, weight=0)

        self._lbl = ctk.CTkLabel(self, text=f"{number}. {label}", font=F_BODY,
                                 text_color=TEXT_DIM, anchor="w")
        self._lbl.grid(row=0, column=0, sticky="w", padx=12, pady=8)

        self._badge = ctk.CTkLabel(self, text="PENDING", font=F_BADGE,
                                   text_color=TEXT_DIM, fg_color="#1E2340",
                                   corner_radius=4, width=58, height=20)
        self._badge.grid(row=0, column=1, padx=12, pady=8)

    def set_status(self, status: str):
        tc, bt, btc, bbg, rbg = self.CONFIGS.get(status, self.CONFIGS["idle"])
        self._lbl.configure(text_color=tc)
        self._badge.configure(text=bt, text_color=btc, fg_color=bbg)
        self.configure(fg_color=rbg)


# ── App principal ─────────────────────────────────────────────────────────────

class OvxrNightApp(ctk.CTk):

    def __init__(self):
        super().__init__()
        self.title("OvxrNight Control Center v1.0")
        self.geometry("1440x900")
        self.minsize(1280, 800)
        self.configure(fg_color=BG_APP)

        self._worker: Optional[PipelineWorker] = None
        self._current_audio: Optional[Path]    = None
        self._video_path: Optional[str]        = None

        # Fila de callbacks GUI (thread-safe)
        self._q: _queue.Queue = _queue.Queue()
        self.after(40, self._drain)

        self._build_ui()
        self._refresh_queue()
        self._refresh_history()
        self.after(6000, self._auto_refresh)

    # ── Queue drain ───────────────────────────────────────────────────────────

    def _drain(self):
        try:
            while True:
                self._q.get_nowait()()
        except _queue.Empty:
            pass
        self.after(40, self._drain)

    def _post(self, fn: Callable):
        self._q.put(fn)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=0, minsize=310)
        self.grid_columnconfigure(1, weight=1)
        self.grid_columnconfigure(2, weight=0, minsize=330)
        self.grid_rowconfigure(0, weight=1)

        self._build_left().grid(row=0, column=0, sticky="nsew")
        ctk.CTkFrame(self, width=1, fg_color=BORDER, corner_radius=0
                     ).grid(row=0, column=0, sticky="nse")

        self._build_center().grid(row=0, column=1, sticky="nsew", padx=1)

        ctk.CTkFrame(self, width=1, fg_color=BORDER, corner_radius=0
                     ).grid(row=0, column=2, sticky="nsw")
        self._build_right().grid(row=0, column=2, sticky="nsew")

    # ── Left Panel ────────────────────────────────────────────────────────────

    def _build_left(self) -> ctk.CTkFrame:
        pnl = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0)
        pnl.grid_rowconfigure(1, weight=1)
        pnl.grid_columnconfigure(0, weight=1)

        # Header
        hdr = ctk.CTkFrame(pnl, fg_color="transparent", corner_radius=0)
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        _section_label(hdr, "Queue Management").pack(side="left")
        ctk.CTkLabel(hdr, text="⚙", font=F_BODY, text_color=TEXT_DIM
                     ).pack(side="right")

        # Inbox sub-header
        sub = ctk.CTkFrame(pnl, fg_color=BG_CARD, corner_radius=6)
        sub.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 4))
        sub.grid_columnconfigure(0, weight=1)

        sub_row = ctk.CTkFrame(sub, fg_color="transparent")
        sub_row.grid(row=0, column=0, sticky="ew", padx=12, pady=(8, 2))
        self.lbl_inbox_count = ctk.CTkLabel(
            sub_row, text="INBOX", font=F_LABEL, text_color=TEXT_MAIN, anchor="w"
        )
        self.lbl_inbox_count.pack(side="left")
        ctk.CTkLabel(sub_row, text="···", font=F_BODY, text_color=TEXT_DIM
                     ).pack(side="right")
        ctk.CTkLabel(sub, text="Ordenado do mais antigo", font=F_SMALL,
                     text_color=TEXT_DIM, anchor="w"
                     ).grid(row=1, column=0, sticky="w", padx=12, pady=(0, 8))

        # Queue scroll area
        self.queue_scroll = ctk.CTkScrollableFrame(
            pnl, fg_color="transparent", scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        self.queue_scroll.grid(row=2, column=0, sticky="nsew", padx=12, pady=4)
        pnl.grid_rowconfigure(2, weight=1)

        _divider(pnl).grid(row=3, column=0, sticky="ew", padx=12, pady=6)

        # History
        hist_hdr = ctk.CTkFrame(pnl, fg_color="transparent")
        hist_hdr.grid(row=4, column=0, sticky="ew", padx=16, pady=(4, 6))
        _section_label(hist_hdr, "History").pack(side="left")

        ctk.CTkLabel(pnl, text="PUBLISHED", font=F_BADGE,
                     text_color=TEXT_GREEN, anchor="w"
                     ).grid(row=5, column=0, sticky="w", padx=16, pady=(0, 4))

        self.scroll_published = ctk.CTkScrollableFrame(
            pnl, fg_color="transparent", height=100,
            scrollbar_button_color=BORDER,
        )
        self.scroll_published.grid(row=6, column=0, sticky="ew", padx=12, pady=(0, 6))

        ctk.CTkLabel(pnl, text="REJECTED", font=F_BADGE,
                     text_color=TEXT_RED, anchor="w"
                     ).grid(row=7, column=0, sticky="w", padx=16, pady=(0, 4))

        self.scroll_rejected = ctk.CTkScrollableFrame(
            pnl, fg_color="transparent", height=80,
            scrollbar_button_color=BORDER,
        )
        self.scroll_rejected.grid(row=8, column=0, sticky="ew", padx=12, pady=(0, 14))

        return pnl

    # ── Center Panel ──────────────────────────────────────────────────────────

    def _build_center(self) -> ctk.CTkFrame:
        pnl = ctk.CTkFrame(self, fg_color=BG_APP, corner_radius=0)
        pnl.grid_columnconfigure(0, weight=1)
        pnl.grid_rowconfigure(2, weight=1)

        # Workspace header
        wk = ctk.CTkFrame(pnl, fg_color="transparent")
        wk.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 4))
        ctk.CTkLabel(wk, text="ACTIVE WORKSPACE", font=F_ACCENT,
                     text_color=ACCENT, anchor="w"
                     ).pack(anchor="w")
        self.lbl_song_title = ctk.CTkLabel(
            wk, text="Nenhum arquivo selecionado",
            font=F_TITLE, text_color=TEXT_MAIN, anchor="w", wraplength=660,
        )
        self.lbl_song_title.pack(anchor="w", pady=(2, 0))

        # Start button
        self.btn_start = ctk.CTkButton(
            pnl, text="▶   Iniciar Pipeline",
            font=F_H2, fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="#FFFFFF", height=38, corner_radius=6,
            state="disabled", command=self._on_start,
        )
        self.btn_start.grid(row=1, column=0, sticky="e", padx=20, pady=(0, 12))

        # Scroll for center content
        scroll = ctk.CTkScrollableFrame(
            pnl, fg_color="transparent",
            scrollbar_button_color=BORDER,
            scrollbar_button_hover_color=ACCENT,
        )
        scroll.grid(row=2, column=0, sticky="nsew", padx=8, pady=0)
        scroll.grid_columnconfigure(0, weight=1)
        scroll.grid_columnconfigure(1, weight=1)

        # Metadata card
        self._build_metadata_card(scroll).grid(
            row=0, column=0, sticky="nsew", padx=(8, 4), pady=8
        )

        # Image review card
        self._build_image_card(scroll).grid(
            row=0, column=1, sticky="nsew", padx=(4, 8), pady=8
        )

        # Video preview card (full width)
        self._build_video_card(scroll).grid(
            row=1, column=0, columnspan=2, sticky="ew", padx=8, pady=(0, 12)
        )

        return pnl

    def _build_metadata_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        card.grid_columnconfigure(0, weight=1)

        _section_label(card, "Metadata Edit").grid(
            row=0, column=0, sticky="w", padx=14, pady=(14, 8)
        )

        # Title row
        ctk.CTkLabel(card, text="Title", font=F_LABEL,
                     text_color=TEXT_DIM, anchor="w"
                     ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 4))

        title_row = ctk.CTkFrame(card, fg_color="transparent")
        title_row.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 10))
        title_row.grid_columnconfigure(0, weight=1)

        self.entry_titulo = ctk.CTkEntry(
            title_row, placeholder_text="Artista - Nome da Música",
            font=F_BODY, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_MAIN, height=36,
        )
        self.entry_titulo.grid(row=0, column=0, sticky="ew", padx=(0, 8))

        self.btn_confirm_inline = ctk.CTkButton(
            title_row, text="Confirm Title",
            font=F_SMALL, fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="#FFFFFF", height=36, width=110, corner_radius=6,
            state="disabled", command=self._on_confirm_meta,
        )
        self.btn_confirm_inline.grid(row=0, column=1)

        # Description
        ctk.CTkLabel(card, text="Description", font=F_LABEL,
                     text_color=TEXT_DIM, anchor="w"
                     ).grid(row=3, column=0, sticky="w", padx=14, pady=(0, 4))
        self.txt_desc = ctk.CTkTextbox(
            card, height=80, font=F_BODY,
            fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_MAIN, border_width=1,
        )
        self.txt_desc.grid(row=4, column=0, sticky="ew", padx=14, pady=(0, 10))

        # Tags
        ctk.CTkLabel(card, text="Tags", font=F_LABEL,
                     text_color=TEXT_DIM, anchor="w"
                     ).grid(row=5, column=0, sticky="w", padx=14, pady=(0, 4))
        self.entry_tags = ctk.CTkEntry(
            card, placeholder_text="slowed, reverb, anime, ...",
            font=F_BODY, fg_color=BG_INPUT, border_color=BORDER,
            text_color=TEXT_MAIN, height=36,
        )
        self.entry_tags.grid(row=6, column=0, sticky="ew", padx=14, pady=(0, 12))

        # Confirm button full width
        self.btn_confirm_full = ctk.CTkButton(
            card, text="Confirm Title",
            font=F_H2, fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="#FFFFFF", height=42, corner_radius=6,
            state="disabled", command=self._on_confirm_meta,
        )
        self.btn_confirm_full.grid(row=7, column=0, sticky="ew", padx=14, pady=(0, 14))

        return card

    def _build_image_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        card.grid_columnconfigure(0, weight=1)

        _section_label(card, "Image Review").grid(
            row=0, column=0, sticky="w", padx=14, pady=(14, 8)
        )

        # Image preview area
        img_container = ctk.CTkFrame(card, fg_color=BG_INPUT, corner_radius=8, height=200)
        img_container.grid(row=1, column=0, sticky="ew", padx=14, pady=(0, 10))
        img_container.grid_propagate(False)
        img_container.grid_columnconfigure(0, weight=1)
        img_container.grid_rowconfigure(0, weight=1)

        self.lbl_img_preview = ctk.CTkLabel(
            img_container, text="Aguardando geração da imagem...",
            font=F_BODY, text_color=TEXT_DIM,
            image=None,
        )
        self.lbl_img_preview.grid(row=0, column=0, sticky="nsew", padx=8, pady=8)

        # Prompt elements
        prompt_frame = ctk.CTkFrame(card, fg_color="transparent")
        prompt_frame.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 8))
        ctk.CTkLabel(prompt_frame, text="Prompt Elements:", font=F_LABEL,
                     text_color=TEXT_DIM, anchor="w"
                     ).pack(anchor="w")

        self.lbl_img_char  = ctk.CTkLabel(prompt_frame, text="Character: —",
                                          font=F_SMALL, text_color=TEXT_DIM, anchor="w")
        self.lbl_img_scene = ctk.CTkLabel(prompt_frame, text="Scene: —",
                                          font=F_SMALL, text_color=TEXT_DIM, anchor="w")
        self.lbl_img_style = ctk.CTkLabel(prompt_frame, text="Style: —",
                                          font=F_SMALL, text_color=TEXT_DIM, anchor="w")
        for lbl in (self.lbl_img_char, self.lbl_img_scene, self.lbl_img_style):
            lbl.pack(anchor="w", pady=1)

        # Image action buttons
        btn_row = ctk.CTkFrame(card, fg_color="transparent")
        btn_row.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 14))
        btn_row.grid_columnconfigure((0, 1, 2), weight=1)

        self.btn_img_ok = ctk.CTkButton(
            btn_row, text="Aprovar", font=F_SMALL,
            fg_color="#0A6B52", hover_color="#0D8568",
            text_color="#FFFFFF", height=34, corner_radius=6,
            state="disabled", command=lambda: self._on_img_decision("s"),
        )
        self.btn_img_ok.grid(row=0, column=0, sticky="ew", padx=(0, 4))

        self.btn_img_new = ctk.CTkButton(
            btn_row, text="Nova Imagem", font=F_SMALL,
            fg_color="#1E4070", hover_color="#265090",
            text_color="#FFFFFF", height=34, corner_radius=6,
            state="disabled", command=lambda: self._on_img_decision("n"),
        )
        self.btn_img_new.grid(row=0, column=1, sticky="ew", padx=4)

        self.btn_img_del = ctk.CTkButton(
            btn_row, text="Descartar", font=F_SMALL,
            fg_color="#7A1515", hover_color="#9A1A1A",
            text_color="#FFFFFF", height=34, corner_radius=6,
            state="disabled", command=lambda: self._on_img_decision("d"),
        )
        self.btn_img_del.grid(row=0, column=2, sticky="ew", padx=(4, 0))

        return card

    def _build_video_card(self, parent) -> ctk.CTkFrame:
        card = ctk.CTkFrame(parent, fg_color=BG_CARD, corner_radius=10)
        card.grid_columnconfigure(0, weight=3)
        card.grid_columnconfigure(1, weight=2)

        _section_label(card, "Video Preview").grid(
            row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8)
        )

        # Video display area
        vid_area = ctk.CTkFrame(card, fg_color=BG_INPUT, corner_radius=8, height=180)
        vid_area.grid(row=1, column=0, sticky="nsew", padx=(14, 6), pady=(0, 8))
        vid_area.grid_propagate(False)
        vid_area.grid_columnconfigure(0, weight=1)
        vid_area.grid_rowconfigure(0, weight=1)

        self.lbl_vid_preview = ctk.CTkLabel(
            vid_area, text="Aguardando vídeo...",
            font=F_BODY, text_color=TEXT_DIM,
        )
        self.lbl_vid_preview.grid(row=0, column=0, sticky="nsew")

        # Progress bar
        self.vid_progress = ctk.CTkProgressBar(
            card, fg_color=BG_INPUT, progress_color=ACCENT,
            height=4, corner_radius=2,
        )
        self.vid_progress.set(0)
        self.vid_progress.grid(row=2, column=0, sticky="ew", padx=14, pady=(0, 6))

        # Player controls
        ctrl = ctk.CTkFrame(card, fg_color="transparent")
        ctrl.grid(row=3, column=0, sticky="ew", padx=14, pady=(0, 10))

        self.btn_vid_play = ctk.CTkButton(
            ctrl, text="▶", font=F_BODY, width=36, height=30,
            fg_color=BG_INPUT, hover_color="#2A3255",
            text_color=TEXT_DIM, corner_radius=4,
            command=self._on_open_video,
        )
        self.btn_vid_play.pack(side="left", padx=(0, 4))
        for sym in ("⏸", "⏭"):
            ctk.CTkButton(ctrl, text=sym, font=F_BODY, width=30, height=30,
                          fg_color=BG_INPUT, hover_color="#2A3255",
                          text_color=TEXT_DIM, corner_radius=4,
                          ).pack(side="left", padx=2)

        ctk.CTkButton(ctrl, text="🔊", font=F_BODY, width=30, height=30,
                      fg_color=BG_INPUT, hover_color="#2A3255",
                      text_color=TEXT_DIM, corner_radius=4,
                      ).pack(side="right", padx=2)
        ctk.CTkButton(ctrl, text="⛶", font=F_BODY, width=30, height=30,
                      fg_color=BG_INPUT, hover_color="#2A3255",
                      text_color=TEXT_DIM, corner_radius=4,
                      ).pack(side="right", padx=2)

        # Right side — publish/reject
        right = ctk.CTkFrame(card, fg_color="transparent")
        right.grid(row=1, column=1, rowspan=3, sticky="nsew", padx=(6, 14), pady=(0, 10))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(0, weight=1)

        self.lbl_vid_name = ctk.CTkLabel(
            right, text="—", font=F_SMALL, text_color=TEXT_DIM,
            anchor="w", wraplength=260,
        )
        self.lbl_vid_name.grid(row=0, column=0, sticky="ew", pady=(4, 8))

        ctk.CTkButton(
            right, text="📁  Abrir /review",
            font=F_SMALL, fg_color=BG_INPUT, hover_color="#2A3255",
            text_color=TEXT_DIM, height=32, corner_radius=6,
            command=self._on_open_review,
        ).grid(row=1, column=0, sticky="ew", pady=(0, 12))

        self.btn_publish = ctk.CTkButton(
            right, text="▶   Publicar no YouTube",
            font=F_H2, fg_color=ACCENT, hover_color=ACCENT_HOV,
            text_color="#FFFFFF", height=42, corner_radius=6,
            state="disabled", command=lambda: self._on_vid_decision("s"),
        )
        self.btn_publish.grid(row=2, column=0, sticky="ew", pady=(0, 8))

        self.btn_reject_vid = ctk.CTkButton(
            right, text="✗  Descartar Vídeo",
            font=F_SMALL, fg_color="#7A1515", hover_color="#9A1A1A",
            text_color="#FFFFFF", height=36, corner_radius=6,
            state="disabled", command=lambda: self._on_vid_decision("n"),
        )
        self.btn_reject_vid.grid(row=3, column=0, sticky="ew")

        return card

    # ── Right Panel ───────────────────────────────────────────────────────────

    def _build_right(self) -> ctk.CTkFrame:
        pnl = ctk.CTkFrame(self, fg_color=BG_PANEL, corner_radius=0)
        pnl.grid_columnconfigure(0, weight=1)
        pnl.grid_rowconfigure(2, weight=1)

        # Header
        hdr = ctk.CTkFrame(pnl, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 8))
        _section_label(hdr, "Pipeline Monitoring").pack(side="left")
        ctk.CTkLabel(hdr, text="ⓘ", font=F_BODY, text_color=TEXT_DIM).pack(side="right")

        # Task Status
        status_card = ctk.CTkFrame(pnl, fg_color=BG_CARD, corner_radius=8)
        status_card.grid(row=1, column=0, sticky="ew", padx=12, pady=(0, 10))
        status_card.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(status_card, text="TASK STATUS", font=F_BADGE,
                     text_color=TEXT_DIM, anchor="w"
                     ).grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))

        self.step_rows: list[StepRow] = []
        for i, name in enumerate(["Metadata", "Image", "Video", "Upload"]):
            row = StepRow(status_card, i + 1, name)
            row.grid(row=i + 1, column=0, sticky="ew", padx=4, pady=1)
            self.step_rows.append(row)

        ctk.CTkFrame(status_card, height=6, fg_color="transparent"
                     ).grid(row=5, column=0)

        # Real-time log
        log_hdr = ctk.CTkFrame(pnl, fg_color="transparent")
        log_hdr.grid(row=2, column=0, sticky="new", padx=16, pady=(4, 6))
        _section_label(log_hdr, "Real-Time Log").pack(side="left")
        ctk.CTkButton(log_hdr, text="Limpar", font=F_SMALL, width=60, height=24,
                      fg_color=BG_INPUT, hover_color="#2A3255", text_color=TEXT_DIM,
                      corner_radius=4, command=self._clear_log,
                      ).pack(side="right")

        self.log_box = ctk.CTkTextbox(
            pnl, fg_color=BG_CARD, text_color=TEXT_DIM,
            font=F_MONO, border_width=1, border_color=BORDER,
            corner_radius=8, wrap="none",
        )
        self.log_box.grid(row=3, column=0, sticky="nsew", padx=12, pady=(0, 12))
        pnl.grid_rowconfigure(3, weight=1)

        return pnl

    # ── Refresh ───────────────────────────────────────────────────────────────

    def _auto_refresh(self):
        self._refresh_queue()
        self.after(6000, self._auto_refresh)

    def _refresh_queue(self):
        DIR_INBOX = Path("inbox")
        DIR_INBOX.mkdir(exist_ok=True)
        exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
        queue = sorted(
            (f for f in DIR_INBOX.iterdir() if f.is_file() and f.suffix.lower() in exts),
            key=lambda f: f.stat().st_mtime,
        )

        for w in self.queue_scroll.winfo_children():
            w.destroy()

        for i, f in enumerate(queue):
            row = TrackRow(self.queue_scroll, i + 1, f, selected=(i == 0))
            row.pack(fill="x", padx=4, pady=2)

        n = len(queue)
        self.lbl_inbox_count.configure(
            text=f"INBOX  ({n} {'Track' if n == 1 else 'Tracks'})"
        )

        running = self._worker is not None and self._worker.is_alive()
        if queue:
            self._current_audio = queue[0]
            stem = queue[0].stem
            display = stem if len(stem) <= 50 else stem[:48] + "…"
            self.lbl_song_title.configure(text=display, text_color=TEXT_MAIN)
            self.btn_start.configure(state="normal" if not running else "disabled")
        else:
            self._current_audio = None
            self.lbl_song_title.configure(text="Inbox vazia", text_color=TEXT_DIM)
            self.btn_start.configure(state="disabled")

    def _refresh_history(self):
        DIR_LOGS     = Path("logs");     DIR_LOGS.mkdir(exist_ok=True)
        DIR_REJECTED = Path("rejected"); DIR_REJECTED.mkdir(exist_ok=True)

        for w in self.scroll_published.winfo_children():
            w.destroy()
        for f in sorted(DIR_LOGS.glob("publicado_*.txt"),
                        key=lambda x: x.stat().st_mtime, reverse=True)[:12]:
            stem = f.stem[10:]
            ctk.CTkLabel(self.scroll_published, text=stem, font=F_SMALL,
                         text_color=TEXT_GREEN, anchor="w",
                         ).pack(fill="x", padx=6, pady=1)

        for w in self.scroll_rejected.winfo_children():
            w.destroy()
        for f in sorted(DIR_REJECTED.glob("*_final.mp4"),
                        key=lambda x: x.stat().st_mtime, reverse=True)[:8]:
            name = f.stem[:-6]
            ctk.CTkLabel(self.scroll_rejected, text=f"♪  {name}", font=F_SMALL,
                         text_color=TEXT_RED, anchor="w",
                         ).pack(fill="x", padx=6, pady=1)

    # ── Pipeline ──────────────────────────────────────────────────────────────

    def _on_start(self):
        if not self._current_audio or not self._current_audio.exists():
            self._refresh_queue()
            return

        self._reset_ui()

        self._worker = PipelineWorker(
            audio_path  = self._current_audio,
            post        = self._post,
            on_log      = self._append_log,
            on_step     = self._update_step,
            on_meta     = self._on_meta_ready,
            on_img      = self._on_img_ready,
            on_vid      = self._on_vid_ready,
            on_done_ok  = self._on_finished_ok,
            on_done_ko  = self._on_finished_ko,
        )
        self._worker.start()
        self.btn_start.configure(state="disabled")
        self._append_log(f"Pipeline iniciado: {self._current_audio.name}")

    def _reset_ui(self):
        for row in self.step_rows:
            row.set_status("idle")
        for btn in (self.btn_confirm_inline, self.btn_confirm_full):
            btn.configure(state="disabled")
        for btn in (self.btn_img_ok, self.btn_img_new, self.btn_img_del,
                    self.btn_publish, self.btn_reject_vid):
            btn.configure(state="disabled")

        self.entry_titulo.delete(0, "end")
        self.txt_desc.delete("1.0", "end")
        self.entry_tags.delete(0, "end")
        self.lbl_img_preview.configure(
            text="Aguardando geração da imagem...", image=None
        )
        self.lbl_img_char.configure(text="Character: —")
        self.lbl_img_scene.configure(text="Scene: —")
        self.lbl_img_style.configure(text="Style: —")
        self.lbl_vid_preview.configure(text="Aguardando vídeo...", image=None)
        self.lbl_vid_name.configure(text="—")
        self.vid_progress.set(0)
        self._video_path = None

    # ── Worker callbacks (already on GUI thread via _drain) ───────────────────

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_box.configure(state="normal")
        self.log_box.insert("end", f"[{ts}] {msg}\n")
        self.log_box.see("end")
        self.log_box.configure(state="disabled")

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("1.0", "end")
        self.log_box.configure(state="disabled")

    def _update_step(self, index: int, status: str):
        if 0 <= index < len(self.step_rows):
            self.step_rows[index].set_status(status)

    def _on_meta_ready(self, meta: dict):
        self.entry_titulo.delete(0, "end")
        self.entry_titulo.insert(0, meta.get("titulo", ""))
        self.txt_desc.delete("1.0", "end")
        self.txt_desc.insert("1.0", meta.get("descricao", ""))
        tags = meta.get("tags", [])
        self.entry_tags.delete(0, "end")
        self.entry_tags.insert(0, ", ".join(tags) if isinstance(tags, list) else str(tags))
        for btn in (self.btn_confirm_inline, self.btn_confirm_full):
            btn.configure(state="normal")
        self._append_log("Metadados prontos — edite o título e confirme.")

    def _on_confirm_meta(self):
        titulo = self.entry_titulo.get().strip()
        for btn in (self.btn_confirm_inline, self.btn_confirm_full):
            btn.configure(state="disabled")
        if self._worker:
            self._worker.set_titulo(titulo)
        self._append_log(f"Título confirmado: {titulo or '(mantido)'}")

    def _on_img_ready(self, img_path: str, img_meta: dict):
        try:
            pil = Image.open(img_path)
            pil.thumbnail((340, 200), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=pil, dark_image=pil,
                                   size=(pil.width, pil.height))
            self.lbl_img_preview.configure(image=ctk_img, text="")
            self.lbl_img_preview._image = ctk_img   # keep reference
        except Exception:
            self.lbl_img_preview.configure(text="Erro ao carregar imagem", image=None)

        self.lbl_img_char.configure(text=f"Character: {img_meta.get('personagem','—')}")
        self.lbl_img_scene.configure(text=f"Scene: {img_meta.get('cenario','—')}")
        self.lbl_img_style.configure(text=f"Style: {img_meta.get('estilo','—')}")
        for btn in (self.btn_img_ok, self.btn_img_new, self.btn_img_del):
            btn.configure(state="normal")
        self._append_log("Imagem pronta — avalie e decida.")

    def _on_img_decision(self, decisao: str):
        for btn in (self.btn_img_ok, self.btn_img_new, self.btn_img_del):
            btn.configure(state="disabled")
        if self._worker:
            self._worker.set_decisao_imagem(decisao)
        msgs = {"s": "Imagem aprovada.", "n": "Gerando nova imagem...", "d": "Descartado."}
        self._append_log(msgs.get(decisao, ""))

    def _on_vid_ready(self, video_path: str):
        self._video_path = video_path
        self.lbl_vid_name.configure(text=Path(video_path).name)
        self.lbl_vid_preview.configure(
            text="▶  Vídeo pronto\nAbra /review para assistir", image=None
        )
        self.vid_progress.set(0.6)
        self.btn_vid_play.configure(text_color=ACCENT)
        for btn in (self.btn_publish, self.btn_reject_vid):
            btn.configure(state="normal")
        self._append_log("Vídeo pronto em /review — assista e decida.")

    def _on_vid_decision(self, decisao: str):
        for btn in (self.btn_publish, self.btn_reject_vid):
            btn.configure(state="disabled")
        if self._worker:
            self._worker.set_decisao_video(decisao)
        self._append_log(
            "Publicando no YouTube..." if decisao == "s"
            else "Vídeo rejeitado. Devolvendo áudio ao /inbox."
        )

    def _on_finished_ok(self, url: str):
        self._append_log(f"✓ Publicado: {url}")
        self.vid_progress.set(1.0)
        self.btn_start.configure(state="normal")
        self._refresh_queue()
        self._refresh_history()
        self._show_dialog("Publicado!", f"Vídeo publicado com sucesso!\n\n{url}")

    def _on_finished_ko(self, msg: str):
        if msg not in ("descartado", "rejeitado"):
            self._append_log(f"✗ Erro: {msg}")
            self._show_dialog("Erro", msg[:300])
        self.btn_start.configure(state="normal")
        self._refresh_queue()
        self._refresh_history()

    def _on_open_review(self):
        d = Path("review")
        d.mkdir(exist_ok=True)
        subprocess.Popen(["explorer", str(d.resolve())])

    def _on_open_video(self):
        if self._video_path and Path(self._video_path).exists():
            os.startfile(self._video_path)
        else:
            self._on_open_review()

    def _show_dialog(self, title: str, msg: str):
        dlg = ctk.CTkToplevel(self)
        dlg.title(title)
        dlg.geometry("420x200")
        dlg.configure(fg_color=BG_CARD)
        dlg.grab_set()
        ctk.CTkLabel(dlg, text=title, font=F_H2, text_color=ACCENT
                     ).pack(pady=(20, 6))
        ctk.CTkLabel(dlg, text=msg, font=F_BODY, text_color=TEXT_MAIN,
                     wraplength=380
                     ).pack(pady=6, padx=20)
        ctk.CTkButton(dlg, text="OK", font=F_H2, fg_color=ACCENT,
                      hover_color=ACCENT_HOV, text_color="#FFFFFF",
                      width=100, height=36, corner_radius=6,
                      command=dlg.destroy
                      ).pack(pady=(10, 20))

    def on_closing(self):
        if self._worker and self._worker.is_alive():
            self._worker.cancel()
            self._worker.join(timeout=3)
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = OvxrNightApp()
    app.protocol("WM_DELETE_WINDOW", app.on_closing)
    app.mainloop()


if __name__ == "__main__":
    main()
