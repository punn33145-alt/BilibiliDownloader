"""Module 2 — offline Chinese → Vietnamese subtitle translation (lazy-loaded)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Callable, Optional

from app.core.paths import get_models_dir
from app.core.ssl_setup import configure_ssl_certificates, get_ca_bundle_path
from app.translator.deps import get_missing_translation_packages, translation_install_message
from app.translator.models import TranslationResult
from app.translator.srt import SubtitleCue, read_srt_file, write_srt_file
from app.translator.text import (
    ProtectedText,
    TermGlossary,
    apply_glossary_placeholders,
    block_to_translatable,
    build_glossary_from_terms_batch,
    contains_chinese,
    extract_repeated_chinese_terms,
    is_confident_translation,
    merge_translation_with_original,
    protect_non_translatable,
    restore_glossary_placeholders,
    restore_protected,
    translatable_to_block,
)

logger = logging.getLogger(__name__)

StatusCallback = Callable[[str], None]

_MODEL_CANDIDATES: tuple[dict[str, Any], ...] = (
    # MarianMT is far smaller/faster than NLLB-200 on CPU (no GPU
    # acceleration), so it's tried first. Falls back to the larger,
    # generally higher-quality models below if it's unavailable.
    {
        "label": "MarianMT",
        "model_id": "Helsinki-NLP/opus-mt-zh-vi",
        "backend": "marian",
        "src_lang": None,
        "tgt_lang": None,
    },
    {
        "label": "Meta NLLB-200",
        "model_id": "facebook/nllb-200-distilled-600M",
        "backend": "nllb",
        "src_lang": "zho_Hans",
        "tgt_lang": "vie",
    },
    {
        "label": "Facebook M2M100",
        "model_id": "facebook/m2m100_418M",
        "backend": "m2m100",
        "src_lang": "zh",
        "tgt_lang": "vi",
    },
    {
        "label": "Facebook M2M100 (1.2B fallback)",
        "model_id": "facebook/m2m100_1.2B",
        "backend": "m2m100",
        "src_lang": "zh",
        "tgt_lang": "vi",
    },
)

_BATCH_SIZE = 16
_MAX_BLOCK_CHARS = 512


class TranslateService:
    """Fully offline zh → vi translation. Loads AI dependencies only when invoked."""

    _shared_instance: Optional["TranslateService"] = None

    def __init__(self) -> None:
        self._model: Any = None
        self._tokenizer: Any = None
        self._backend: Optional[str] = None
        self._model_id: Optional[str] = None
        self._src_lang: Optional[str] = None
        self._tgt_lang: Optional[str] = None
        self._device: Optional[str] = None
        self._loaded = False
        self._load_error: Optional[str] = None

    @classmethod
    def instance(cls) -> "TranslateService":
        if cls._shared_instance is None:
            cls._shared_instance = cls()
        return cls._shared_instance

    @property
    def model_id(self) -> Optional[str]:
        return self._model_id

    def translate_srt_file(
        self,
        source_path: Path,
        output_path: Path,
        progress_callback: Optional[StatusCallback] = None,
    ) -> TranslationResult:
        """Translate an SRT file from Chinese to Vietnamese."""
        if not source_path.exists():
            return TranslationResult(success=False, error="Subtitle file not found.")

        missing = get_missing_translation_packages()
        if missing:
            return TranslationResult(
                success=False,
                error=translation_install_message(),
            )

        try:
            cues = read_srt_file(source_path)
            if not cues:
                return TranslationResult(
                    success=False,
                    error="Subtitle file is empty or unreadable.",
                )

            if not self._ensure_model_loaded(progress_callback):
                return TranslationResult(
                    success=False,
                    error=self._load_error or "Could not load offline translation model.",
                )

            translated_cues = self._translate_cues(cues, progress_callback)
            write_srt_file(output_path, translated_cues)
            logger.info(
                "Translated %d cues → %s (model: %s)",
                len(translated_cues),
                output_path,
                self._model_id,
            )
            return TranslationResult(
                success=True,
                output_path=output_path,
                model_used=self._model_id,
            )
        except Exception as exc:
            logger.exception("Subtitle translation failed")
            return TranslationResult(success=False, error=f"Subtitle translation failed: {exc}")

    @staticmethod
    def _from_pretrained_prefer_local(loader_cls: Any, model_id: str, cache_dir: str) -> Any:
        """Load a tokenizer/model, preferring the local cache.

        With ``local_files_only=False``, every startup makes a network
        round-trip to Hugging Face Hub to check for updated files, even
        when the model is already fully cached. On a slow or unstable
        connection this can hang for a long time before falling back to
        the cache. Try the cache first (instant, no network) and only
        hit the network if the cache is incomplete or missing.
        """
        try:
            return loader_cls.from_pretrained(
                model_id,
                cache_dir=cache_dir,
                local_files_only=True,
            )
        except Exception:
            logger.info(
                "%s not fully cached locally for %s; fetching from network.",
                loader_cls.__name__,
                model_id,
            )
            return loader_cls.from_pretrained(
                model_id,
                cache_dir=cache_dir,
                local_files_only=False,
            )

    def _ensure_model_loaded(self, progress_callback: Optional[StatusCallback] = None) -> bool:
        if self._loaded:
            return True
        if self._load_error:
            return False

        self._notify(
            progress_callback,
            "Preparing offline translation model (first run may download)...",
        )

        configure_ssl_certificates()
        ca_bundle = get_ca_bundle_path()

        import torch
        from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, MarianMTModel, MarianTokenizer

        self._device = "cuda" if torch.cuda.is_available() else "cpu"
        cache_dir = str(get_models_dir())

        for candidate in _MODEL_CANDIDATES:
            model_id = candidate["model_id"]
            backend = candidate["backend"]
            try:
                self._notify(progress_callback, f"Loading {candidate['label']} model...")
                logger.info("Attempting to load translation model: %s", model_id)

                if backend == "marian":
                    tokenizer = self._from_pretrained_prefer_local(
                        MarianTokenizer, model_id, cache_dir
                    )
                    model = self._from_pretrained_prefer_local(
                        MarianMTModel, model_id, cache_dir
                    )
                else:
                    tokenizer = self._from_pretrained_prefer_local(
                        AutoTokenizer, model_id, cache_dir
                    )
                    model = self._from_pretrained_prefer_local(
                        AutoModelForSeq2SeqLM, model_id, cache_dir
                    )

                model.to(self._device)
                model.eval()

                # The pretrained generation_config ships a default
                # max_length (e.g. 200), which conflicts with the
                # max_new_tokens we pass on every generate() call below
                # and spams "Both `max_new_tokens` and `max_length`..."
                # warnings once per translated block/cue. Clear it so
                # max_new_tokens is the sole limit, as intended.
                if hasattr(model, "generation_config") and model.generation_config is not None:
                    model.generation_config.max_length = None

                self._model = model
                self._tokenizer = tokenizer
                self._backend = backend
                self._model_id = model_id
                self._src_lang = candidate.get("src_lang")
                self._tgt_lang = candidate.get("tgt_lang")
                self._loaded = True
                logger.info("Translation model ready: %s on %s", model_id, self._device)
                return True
            except Exception as exc:
                logger.warning("Model %s unavailable: %s", model_id, exc)
                if "certificate" in str(exc).lower() or "ssl" in str(exc).lower():
                    self._load_error = (
                        "Secure connection failed while downloading the translation model. "
                        f'Run: {sys.executable} -m pip install -r requirements-translate.txt '
                        "(includes truststore + certifi), then restart the app."
                    )
                continue

        if not self._load_error:
            self._load_error = (
                "No offline translation model could be loaded. "
                "Ensure you have internet access for the first-time model download, "
                "then try again."
            )
        if ca_bundle is None and not (self._load_error or "").startswith("Secure"):
            self._load_error += (
                " Tip: install certifi for HTTPS on Windows: python -m pip install certifi"
            )
        return False

    def _translate_cues(
        self,
        cues: list[SubtitleCue],
        progress_callback: Optional[StatusCallback] = None,
    ) -> list[SubtitleCue]:
        if not cues:
            return cues

        result = [
            SubtitleCue(index=cue.index, timing=cue.timing, text_lines=list(cue.text_lines))
            for cue in cues
        ]

        block_sources = [block_to_translatable(cue.text_lines) for cue in cues]
        translatable_indices = [
            idx
            for idx, text in enumerate(block_sources)
            if text.strip() and contains_chinese(text)
        ]

        if not translatable_indices:
            return result

        self._notify(progress_callback, "Building terminology glossary...")
        repeated_terms = extract_repeated_chinese_terms(
            [block_sources[i] for i in translatable_indices]
        )
        glossary = build_glossary_from_terms_batch(
            repeated_terms,
            translate_batch=self._translate_raw_texts,
            batch_size=_BATCH_SIZE,
        )

        total = len(translatable_indices)
        for batch_start in range(0, total, _BATCH_SIZE):
            batch_indices = translatable_indices[batch_start : batch_start + _BATCH_SIZE]
            sources = [block_sources[i] for i in batch_indices]
            originals = [result[i].text_lines for i in batch_indices]
            translated_blocks = self._translate_blocks_batch(sources, glossary)

            for cue_idx, source_block, original_lines, translated in zip(
                batch_indices, sources, originals, translated_blocks
            ):
                expected_lines = len(original_lines)
                if is_confident_translation(source_block, translated):
                    new_lines = translatable_to_block(translated, expected_lines)
                else:
                    new_lines = list(original_lines)

                result[cue_idx].text_lines = merge_translation_with_original(
                    original_lines,
                    new_lines,
                )

            done = min(batch_start + _BATCH_SIZE, total)
            pct = int((done / total) * 100)
            self._notify(
                progress_callback,
                f"Translating subtitles... {pct}% ({done}/{total} blocks)",
            )

        return result

    def _translate_blocks_batch(
        self,
        blocks: list[str],
        glossary: TermGlossary,
    ) -> list[str]:
        prepared: list[tuple[str, ProtectedText, dict[str, str]]] = []

        for block in blocks:
            protected = protect_non_translatable(block)
            masked, term_placeholders = apply_glossary_placeholders(
                protected.masked,
                glossary,
            )
            prepared.append((masked, protected, term_placeholders))

        raw_outputs = self._run_model_batch([item[0] for item in prepared])
        results: list[str] = []

        for (_masked, protected, term_placeholders), raw in zip(prepared, raw_outputs):
            text = restore_glossary_placeholders(raw, term_placeholders)
            text = restore_protected(text, protected)
            results.append(text)

        return results

    def _translate_raw_text(self, text: str) -> str:
        if not text.strip():
            return text
        protected = protect_non_translatable(text)
        outputs = self._run_model_batch([protected.masked])
        return restore_protected(outputs[0], protected)

    def _translate_raw_texts(self, texts: list[str]) -> list[str]:
        """Batch variant of _translate_raw_text — one model call for many texts."""
        if not texts:
            return []

        prepared: list[tuple[str, ProtectedText]] = []
        for text in texts:
            if not text.strip():
                prepared.append((text, ProtectedText(masked=text)))
                continue
            protected = protect_non_translatable(text)
            prepared.append((protected.masked, protected))

        raw_outputs = self._run_model_batch([item[0] for item in prepared])
        results: list[str] = []
        for original_text, (_masked, protected), raw in zip(texts, prepared, raw_outputs):
            if not original_text.strip():
                results.append(original_text)
                continue
            results.append(restore_protected(raw, protected))
        return results

    def _run_model_batch(self, texts: list[str]) -> list[str]:
        import torch

        assert self._model is not None
        assert self._tokenizer is not None
        assert self._device is not None

        clipped = [t[:_MAX_BLOCK_CHARS] for t in texts]
        if not clipped:
            return []

        generate_kwargs: dict[str, Any] = {
            "max_new_tokens": 512,
            # Lower beam count trades a small amount of translation quality
            # for a large CPU speedup (beam search cost scales ~linearly
            # with num_beams). 4 -> 2 roughly halves generate() time.
            "num_beams": 2,
            "do_sample": False,
        }

        if self._backend == "nllb":
            self._tokenizer.src_lang = self._src_lang  # type: ignore[assignment]
            forced_bos = self._get_nllb_forced_bos_id(self._tgt_lang)  # type: ignore[arg-type]
            generate_kwargs["forced_bos_token_id"] = forced_bos
        elif self._backend == "m2m100":
            self._tokenizer.src_lang = self._src_lang  # type: ignore[assignment]
            generate_kwargs["forced_bos_token_id"] = self._tokenizer.get_lang_id(
                self._tgt_lang  # type: ignore[arg-type]
            )

        inputs = self._tokenizer(
            clipped,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )
        inputs = {k: v.to(self._device) for k, v in inputs.items()}

        with torch.inference_mode():
            output_ids = self._model.generate(**inputs, **generate_kwargs)

        decoded = self._tokenizer.batch_decode(output_ids, skip_special_tokens=True)
        outputs: list[str] = []
        for original, translated in zip(texts, decoded):
            cleaned = translated.strip()
            outputs.append(cleaned if cleaned else original)
        return outputs

    def _get_nllb_forced_bos_id(self, lang_code: str) -> int:
        """Return the forced BOS token id for an NLLB target language.

        ``transformers`` removed the ``lang_code_to_id`` attribute from
        ``NllbTokenizer``/``NllbTokenizerFast`` in newer releases; language
        codes are now resolved like any other added token via
        ``convert_tokens_to_ids``. Support both so this works across
        ``transformers>=4.36`` installs.
        """
        lang_to_id = getattr(self._tokenizer, "lang_code_to_id", None)
        if lang_to_id is not None:
            return lang_to_id[lang_code]
        return self._tokenizer.convert_tokens_to_ids(lang_code)  # type: ignore[union-attr]

    @staticmethod
    def _notify(progress_callback: Optional[StatusCallback], message: str) -> None:
        if progress_callback:
            progress_callback(message)
        logger.info(message)
