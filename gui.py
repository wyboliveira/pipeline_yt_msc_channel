"""
gui.py
Interface gráfica do pipeline OvxrNight.

Uso:
    python gui.py
"""

import sys
import shutil
import subprocess
import threading
import traceback
from datetime import datetime
from pathlib import Path
from typing import Optional

from PyQt6.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QListWidget, QListWidgetItem, QTextEdit, QLineEdit,
    QPushButton, QSplitter, QFrame, QScrollArea, QSizePolicy,
    QMessageBox, QGroupBox,
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QTimer
from PyQt6.QtGui import QPixmap, QColor, QFont


# ── Paleta de cores ────────────────────────────────────────────────────────────

BG_DARK    = "#07090F"   # fundo da janela — quase preto com tint azul
BG_PANEL   = "#0D1525"   # header bar e bordas de seção
BG_CARD    = "#111D35"   # GroupBox / painéis de conteúdo — contraste visível
BG_INPUT   = "#192540"   # campos de input — um tom acima do card
ACCENT     = "#00D4FF"
ACCENT_DIM = "#0099BB"
TEXT_MAIN  = "#E6EDF3"
TEXT_DIM   = "#8B949E"
TEXT_GREEN = "#3FB950"
TEXT_RED   = "#F85149"
TEXT_AMBER = "#D29922"
BORDER     = "#1E2D48"

STYLE = f"""
QMainWindow, QWidget {{
    background-color: {BG_DARK};
    color: {TEXT_MAIN};
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}}
QGroupBox {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    margin-top: 20px;
    padding: 20px 12px 12px 12px;
    font-size: 10px;
    font-weight: bold;
    color: {ACCENT};
    letter-spacing: 1.5px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    top: -10px;
    padding: 2px 8px;
    background-color: {BG_PANEL};
    border: 1px solid {BORDER};
    border-radius: 3px;
}}
QListWidget {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    outline: none;
    color: {TEXT_MAIN};
}}
QListWidget::item {{
    padding: 6px 8px;
    border-bottom: 1px solid {BORDER};
}}
QListWidget::item:selected {{
    background-color: #0E2840;
    color: {ACCENT};
    border-left: 3px solid {ACCENT};
}}
QListWidget::item:hover {{
    background-color: #0D2035;
}}
QLineEdit, QTextEdit {{
    background-color: {BG_INPUT};
    border: 1px solid #3A5275;
    border-radius: 4px;
    padding: 6px 8px;
    color: {TEXT_MAIN};
    selection-background-color: {ACCENT_DIM};
}}
QLineEdit:focus, QTextEdit:focus {{
    border: 2px solid {ACCENT};
}}
QPushButton {{
    background-color: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 7px 14px;
    color: {TEXT_MAIN};
    font-weight: 500;
}}
QPushButton:hover {{
    background-color: #1A2840;
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background-color: #0E2035;
}}
QPushButton:disabled {{
    color: {TEXT_DIM};
    border-color: {BORDER};
    background-color: {BG_CARD};
}}
QPushButton#btn_primary {{
    background-color: {ACCENT};
    color: #000000;
    font-weight: bold;
    border: 2px solid {ACCENT};
}}
QPushButton#btn_primary:hover {{
    background-color: {ACCENT_DIM};
    border-color: {ACCENT_DIM};
}}
QPushButton#btn_primary:disabled {{
    background-color: transparent;
    border: 2px solid {ACCENT_DIM};
    color: {ACCENT_DIM};
    font-weight: bold;
}}
QPushButton#btn_danger {{
    background-color: #8B1A1A;
    border: none;
    color: #FFFFFF;
    font-weight: bold;
}}
QPushButton#btn_danger:hover {{
    background-color: #A82020;
}}
QPushButton#btn_danger:disabled {{
    background-color: #3A1010;
    color: {TEXT_DIM};
}}
QPushButton#btn_success {{
    background-color: #0A6B52;
    border: none;
    color: #FFFFFF;
    font-weight: bold;
}}
QPushButton#btn_success:hover {{
    background-color: #0D856A;
}}
QPushButton#btn_success:disabled {{
    background-color: #0A3028;
    color: {TEXT_DIM};
}}
QPushButton#btn_neutral {{
    background-color: #1E4070;
    border: none;
    color: #FFFFFF;
    font-weight: 500;
}}
QPushButton#btn_neutral:hover {{
    background-color: #265090;
}}
QPushButton#btn_neutral:disabled {{
    background-color: #142840;
    color: {TEXT_DIM};
}}
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    border-radius: 4px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 20px;
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{
    background: {BG_DARK};
    height: 8px;
    border-radius: 4px;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 4px;
    min-width: 20px;
}}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QSplitter::handle {{
    background-color: {BORDER};
}}
QSplitter::handle:horizontal {{
    width: 1px;
}}
"""


# ── Worker Thread ──────────────────────────────────────────────────────────────

class PipelineWorker(QThread):
    """Executa o pipeline em background, pausando para input do usuário via eventos."""

    STEPS = ["Metadados", "Imagem", "Vídeo", "Upload"]

    log         = pyqtSignal(str)
    step_update = pyqtSignal(int, str)   # (index, 'running'|'done'|'error'|'idle')
    meta_ready  = pyqtSignal(dict)
    img_ready   = pyqtSignal(str, dict)  # (path, meta)
    vid_ready   = pyqtSignal(str)
    finished_ok = pyqtSignal(str)        # YouTube URL
    finished_ko = pyqtSignal(str)        # mensagem

    def __init__(self, audio_path: Path):
        super().__init__()
        self.audio_path = audio_path

        self._meta:           dict = {}
        self._titulo_editado: str  = ""
        self._img_path:       str  = ""
        self._img_meta:       dict = {}
        self._video_path:     str  = ""
        self._decisao_img:    str  = ""
        self._decisao_vid:    str  = ""
        self._cancelled:      bool = False

        self._evt_titulo = threading.Event()
        self._evt_imagem = threading.Event()
        self._evt_video  = threading.Event()

    # ── API para a GUI enviar decisões ────────────────────────────────────────

    def set_titulo(self, titulo: str):
        self._titulo_editado = titulo
        self._evt_titulo.set()

    def set_decisao_imagem(self, decisao: str):
        self._decisao_img = decisao
        self._evt_imagem.set()

    def set_decisao_video(self, decisao: str):
        self._decisao_vid = decisao
        self._evt_video.set()

    def cancel(self):
        self._cancelled = True
        self._evt_titulo.set()
        self._evt_imagem.set()
        self._evt_video.set()

    # ── Run ───────────────────────────────────────────────────────────────────

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

        def devolver_audio():
            try:
                shutil.move(str(audio_proc), str(self.audio_path))
            except Exception:
                pass

        def limpar_processing(manter=None):
            for f in DIR_PROCESSING.iterdir():
                if manter and f.resolve() == Path(manter).resolve():
                    continue
                try:
                    f.unlink()
                except Exception:
                    pass

        try:
            # [1] Metadados
            self.step_update.emit(0, "running")
            self.log.emit(f"[1/4] Gerando metadados — {nome}")
            self._meta = gerar_metadados(nome)
            self.step_update.emit(0, "done")
            self.log.emit(f"  Título: {self._meta['titulo']}")

            self.meta_ready.emit(self._meta)
            self._evt_titulo.wait()
            if self._cancelled:
                devolver_audio()
                return

            if self._titulo_editado:
                titulo_antigo = self._meta["titulo"]
                self._meta["titulo"] = (
                    f"｜ {self._titulo_editado} ｜ slowed + reverb - vers {NOME_CANAL}"
                )
                self._meta["descricao"] = self._meta["descricao"].replace(
                    titulo_antigo, self._meta["titulo"]
                )
            self.log.emit(f"  Título final: {self._meta['titulo']}")

            # Duração do áudio
            res = subprocess.run(
                ["ffprobe", "-v", "quiet", "-print_format", "json",
                 "-show_streams", str(audio_proc)],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(f"ffprobe falhou: {res.stderr}")
            duracao = 0
            for stream in _json.loads(res.stdout).get("streams", []):
                d = stream.get("duration")
                if d:
                    duracao = int(float(d))
                    break
            if not duracao:
                raise RuntimeError("Não foi possível obter a duração do áudio.")
            self.log.emit(f"  Duração: {duracao}s")

            # [2] Imagem — loop de aprovação
            tentativa = 0
            while True:
                tentativa += 1
                self.step_update.emit(1, "running")
                self._evt_imagem.clear()
                self.log.emit(f"[2/4] Gerando imagem (tentativa {tentativa})...")

                self._img_path, self._img_meta = gerar_imagem(
                    destino=str(DIR_PROCESSING / "imagem_gerada.png")
                )
                self.step_update.emit(1, "done")
                self.log.emit(f"  Personagem: {self._img_meta.get('personagem', '')}")
                self.log.emit(f"  Cenário   : {self._img_meta.get('cenario', '')}")
                self.log.emit(f"  Estilo    : {self._img_meta.get('estilo', '')}")

                self.img_ready.emit(self._img_path, self._img_meta)
                self._evt_imagem.wait()
                if self._cancelled:
                    devolver_audio()
                    return

                if self._decisao_img == "s":
                    break
                elif self._decisao_img == "d":
                    self.step_update.emit(1, "error")
                    devolver_audio()
                    limpar_processing()
                    self.log.emit("  Música descartada. Áudio devolvido ao /inbox.")
                    self.finished_ko.emit("descartado")
                    return
                # "n" → gera nova imagem

            # [3] Ken Burns
            self.step_update.emit(2, "running")
            self.log.emit("[3/4] Aplicando efeito Ken Burns...")
            video_animado = str(DIR_PROCESSING / "video_animado.mp4")
            aplicar_ken_burns(
                imagem=self._img_path,
                duracao=duracao,
                saida=video_animado,
                efeito_nome=None,
                fps=60,
                resolucao="1920x1080",
            )
            self.log.emit("  Vídeo animado gerado.")

            # Combinar áudio + vídeo
            self.log.emit("[4a] Combinando áudio + vídeo...")
            nome_final  = Path(nome).stem + "_final.mp4"
            video_final = DIR_PROCESSING / nome_final
            res = subprocess.run(
                [
                    "ffmpeg", "-y",
                    "-i", str(video_animado),
                    "-i", str(audio_proc),
                    "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-shortest",
                    str(video_final),
                ],
                capture_output=True, text=True,
            )
            if res.returncode != 0:
                raise RuntimeError(f"FFmpeg falhou ao combinar: {res.stderr[-800:]}")
            self.step_update.emit(2, "done")

            DIR_REVIEW.mkdir(exist_ok=True)
            video_review = DIR_REVIEW / nome_final
            shutil.move(str(video_final), str(video_review))
            limpar_processing(manter=audio_proc)

            self._video_path = str(video_review)
            self.log.emit(f"  Vídeo pronto: {video_review.name}")
            self.vid_ready.emit(self._video_path)

            # Aguarda decisão de publicação
            self._evt_video.wait()
            if self._cancelled:
                devolver_audio()
                return

            if self._decisao_vid != "s":
                DIR_REJECTED.mkdir(exist_ok=True)
                shutil.move(str(video_review), str(DIR_REJECTED / nome_final))
                devolver_audio()
                limpar_processing()
                self.log.emit("  Vídeo rejeitado. Áudio devolvido ao /inbox.")
                self.finished_ko.emit("rejeitado")
                return

            # [4] Upload YouTube
            self.step_update.emit(3, "running")
            self.log.emit("[4/4] Publicando no YouTube...")
            resultado = publicar_video(
                video_path=str(video_review),
                titulo=self._meta["titulo"],
                descricao=self._meta["descricao"],
                tags=self._meta["tags"],
            )
            self.step_update.emit(3, "done")

            DIR_LOGS.mkdir(exist_ok=True)
            agora    = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            log_path = DIR_LOGS / f"publicado_{Path(nome).stem}_{agora}.txt"
            log_path.write_text(
                f"Arquivo  : {nome}\nTítulo   : {resultado['titulo']}\n"
                f"Video ID : {resultado['video_id']}\nURL      : {resultado['url']}\n"
                f"Horário  : {agora}\n\nPrompt da imagem:\n"
                f"{self._img_meta.get('prompt_completo', '')}\n",
                encoding="utf-8",
            )
            limpar_processing()

            self.log.emit(f"  ✓ Publicado: {resultado['url']}")
            self.finished_ok.emit(resultado["url"])

        except Exception:
            err = traceback.format_exc()
            devolver_audio()
            self.log.emit(f"[ERRO] {err.splitlines()[-1]}")
            self.finished_ko.emit(err.splitlines()[-1])
            for i in range(4):
                self.step_update.emit(i, "error")


# ── Widgets auxiliares ─────────────────────────────────────────────────────────

class SectionLabel(QLabel):
    def __init__(self, text: str, parent=None):
        super().__init__(text.upper(), parent)
        self.setStyleSheet(
            f"color: {ACCENT}; font-size: 10px; font-weight: bold;"
            f" letter-spacing: 1.5px; padding: 2px 0 6px 0;"
        )


class StepIndicator(QWidget):
    def __init__(self, number: int, label: str, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(8)

        self.icon = QLabel("○")
        self.icon.setFixedWidth(16)
        self.icon.setStyleSheet(f"color: {TEXT_DIM}; font-size: 14px;")

        self.text = QLabel(f"{number}. {label}")
        self.text.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")

        layout.addWidget(self.icon)
        layout.addWidget(self.text)
        layout.addStretch()

    def set_status(self, status: str):
        styles = {
            "idle":    (f"color: {TEXT_DIM}",   "○", f"color: {TEXT_DIM}; font-size: 12px;"),
            "running": (f"color: {TEXT_AMBER}",  "●", f"color: {TEXT_AMBER}; font-size: 12px; font-weight: bold;"),
            "done":    (f"color: {TEXT_GREEN}",  "✓", f"color: {TEXT_GREEN}; font-size: 12px;"),
            "error":   (f"color: {TEXT_RED}",    "✗", f"color: {TEXT_RED}; font-size: 12px;"),
        }
        icon_style, icon_text, text_style = styles.get(status, styles["idle"])
        self.icon.setStyleSheet(f"{icon_style}; font-size: 14px;")
        self.icon.setText(icon_text)
        self.text.setStyleSheet(text_style)


class ImagePreview(QLabel):
    """QLabel que mantém aspect ratio e mostra placeholder quando sem imagem."""

    PLACEHOLDER_STYLE = (
        f"background: {BG_CARD}; border: 1px solid {BORDER};"
        f" border-radius: 6px; color: {TEXT_DIM};"
    )
    IMAGE_STYLE = (
        f"background: {BG_CARD}; border: 1px solid {ACCENT};"
        f" border-radius: 6px;"
    )

    def __init__(self, w: int, h: int, placeholder: str, parent=None):
        super().__init__(placeholder, parent)
        self.setFixedSize(w, h)
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setWordWrap(True)
        self.setStyleSheet(self.PLACEHOLDER_STYLE)
        self._img_w = w
        self._img_h = h

    def show_image(self, path: str):
        px = QPixmap(path)
        if px.isNull():
            self.reset("Erro ao carregar imagem")
            return
        px = px.scaled(
            self._img_w, self._img_h,
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.SmoothTransformation,
        )
        self.setPixmap(px)
        self.setStyleSheet(self.IMAGE_STYLE)

    def reset(self, text: str):
        self.clear()
        self.setText(text)
        self.setStyleSheet(self.PLACEHOLDER_STYLE)


# ── Janela Principal ───────────────────────────────────────────────────────────

class OvxrNightGUI(QMainWindow):

    def __init__(self):
        super().__init__()
        self.setWindowTitle("OvxrNight Control Center v1.0")
        self.setMinimumSize(1280, 800)
        self.resize(1440, 900)
        self.setStyleSheet(STYLE)

        self._worker: Optional[PipelineWorker] = None
        self._current_audio: Optional[Path]    = None

        self._build_ui()
        self._refresh_queue()
        self._refresh_history()

        refresh_timer = QTimer(self)
        refresh_timer.timeout.connect(self._refresh_queue)
        refresh_timer.start(6000)

    # ── Build UI ──────────────────────────────────────────────────────────────

    def _build_ui(self):
        central = QWidget()
        self.setCentralWidget(central)
        root = QVBoxLayout(central)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        root.addWidget(self._build_header())

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background: {BORDER}; max-height: 1px;")
        root.addWidget(sep)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.setHandleWidth(1)
        splitter.addWidget(self._build_left())
        splitter.addWidget(self._build_center())
        splitter.addWidget(self._build_right())
        splitter.setSizes([260, 700, 300])
        root.addWidget(splitter, 1)

    # ── Header ────────────────────────────────────────────────────────────────

    def _build_header(self) -> QWidget:
        w = QWidget()
        w.setFixedHeight(54)
        w.setStyleSheet(f"background: {BG_PANEL}; border-bottom: 1px solid {BORDER};")
        lay = QHBoxLayout(w)
        lay.setContentsMargins(20, 0, 20, 0)

        logo = QLabel("◈  OvxrNight Control Center")
        logo.setStyleSheet(
            f"color: {ACCENT}; font-size: 15px; font-weight: bold; letter-spacing: 1px;"
        )
        lay.addWidget(logo)
        lay.addStretch()

        self.lbl_header_song = QLabel("Nenhum arquivo selecionado")
        self.lbl_header_song.setStyleSheet(f"color: {TEXT_DIM}; font-size: 13px; font-style: italic;")
        lay.addWidget(self.lbl_header_song)
        lay.addStretch()

        self.btn_start = QPushButton("▶   Iniciar Pipeline")
        self.btn_start.setObjectName("btn_primary")
        self.btn_start.setFixedHeight(36)
        self.btn_start.setMinimumWidth(160)
        self.btn_start.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #000000;
                font-weight: bold;
                font-size: 13px;
                border: 2px solid {ACCENT};
                border-radius: 4px;
                padding: 0 18px;
            }}
            QPushButton:hover {{ background-color: {ACCENT_DIM}; border-color: {ACCENT_DIM}; }}
            QPushButton:pressed {{ background-color: #007A99; }}
            QPushButton:disabled {{
                background-color: transparent;
                border: 2px solid {ACCENT_DIM};
                color: {ACCENT_DIM};
            }}
        """)
        self.btn_start.setEnabled(False)
        self.btn_start.clicked.connect(self._on_start)
        lay.addWidget(self.btn_start)
        return w

    # ── Left panel ────────────────────────────────────────────────────────────

    def _build_left(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(200)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(14, 14, 8, 14)
        lay.setSpacing(8)

        lay.addWidget(SectionLabel("Queue Management"))

        self.list_queue = QListWidget()
        self.list_queue.setMinimumHeight(160)
        self.list_queue.setToolTip("Arquivos em /inbox aguardando processamento")
        lay.addWidget(self.list_queue)

        btn_refresh = QPushButton("↻  Atualizar Fila")
        btn_refresh.clicked.connect(self._refresh_queue)
        lay.addWidget(btn_refresh)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {BORDER}; max-height: 1px; margin: 6px 0;")
        lay.addWidget(line)

        lay.addWidget(SectionLabel("History"))

        pub = QLabel("PUBLISHED")
        pub.setStyleSheet(f"color: {TEXT_GREEN}; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        lay.addWidget(pub)
        self.list_published = QListWidget()
        self.list_published.setMaximumHeight(130)
        self.list_published.setStyleSheet(
            f"QListWidget {{ border-left: 2px solid {TEXT_GREEN}; }}"
            + self.list_published.styleSheet()
        )
        lay.addWidget(self.list_published)

        rej = QLabel("REJECTED")
        rej.setStyleSheet(f"color: {TEXT_RED}; font-size: 10px; font-weight: bold; letter-spacing: 1px;")
        lay.addWidget(rej)
        self.list_rejected = QListWidget()
        self.list_rejected.setMaximumHeight(100)
        self.list_rejected.setStyleSheet(
            f"QListWidget {{ border-left: 2px solid {TEXT_RED}; }}"
            + self.list_rejected.styleSheet()
        )
        lay.addWidget(self.list_rejected)

        lay.addStretch()
        return w

    # ── Center panel ──────────────────────────────────────────────────────────

    def _build_center(self) -> QScrollArea:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setStyleSheet(f"border: none; background: {BG_DARK};")

        inner = QWidget()
        inner.setStyleSheet(f"background: {BG_DARK};")
        lay = QVBoxLayout(inner)
        lay.setContentsMargins(16, 16, 16, 16)
        lay.setSpacing(16)
        lay.addWidget(self._build_metadata_box())
        lay.addWidget(self._build_image_box())
        lay.addWidget(self._build_video_box())
        lay.addStretch()

        scroll.setWidget(inner)
        return scroll

    def _build_metadata_box(self) -> QGroupBox:
        box = QGroupBox("METADATA EDIT")
        lay = QVBoxLayout(box)
        lay.setSpacing(8)

        lay.addWidget(QLabel("Título:"))
        self.input_titulo = QLineEdit()
        self.input_titulo.setPlaceholderText("Artista - Nome da Música")
        lay.addWidget(self.input_titulo)

        lay.addWidget(QLabel("Descrição:"))
        self.input_desc = QTextEdit()
        self.input_desc.setFixedHeight(76)
        self.input_desc.setPlaceholderText("Gerado automaticamente pelo Ollama...")
        lay.addWidget(self.input_desc)

        lay.addWidget(QLabel("Tags:"))
        self.input_tags = QLineEdit()
        self.input_tags.setPlaceholderText("slowed, reverb, anime, ...")
        lay.addWidget(self.input_tags)

        btn_row = QHBoxLayout()
        self.btn_confirm_meta = QPushButton("✓  Confirmar e Continuar")
        self.btn_confirm_meta.setObjectName("btn_success")
        self.btn_confirm_meta.setEnabled(False)
        self.btn_confirm_meta.clicked.connect(self._on_confirm_meta)
        btn_row.addWidget(self.btn_confirm_meta)
        btn_row.addStretch()
        lay.addLayout(btn_row)

        return box

    def _build_image_box(self) -> QGroupBox:
        box = QGroupBox("IMAGE REVIEW")
        lay = QHBoxLayout(box)
        lay.setSpacing(16)

        self.img_preview = ImagePreview(320, 182, "Aguardando geração da imagem...")
        lay.addWidget(self.img_preview)

        right = QVBoxLayout()
        right.setSpacing(6)

        self.lbl_img_char   = QLabel("Personagem : —")
        self.lbl_img_scene  = QLabel("Cenário    : —")
        self.lbl_img_style  = QLabel("Estilo     : —")
        for lbl in [self.lbl_img_char, self.lbl_img_scene, self.lbl_img_style]:
            lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 12px;")
            right.addWidget(lbl)

        right.addStretch()

        self.btn_img_ok  = QPushButton("✓  Aprovar Imagem")
        self.btn_img_ok.setObjectName("btn_success")
        self.btn_img_new = QPushButton("↺  Gerar Nova Imagem")
        self.btn_img_new.setObjectName("btn_neutral")
        self.btn_img_del = QPushButton("✗  Descartar Música")
        self.btn_img_del.setObjectName("btn_danger")

        for btn in [self.btn_img_ok, self.btn_img_new, self.btn_img_del]:
            btn.setEnabled(False)
            right.addWidget(btn)

        self.btn_img_ok.clicked.connect(lambda: self._on_img_decision("s"))
        self.btn_img_new.clicked.connect(lambda: self._on_img_decision("n"))
        self.btn_img_del.clicked.connect(lambda: self._on_img_decision("d"))

        lay.addLayout(right)
        return box

    def _build_video_box(self) -> QGroupBox:
        box = QGroupBox("VIDEO PREVIEW")
        lay = QHBoxLayout(box)
        lay.setSpacing(16)

        self.vid_thumb = ImagePreview(320, 182, "Aguardando vídeo finalizado...")
        lay.addWidget(self.vid_thumb)

        right = QVBoxLayout()
        right.setSpacing(8)

        self.lbl_vid_path = QLabel("—")
        self.lbl_vid_path.setStyleSheet(f"color: {TEXT_DIM}; font-size: 11px;")
        self.lbl_vid_path.setWordWrap(True)
        right.addWidget(self.lbl_vid_path)

        btn_open = QPushButton("📁  Abrir Pasta /review")
        btn_open.clicked.connect(self._on_open_review)
        right.addWidget(btn_open)

        right.addStretch()

        self.btn_publish = QPushButton("▶   Publicar no YouTube")
        self.btn_publish.setObjectName("btn_primary")
        self.btn_publish.setStyleSheet(f"""
            QPushButton {{
                background-color: {ACCENT};
                color: #000000;
                font-weight: bold;
                border: 2px solid {ACCENT};
                border-radius: 4px;
                padding: 7px 14px;
            }}
            QPushButton:hover {{ background-color: {ACCENT_DIM}; border-color: {ACCENT_DIM}; }}
            QPushButton:pressed {{ background-color: #007A99; }}
            QPushButton:disabled {{
                background-color: transparent;
                border: 2px solid {ACCENT_DIM};
                color: {ACCENT_DIM};
            }}
        """)
        self.btn_reject  = QPushButton("✗  Rejeitar Vídeo")
        self.btn_reject.setObjectName("btn_danger")

        for btn in [self.btn_publish, self.btn_reject]:
            btn.setEnabled(False)
            right.addWidget(btn)

        self.btn_publish.clicked.connect(lambda: self._on_vid_decision("s"))
        self.btn_reject.clicked.connect(lambda: self._on_vid_decision("n"))

        lay.addLayout(right)
        return box

    # ── Right panel ───────────────────────────────────────────────────────────

    def _build_right(self) -> QWidget:
        w = QWidget()
        w.setMinimumWidth(240)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(8, 14, 14, 14)
        lay.setSpacing(8)

        lay.addWidget(SectionLabel("Pipeline Monitoring"))

        status_title = QLabel("RUN STATUS")
        status_title.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: 10px; font-weight: bold; letter-spacing: 1px;"
        )
        lay.addWidget(status_title)

        self.step_indicators: list[StepIndicator] = []
        for i, name in enumerate(PipelineWorker.STEPS):
            ind = StepIndicator(i + 1, name)
            self.step_indicators.append(ind)
            lay.addWidget(ind)

        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setStyleSheet(f"background: {BORDER}; max-height: 1px; margin: 6px 0;")
        lay.addWidget(line)

        lay.addWidget(SectionLabel("Real Time Log"))

        self.log_view = QTextEdit()
        self.log_view.setReadOnly(True)
        self.log_view.setStyleSheet(
            f"background: {BG_DARK}; border: 1px solid {BORDER}; border-radius: 4px;"
            f" font-family: Consolas, monospace; font-size: 11px; color: {TEXT_DIM};"
            f" padding: 4px;"
        )
        lay.addWidget(self.log_view, 1)

        btn_clear = QPushButton("Limpar Log")
        btn_clear.clicked.connect(self.log_view.clear)
        lay.addWidget(btn_clear)

        return w

    # ── Atualizar dados ────────────────────────────────────────────────────────

    def _refresh_queue(self):
        DIR_INBOX = Path("inbox")
        DIR_INBOX.mkdir(exist_ok=True)
        exts = {".mp3", ".wav", ".flac", ".m4a", ".ogg"}
        queue = sorted(
            (f for f in DIR_INBOX.iterdir() if f.is_file() and f.suffix.lower() in exts),
            key=lambda f: f.stat().st_mtime,
        )

        self.list_queue.clear()
        for i, f in enumerate(queue):
            if i == 0:
                item = QListWidgetItem(f"▶  {f.name}")
                item.setForeground(QColor(ACCENT))
            else:
                item = QListWidgetItem(f"   {f.name}")
                item.setForeground(QColor(TEXT_DIM))
            item.setToolTip(f.name)
            self.list_queue.addItem(item)

        running = self._worker is not None and self._worker.isRunning()
        if queue:
            self._current_audio = queue[0]
            self.lbl_header_song.setText(queue[0].stem)
            self.lbl_header_song.setStyleSheet(
                f"color: {TEXT_MAIN}; font-size: 13px; font-weight: 500;"
            )
            self.btn_start.setEnabled(not running)
        else:
            self._current_audio = None
            self.lbl_header_song.setText("Inbox vazia")
            self.lbl_header_song.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: 13px; font-style: italic;"
            )
            self.btn_start.setEnabled(False)

    def _refresh_history(self):
        DIR_LOGS     = Path("logs");     DIR_LOGS.mkdir(exist_ok=True)
        DIR_REJECTED = Path("rejected"); DIR_REJECTED.mkdir(exist_ok=True)

        self.list_published.clear()
        for f in sorted(DIR_LOGS.glob("publicado_*.txt"),
                        key=lambda x: x.stat().st_mtime, reverse=True)[:12]:
            stem = f.stem[10:]  # strip "publicado_"
            item = QListWidgetItem(f"  {stem}")
            item.setForeground(QColor(TEXT_GREEN))
            item.setToolTip(stem)
            self.list_published.addItem(item)

        self.list_rejected.clear()
        for f in sorted(DIR_REJECTED.glob("*_final.mp4"),
                        key=lambda x: x.stat().st_mtime, reverse=True)[:8]:
            name = f.stem[:-6]
            item = QListWidgetItem(f"  {name}")
            item.setForeground(QColor(TEXT_RED))
            item.setToolTip(name)
            self.list_rejected.addItem(item)

    # ── Pipeline controls ─────────────────────────────────────────────────────

    def _on_start(self):
        if not self._current_audio or not self._current_audio.exists():
            self._refresh_queue()
            return

        self._reset_ui()

        self._worker = PipelineWorker(self._current_audio)
        self._worker.log.connect(self._append_log)
        self._worker.step_update.connect(self._on_step_update)
        self._worker.meta_ready.connect(self._on_meta_ready)
        self._worker.img_ready.connect(self._on_img_ready)
        self._worker.vid_ready.connect(self._on_vid_ready)
        self._worker.finished_ok.connect(self._on_finished_ok)
        self._worker.finished_ko.connect(self._on_finished_ko)
        self._worker.start()

        self.btn_start.setEnabled(False)
        self._append_log(f"Iniciando pipeline: {self._current_audio.name}")

    def _reset_ui(self):
        for ind in self.step_indicators:
            ind.set_status("idle")
        self.btn_confirm_meta.setEnabled(False)
        for btn in [self.btn_img_ok, self.btn_img_new, self.btn_img_del,
                    self.btn_publish, self.btn_reject]:
            btn.setEnabled(False)
        self.input_titulo.clear()
        self.input_desc.clear()
        self.input_tags.clear()
        self.img_preview.reset("Aguardando geração da imagem...")
        self.vid_thumb.reset("Aguardando vídeo finalizado...")
        self.lbl_vid_path.setText("—")
        self.lbl_img_char.setText("Personagem : —")
        self.lbl_img_scene.setText("Cenário    : —")
        self.lbl_img_style.setText("Estilo     : —")

    # ── Worker signal handlers ─────────────────────────────────────────────────

    def _append_log(self, msg: str):
        ts = datetime.now().strftime("%H:%M:%S")
        self.log_view.append(
            f'<span style="color:{TEXT_DIM}">[{ts}]</span>'
            f' <span style="color:{TEXT_MAIN}">{msg}</span>'
        )

    def _on_step_update(self, step: int, status: str):
        if 0 <= step < len(self.step_indicators):
            self.step_indicators[step].set_status(status)

    def _on_meta_ready(self, meta: dict):
        self.input_titulo.setText(meta.get("titulo", ""))
        self.input_desc.setPlainText(meta.get("descricao", ""))
        tags = meta.get("tags", [])
        self.input_tags.setText(", ".join(tags) if isinstance(tags, list) else str(tags))
        self.btn_confirm_meta.setEnabled(True)
        self._append_log("Metadados prontos — edite o título se necessário e confirme.")

    def _on_confirm_meta(self):
        titulo = self.input_titulo.text().strip()
        self.btn_confirm_meta.setEnabled(False)
        if self._worker:
            self._worker.set_titulo(titulo)
        self._append_log(f"Título confirmado: {titulo or '(mantido original)'}")

    def _on_img_ready(self, img_path: str, img_meta: dict):
        self.img_preview.show_image(img_path)
        self.lbl_img_char.setText(f"Personagem : {img_meta.get('personagem', '—')}")
        self.lbl_img_scene.setText(f"Cenário    : {img_meta.get('cenario', '—')}")
        self.lbl_img_style.setText(f"Estilo     : {img_meta.get('estilo', '—')}")
        for btn in [self.btn_img_ok, self.btn_img_new, self.btn_img_del]:
            btn.setEnabled(True)
        self._append_log("Imagem gerada — avalie e tome uma decisão.")

    def _on_img_decision(self, decisao: str):
        for btn in [self.btn_img_ok, self.btn_img_new, self.btn_img_del]:
            btn.setEnabled(False)
        if self._worker:
            self._worker.set_decisao_imagem(decisao)
        labels = {
            "s": "Imagem aprovada. Montando vídeo...",
            "n": "Solicitando nova imagem...",
            "d": "Música descartada.",
        }
        self._append_log(labels.get(decisao, ""))

    def _on_vid_ready(self, video_path: str):
        self.lbl_vid_path.setText(Path(video_path).name)
        self.vid_thumb.reset("▶  Vídeo pronto\nAbra /review para assistir")
        self.vid_thumb.setStyleSheet(
            f"background: {BG_CARD}; border: 2px solid {ACCENT};"
            f" border-radius: 6px; color: {ACCENT}; font-weight: bold; font-size: 13px;"
        )
        self.btn_publish.setEnabled(True)
        self.btn_reject.setEnabled(True)
        self._append_log("Vídeo pronto em /review — assista e decida.")

    def _on_vid_decision(self, decisao: str):
        self.btn_publish.setEnabled(False)
        self.btn_reject.setEnabled(False)
        if self._worker:
            self._worker.set_decisao_video(decisao)
        if decisao == "s":
            self._append_log("Publicando no YouTube...")
        else:
            self._append_log("Vídeo rejeitado. Devolvendo áudio ao /inbox.")

    def _on_finished_ok(self, url: str):
        self._append_log(f"✓ Publicado: {url}")
        self.btn_start.setEnabled(True)
        self._refresh_queue()
        self._refresh_history()
        QMessageBox.information(self, "Publicado!", f"Vídeo publicado com sucesso!\n\n{url}")

    def _on_finished_ko(self, msg: str):
        if msg not in ("descartado", "rejeitado"):
            self._append_log(f"✗ Erro: {msg}")
            QMessageBox.warning(self, "Pipeline — Erro", msg[:400])
        self.btn_start.setEnabled(True)
        self._refresh_queue()
        self._refresh_history()

    def _on_open_review(self):
        review = Path("review")
        review.mkdir(exist_ok=True)
        subprocess.Popen(["explorer", str(review.resolve())])

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            reply = QMessageBox.question(
                self, "Pipeline em execução",
                "O pipeline está rodando. Deseja cancelar e sair?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if reply == QMessageBox.StandardButton.Yes:
                self._worker.cancel()
                self._worker.wait(3000)
                event.accept()
            else:
                event.ignore()
        else:
            event.accept()


# ── Entry point ────────────────────────────────────────────────────────────────

def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = OvxrNightGUI()
    win.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
