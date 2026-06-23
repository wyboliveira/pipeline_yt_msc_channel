"""
Testes para pinterest_uploader.py
Cobre: leitura de config, criação de pin (base64), flush com remoção segura,
       comportamento de mínimo e tratamento de falhas. Sem chamadas reais.
"""
import json
import base64
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import pinterest_uploader as pin


# ---------------------------------------------------------------------------
# Configuração
# ---------------------------------------------------------------------------

class TestConfig:
    def test_variavel_de_ambiente_tem_prioridade(self, monkeypatch):
        monkeypatch.setenv("PINTEREST_APP_ID", "abc123")
        assert pin._ler_env("PINTEREST_APP_ID") == "abc123"

    def test_redirect_uri_usa_padrao(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PINTEREST_REDIRECT_URI", raising=False)
        monkeypatch.chdir(tmp_path)   # sem .env
        assert pin._config()["redirect_uri"] == pin.DEFAULT_REDIRECT

    def test_le_board_do_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("PINTEREST_BOARD_ID", raising=False)
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text("PINTEREST_BOARD_ID=board-987\n", encoding="utf-8")
        assert pin._config()["board_id"] == "board-987"


# ---------------------------------------------------------------------------
# criar_pin
# ---------------------------------------------------------------------------

class TestCriarPin:
    def _imagem_fake(self, tmp_path: Path) -> Path:
        img = tmp_path / "gerada_20260623.png"
        img.write_bytes(b"\x89PNG\r\n\x1a\nFAKE")
        return img

    def test_envia_base64_e_retorna_id(self, tmp_path):
        img = self._imagem_fake(tmp_path)
        resp = MagicMock(status_code=201)
        resp.json.return_value = {"id": "pin-1"}

        with patch("pinterest_uploader.requests.post", return_value=resp) as mp:
            pin_id = pin.criar_pin(str(img), "board-1", titulo="t", token="tok")

        assert pin_id == "pin-1"
        body = mp.call_args.kwargs["json"]
        assert body["board_id"] == "board-1"
        assert body["media_source"]["source_type"] == "image_base64"
        assert body["media_source"]["content_type"] == "image/png"
        esperado = base64.b64encode(img.read_bytes()).decode("ascii")
        assert body["media_source"]["data"] == esperado
        # token usado no header
        assert mp.call_args.kwargs["headers"]["Authorization"] == "Bearer tok"

    def test_jpg_usa_content_type_jpeg(self, tmp_path):
        img = tmp_path / "foto.jpg"
        img.write_bytes(b"\xff\xd8\xff")
        resp = MagicMock(status_code=201)
        resp.json.return_value = {"id": "pin-2"}

        with patch("pinterest_uploader.requests.post", return_value=resp) as mp:
            pin.criar_pin(str(img), "board-1", token="tok")

        assert mp.call_args.kwargs["json"]["media_source"]["content_type"] == "image/jpeg"

    def test_erro_http_levanta(self, tmp_path):
        img = self._imagem_fake(tmp_path)
        resp = MagicMock(status_code=400, text="bad request")
        with patch("pinterest_uploader.requests.post", return_value=resp):
            with pytest.raises(RuntimeError, match="Falha ao criar pin"):
                pin.criar_pin(str(img), "board-1", token="tok")


# ---------------------------------------------------------------------------
# flush_assets
# ---------------------------------------------------------------------------

class TestFlushAssets:
    def _povoar(self, tmp_path: Path, n: int) -> Path:
        d = tmp_path / "assets" / "images"
        d.mkdir(parents=True)
        for i in range(n):
            (d / f"gerada_{i}.png").write_bytes(b"data")
        return d

    def test_sem_board_levanta(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        monkeypatch.delenv("PINTEREST_BOARD_ID", raising=False)
        with pytest.raises(RuntimeError, match="BOARD_ID"):
            pin.flush_assets(assets_dir=str(tmp_path / "assets" / "images"))

    def test_apaga_apenas_apos_sucesso(self, tmp_path):
        d = self._povoar(tmp_path, 3)
        with patch("pinterest_uploader._access_token_valido", return_value="tok"), \
             patch("pinterest_uploader.criar_pin", return_value="pin-x") as mp:
            res = pin.flush_assets(board_id="b1", assets_dir=str(d))

        assert mp.call_count == 3
        assert res == {"total": 3, "enviadas": 3, "falhas": 0, "ignorado": False}
        assert list(d.glob("*.png")) == []   # pasta limpa

    def test_imagem_que_falha_permanece(self, tmp_path):
        d = self._povoar(tmp_path, 2)

        def fake_criar(img, board_id, titulo="", token=None):
            if "gerada_0" in img:
                raise RuntimeError("boom")
            return "pin-ok"

        with patch("pinterest_uploader._access_token_valido", return_value="tok"), \
             patch("pinterest_uploader.criar_pin", side_effect=fake_criar):
            res = pin.flush_assets(board_id="b1", assets_dir=str(d))

        assert res["enviadas"] == 1
        assert res["falhas"] == 1
        restantes = [p.name for p in d.glob("*.png")]
        assert restantes == ["gerada_0.png"]   # a que falhou não foi apagada

    def test_respeita_minimo(self, tmp_path):
        d = self._povoar(tmp_path, 3)
        with patch("pinterest_uploader._access_token_valido", return_value="tok"), \
             patch("pinterest_uploader.criar_pin") as mp:
            res = pin.flush_assets(board_id="b1", assets_dir=str(d), minimo=10)

        assert res["ignorado"] is True
        mp.assert_not_called()
        assert len(list(d.glob("*.png"))) == 3   # nada apagado

    def test_pasta_vazia(self, tmp_path):
        d = tmp_path / "assets" / "images"
        d.mkdir(parents=True)
        with patch("pinterest_uploader._access_token_valido") as auth:
            res = pin.flush_assets(board_id="b1", assets_dir=str(d))
        assert res == {"total": 0, "enviadas": 0, "falhas": 0, "ignorado": False}
        auth.assert_not_called()


# ---------------------------------------------------------------------------
# Token / OAuth
# ---------------------------------------------------------------------------

class TestToken:
    def test_reutiliza_token_valido(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        Path(pin.TOKEN_PATH).write_text(json.dumps({
            "access_token": "valido",
            "refresh_token": "r",
            "expires_at": 9_999_999_999,
        }), encoding="utf-8")
        assert pin._access_token_valido() == "valido"

    def test_renova_quando_expirado(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        Path(pin.TOKEN_PATH).write_text(json.dumps({
            "access_token": "velho",
            "refresh_token": "r",
            "expires_at": 0,
        }), encoding="utf-8")
        resp = MagicMock(status_code=200)
        resp.json.return_value = {"access_token": "novo", "expires_in": 2592000}
        with patch("pinterest_uploader.requests.post", return_value=resp):
            assert pin._access_token_valido() == "novo"
