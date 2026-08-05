"""Configure trusted CA certificates for HTTPS on Windows/Python."""

from __future__ import annotations

import logging
import os
import ssl

logger = logging.getLogger(__name__)

_configured = False


def configure_ssl_certificates() -> None:
    """Configure HTTPS trust. Called before network use (download / translate)."""
    global _configured
    if _configured:
        return

    try:
        import truststore

        truststore.inject_into_ssl()
        _configured = True
        return
    except ImportError:
        pass
    except Exception as exc:
        logger.warning("truststore SSL setup failed: %s", exc)

    try:
        import certifi

        cafile = certifi.where()
        os.environ.setdefault("SSL_CERT_FILE", cafile)
        os.environ.setdefault("REQUESTS_CA_BUNDLE", cafile)
        os.environ.setdefault("CURL_CA_BUNDLE", cafile)

        def _default_context() -> ssl.SSLContext:
            return ssl.create_default_context(cafile=cafile)

        ssl._create_default_https_context = _default_context  # type: ignore[attr-defined]
        _configured = True
    except ImportError:
        logger.warning("Install truststore or certifi for HTTPS support.")
    except Exception as exc:
        logger.warning("SSL configuration failed: %s", exc)


def get_ca_bundle_path() -> str | None:
    try:
        import certifi

        return certifi.where()
    except ImportError:
        return None
