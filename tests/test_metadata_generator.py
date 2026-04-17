"""
Testes para metadata_generator.py
Cobre: limpeza de nomes de arquivo, verificação do Ollama,
       parsing de JSON, fallbacks e montagem do resultado final.
"""
import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from metadata_generator import (
    NOME_CANAL,
    _checar_ollama,
    _gerar_com_ollama,
    _limpar_nome_arquivo,
    gerar_metadados,
)


class TestLimparNomeArquivo:
    """Testa a extração e limpeza do nome da música a partir do nome do arquivo."""

    @pytest.mark.parametrize("entrada, esperado", [
        ("bohemian_rhapsody.mp3",           "Bohemian Rhapsody"),
        ("my-song (slowed).wav",            "My Song"),
        ("my-song (reverb).wav",            "My Song"),
        ("artist - song (slowed + reverb).mp3", "Artist Song"),
        ("track_name_here.flac",            "Track Name Here"),
        ("song - slowed version.ogg",       "Song"),
        ("song - reverb mix.m4a",           "Song"),
        ("Simple Song.mp3",                 "Simple Song"),
        ("Song [slowed].mp3",               "Song"),
    ])
    def test_casos_de_limpeza(self, entrada, esperado):
        resultado = _limpar_nome_arquivo(entrada)
        # Normaliza espaços múltiplos para comparação
        assert resultado.strip() == esperado.strip()

    def test_retorna_string(self):
        assert isinstance(_limpar_nome_arquivo("qualquer.mp3"), str)

    def test_nao_retorna_vazio_para_nome_simples(self):
        assert _limpar_nome_arquivo("musica.mp3") != ""

    def test_capitaliza_primeira_letra(self):
        resultado = _limpar_nome_arquivo("lower case.mp3")
        assert resultado[0].isupper()


class TestChecarOllama:
    """Testa a verificação de acessibilidade do Ollama."""

    def test_levanta_runtime_error_quando_ollama_inacessivel(self):
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(RuntimeError, match="Ollama não está acessível"):
                _checar_ollama()

    def test_levanta_runtime_error_em_timeout(self):
        with patch("requests.get", side_effect=requests.exceptions.Timeout):
            with pytest.raises(RuntimeError, match="Ollama"):
                _checar_ollama()

    def test_nao_levanta_quando_ollama_acessivel(self):
        resp = MagicMock()
        resp.raise_for_status.return_value = None
        with patch("requests.get", return_value=resp):
            _checar_ollama()   # não deve lançar exceção


class TestGerarComOllama:
    """Testa a chamada ao Ollama e o parsing da resposta."""

    def _mock_ollama(self, payload: dict, status: int = 200):
        resp = MagicMock()
        resp.status_code = status
        resp.json.return_value = {"response": json.dumps(payload)}
        resp.text = json.dumps(payload)
        return resp

    def test_retorna_dict_com_campos_obrigatorios(self):
        payload = {
            "creditos": "Créditos teste",
            "hashtags": "#slowedreverb",
            "tags": ["tag1", "tag2", "t3", "t4", "t5", "t6", "t7", "t8", "t9", "t10"],
        }
        with patch("requests.post", return_value=self._mock_ollama(payload)):
            resultado = _gerar_com_ollama("Artista - Música")
        assert "creditos" in resultado
        assert "hashtags" in resultado
        assert "tags" in resultado

    def test_levanta_runtime_error_em_http_erro(self):
        resp = MagicMock()
        resp.status_code = 500
        resp.text = "Internal Server Error"
        with patch("requests.post", return_value=resp):
            with pytest.raises(RuntimeError, match="HTTP 500"):
                _gerar_com_ollama("Artista")

    def test_levanta_runtime_error_em_json_invalido(self):
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": "não é json válido {{{"}
        with patch("requests.post", return_value=resp):
            with pytest.raises(RuntimeError, match="JSON válido"):
                _gerar_com_ollama("Artista")

    def test_remove_bloco_think_do_qwen3(self):
        payload = {
            "creditos": "c",
            "hashtags": "#h",
            "tags": ["t"] * 10,
        }
        resposta_com_think = f"<think>pensamento interno</think>\n{json.dumps(payload)}"
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": resposta_com_think}
        with patch("requests.post", return_value=resp):
            resultado = _gerar_com_ollama("Artista")
        assert isinstance(resultado["tags"], list)

    def test_remove_bloco_de_codigo_markdown(self):
        payload = {"creditos": "c", "hashtags": "#h", "tags": ["t"] * 10}
        resposta_com_md = f"```json\n{json.dumps(payload)}\n```"
        resp = MagicMock()
        resp.status_code = 200
        resp.json.return_value = {"response": resposta_com_md}
        with patch("requests.post", return_value=resp):
            resultado = _gerar_com_ollama("Artista")
        assert isinstance(resultado["tags"], list)

    def test_fallback_tags_quando_nao_lista(self):
        payload = {"creditos": "c", "hashtags": "#h", "tags": "tag1, tag2"}
        with patch("requests.post", return_value=self._mock_ollama(payload)):
            resultado = _gerar_com_ollama("Artista")
        assert isinstance(resultado["tags"], list)

    def test_hashtags_lista_vira_string(self):
        payload = {
            "creditos": "c",
            "hashtags": ["#slowedreverb", "#anime"],
            "tags": ["t"] * 10,
        }
        with patch("requests.post", return_value=self._mock_ollama(payload)):
            resultado = _gerar_com_ollama("Artista")
        assert isinstance(resultado["hashtags"], str)

    def test_levanta_erro_campo_creditos_ausente(self):
        payload = {"hashtags": "#h", "tags": ["t"] * 10}
        with patch("requests.post", return_value=self._mock_ollama(payload)):
            with pytest.raises(RuntimeError, match="'creditos'"):
                _gerar_com_ollama("Artista")


class TestGerarMetadados:
    """Testa gerar_metadados — função pública completa."""

    def _mock_all(self, tags=None):
        """Prepara todos os mocks necessários (Ollama check + geração)."""
        tags = tags or [f"tag{i}" for i in range(10)]
        payload = {
            "creditos": "Créditos da música",
            "hashtags": "#slowedreverb #anime",
            "tags": tags,
        }
        ok_get  = MagicMock()
        ok_get.raise_for_status.return_value = None
        ok_post = MagicMock()
        ok_post.status_code = 200
        ok_post.json.return_value = {"response": json.dumps(payload)}
        return ok_get, ok_post

    def test_retorna_dict_com_titulo_descricao_tags(self):
        ok_get, ok_post = self._mock_all()
        with patch("requests.get", return_value=ok_get), \
             patch("requests.post", return_value=ok_post):
            resultado = gerar_metadados("bohemian_rhapsody.mp3")
        assert set(resultado.keys()) >= {"titulo", "descricao", "tags"}

    def test_titulo_contem_nome_canal(self):
        ok_get, ok_post = self._mock_all()
        with patch("requests.get", return_value=ok_get), \
             patch("requests.post", return_value=ok_post):
            resultado = gerar_metadados("bohemian_rhapsody.mp3")
        assert NOME_CANAL in resultado["titulo"]

    def test_titulo_contem_slowed_reverb(self):
        ok_get, ok_post = self._mock_all()
        with patch("requests.get", return_value=ok_get), \
             patch("requests.post", return_value=ok_post):
            resultado = gerar_metadados("bohemian_rhapsody.mp3")
        assert "slowed" in resultado["titulo"].lower()
        assert "reverb" in resultado["titulo"].lower()

    def test_tags_e_lista(self):
        ok_get, ok_post = self._mock_all()
        with patch("requests.get", return_value=ok_get), \
             patch("requests.post", return_value=ok_post):
            resultado = gerar_metadados("song.mp3")
        assert isinstance(resultado["tags"], list)
        assert len(resultado["tags"]) > 0

    def test_descricao_contem_titulo(self):
        ok_get, ok_post = self._mock_all()
        with patch("requests.get", return_value=ok_get), \
             patch("requests.post", return_value=ok_post):
            resultado = gerar_metadados("song.mp3")
        assert resultado["titulo"] in resultado["descricao"]

    def test_levanta_erro_quando_ollama_fora(self):
        with patch("requests.get", side_effect=requests.exceptions.ConnectionError):
            with pytest.raises(RuntimeError, match="Ollama"):
                gerar_metadados("song.mp3")
