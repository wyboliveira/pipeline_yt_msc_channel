"""
Testes para ken_burns.py
Cobre: funções de efeito (puras), registro EFEITOS_POR_NOME,
       e aplicar_ken_burns com subprocess mockado.
"""
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from ken_burns import (
    EFEITOS,
    EFEITOS_POR_NOME,
    aplicar_ken_burns,
    efeito_diagonal_melancolico,
    efeito_oscilacao,
    efeito_pan_direita,
    efeito_pan_esquerda,
    efeito_pulsacao,
    efeito_pulsacao_pan,
    efeito_zoom_in,
    efeito_zoom_out,
    efeito_zoom_snap,
)

# ── Parâmetros para testar todas as funções de efeito ────────────────────────

TODAS_FUNCOES = [
    efeito_zoom_in,
    efeito_zoom_out,
    efeito_pan_esquerda,
    efeito_pan_direita,
    efeito_diagonal_melancolico,
    efeito_pulsacao,
    efeito_pulsacao_pan,
    efeito_zoom_snap,
    efeito_oscilacao,
]


class TestFuncoesDeEfeito:
    """Testa que cada função de efeito retorna um dict bem formado."""

    @pytest.mark.parametrize("fn", TODAS_FUNCOES, ids=lambda f: f.__name__)
    def test_retorna_dict_com_chaves_obrigatorias(self, fn):
        resultado = fn(frames=3600, fps=60)
        assert isinstance(resultado, dict)
        for chave in ("nome", "z", "x", "y"):
            assert chave in resultado, f"Chave '{chave}' ausente em {fn.__name__}"

    @pytest.mark.parametrize("fn", TODAS_FUNCOES, ids=lambda f: f.__name__)
    def test_todos_os_valores_sao_strings(self, fn):
        resultado = fn(frames=3600, fps=60)
        for chave in ("nome", "z", "x", "y"):
            assert isinstance(resultado[chave], str), (
                f"Valor de '{chave}' em {fn.__name__} deveria ser str"
            )

    @pytest.mark.parametrize("fn", TODAS_FUNCOES, ids=lambda f: f.__name__)
    def test_nome_nao_vazio(self, fn):
        assert fn(frames=1, fps=30)["nome"] != ""

    def test_zoom_in_cresce(self):
        r = efeito_zoom_in(frames=600, fps=60)
        assert "zoom" in r["z"].lower() or "min" in r["z"]

    def test_zoom_out_diminui(self):
        r = efeito_zoom_out(frames=600, fps=60)
        assert "1.10" in r["z"] or "1.1" in r["z"]

    def test_pulsacao_usa_sin(self):
        r = efeito_pulsacao(frames=600, fps=60)
        assert "sin" in r["z"]

    def test_pan_esquerda_e_pan_direita_tem_nomes_distintos(self):
        assert efeito_pan_esquerda(600, 60)["nome"] != efeito_pan_direita(600, 60)["nome"]

    def test_fps_diferente_nao_causa_excecao(self):
        for fps in (24, 30, 60):
            fn = efeito_pulsacao
            resultado = fn(frames=fps * 10, fps=fps)
            assert "nome" in resultado


class TestEfeitosPorNome:
    """Testa o dicionário de lookup EFEITOS_POR_NOME."""

    NOMES_ESPERADOS = {
        "zoom_in", "zoom_out", "pan_esquerda", "pan_direita",
        "diagonal_melancolico", "pulsacao", "pulsacao_pan",
        "zoom_snap", "oscilacao",
    }

    def test_contem_todos_os_efeitos_esperados(self):
        assert self.NOMES_ESPERADOS == set(EFEITOS_POR_NOME.keys())

    def test_valores_sao_callables(self):
        for nome, fn in EFEITOS_POR_NOME.items():
            assert callable(fn), f"Efeito '{nome}' não é callable"

    def test_todos_os_efeitos_registrados(self):
        assert len(EFEITOS) == len(EFEITOS_POR_NOME)

    def test_lookup_por_nome_retorna_efeito_correto(self):
        fn = EFEITOS_POR_NOME["zoom_in"]
        assert fn(600, 60)["nome"] == "zoom_in"


class TestAplicarKenBurns:
    """Testa aplicar_ken_burns com subprocess e filesystem mockados."""

    def _mock_ffmpeg_ok(self, saida: str):
        """Retorna side_effect que cria o arquivo de saída (simula FFmpeg ok)."""
        def _side(cmd, *a, **kw):
            m = MagicMock()
            m.returncode = 0
            if "-version" not in cmd:
                Path(saida).write_bytes(b"\x00" * 100)  # arquivo falso
            return m
        return _side

    def test_erro_imagem_inexistente(self, tmp_path):
        with pytest.raises(FileNotFoundError, match="Imagem não encontrada"):
            aplicar_ken_burns(str(tmp_path / "nao_existe.png"))

    def test_erro_ffmpeg_ausente(self, dummy_image):
        with patch("subprocess.run", side_effect=FileNotFoundError):
            with pytest.raises(FileNotFoundError, match="FFmpeg"):
                aplicar_ken_burns(str(dummy_image))

    def test_erro_efeito_invalido(self, dummy_image):
        with patch("subprocess.run", return_value=MagicMock(returncode=0)):
            with pytest.raises(ValueError, match="não existe"):
                aplicar_ken_burns(str(dummy_image), efeito_nome="efeito_inexistente")

    def test_erro_ffmpeg_returncode_nonzero(self, dummy_image):
        falha = MagicMock(returncode=1, stderr="erro simulado de ffmpeg")
        with patch("subprocess.run", return_value=falha):
            with pytest.raises(RuntimeError, match="FFmpeg falhou"):
                aplicar_ken_burns(str(dummy_image), efeito_nome="zoom_in")

    def test_saida_automatica_quando_nao_informada(self, dummy_image):
        saida_esperada = str(dummy_image.parent / f"{dummy_image.stem}_kenbur.mp4")
        with patch("subprocess.run", side_effect=self._mock_ffmpeg_ok(saida_esperada)):
            resultado = aplicar_ken_burns(str(dummy_image), efeito_nome="zoom_in")
        assert resultado == saida_esperada

    def test_saida_personalizada(self, dummy_image, tmp_path):
        saida = str(tmp_path / "custom_output.mp4")
        with patch("subprocess.run", side_effect=self._mock_ffmpeg_ok(saida)):
            resultado = aplicar_ken_burns(
                str(dummy_image), saida=saida, efeito_nome="zoom_out"
            )
        assert resultado == saida

    def test_todos_os_efeitos_nao_levantam_excecao(self, dummy_image, tmp_path):
        for nome in EFEITOS_POR_NOME:
            saida = str(tmp_path / f"out_{nome}.mp4")
            with patch("subprocess.run", side_effect=self._mock_ffmpeg_ok(saida)):
                resultado = aplicar_ken_burns(
                    str(dummy_image), saida=saida, efeito_nome=nome
                )
            assert resultado == saida

    def test_rgb_split_false_nao_inclui_rgbashift(self, dummy_image, tmp_path):
        saida = str(tmp_path / "sem_rgb.mp4")
        chamadas = []
        def _capturar(cmd, *a, **kw):
            chamadas.append(cmd)
            m = MagicMock(returncode=0)
            if "-version" not in cmd:
                Path(saida).write_bytes(b"\x00")
            return m
        with patch("subprocess.run", side_effect=_capturar):
            aplicar_ken_burns(str(dummy_image), saida=saida,
                              efeito_nome="zoom_in", rgb_split=False)
        cmd_ffmpeg = next(c for c in chamadas if "-version" not in c)
        filtro = cmd_ffmpeg[cmd_ffmpeg.index("-vf") + 1]
        assert "rgbashift" not in filtro

    def test_rgb_split_true_inclui_rgbashift(self, dummy_image, tmp_path):
        saida = str(tmp_path / "com_rgb.mp4")
        chamadas = []
        def _capturar(cmd, *a, **kw):
            chamadas.append(cmd)
            m = MagicMock(returncode=0)
            if "-version" not in cmd:
                Path(saida).write_bytes(b"\x00")
            return m
        with patch("subprocess.run", side_effect=_capturar):
            aplicar_ken_burns(str(dummy_image), saida=saida,
                              efeito_nome="zoom_in", rgb_split=True)
        cmd_ffmpeg = next(c for c in chamadas if "-version" not in c)
        filtro = cmd_ffmpeg[cmd_ffmpeg.index("-vf") + 1]
        assert "rgbashift" in filtro
