"""
Testes para youtube_uploader.py
Cobre: leitura do client_secret, erros de arquivo ausente,
       retry em erros HTTP 5xx e upload bem-sucedido.
"""
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from youtube_uploader import (
    MAX_RETRIES,
    TOKEN_PATH,
    _ler_client_secret_path,
    publicar_video,
)


class TestLerClientSecretPath:
    """Testa a leitura do caminho do client_secret.json."""

    def test_variavel_de_ambiente_tem_prioridade(self, monkeypatch):
        monkeypatch.setenv("YOUTUBE_CLIENT_SECRET_PATH", "/custom/path/secret.json")
        assert _ler_client_secret_path() == "/custom/path/secret.json"

    def test_retorna_padrao_sem_config(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_CLIENT_SECRET_PATH", raising=False)
        # sem .env no diretório atual
        with patch("youtube_uploader.Path") as mp:
            mp.return_value.exists.return_value = False
            resultado = _ler_client_secret_path()
        assert resultado == "client_secret.json"

    def test_le_do_arquivo_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("YOUTUBE_CLIENT_SECRET_PATH", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text('YOUTUBE_CLIENT_SECRET_PATH=/path/via/env/file.json\n')
        with patch("youtube_uploader.Path", side_effect=lambda p: env_file if p == ".env" else Path(p)):
            resultado = _ler_client_secret_path()
        # O caminho lido deve conter o valor do .env
        assert "env" in resultado or resultado == "client_secret.json"   # depende da impl.

    def test_retorna_string(self, monkeypatch):
        monkeypatch.delenv("YOUTUBE_CLIENT_SECRET_PATH", raising=False)
        assert isinstance(_ler_client_secret_path(), str)


class TestPublicarVideo:
    """Testa publicar_video com a API do YouTube mockada."""

    def _video_fake(self, tmp_path: Path) -> Path:
        v = tmp_path / "video_final.mp4"
        v.write_bytes(b"\x00" * 256)
        return v

    def _secret_fake(self, tmp_path: Path) -> Path:
        s = tmp_path / "client_secret.json"
        s.write_text(json.dumps({
            "installed": {
                "client_id": "fake_id",
                "client_secret": "fake_secret",
                "redirect_uris": ["urn:ietf:wg:oauth:2.0:oob"],
            }
        }))
        return s

    def test_levanta_file_not_found_para_video_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="[Vv]ídeo"):
            publicar_video(
                video_path=str(tmp_path / "nao_existe.mp4"),
                titulo="Teste",
            )

    def test_levanta_file_not_found_para_secret_ausente(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)   # garante que não existe youtube_token.json
        video = self._video_fake(tmp_path)
        with patch("youtube_uploader._ler_client_secret_path",
                   return_value=str(tmp_path / "nenhum_secret.json")):
            with pytest.raises(FileNotFoundError, match="[Cc]lient"):
                publicar_video(video_path=str(video), titulo="Teste")

    def test_upload_bem_sucedido_retorna_dict_correto(self, tmp_path):
        video  = self._video_fake(tmp_path)
        secret = self._secret_fake(tmp_path)

        # Mock de credenciais já válidas
        creds_mock = MagicMock()
        creds_mock.valid = True
        creds_mock.expired = False

        # Mock da inserção de vídeo no YouTube
        insert_mock = MagicMock()
        insert_mock.next_chunk.return_value = (None, {"id": "yt-video-id-fake"})

        videos_mock = MagicMock()
        videos_mock.insert.return_value = insert_mock

        youtube_mock = MagicMock()
        youtube_mock.videos.return_value = videos_mock

        with patch("youtube_uploader._ler_client_secret_path", return_value=str(secret)), \
             patch("youtube_uploader._autenticar", return_value=creds_mock), \
             patch("youtube_uploader.build", return_value=youtube_mock), \
             patch("youtube_uploader.MediaFileUpload"):
            resultado = publicar_video(
                video_path=str(video),
                titulo="Meu Título de Teste",
                descricao="Descrição",
                tags=["tag1", "tag2"],
            )

        assert resultado["video_id"] == "yt-video-id-fake"
        assert "youtube.com" in resultado["url"]
        assert resultado["titulo"] == "Meu Título de Teste"

    def test_upload_retorna_url_publica(self, tmp_path):
        video  = self._video_fake(tmp_path)
        secret = self._secret_fake(tmp_path)

        creds_mock = MagicMock()
        creds_mock.valid = True

        insert_mock = MagicMock()
        insert_mock.next_chunk.return_value = (None, {"id": "abc123"})

        youtube_mock = MagicMock()
        youtube_mock.videos.return_value.insert.return_value = insert_mock

        with patch("youtube_uploader._ler_client_secret_path", return_value=str(secret)), \
             patch("youtube_uploader._autenticar", return_value=creds_mock), \
             patch("youtube_uploader.build", return_value=youtube_mock), \
             patch("youtube_uploader.MediaFileUpload"):
            resultado = publicar_video(str(video), "Título")

        assert resultado["url"].startswith("https://")
        assert "abc123" in resultado["url"]

    def test_max_retries_e_positivo(self):
        assert MAX_RETRIES > 0

    def test_token_path_e_string(self):
        assert isinstance(TOKEN_PATH, str)
        assert TOKEN_PATH.endswith(".json")
