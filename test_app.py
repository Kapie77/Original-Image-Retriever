# comando do teste:
# python -m unittest -v test_app.py

# Testes automatizados de todas as coisas possíveis que pensei
# ----------------------------------------------------- #

import unittest
from unittest.mock import patch, MagicMock
from urllib.parse import urlparse

import app as oir
import socket
import urllib.error
import urllib.request

from io import BytesIO
from unittest.mock import MagicMock, patch
from email.message import Message
from unittest.mock import patch

import time

# ====================================================== #
#                   URL VALIDATION TESTS
# ====================================================== #

class TestURLValidation(unittest.TestCase):
    """Tests URL validation without making real network requests."""

    @patch("app.socket.getaddrinfo")
    def test_accepts_public_https_image_url(self, mock_dns):
        """A valid public HTTPS image URL should be accepted."""
        mock_dns.return_value = [
            (
                oir.socket.AF_INET,
                oir.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            )
        ]

        result = oir.validate_url(
            "https://images.example.com/photo.jpg"
        )

        self.assertEqual(result.scheme, "https")
        self.assertEqual(result.hostname, "images.example.com")

    def test_rejects_http_url(self):
        """HTTP URLs must be rejected."""
        with self.assertRaises(ValueError):
            oir.validate_url("http://images.example.com/photo.jpg")

    def test_rejects_localhost(self):
        """Localhost must be rejected."""
        with self.assertRaises(ValueError):
            oir.validate_url("https://localhost/photo.jpg")

    def test_rejects_loopback_ip(self):
        """Loopback IP addresses must be rejected."""
        with self.assertRaises(ValueError):
            oir.validate_url("https://127.0.0.1/photo.jpg")

    def test_rejects_private_ip(self):
        """Private IP addresses must be rejected."""
        with self.assertRaises(ValueError):
            oir.validate_url("https://192.168.1.10/photo.jpg")

    def test_rejects_embedded_credentials(self):
        """URLs containing usernames or passwords must be rejected."""
        with self.assertRaisesRegex(
            ValueError,
            "credentials",
        ):
            oir.validate_url(
                "https://username:password@example.com/photo.jpg"
            )

    def test_rejects_disallowed_port(self):
        """Non-standard HTTPS ports must be rejected."""
        with self.assertRaises(ValueError):
            oir.validate_url(
                "https://images.example.com:8443/photo.jpg"
            )

    def test_rejects_url_without_image_extension(self):
        """URLs without a recognized image extension must be rejected."""
        with self.assertRaises(ValueError):
            oir.validate_url(
                "https://images.example.com/gallery"
            )

    @patch("app.socket.getaddrinfo")
    def test_rejects_domain_resolving_to_private_ip(self, mock_dns):
        """A domain resolving to a private IP must be rejected."""
        mock_dns.return_value = [
            (
                oir.socket.AF_INET,
                oir.socket.SOCK_STREAM,
                6,
                "",
                ("192.168.1.10", 443),
            )
        ]

        with self.assertRaisesRegex(ValueError, "not public"):
            oir.validate_url(
                "https://images.example.com/photo.jpg"
            )

    @patch("app.socket.getaddrinfo")
    def test_rejects_domain_with_mixed_public_and_private_ips(
        self,
        mock_dns,
    ):
        """Every resolved IP must be public."""
        mock_dns.return_value = [
            (
                oir.socket.AF_INET,
                oir.socket.SOCK_STREAM,
                6,
                "",
                ("93.184.216.34", 443),
            ),
            (
                oir.socket.AF_INET,
                oir.socket.SOCK_STREAM,
                6,
                "",
                ("192.168.1.10", 443),
            ),
        ]

        with self.assertRaisesRegex(ValueError, "not public"):
            oir.validate_url(
                "https://images.example.com/photo.jpg"
            )


# ====================================================== #
#                   DOWNLOAD SIZE TESTS
# ====================================================== #

class TestDownloadSizeLimit(unittest.TestCase):
    """Tests download-size enforcement without external requests."""

    def setUp(self):
        self.response = MagicMock()
        self.response.__enter__.return_value = self.response
        self.response.__exit__.return_value = False
        self.response.geturl.return_value = (
            "https://images.example.com/photo.jpg"
        )

        self.opener = MagicMock()
        self.opener.open.return_value = self.response

        self.url = "https://images.example.com/photo.jpg"

    @patch("app.validate_url")
    @patch("app.urllib.request.build_opener")
    def test_rejects_file_exceeding_declared_size(
        self,
        mock_build_opener,
        mock_validate_url,
    ):
        """A Content-Length above the limit must be rejected immediately."""
        mock_validate_url.return_value = urlparse(self.url)
        mock_build_opener.return_value = self.opener

        self.response.headers = {
            "Content-Length": str(oir.MAX_FILE_SIZE + 1)
        }

        with self.assertRaisesRegex(
            oir.ImageError,
            "25 MB size limit",
        ):
            oir.fetch_image(self.url)

        # The response should be rejected before reading its contents.
        self.response.read.assert_not_called()

    @patch("app.validate_url")
    @patch("app.urllib.request.build_opener")
    def test_rejects_file_exceeding_limit_during_read(
        self,
        mock_build_opener,
        mock_validate_url,
    ):
        """The actual downloaded bytes must not exceed the size limit."""
        mock_validate_url.return_value = urlparse(self.url)
        mock_build_opener.return_value = self.opener

        self.response.headers = {}

        # Use a small limit so the test does not allocate 25 MB.
        with patch.object(oir, "MAX_FILE_SIZE", 100):
            self.response.read.side_effect = [
                b"x" * 101,
            ]

            with self.assertRaisesRegex(
                oir.ImageError,
                "25 MB size limit",
            ):
                oir.fetch_image(self.url)

        self.response.read.assert_called_once()

# ====================================================== #
#              REDIRECT SECURITY TESTS
# ====================================================== #

class TestRedirectSecurity(unittest.TestCase):
    """
    Tests redirect destination validation and the configured
    maximum number of HTTP redirects.
    """

    def get_redirect_handler(self):
        """
        Captures the SafeRedirectHandler class created inside
        fetch_image(), without making a real network request.
        """

        captured = {}

        def fake_build_opener(*handlers):
            captured["handler"] = handlers[0]

            fake_opener = MagicMock()
            fake_opener.open.side_effect = urllib.error.URLError(
                "Stop test before making a network request."
            )

            return fake_opener

        public_dns_result = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]

        with patch(
            "app.socket.getaddrinfo",
            return_value=public_dns_result,
        ):
            with patch(
                "app.urllib.request.build_opener",
                side_effect=fake_build_opener,
            ):
                with self.assertRaises(oir.ImageError):
                    oir.fetch_image(
                        "https://source.example/image.png"
                    )

        return captured["handler"]

    def test_accepts_redirect_to_public_https_url(self):
        """
        A redirect to a valid public HTTPS image URL should
        be accepted.
        """

        handler_class = self.get_redirect_handler()
        handler = handler_class()

        request = urllib.request.Request(
            "https://source.example/image.png"
        )

        public_dns_result = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]

        with patch(
            "app.socket.getaddrinfo",
            return_value=public_dns_result,
        ):
            redirected = handler.redirect_request(
                request,
                BytesIO(b""),
                302,
                "Found",
                {},
                "https://images.example/photo.png",
            )

        self.assertIsNotNone(redirected)
        self.assertEqual(
            redirected.full_url,
            "https://images.example/photo.png",
        )

    def test_rejects_redirect_to_localhost(self):
        """
        Redirects to localhost must be rejected.
        """

        handler_class = self.get_redirect_handler()
        handler = handler_class()

        request = urllib.request.Request(
            "https://source.example/image.png"
        )

        with self.assertRaises(ValueError):
            handler.redirect_request(
                request,
                BytesIO(b""),
                302,
                "Found",
                {},
                "https://localhost/image.png",
            )

    def test_rejects_redirect_to_private_ip(self):
        """
        Redirects to a private IP address must be rejected.
        """

        handler_class = self.get_redirect_handler()
        handler = handler_class()

        request = urllib.request.Request(
            "https://source.example/image.png"
        )

        with self.assertRaises(ValueError):
            handler.redirect_request(
                request,
                BytesIO(b""),
                302,
                "Found",
                {},
                "https://192.168.1.10/image.png",
            )

    def test_redirect_limit_is_five(self):
        """
        The redirect handler must use the configured limit
        of five redirects.
        """

        handler_class = self.get_redirect_handler()
        handler = handler_class()

        self.assertEqual(oir.MAX_REDIRECTS, 5)
        self.assertEqual(handler.max_redirections, 5)
        self.assertEqual(handler.max_repeats, 5)


    def test_stops_after_five_redirects(self):
        """
        Verifies that urllib raises HTTPError when the redirect
        limit has already been reached.
        """

        handler_class = self.get_redirect_handler()
        handler = handler_class()

        request = urllib.request.Request(
            "https://source.example/image0.png"
        )
        request.timeout = 20

        # Simulate five redirects already followed.
        request.redirect_dict = {
            f"https://images.example/image{number}.png": 1
            for number in range(1, 6)
        }

        headers = Message()
        headers["Location"] = "https://images.example/image6.png"

        public_dns_result = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("93.184.216.34", 443),
            )
        ]

        with patch(
            "app.socket.getaddrinfo",
            return_value=public_dns_result,
        ):
            with self.assertRaises(urllib.error.HTTPError) as context:
                handler.http_error_302(
                    request,
                    BytesIO(b""),
                    302,
                    "Found",
                    headers,
                )

        self.assertIn(
            "redirect error",
            str(context.exception).lower(),
        )



class TestOriginalImageRecovery(unittest.TestCase):

    @patch("app.socket.getaddrinfo")
    def test_fandom_url_requests_original_image(self, mock_getaddrinfo):
        """Verifica se uma URL do Fandom é convertida para solicitar a imagem original."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "",
             ("93.184.216.34", 443))
        ]

        url = (
            "https://static.wikia.nocookie.net/example/"
            "logo.png/revision/latest/scale-to-width-down/1000"
        )

        result = oir.build_original_url(url)

        self.assertIn("logo.png", result)
        self.assertIn("format=original", result)
        self.assertNotIn("scale-to-width-down", result)

    @patch("app.socket.getaddrinfo")
    def test_non_fandom_url_remains_unchanged(self, mock_getaddrinfo):
        """Verifica se uma URL de imagem fora do Fandom permanece inalterada."""
        mock_getaddrinfo.return_value = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "",
             ("93.184.216.34", 443))
        ]

        url = "https://images.example.com/photo.jpg"

        result = oir.build_original_url(url)

        self.assertEqual(result, url)

    def test_reddit_image_removes_preview_parameters(self):
        """Verifica se os parâmetros de redimensionamento são removidos de imagens do Reddit."""
        url = "https://i.redd.it/example.jpg?width=100&format=pjpg"

        result = oir.resolve_original_image_url(url)

        self.assertEqual(result, "https://i.redd.it/example.jpg")

    def test_duckduckgo_proxy_resolves_source_url(self):
        """Verifica se uma URL de proxy do DuckDuckGo revela a URL original."""
        url = (
            "https://external-content.duckduckgo.com/iu/"
            "?u=https%3A%2F%2Fimages.example.com%2Fphoto.png"
        )

        result = oir.resolve_image_url(url)

        self.assertEqual(result, "https://images.example.com/photo.png")

    def test_reddit_preview_converts_matching_filename(self):
        """Verifica a conversão de uma URL preview do Reddit com nome compatível."""
        url = (
            "https://preview.redd.it/abc123-v1-photo.jpg"
            "?width=640&crop=smart"
        )

        result = oir.resolve_original_image_url(url)

        self.assertEqual(result, "https://i.redd.it/photo.jpg")

    def test_reddit_preview_preserves_unrecognized_filename(self):
        """Garante que nomes desconhecidos não sejam convertidos por suposição."""
        url = "https://preview.redd.it/abc123.jpg?width=640"

        result = oir.resolve_original_image_url(url)

        self.assertEqual(result, url)

    def test_reddit_preview_supports_uppercase_extension(self):
        """Verifica se extensões em maiúsculas são reconhecidas."""
        url = "https://preview.redd.it/abc123-v1-photo.JPG?width=640"

        result = oir.resolve_original_image_url(url)

        self.assertEqual(result, "https://i.redd.it/photo.JPG")

    def test_reddit_non_image_host_remains_unchanged(self):
        """Garante que URLs de outros hosts não sejam modificadas."""
        url = "https://images.example.com/photo.jpg?width=640"

        result = oir.resolve_original_image_url(url)

        self.assertEqual(result, url)



class TestImageIdentification(unittest.TestCase):

    def test_identifies_png(self):
        """Reconhece PNG pela assinatura binária."""
        result = oir.identify_image(
            b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
            "image/jpeg"
        )
        self.assertEqual(result, ("PNG", "png"))

    def test_identifies_jpeg(self):
        """Reconhece JPEG pela assinatura binária."""
        result = oir.identify_image(
            b"\xff\xd8\xff" + b"\x00" * 16,
            "image/png"
        )
        self.assertEqual(result, ("JPEG", "jpg"))

    def test_identifies_gif87a(self):
        """Reconhece imagens GIF87a."""
        result = oir.identify_image(b"GIF87a" + b"\x00" * 16, "")
        self.assertEqual(result, ("GIF", "gif"))

    def test_identifies_gif89a(self):
        """Reconhece imagens GIF89a."""
        result = oir.identify_image(b"GIF89a" + b"\x00" * 16, "")
        self.assertEqual(result, ("GIF", "gif"))

    def test_identifies_webp(self):
        """Reconhece WebP pela estrutura RIFF/WEBP."""
        data = b"RIFF" + (16).to_bytes(4, "little") + b"WEBP" + b"\x00" * 12
        result = oir.identify_image(data, "image/jpeg")
        self.assertEqual(result, ("WebP", "webp"))

    def test_identifies_avif(self):
        """Reconhece AVIF pelo identificador de marca do contêiner ISO BMFF."""
        data = (
            b"\x00\x00\x00\x18"
            b"ftyp"
            b"avif"
            b"\x00\x00\x00\x00"
            b"mif1"
            b"\x00\x00\x00\x00"
        )
        result = oir.identify_image(data, "")
        self.assertEqual(result, ("AVIF", "avif"))

    def test_identifies_bmp(self):
        """Reconhece BMP pela assinatura BM."""
        result = oir.identify_image(b"BM" + b"\x00" * 16, "")
        self.assertEqual(result, ("BMP", "bmp"))

    def test_identifies_svg_with_xml_declaration(self):
        """Reconhece SVG precedido por declaração XML."""
        data = b'<?xml version="1.0"?>\n<svg xmlns="http://www.w3.org/2000/svg"></svg>'
        result = oir.identify_image(data, "text/xml")
        self.assertEqual(result, ("SVG", "svg"))

    def test_rejects_html_disguised_as_svg(self):
        """Não deve identificar uma página HTML como SVG."""
        data = b"<!doctype html><html><body><svg></svg></body></html>"
        result = oir.identify_image(data, "image/svg+xml")
        self.assertEqual(result, ("Unknown", "bin"))

    def test_unknown_data_returns_bin(self):
        """Retorna formato desconhecido para dados sem assinatura reconhecida."""
        result = oir.identify_image(b"conteudo desconhecido", "image/png")
        self.assertEqual(result, ("Unknown", "bin"))

    def test_empty_data_returns_bin(self):
        """Lida com dados vazios sem gerar exceção."""
        result = oir.identify_image(b"", "")
        self.assertEqual(result, ("Unknown", "bin"))


    def test_rejects_html_with_comment_disguised_as_svg(self):
        """Não deve identificar HTML com comentário inicial como SVG."""
        data = (
            b"<!-- pagina de teste -->"
            b"<!DOCTYPE html>"
            b"<html><body><svg></svg></body></html>"
        )

        result = oir.identify_image(data, "image/svg+xml")

        self.assertEqual(result, ("Unknown", "bin"))


    def test_rejects_truncated_avif_header(self):
        """Não deve identificar como AVIF um cabeçalho incompleto."""
        data = b"\x00\x00\x00\x18ftypavif"

        result = oir.identify_image(data, "")

        self.assertEqual(result, ("Unknown", "bin"))

    def test_rejects_truncated_webp_header(self):
        """Não deve identificar como WebP um cabeçalho RIFF incompleto."""
        data = b"RIFF" + b"\xff\xff\xff\xff" + b"WEBP"

        result = oir.identify_image(data, "")

        self.assertEqual(result, ("Unknown", "bin"))

class TestDownloadFilename(unittest.TestCase):

    def test_download_preserves_original_filename(self):
        """Verifica se o download mantém o nome da imagem original."""
        pass

    def test_download_corrects_extension_to_detected_format(self):
        """Verifica se a extensão corresponde ao formato identificado."""
        pass

    def test_download_uses_fallback_when_filename_is_missing(self):
        """Verifica se um nome padrão é usado quando não há nome recuperável."""
        pass

    def test_download_sanitizes_unsafe_filename(self):
        """Verifica se nomes perigosos são tratados com segurança."""
        pass

class TestDownloadFilename(unittest.TestCase):
    """Testa a preservação e a segurança do nome dos downloads."""

    def setUp(self):
        """Cria um cliente de testes para a aplicação Flask."""
        self.client = oir.app.test_client()

    def mock_download_result(
        self,
        url="https://cdn.example.com/The_Slasher_Forest_Hill.png",
        image_format="PNG",
        extension="png",
    ):
        """Prepara uma resposta simulada de download."""
        return {
            "url": url,
            "format": image_format,
            "extension": extension,
            "data": b"\x89PNG\r\n\x1a\n" + b"\x00" * 16,
        }

    def test_download_preserves_original_filename(self):
        """Verifica se o download mantém o nome original."""
        result = self.mock_download_result()

        with patch("test_app.oir.get_download", return_value=result):
            response = self.client.get(
                "/api/download",
                query_string={
                    "url": "https://example.com/The_Slasher_Forest_Hill.png"
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "The_Slasher_Forest_Hill.png",
            response.headers.get("Content-Disposition", ""),
        )

    def test_download_corrects_extension_to_detected_format(self):
        """Verifica se a extensão corresponde ao formato identificado."""
        result = self.mock_download_result(
            url="https://cdn.example.com/photo.jpg",
            image_format="PNG",
            extension="png",
        )

        with patch("test_app.oir.get_download", return_value=result):
            response = self.client.get(
                "/api/download",
                query_string={
                    "url": "https://example.com/photo.jpg"
                },
            )

        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "photo.png",
            response.headers.get("Content-Disposition", ""),
        )

    def test_download_uses_fallback_when_filename_is_missing(self):
        """Verifica o nome padrão quando nenhuma URL fornece um nome válido."""
        result = self.mock_download_result(
            url="https://cdn.example.com/download"
        )

        with patch("test_app.oir.get_download", return_value=result):
            response = self.client.get(
                "/api/download",
                query_string={
                    "url": "https://example.com/download"
                },
            )
        
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "image.png",
            response.headers.get("Content-Disposition", ""),
        )

    def test_download_sanitizes_unsafe_filename(self):
        """Verifica se o nome não contém caminhos de diretório."""
        result = self.mock_download_result(
            url="https://cdn.example.com/..%2Fsecret.png"
        )

        with patch("test_app.oir.get_download", return_value=result):
            response = self.client.get(
                "/api/download",
                query_string={
                    "url": "https://example.com/image.png"
                },
            )

        self.assertEqual(response.status_code, 200)

        disposition = response.headers.get("Content-Disposition", "")

        self.assertIn("filename=secret.png", disposition)
        self.assertNotIn("../", disposition)


class TestDownloadCache(unittest.TestCase):
    """Testa o reaproveitamento de downloads armazenados em cache."""

    def setUp(self):
        """Limpa o cache antes de cada teste."""
        self.original_cache = oir._download_cache.copy()
        self.original_cache_size = oir._download_cache_size

        oir._download_cache.clear()
        oir._download_cache_size = 0

    def tearDown(self):
        """Restaura o cache anterior ao teste."""
        oir._download_cache.clear()
        oir._download_cache.update(self.original_cache)
        oir._download_cache_size = self.original_cache_size

    def test_reuses_download_for_same_url(self):
        """Duas solicitações à mesma URL devem reutilizar o resultado."""
        url = "https://cache-test.example.com/image.png"

        result = {
            "data": b"fake-image-data",
            "format": "png",
            "extension": "png",
            "size": len(b"fake-image-data"),
            "content_type": "image/png",
            "url": url,
        }

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.fetch_image", return_value=result) as mocked,
        ):
            first = oir.get_download(url)
            second = oir.get_download(url)

        self.assertEqual(first["data"], second["data"])
        self.assertEqual(mocked.call_count, 1)

    def test_does_not_reuse_download_for_different_urls(self):
        """URLs diferentes devem gerar downloads independentes."""
        first_url = "https://cache-test.example.com/first.png"
        second_url = "https://cache-test.example.com/second.png"

        first_result = {
            "data": b"first-image",
            "format": "png",
            "extension": "png",
            "size": len(b"first-image"),
            "content_type": "image/png",
            "url": first_url,
        }

        second_result = {
            "data": b"second-image",
            "format": "png",
            "extension": "png",
            "size": len(b"second-image"),
            "content_type": "image/png",
            "url": second_url,
        }

        with (
            patch("test_app.oir.validate_url"),
            patch(
                "test_app.oir.fetch_image",
                side_effect=[first_result, second_result],
            ) as mocked,
        ):
            first = oir.get_download(first_url)
            second = oir.get_download(second_url)

        self.assertEqual(first["data"], b"first-image")
        self.assertEqual(second["data"], b"second-image")
        self.assertEqual(mocked.call_count, 2)

    def test_expired_download_is_fetched_again(self):
        """Um download expirado deve ser obtido novamente."""
        url = "https://cache-test.example.com/expiration.png"

        result = {
            "data": b"image-data",
            "format": "png",
            "extension": "png",
            "size": len(b"image-data"),
            "content_type": "image/png",
            "url": url,
        }

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.time.monotonic", side_effect=[100, 100, 401, 401]),
            patch("test_app.oir.fetch_image", return_value=result) as mocked,
        ):
            oir.get_download(url)
            oir.get_download(url)

        self.assertEqual(mocked.call_count, 2)

    def test_cache_evicts_least_recently_used_download(self):
        """O cache remove a entrada menos utilizada quando precisa de espaço."""
        first_url = "https://cache-test.example.com/first.png"
        second_url = "https://cache-test.example.com/second.png"
        third_url = "https://cache-test.example.com/third.png"

        first_result = {
            "data": b"A" * 6,
            "format": "png",
            "extension": "png",
            "size": 6,
            "content_type": "image/png",
            "url": first_url,
        }

        second_result = {
            "data": b"B" * 6,
            "format": "png",
            "extension": "png",
            "size": 6,
            "content_type": "image/png",
            "url": second_url,
        }

        third_result = {
            "data": b"C" * 6,
            "format": "png",
            "extension": "png",
            "size": 6,
            "content_type": "image/png",
            "url": third_url,
        }

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.time.monotonic", return_value=100),
            patch.object(oir, "DOWNLOAD_CACHE_MAX_BYTES", 12),
            patch(
                "test_app.oir.fetch_image",
                side_effect=[first_result, second_result, third_result, second_result],
            ) as mocked,
        ):
            oir.get_download(first_url)
            oir.get_download(second_url)

            # A primeira entrada fica menos recentemente utilizada.
            oir.get_download(first_url)

            # A terceira imagem exige espaço e deve remover a segunda.
            oir.get_download(third_url)

            # A segunda imagem foi removida e precisa ser baixada novamente.
            oir.get_download(second_url)

        self.assertEqual(mocked.call_count, 4)
        self.assertEqual(oir._download_cache_size, 12)
        self.assertNotIn(first_url, oir._download_cache)
        self.assertIn(second_url, oir._download_cache)
        self.assertIn(third_url, oir._download_cache)

    def test_failed_download_is_not_cached(self):
        """Downloads que falham não devem ser armazenados no cache."""
        url = "https://cache-test.example.com/failing.png"

        successful_result = {
            "data": b"valid-image-data",
            "format": "png",
            "extension": "png",
            "size": len(b"valid-image-data"),
            "content_type": "image/png",
            "url": url,
        }

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.time.monotonic", return_value=100),
            patch(
                "test_app.oir.fetch_image",
                side_effect=[
                    oir.ImageError("Simulated network failure"),
                    successful_result,
                ],
            ) as mocked,
        ):
            with self.assertRaises(oir.ImageError):
                oir.get_download(url)

            # A segunda solicitação deve tentar baixar novamente.
            result = oir.get_download(url)

        self.assertEqual(result["data"], b"valid-image-data")
        self.assertEqual(mocked.call_count, 2)
        self.assertIn(url, oir._download_cache)

    def test_concurrent_downloads_keep_cache_consistent(self):
        """Solicitações simultâneas não devem corromper o cache."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Barrier

        url = "https://cache-test.example.com/concurrent.png"
        image_data = b"concurrent-image-data"

        result = {
            "data": image_data,
            "format": "png",
            "extension": "png",
            "size": len(image_data),
            "content_type": "image/png",
            "url": url,
        }

        # Garante que as duas tarefas iniciem juntas.
        barrier = Barrier(2)

        def request_download():
            barrier.wait(timeout=5)
            return oir.get_download(url)

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.fetch_image", return_value=result),
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = [
                    executor.submit(request_download),
                    executor.submit(request_download),
                ]
                results = [future.result(timeout=10) for future in futures]

        # Ambas as solicitações devem receber a imagem correta.
        self.assertEqual(len(results), 2)

        for download in results:
            self.assertEqual(download["data"], image_data)

        # O cache deve conter uma entrada e contabilizar os bytes corretamente.
        self.assertEqual(len(oir._download_cache), 1)
        self.assertIn(url, oir._download_cache)
        self.assertEqual(oir._download_cache_size, len(image_data))


    def test_concurrent_requests_share_one_download(self):
        """Solicitações simultâneas à mesma URL compartilham um download."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event

        url = "https://cache-test.example.com/shared.png"
        image_data = b"shared-image-data"

        result = {
            "data": image_data,
            "format": "png",
            "extension": "png",
            "size": len(image_data),
            "content_type": "image/png",
            "url": url,
        }

        download_started = Event()
        release_download = Event()
        second_request_started = Event()

        def fake_fetch(requested_url):
            download_started.set()

            if not release_download.wait(timeout=5):
                raise TimeoutError("O teste não liberou o download a tempo.")

            return result

        def second_request():
            second_request_started.set()
            return oir.get_download(url)

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.fetch_image", side_effect=fake_fetch) as mocked,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(oir.get_download, url)

                # Espera o primeiro download começar.
                self.assertTrue(download_started.wait(timeout=5))

                # Solicita a mesma URL enquanto o primeiro download está ativo.
                second_future = executor.submit(second_request)
                self.assertTrue(second_request_started.wait(timeout=5))

                # Dá oportunidade para a segunda solicitação entrar no fluxo.
                time.sleep(0.1)
                release_download.set()

                first = first_future.result(timeout=5)
                second = second_future.result(timeout=5)

        self.assertEqual(first["data"], image_data)
        self.assertEqual(second["data"], image_data)
        self.assertEqual(mocked.call_count, 1)
        self.assertEqual(len(oir._download_cache), 1)
        self.assertEqual(oir._download_cache_size, len(image_data))

    def test_failed_download_releases_waiting_requests(self):
        """Uma falha libera solicitações que aguardam a mesma URL."""
        from concurrent.futures import ThreadPoolExecutor
        from threading import Event, Lock

        url = "https://cache-test.example.com/retry.png"
        image_data = b"image-after-retry"

        result = {
            "data": image_data,
            "format": "png",
            "extension": "png",
            "size": len(image_data),
            "content_type": "image/png",
            "url": url,
        }

        download_started = Event()
        release_download = Event()
        second_request_started = Event()
        call_lock = Lock()
        call_count = 0

        def fake_fetch(requested_url):
            nonlocal call_count

            with call_lock:
                call_count += 1
                current_call = call_count

            if current_call == 1:
                download_started.set()

                if not release_download.wait(timeout=5):
                    raise TimeoutError("O teste não liberou o download a tempo.")

                raise oir.ImageError("Falha simulada no primeiro download")

            return result

        def second_request():
            second_request_started.set()
            return oir.get_download(url)

        with (
            patch("test_app.oir.validate_url"),
            patch("test_app.oir.fetch_image", side_effect=fake_fetch) as mocked,
        ):
            with ThreadPoolExecutor(max_workers=2) as executor:
                first_future = executor.submit(oir.get_download, url)

                # Aguarda o primeiro download começar.
                self.assertTrue(download_started.wait(timeout=5))

                # A segunda solicitação chega enquanto o download está ativo.
                second_future = executor.submit(second_request)
                self.assertTrue(second_request_started.wait(timeout=5))

                # Permite que a segunda solicitação entre na espera.
                time.sleep(0.1)
                release_download.set()

                # O primeiro pedido deve receber a falha.
                with self.assertRaises(oir.ImageError):
                    first_future.result(timeout=5)

                # O segundo deve tentar novamente e obter a imagem.
                second = second_future.result(timeout=5)

        self.assertEqual(second["data"], image_data)
        self.assertEqual(mocked.call_count, 2)
        self.assertEqual(len(oir._download_cache), 1)
        self.assertIn(url, oir._download_cache)
        self.assertEqual(oir._download_cache_size, len(image_data))


# ====================================================== #
#                 API ERROR HANDLING TESTS
# ====================================================== #

class TestAPIErrorHandling(unittest.TestCase):
    """Testa as respostas de erro das rotas da API."""

    def setUp(self):
        """Cria um cliente Flask para os testes."""
        self.client = oir.app.test_client()

    def test_analyze_rejects_empty_url(self):
        """A análise deve rejeitar uma URL vazia com erro JSON."""
        response = self.client.post(
            "/api/analyze",
            json={"url": ""},
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Please enter an image URL."},
        )

    @patch("test_app.oir.get_download")
    def test_preview_returns_json_on_image_error(self, mock_download):
        """A pré-visualização deve retornar JSON quando a imagem falha."""
        mock_download.side_effect = oir.ImageError(
            "Unable to connect to the image server."
        )

        response = self.client.get(
            "/api/preview",
            query_string={
                "url": "https://example.com/image.png"
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Unable to connect to the image server."},
        )

    @patch("test_app.oir.get_download")
    def test_download_returns_json_on_image_error(self, mock_download):
        """O download deve retornar JSON quando a imagem falha."""
        mock_download.side_effect = oir.ImageError(
            "Unable to connect to the image server."
        )

        response = self.client.get(
            "/api/download",
            query_string={
                "url": "https://example.com/image.png"
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.get_json(),
            {"error": "Unable to connect to the image server."},
        )

    def test_unknown_route_returns_json_error(self):
        """Rotas inexistentes devem retornar erro HTTP em JSON."""
        response = self.client.get("/api/route-that-does-not-exist")

        self.assertEqual(response.status_code, 404)
        self.assertEqual(
            response.get_json(),
            {
                "error": "Not Found",
                "message": "The request could not be completed.",
            },
        )

    def test_wrong_http_method_returns_json_error(self):
        """Métodos HTTP não permitidos devem retornar erro JSON."""
        response = self.client.post("/api/preview")

        self.assertEqual(response.status_code, 405)
        self.assertEqual(
            response.get_json(),
            {
                "error": "Method Not Allowed",
                "message": "The request could not be completed.",
            },
        )

    @patch("test_app.oir.resolve_image_url")
    def test_unexpected_error_returns_generic_500(self, mock_resolve):
        """Erros inesperados não devem expor detalhes internos."""
        mock_resolve.side_effect = RuntimeError(
            "Internal database path: C:\\private\\secret"
        )

        response = self.client.get(
            "/api/preview",
            query_string={
                "url": "https://example.com/image.png"
            },
        )

        self.assertEqual(response.status_code, 500)
        self.assertEqual(
            response.get_json(),
            {
                "error": "Internal Server Error",
                "message": "The request could not be completed.",
            },
        )

# ====================================================== #
#                       TEST RUNNER
# ====================================================== #

if __name__ == "__main__":
    unittest.main(verbosity=2)