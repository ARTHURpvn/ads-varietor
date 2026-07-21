"""Testes de src/ads_varietor/api/storage.py.

Foco em segurança: contenção de caminho, allowlist de extensão, limite de
upload e montagem de ZIP só com os arquivos pedidos.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ads_varietor.api.storage import (
    ALLOWED_EXTENSIONS,
    CHUNK_SIZE,
    DEFAULT_EXTENSION,
    PathTraversalError,
    UploadTooLargeError,
    build_zip_file,
    get_used_bytes,
    is_safe_identifier,
    normalize_extension,
    resolve_within,
    save_upload,
    total_size_of,
)


class FakeUpload:
    """Dublê do UploadFile do Starlette: só `filename` e `read` assíncrono."""

    def __init__(self, payload: bytes, filename: str | None) -> None:
        self.filename = filename
        self._payload = payload
        self._offset = 0
        self.read_sizes: list[int] = []

    async def read(self, size: int = -1) -> bytes:
        self.read_sizes.append(size)
        if size < 0:
            chunk = self._payload[self._offset :]
            self._offset = len(self._payload)
            return chunk
        chunk = self._payload[self._offset : self._offset + size]
        self._offset += len(chunk)
        return chunk


# ---------------------------------------------------------------- resolve_within


def test_resolve_retorna_caminho_dentro_da_base_quando_nome_simples(
    tmp_path: Path,
) -> None:
    assert resolve_within(tmp_path, "arquivo") == tmp_path.resolve() / "arquivo"


def test_resolve_aceita_nome_com_ponto_quando_extensao_de_video(
    tmp_path: Path,
) -> None:
    """Regressão: rejeitar `var_0001.mp4` quebrava todo download individual."""
    resolvido = resolve_within(tmp_path, "var_0001.mp4")

    assert resolvido == tmp_path.resolve() / "var_0001.mp4"


def test_resolve_aceita_multiplos_componentes_quando_todos_seguros(
    tmp_path: Path,
) -> None:
    resolvido = resolve_within(tmp_path, "job-1", "var_0001.mp4")

    assert resolvido == tmp_path.resolve() / "job-1" / "var_0001.mp4"


@pytest.mark.parametrize(
    "parte",
    ["..", "/etc/passwd", "a/b", "a\\b", "", ".", "../..", "./x"],
)
def test_resolve_levanta_path_traversal_quando_componente_perigoso(
    tmp_path: Path, parte: str
) -> None:
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, parte)


def test_resolve_levanta_path_traversal_quando_parte_valida_seguida_de_invalida(
    tmp_path: Path,
) -> None:
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, "job-1", "..")


def test_resolve_levanta_path_traversal_quando_symlink_aponta_para_fora(
    tmp_path: Path,
) -> None:
    """Symlink válido no nome mas resolvendo fora da base deve ser bloqueado."""
    base = tmp_path / "base"
    base.mkdir()
    fora = tmp_path / "fora"
    fora.mkdir()
    segredo = fora / "segredo.mp4"
    segredo.write_bytes(b"segredo")
    (base / "link.mp4").symlink_to(segredo)

    with pytest.raises(PathTraversalError):
        resolve_within(base, "link.mp4")


def test_resolve_aceita_symlink_quando_alvo_esta_dentro_da_base(
    tmp_path: Path,
) -> None:
    base = tmp_path / "base"
    base.mkdir()
    alvo = base / "real.mp4"
    alvo.write_bytes(b"ok")
    (base / "link.mp4").symlink_to(alvo)

    assert resolve_within(base, "link.mp4") == alvo.resolve()


# ------------------------------------------------------------ is_safe_identifier


@pytest.mark.parametrize(
    "valor",
    [
        "a",
        "job1",
        "JOB_1",
        "job-1",
        "_",
        "-",
        "0123456789",
        "A" * 64,
    ],
)
def test_identificador_aceito_quando_alfanumerico_underscore_ou_hifen(
    valor: str,
) -> None:
    assert is_safe_identifier(valor) is True


@pytest.mark.parametrize(
    "valor",
    [
        "",
        ".",
        "job.1",
        "var_0001.mp4",
        "job/1",
        "job\\1",
        "job 1",
        " job",
        "job\t1",
        "A" * 65,
        "café",
        "jobé",
        "ｊｏｂ",
        "job$",
        "job\x00",
        "job\n",
        "\njob",
        "..",
    ],
)
def test_identificador_rejeitado_quando_caractere_fora_do_conjunto(
    valor: str,
) -> None:
    assert is_safe_identifier(valor) is False


# ---------------------------------------------------------- normalize_extension


@pytest.mark.parametrize("extensao", sorted(ALLOWED_EXTENSIONS))
def test_extensao_preservada_quando_esta_na_allowlist(extensao: str) -> None:
    assert normalize_extension(f"video{extensao}") == extensao


def test_extensao_normalizada_para_minusculas_quando_vem_em_maiusculas() -> None:
    assert normalize_extension("VIDEO.MOV") == ".mov"


@pytest.mark.parametrize(
    "nome",
    [
        "payload.exe",
        "script.sh",
        "arquivo.php",
        "sem_extensao",
        "arquivo.",
        ".bashrc",
    ],
)
def test_extensao_cai_no_default_quando_desconhecida_ou_ausente(nome: str) -> None:
    assert normalize_extension(nome) == DEFAULT_EXTENSION


def test_extensao_cai_no_default_quando_filename_e_none() -> None:
    assert normalize_extension(None) == DEFAULT_EXTENSION


def test_extensao_cai_no_default_quando_filename_e_string_vazia() -> None:
    assert normalize_extension("") == DEFAULT_EXTENSION


@pytest.mark.parametrize(
    "nome",
    ["../../etc/passwd.mp4", "a;rm -rf /.mp4", "..\\..\\windows\\x.mp4"],
)
def test_extensao_descarta_o_nome_quando_nome_e_malicioso(nome: str) -> None:
    """Só a extensão sobrevive; nada do caminho ou do shell é aproveitado."""
    resultado = normalize_extension(nome)

    assert resultado in ALLOWED_EXTENSIONS
    assert resultado.startswith(".")
    assert "/" not in resultado
    assert "\\" not in resultado
    assert ";" not in resultado


# -------------------------------------------------------------------- save_upload


async def test_upload_gravado_com_conteudo_integro_quando_dentro_do_limite(
    tmp_path: Path,
) -> None:
    conteudo = b"conteudo-de-video"
    upload = FakeUpload(conteudo, "entrada.mp4")

    destino, escrito = await save_upload(
        upload, tmp_path / "uploads", max_bytes=1024
    )

    assert destino.read_bytes() == conteudo
    assert escrito == len(conteudo)
    assert destino.parent == tmp_path / "uploads"


async def test_upload_lido_em_blocos_quando_arquivo_maior_que_um_chunk(
    tmp_path: Path,
) -> None:
    conteudo = b"x" * (CHUNK_SIZE * 2 + 10)
    upload = FakeUpload(conteudo, "grande.mp4")

    destino, escrito = await save_upload(
        upload, tmp_path / "uploads", max_bytes=len(conteudo)
    )

    assert escrito == len(conteudo)
    assert destino.stat().st_size == len(conteudo)
    assert upload.read_sizes == [CHUNK_SIZE] * 4


async def test_upload_salvo_com_uuid_quando_nome_enviado_e_malicioso(
    tmp_path: Path,
) -> None:
    upload = FakeUpload(b"dados", "../../etc/passwd.mp4")
    destino_dir = tmp_path / "uploads"

    destino, _ = await save_upload(upload, destino_dir, max_bytes=1024)

    assert destino.parent == destino_dir
    assert "passwd" not in destino.name
    assert ".." not in destino.name
    assert destino.suffix == ".mp4"
    assert len(destino.stem) == 32
    int(destino.stem, 16)  # o stem é hex puro (UUID)


async def test_upload_salvo_com_extensao_default_quando_extensao_nao_permitida(
    tmp_path: Path,
) -> None:
    upload = FakeUpload(b"dados", "malware.exe")

    destino, _ = await save_upload(upload, tmp_path / "uploads", max_bytes=1024)

    assert destino.suffix == DEFAULT_EXTENSION


async def test_upload_levanta_too_large_e_nao_deixa_residuo_quando_excede_limite(
    tmp_path: Path,
) -> None:
    destino_dir = tmp_path / "uploads"
    upload = FakeUpload(b"y" * 5000, "grande.mp4")

    with pytest.raises(UploadTooLargeError):
        await save_upload(upload, destino_dir, max_bytes=100)

    assert list(destino_dir.iterdir()) == []


async def test_upload_aceito_quando_tamanho_e_exatamente_o_limite(
    tmp_path: Path,
) -> None:
    upload = FakeUpload(b"z" * 100, "limite.mp4")

    _, escrito = await save_upload(upload, tmp_path / "uploads", max_bytes=100)

    assert escrito == 100


async def test_upload_nao_deixa_residuo_quando_leitura_falha(
    tmp_path: Path,
) -> None:
    class UploadQuebrado:
        filename = "quebrado.mp4"

        async def read(self, size: int = -1) -> bytes:
            raise OSError("falha na leitura")

    destino_dir = tmp_path / "uploads"

    with pytest.raises(OSError):
        await save_upload(UploadQuebrado(), destino_dir, max_bytes=1024)

    assert list(destino_dir.iterdir()) == []


async def test_uploads_recebem_nomes_distintos_quando_mesmo_arquivo_enviado_duas_vezes(
    tmp_path: Path,
) -> None:
    destino_dir = tmp_path / "uploads"

    primeiro, _ = await save_upload(
        FakeUpload(b"a", "video.mp4"), destino_dir, max_bytes=1024
    )
    segundo, _ = await save_upload(
        FakeUpload(b"b", "video.mp4"), destino_dir, max_bytes=1024
    )

    assert primeiro != segundo
    assert len(list(destino_dir.iterdir())) == 2


# ------------------------------------------------------------------ build_zip_file


async def test_zip_contem_apenas_os_arquivos_pedidos_quando_diretorio_tem_extras(
    tmp_path: Path,
) -> None:
    """Regressão: varrer o diretório incluía saídas parciais corrompidas."""
    origem = tmp_path / "saida"
    origem.mkdir()
    (origem / "var_0001.mp4").write_bytes(b"um")
    (origem / "var_0002.mp4").write_bytes(b"dois")
    (origem / "var_0003.mp4.part").write_bytes(b"parcial")
    (origem / "temp.log").write_bytes(b"log")

    destino = tmp_path / "pacote.zip"
    await build_zip_file(origem, ["var_0001.mp4", "var_0002.mp4"], destino)

    with zipfile.ZipFile(destino) as archive:
        assert sorted(archive.namelist()) == ["var_0001.mp4", "var_0002.mp4"]
        assert archive.read("var_0001.mp4") == b"um"


async def test_zip_ignora_nome_inexistente_sem_quebrar_quando_arquivo_sumiu(
    tmp_path: Path,
) -> None:
    origem = tmp_path / "saida"
    origem.mkdir()
    (origem / "var_0001.mp4").write_bytes(b"um")

    destino = tmp_path / "pacote.zip"
    await build_zip_file(
        origem, ["var_0001.mp4", "nao_existe.mp4"], destino
    )

    with zipfile.ZipFile(destino) as archive:
        assert archive.namelist() == ["var_0001.mp4"]


async def test_zip_ignora_subdiretorio_quando_nome_aponta_para_pasta(
    tmp_path: Path,
) -> None:
    origem = tmp_path / "saida"
    (origem / "pasta").mkdir(parents=True)
    (origem / "var_0001.mp4").write_bytes(b"um")

    destino = tmp_path / "pacote.zip"
    await build_zip_file(origem, ["pasta", "var_0001.mp4"], destino)

    with zipfile.ZipFile(destino) as archive:
        assert archive.namelist() == ["var_0001.mp4"]


async def test_zip_fica_vazio_e_valido_quando_lista_de_arquivos_e_vazia(
    tmp_path: Path,
) -> None:
    origem = tmp_path / "saida"
    origem.mkdir()
    (origem / "var_0001.mp4").write_bytes(b"um")

    destino = tmp_path / "pacote.zip"
    retorno = await build_zip_file(origem, [], destino)

    assert retorno == destino
    with zipfile.ZipFile(destino) as archive:
        assert archive.namelist() == []


# -------------------------------------------------------------------- tamanhos


def test_total_size_soma_apenas_os_arquivos_pedidos_quando_ha_extras(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.mp4").write_bytes(b"1234")
    (tmp_path / "b.mp4").write_bytes(b"12345")
    (tmp_path / "ignorado.mp4").write_bytes(b"1234567890")

    assert total_size_of(tmp_path, ["a.mp4", "b.mp4"]) == 9


def test_total_size_ignora_inexistente_e_diretorio_quando_nome_nao_e_arquivo(
    tmp_path: Path,
) -> None:
    (tmp_path / "a.mp4").write_bytes(b"1234")
    (tmp_path / "pasta").mkdir()

    assert total_size_of(tmp_path, ["a.mp4", "sumiu.mp4", "pasta"]) == 4


def test_total_size_zero_quando_lista_vazia(tmp_path: Path) -> None:
    assert total_size_of(tmp_path, []) == 0


async def test_used_bytes_soma_recursivamente_quando_ha_subdiretorios(
    tmp_path: Path,
) -> None:
    (tmp_path / "raiz.mp4").write_bytes(b"12345")
    sub = tmp_path / "job-1"
    sub.mkdir()
    (sub / "var_0001.mp4").write_bytes(b"123")
    (sub / "var_0002.mp4").write_bytes(b"12")

    assert await get_used_bytes(tmp_path) == 10


async def test_used_bytes_zero_quando_diretorio_nao_existe(tmp_path: Path) -> None:
    assert await get_used_bytes(tmp_path / "inexistente") == 0


async def test_used_bytes_zero_quando_diretorio_vazio(tmp_path: Path) -> None:
    vazio = tmp_path / "vazio"
    vazio.mkdir()

    assert await get_used_bytes(vazio) == 0
