"""
Testes para PipelineWorker em gui.py
Cobre: sincronização via Events, comportamento de cancel,
       e fluxo completo com todos os módulos externos mockados.
"""
import threading
import time
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import pytest

from gui import ConnectionManager, PipelineWorker


class TestConnectionManager:
    """Testa ConnectionManager — envio thread-safe via WebSocket."""

    def test_send_sem_conexao_nao_levanta_excecao(self):
        mgr = ConnectionManager()
        mgr.send({"type": "log", "msg": "teste"})   # não deve lançar

    def test_connect_armazena_ws_e_loop(self):
        mgr = ConnectionManager()
        ws_mock   = MagicMock()
        loop_mock = MagicMock()
        loop_mock.is_closed.return_value = False
        mgr.connect(ws_mock, loop_mock)
        # Após connect, send deve tentar enviar
        with patch("asyncio.run_coroutine_threadsafe") as rct:
            mgr.send({"type": "test"})
            rct.assert_called_once()

    def test_disconnect_impede_envio(self):
        mgr = ConnectionManager()
        ws_mock   = MagicMock()
        loop_mock = MagicMock()
        loop_mock.is_closed.return_value = False
        mgr.connect(ws_mock, loop_mock)
        mgr.disconnect()
        with patch("asyncio.run_coroutine_threadsafe") as rct:
            mgr.send({"type": "test"})
            rct.assert_not_called()

    def test_send_nao_envia_quando_loop_fechado(self):
        mgr = ConnectionManager()
        ws_mock   = MagicMock()
        loop_mock = MagicMock()
        loop_mock.is_closed.return_value = True
        mgr.connect(ws_mock, loop_mock)
        with patch("asyncio.run_coroutine_threadsafe") as rct:
            mgr.send({"type": "test"})
            rct.assert_not_called()


class TestPipelineWorkerEventos:
    """Testa os mecanismos de sincronização do PipelineWorker."""

    def _worker(self, tmp_path: Path) -> PipelineWorker:
        audio = tmp_path / "song.mp3"
        audio.write_bytes(b"\x00" * 64)
        return PipelineWorker(audio)

    def test_set_titulo_dispara_evento(self, tmp_path):
        w = self._worker(tmp_path)
        assert not w._evt_titulo.is_set()
        w.set_titulo("Meu Título")
        assert w._evt_titulo.is_set()
        assert w._titulo_editado == "Meu Título"

    def test_set_titulo_vazio_ainda_dispara_evento(self, tmp_path):
        w = self._worker(tmp_path)
        w.set_titulo("")
        assert w._evt_titulo.is_set()

    def test_set_decisao_imagem_aprovar(self, tmp_path):
        w = self._worker(tmp_path)
        w.set_decisao_imagem("s")
        assert w._evt_imagem.is_set()
        assert w._decisao_img == "s"

    def test_set_decisao_imagem_nova(self, tmp_path):
        w = self._worker(tmp_path)
        w.set_decisao_imagem("n")
        assert w._decisao_img == "n"

    def test_set_decisao_imagem_descartar(self, tmp_path):
        w = self._worker(tmp_path)
        w.set_decisao_imagem("d")
        assert w._decisao_img == "d"

    def test_set_decisao_video_publicar(self, tmp_path):
        w = self._worker(tmp_path)
        w.set_decisao_video("s")
        assert w._evt_video.is_set()
        assert w._decisao_vid == "s"

    def test_set_decisao_video_rejeitar(self, tmp_path):
        w = self._worker(tmp_path)
        w.set_decisao_video("n")
        assert w._decisao_vid == "n"

    def test_cancel_dispara_todos_os_eventos(self, tmp_path):
        w = self._worker(tmp_path)
        w.cancel()
        assert w._cancelled is True
        assert w._evt_titulo.is_set()
        assert w._evt_imagem.is_set()
        assert w._evt_video.is_set()

    def test_worker_e_daemon_thread(self, tmp_path):
        w = self._worker(tmp_path)
        assert w.daemon is True


class TestPipelineWorkerFluxoCompleto:
    """Testa o fluxo completo do worker com todos os módulos externos mockados."""

    def _audio(self, tmp_path: Path) -> Path:
        audio = tmp_path / "inbox" / "Artista - Musica.mp3"
        audio.parent.mkdir(parents=True, exist_ok=True)
        audio.write_bytes(b"\x00" * 64)
        return audio

    def _mock_ffprobe_ok(self):
        r = MagicMock()
        r.returncode = 0
        r.stdout = '{"streams":[{"duration":"180"}]}'
        return r

    def _mock_ffmpeg_ok(self, saida: str):
        r = MagicMock()
        r.returncode = 0
        Path(saida).write_bytes(b"\x00" * 64) if saida else None
        return r

    def test_fluxo_aprovacao_e_publicacao(self, tmp_path):
        """Worker percorre todos os 4 passos quando o usuário aprova tudo."""
        audio = self._audio(tmp_path)
        for d in ("processing", "review", "rejected", "logs"):
            (tmp_path / d).mkdir(exist_ok=True)

        mensagens_enviadas = []

        def fake_send(data):
            mensagens_enviadas.append(data)
            # Simula resposta automática do "usuário" conforme o worker aguarda
            t = data.get("type")
            if t == "meta_ready":
                threading.Timer(0.05, worker.set_titulo, args=("Título Aprovado",)).start()
            elif t == "img_ready":
                threading.Timer(0.05, worker.set_decisao_imagem, args=("s",)).start()
            elif t == "vid_ready":
                threading.Timer(0.05, worker.set_decisao_video, args=("s",)).start()

        meta_fake = {
            "titulo": "Título Gerado",
            "descricao": "Descrição gerada",
            "tags": ["tag1", "tag2"],
        }
        img_meta_fake = {
            "personagem": "ninja",
            "cenario": "floresta",
            "estilo": "dark",
            "prompt_completo": "ninja in forest",
        }

        video_review = tmp_path / "review" / "Artista - Musica_final.mp4"

        def fake_ken_burns(**kw):
            out = kw.get("saida") or str(tmp_path / "processing" / "video_animado.mp4")
            Path(out).write_bytes(b"\x00" * 64)
            return out

        def fake_subprocess(cmd, *a, **kw):
            r = MagicMock()
            r.returncode = 0
            if "ffprobe" in cmd:
                r.stdout = '{"streams":[{"duration":"180"}]}'
            elif "ffmpeg" in cmd:
                # Cria o arquivo de saída esperado
                saida = cmd[-1]
                Path(saida).write_bytes(b"\x00" * 64)
            return r

        def fake_publicar(**kw):
            video_review.write_bytes(b"\x00" * 64)
            return {"video_id": "YT123", "url": "https://youtu.be/YT123", "titulo": kw["titulo"]}

        import gui
        original_manager_send = gui.manager.send
        gui.manager.send = fake_send

        worker = PipelineWorker(audio)

        try:
            with patch("image_generator.gerar_imagem",
                       return_value=(str(tmp_path / "processing" / "imagem_gerada.png"), img_meta_fake)), \
                 patch("ken_burns.aplicar_ken_burns", side_effect=lambda **kw: fake_ken_burns(**kw)), \
                 patch("metadata_generator.gerar_metadados", return_value=meta_fake), \
                 patch("metadata_generator._checar_ollama"), \
                 patch("youtube_uploader.publicar_video", side_effect=lambda **kw: fake_publicar(**kw)), \
                 patch("subprocess.run", side_effect=fake_subprocess):

                # Cria imagem fake para o worker encontrar
                (tmp_path / "processing").mkdir(exist_ok=True)
                (tmp_path / "processing" / "imagem_gerada.png").write_bytes(b"\x89PNG\r\n" + b"\x00" * 32)

                worker.start()
                worker.join(timeout=10)

        finally:
            gui.manager.send = original_manager_send

        assert not worker.is_alive(), "Worker deveria ter terminado"

        tipos_enviados = [m["type"] for m in mensagens_enviadas]
        assert "meta_ready" in tipos_enviados
        assert "img_ready"  in tipos_enviados
        assert "vid_ready"  in tipos_enviados

    def test_fluxo_cancelamento_imediato(self, tmp_path):
        """Worker deve parar ao ser cancelado antes de processar metadados."""
        audio = self._audio(tmp_path)
        (tmp_path / "processing").mkdir(exist_ok=True)

        def fake_gerar_metadados(*a, **kw):
            time.sleep(0.01)
            return {"titulo": "t", "descricao": "d", "tags": []}

        import gui
        original_send = gui.manager.send
        gui.manager.send = lambda d: None

        worker = PipelineWorker(audio)

        try:
            with patch("metadata_generator.gerar_metadados", side_effect=fake_gerar_metadados), \
                 patch("metadata_generator._checar_ollama"):
                worker.start()
                # Cancela logo após iniciar
                threading.Timer(0.02, worker.cancel).start()
                worker.join(timeout=5)
        finally:
            gui.manager.send = original_send

        assert not worker.is_alive()
        assert worker._cancelled is True

    def test_fluxo_descarte_imagem(self, tmp_path):
        """Worker deve encerrar e devolver o áudio ao descartar a imagem."""
        audio = self._audio(tmp_path)
        for d in ("processing", "review", "rejected", "logs"):
            (tmp_path / d).mkdir(exist_ok=True)

        mensagens = []

        def fake_send(data):
            mensagens.append(data)
            t = data.get("type")
            if t == "meta_ready":
                threading.Timer(0.03, worker.set_titulo, args=("",)).start()
            elif t == "img_ready":
                threading.Timer(0.03, worker.set_decisao_imagem, args=("d",)).start()

        meta_fake = {"titulo": "t", "descricao": "d", "tags": []}
        img_meta_fake = {"personagem": "p", "cenario": "c", "estilo": "e", "prompt_completo": "x"}

        def fake_subprocess(cmd, *a, **kw):
            r = MagicMock()
            r.returncode = 0
            r.stdout = '{"streams":[{"duration":"60"}]}'
            return r

        import gui
        gui.manager.send = fake_send
        worker = PipelineWorker(audio)

        try:
            with patch("image_generator.gerar_imagem",
                       return_value=(str(tmp_path / "processing" / "imagem_gerada.png"), img_meta_fake)), \
                 patch("metadata_generator.gerar_metadados", return_value=meta_fake), \
                 patch("metadata_generator._checar_ollama"), \
                 patch("subprocess.run", side_effect=fake_subprocess):
                (tmp_path / "processing" / "imagem_gerada.png").write_bytes(b"\x89PNG" + b"\x00" * 32)
                worker.start()
                worker.join(timeout=8)
        finally:
            gui.manager.send = lambda d: None

        tipos = [m["type"] for m in mensagens]
        assert "done_ko" in tipos
        done_msg = next(m for m in mensagens if m["type"] == "done_ko")
        assert done_msg["msg"] == "descartado"
