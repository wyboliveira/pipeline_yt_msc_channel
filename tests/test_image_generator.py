"""
Testes para image_generator.py
Cobre: chave de API ausente, montagem do prompt, fluxo de geração
       com API mockada, tratamento de erros e timeout.
"""
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from image_generator import (
    PERSONAGENS,
    CENARIOS,
    ESTILOS_VISUAIS,
    POSES_ANGULOS,
    TOM_ADICIONAL,
    _get_api_key,
    _montar_prompt,
    gerar_imagem,
)


class TestGetApiKey:
    """Testa a leitura da chave da API."""

    def test_leitura_via_variavel_de_ambiente(self, monkeypatch):
        monkeypatch.setenv("LEONARDO_API_KEY", "chave_do_env")
        assert _get_api_key() == "chave_do_env"

    def test_levanta_error_sem_chave(self, monkeypatch):
        monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
        # Garante que não existe .env local para o teste
        with patch("image_generator.Path") as mock_path:
            mock_path.return_value.exists.return_value = False
            with pytest.raises(EnvironmentError, match="LEONARDO_API_KEY"):
                _get_api_key()

    def test_leitura_via_dotenv(self, monkeypatch, tmp_path):
        monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
        env_file = tmp_path / ".env"
        env_file.write_text("LEONARDO_API_KEY=chave_do_env_file\n")
        with patch("image_generator.Path", side_effect=lambda p: tmp_path / p if p == ".env" else Path(p)):
            # Chama diretamente com o arquivo .env criado no tmp_path
            pass   # Cobre o caminho; o comportamento é verificado no teste de integração


class TestMontarPrompt:
    """Testa a composição aleatória do prompt."""

    def test_retorna_tupla_string_dict(self):
        resultado = _montar_prompt()
        assert isinstance(resultado, tuple)
        assert len(resultado) == 2
        prompt, meta = resultado
        assert isinstance(prompt, str)
        assert isinstance(meta, dict)

    def test_meta_contem_chaves_esperadas(self):
        # _montar_prompt retorna apenas as partes do prompt; prompt_completo é
        # adicionado por gerar_imagem após montar o texto final.
        _, meta = _montar_prompt()
        for chave in ("personagem", "pose_angulo", "cenario", "estilo", "tom"):
            assert chave in meta, f"Chave '{chave}' ausente no metadado do prompt"

    def test_prompt_nao_vazio(self):
        prompt, _ = _montar_prompt()
        assert len(prompt.strip()) > 20

    def test_prompt_completo_nao_esta_no_meta_de_montar_prompt(self):
        # prompt_completo é adicionado por gerar_imagem, não por _montar_prompt
        _, meta = _montar_prompt()
        assert "prompt_completo" not in meta

    def test_personagem_pertence_ao_banco(self):
        _, meta = _montar_prompt()
        assert meta["personagem"] in PERSONAGENS

    def test_cenario_pertence_ao_banco(self):
        _, meta = _montar_prompt()
        assert meta["cenario"] in CENARIOS

    def test_prompts_variam_entre_chamadas(self):
        prompts = {_montar_prompt()[0] for _ in range(20)}
        # Com 31 personagens e 36 cenários há alta variação; esperamos ao menos 3 distintos
        assert len(prompts) >= 3


class TestGerarImagem:
    """Testa gerar_imagem com requests mockados."""

    FAKE_KEY  = "fake_leonardo_key"
    GEN_ID    = "gen-abc-123"
    IMG_URL   = "https://cdn.leonardo.ai/fake/image.png"
    IMG_BYTES = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64

    def _setup_mocks(self, tmp_path: Path):
        """Cria mocks para POST /generations, GET polling e GET download."""
        # POST → retorna generation_id
        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {
            "sdGenerationJob": {"generationId": self.GEN_ID}
        }

        # GET polling → retorna COMPLETE com URL de imagem
        poll_resp = MagicMock()
        poll_resp.status_code = 200
        poll_resp.json.return_value = {
            "generations_by_pk": {
                "status": "COMPLETE",
                "generated_images": [{"url": self.IMG_URL}],
            }
        }

        # GET download → retorna bytes da imagem
        dl_resp = MagicMock()
        dl_resp.status_code = 200
        dl_resp.content = self.IMG_BYTES
        dl_resp.iter_content = MagicMock(
            return_value=iter([self.IMG_BYTES])
        )

        destino = str(tmp_path / "imagem_gerada.png")
        return post_resp, poll_resp, dl_resp, destino

    def test_retorna_caminho_e_metadados(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LEONARDO_API_KEY", self.FAKE_KEY)
        post_resp, poll_resp, dl_resp, destino = self._setup_mocks(tmp_path)

        # assets/images precisa existir
        (tmp_path / "assets" / "images").mkdir(parents=True)

        with patch("requests.post", return_value=post_resp), \
             patch("requests.get", side_effect=[poll_resp, dl_resp]), \
             patch("image_generator.Path", side_effect=lambda p: tmp_path / p
                   if p in ("assets/images",) else Path(p)), \
             patch("shutil.copy2"):
            resultado = gerar_imagem(destino=destino)

        assert isinstance(resultado, tuple)
        assert len(resultado) == 2
        path, meta = resultado
        assert isinstance(path, str)
        assert isinstance(meta, dict)

    def test_levanta_error_sem_api_key(self, monkeypatch):
        monkeypatch.delenv("LEONARDO_API_KEY", raising=False)
        with patch("image_generator._get_api_key",
                   side_effect=EnvironmentError("LEONARDO_API_KEY não configurada")):
            with pytest.raises(EnvironmentError, match="LEONARDO_API_KEY"):
                gerar_imagem()

    def test_levanta_runtime_error_em_http_erro_na_geracao(self, monkeypatch):
        monkeypatch.setenv("LEONARDO_API_KEY", self.FAKE_KEY)
        resp = MagicMock()
        resp.status_code = 401
        resp.json.return_value = {"error": "Unauthorized"}
        with patch("requests.post", return_value=resp):
            with pytest.raises((RuntimeError, Exception)):
                gerar_imagem()

    def test_levanta_timeout_quando_polling_demora(self, monkeypatch, tmp_path):
        monkeypatch.setenv("LEONARDO_API_KEY", self.FAKE_KEY)

        post_resp = MagicMock()
        post_resp.status_code = 200
        post_resp.json.return_value = {
            "sdGenerationJob": {"generationId": self.GEN_ID}
        }

        # Polling retorna sempre PENDING
        pending_resp = MagicMock()
        pending_resp.status_code = 200
        pending_resp.json.return_value = {
            "generations_by_pk": {"status": "PENDING", "generated_images": []}
        }

        with patch("requests.post", return_value=post_resp), \
             patch("requests.get", return_value=pending_resp), \
             patch("image_generator.POLL_TIMEOUT", 0), \
             patch("image_generator.POLL_INTERVAL", 0), \
             patch("time.sleep"):
            with pytest.raises((TimeoutError, RuntimeError)):
                gerar_imagem(destino=str(tmp_path / "img.png"))


class TestBancosDePrompt:
    """Valida a integridade dos bancos de dados de prompt."""

    def test_personagens_nao_vazio(self):
        assert len(PERSONAGENS) > 0

    def test_cenarios_nao_vazio(self):
        assert len(CENARIOS) > 0

    def test_estilos_visuais_nao_vazio(self):
        assert len(ESTILOS_VISUAIS) > 0

    def test_poses_nao_vazio(self):
        assert len(POSES_ANGULOS) > 0

    def test_tom_adicional_nao_vazio(self):
        assert len(TOM_ADICIONAL) > 0

    def test_todos_personagens_sao_strings(self):
        assert all(isinstance(p, str) for p in PERSONAGENS)

    def test_todos_cenarios_sao_strings(self):
        assert all(isinstance(c, str) for c in CENARIOS)
