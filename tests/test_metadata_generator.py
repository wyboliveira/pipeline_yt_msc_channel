"""
Testes para metadata_generator.py
Cobre: limpeza de nomes de arquivo e montagem do resultado final.
Ollama foi removido — metadados são gerados 100% localmente.
"""
import pytest

from metadata_generator import (
    NOME_CANAL,
    TAG_POOL,
    _limpar_nome_arquivo,
    gerar_metadados,
)


class TestLimparNomeArquivo:
    """Testa a extração e limpeza do nome da música a partir do nome do arquivo."""

    @pytest.mark.parametrize("entrada, esperado", [
        # Separadores de palavra (underscore/hífen colado) → espaço
        ("bohemian_rhapsody.mp3",                        "Bohemian Rhapsody"),
        ("my-song (slowed).wav",                         "My Song"),
        ("my-song (reverb).wav",                         "My Song"),
        ("track_name_here.flac",                         "Track Name Here"),
        ("Simple Song.mp3",                              "Simple Song"),
        # Remoção de sufixos slowed/reverb
        ("song - slowed version.ogg",                    "Song"),
        ("song - reverb mix.m4a",                        "Song"),
        ("Song [slowed].mp3",                            "Song"),
        # Separador artista - música preservado
        ("artist - song (slowed + reverb).mp3",          "Artist - Song"),
        ("Falxce - Space Dawn (128 kbps)-slowedandreverbstudio.mp3", "Falxce - Space Dawn"),
        ("Artista - Nome Da Musica.mp3",                 "Artista - Nome Da Musica"),
        # Remoção de tags de qualidade
        ("Song (128 kbps).mp3",                          "Song"),
        ("Song (256 kbps).mp3",                          "Song"),
        ("Song (320kbps).mp3",                           "Song"),
        # Remoção de labels do YouTube
        ("Song (Official Video).mp3",                    "Song"),
        ("Song (OFFICIAL AUDIO).mp3",                    "Song"),
        ("Song (Youtube).mp3",                           "Song"),
        ("Artist - Song (Lyrics).mp3",                   "Artist - Song"),
        ("Artist - Song (HD).mp3",                       "Artist - Song"),
    ])
    def test_casos_de_limpeza(self, entrada, esperado):
        resultado = _limpar_nome_arquivo(entrada)
        assert resultado.strip() == esperado.strip()

    def test_retorna_string(self):
        assert isinstance(_limpar_nome_arquivo("qualquer.mp3"), str)

    def test_nao_retorna_vazio_para_nome_simples(self):
        assert _limpar_nome_arquivo("musica.mp3") != ""

    def test_capitaliza_primeira_letra(self):
        resultado = _limpar_nome_arquivo("lower case.mp3")
        assert resultado[0].isupper()


class TestGerarMetadados:
    """Testa gerar_metadados — função pública completa (sem dependências externas)."""

    def test_retorna_dict_com_chaves_obrigatorias(self):
        resultado = gerar_metadados("bohemian_rhapsody.mp3")
        assert set(resultado.keys()) >= {"titulo", "nome_musica", "descricao", "tags"}

    def test_titulo_contem_nome_canal(self):
        resultado = gerar_metadados("bohemian_rhapsody.mp3")
        assert NOME_CANAL in resultado["titulo"]

    def test_titulo_contem_slowed_e_reverb(self):
        resultado = gerar_metadados("bohemian_rhapsody.mp3")
        assert "slowed" in resultado["titulo"].lower()
        assert "reverb" in resultado["titulo"].lower()

    def test_tags_e_lista_com_dez_itens(self):
        resultado = gerar_metadados("song.mp3")
        assert isinstance(resultado["tags"], list)
        assert len(resultado["tags"]) == 10

    def test_tags_sao_subconjunto_do_pool(self):
        resultado = gerar_metadados("song.mp3")
        for tag in resultado["tags"]:
            assert tag in TAG_POOL

    def test_descricao_contem_titulo(self):
        resultado = gerar_metadados("song.mp3")
        assert resultado["titulo"] in resultado["descricao"]

    def test_descricao_contem_creditos_com_nome_musica(self):
        resultado = gerar_metadados("artist - my song.mp3")
        assert resultado["nome_musica"] in resultado["descricao"]

    def test_creditos_formato_correto(self):
        resultado = gerar_metadados("artist - my song.mp3")
        assert "todos os direitos reservados" in resultado["descricao"].lower()

    def test_tags_variam_entre_chamadas(self):
        """Amostragem aleatória deve gerar conjuntos distintos com alta probabilidade."""
        tags1 = set(gerar_metadados("song.mp3")["tags"])
        tags2 = set(gerar_metadados("song.mp3")["tags"])
        # Com 58 tags no pool e 10 sorteadas, a probabilidade de serem idênticas
        # é astronomicamente baixa — se falhar, é bug no random.sample
        assert tags1 != tags2 or len(TAG_POOL) < 11

    def test_nome_musica_preservado_no_resultado(self):
        resultado = gerar_metadados("Falxce - Space Dawn (128 kbps)-slowedandreverbstudio.mp3")
        assert resultado["nome_musica"] == "Falxce - Space Dawn"

    def test_titulo_usa_nome_limpo(self):
        resultado = gerar_metadados("Falxce - Space Dawn (128 kbps)-slowedandreverbstudio.mp3")
        assert "Falxce - Space Dawn" in resultado["titulo"]
        assert "128 kbps" not in resultado["titulo"]
