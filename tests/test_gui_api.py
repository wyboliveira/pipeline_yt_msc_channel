"""
Testes para as rotas HTTP da GUI (FastAPI).
Cobre: GET /, /api/queue, /api/history, /img/current,
       POST /api/open-review, /api/open-video, /api/shutdown.
"""
import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from gui import app, _get_queue_items, _get_history


@pytest.fixture
def client():
    return TestClient(app, raise_server_exceptions=True)


@pytest.fixture(autouse=True)
def chdir_tmp(tmp_path, monkeypatch):
    """Executa cada teste em um diretório temporário isolado."""
    monkeypatch.chdir(tmp_path)
    for d in ("inbox", "processing", "review", "rejected", "logs", "assets/images"):
        (tmp_path / d).mkdir(parents=True)


# ── GET / ────────────────────────────────────────────────────────────────────

class TestIndex:
    def test_retorna_200(self, client):
        r = client.get("/")
        assert r.status_code == 200

    def test_retorna_html(self, client):
        r = client.get("/")
        assert "text/html" in r.headers["content-type"]

    def test_html_contem_ovxrnight(self, client):
        r = client.get("/")
        assert "OVXRNIGHT" in r.text or "OvxrNight" in r.text

    def test_html_contem_websocket(self, client):
        r = client.get("/")
        assert "WebSocket" in r.text or "ws://" in r.text


# ── GET /api/queue ────────────────────────────────────────────────────────────

class TestApiQueue:
    def test_inbox_vazia_retorna_lista_vazia(self, client):
        r = client.get("/api/queue")
        assert r.status_code == 200
        data = r.json()
        assert data["items"] == []

    def test_inbox_com_mp3_retorna_item(self, client, tmp_path):
        (tmp_path / "inbox" / "Artista - Musica.mp3").write_bytes(b"\x00" * 64)
        r = client.get("/api/queue")
        assert r.status_code == 200
        items = r.json()["items"]
        assert len(items) == 1
        assert items[0]["stem"] == "Artista - Musica"

    def test_multiplos_arquivos_ordenados_por_mtime(self, client, tmp_path):
        import time
        for nome in ("a.mp3", "b.wav", "c.flac"):
            f = tmp_path / "inbox" / nome
            f.write_bytes(b"\x00")
            time.sleep(0.01)   # garantir mtime diferente
        r = client.get("/api/queue")
        items = r.json()["items"]
        assert len(items) == 3
        nomes = [i["stem"] for i in items]
        assert nomes == sorted(nomes, key=lambda n: ["a", "b", "c"].index(n))

    def test_extensao_nao_suportada_ignorada(self, client, tmp_path):
        (tmp_path / "inbox" / "video.mp4").write_bytes(b"\x00")
        (tmp_path / "inbox" / "doc.txt").write_bytes(b"\x00")
        r = client.get("/api/queue")
        assert r.json()["items"] == []

    def test_item_contem_campo_date(self, client, tmp_path):
        (tmp_path / "inbox" / "song.mp3").write_bytes(b"\x00")
        r = client.get("/api/queue")
        item = r.json()["items"][0]
        assert "date" in item
        # formato DD/MM/YYYY
        assert len(item["date"]) == 10
        assert item["date"].count("/") == 2


# ── GET /api/history ─────────────────────────────────────────────────────────

class TestApiHistory:
    def test_historico_vazio(self, client):
        r = client.get("/api/history")
        assert r.status_code == 200
        data = r.json()
        assert data["published"] == []
        assert data["rejected"]  == []

    def test_publicado_aparece_em_published(self, client, tmp_path):
        log = tmp_path / "logs" / "publicado_Artista - Musica_2026-01-01_00-00-00.txt"
        log.write_text("Arquivo  : teste.mp3\nTítulo   : Teste\n")
        r = client.get("/api/history")
        assert len(r.json()["published"]) == 1

    def test_rejeitado_aparece_em_rejected(self, client, tmp_path):
        video = tmp_path / "rejected" / "Artista - Musica_final.mp4"
        video.write_bytes(b"\x00")
        r = client.get("/api/history")
        assert len(r.json()["rejected"]) == 1

    def test_limite_de_12_publicados(self, client, tmp_path):
        for i in range(15):
            f = tmp_path / "logs" / f"publicado_song{i:02d}_2026-01-{i+1:02d}_00-00-00.txt"
            f.write_text("x")
        r = client.get("/api/history")
        assert len(r.json()["published"]) <= 12

    def test_limite_de_8_rejeitados(self, client, tmp_path):
        for i in range(10):
            f = tmp_path / "rejected" / f"song{i:02d}_final.mp4"
            f.write_bytes(b"\x00")
        r = client.get("/api/history")
        assert len(r.json()["rejected"]) <= 8


# ── GET /img/current ─────────────────────────────────────────────────────────

class TestImgCurrent:
    def test_retorna_404_quando_imagem_ausente(self, client):
        r = client.get("/img/current")
        assert r.status_code == 404

    def test_retorna_imagem_quando_presente(self, client, tmp_path):
        img = tmp_path / "processing" / "imagem_gerada.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\n" + b"\x00" * 32)
        r = client.get("/img/current")
        assert r.status_code == 200
        assert r.headers["content-type"] == "image/png"


# ── POST /api/open-review ─────────────────────────────────────────────────────

class TestApiOpenReview:
    def test_retorna_ok(self, client):
        with patch("subprocess.Popen"):
            r = client.post("/api/open-review")
        assert r.status_code == 200
        assert r.json()["ok"] is True

    def test_chama_explorer(self, client):
        with patch("subprocess.Popen") as mock_popen:
            client.post("/api/open-review")
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "explorer" in cmd


# ── POST /api/open-video ─────────────────────────────────────────────────────

class TestApiOpenVideo:
    def test_abre_arquivo_existente(self, client, tmp_path):
        video = tmp_path / "review" / "video_final.mp4"
        video.write_bytes(b"\x00" * 64)
        with patch("os.startfile") as mock_sf:
            r = client.post("/api/open-video",
                            json={"path": str(video)},
                            headers={"Content-Type": "application/json"})
        assert r.status_code == 200
        mock_sf.assert_called_once_with(str(video))

    def test_abre_explorer_quando_arquivo_ausente(self, client):
        with patch("subprocess.Popen") as mock_popen:
            r = client.post("/api/open-video",
                            json={"path": "/nao/existe/video.mp4"},
                            headers={"Content-Type": "application/json"})
        assert r.status_code == 200
        mock_popen.assert_called_once()


# ── POST /api/shutdown ────────────────────────────────────────────────────────

class TestApiShutdown:
    def test_retorna_ok(self, client):
        with patch("threading.Thread"):
            r = client.post("/api/shutdown")
        assert r.status_code == 200
        assert r.json()["ok"] is True


# ── Helpers internos ──────────────────────────────────────────────────────────

class TestHelpers:
    def test_get_queue_items_cria_inbox_se_nao_existe(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import shutil
        shutil.rmtree(tmp_path / "inbox", ignore_errors=True)
        items = _get_queue_items()
        assert isinstance(items, list)
        assert (tmp_path / "inbox").exists()

    def test_get_history_cria_diretorios_se_ausentes(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        import shutil
        shutil.rmtree(tmp_path / "logs",     ignore_errors=True)
        shutil.rmtree(tmp_path / "rejected", ignore_errors=True)
        pub, rej = _get_history()
        assert isinstance(pub, list)
        assert isinstance(rej, list)
