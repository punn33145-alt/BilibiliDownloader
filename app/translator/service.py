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
    build_glossary_from_terms,
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
        "label": "MarianMT",
        "model_id": "Helsinki-NLP/opus-mt-zh-vi",
        "backend": "marian",
        "src_lang": None,
        "tgt_lang": None,
    },
    {
        "label": "Facebook M2M100 (1.2B fallback)",
        "model_id": "facebook/m2m100_1.2B",
        "backend": "m2m100",
        "src_lang": "zh",
        "tgt_lang": "vi",
    },
)

_BATCH_SIZE = 8
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
                    tokenizer = MarianTokenizer.from_pretrained(
                        model_id,
                        cache_dir=cache_dir,
                        local_files_only=False,
                    )
                    model = MarianMTModel.from_pretrained(
                        model_id,
                        cache_dir=cache_dir,
                        local_files_only=False,
                    )
                else:
                    tokenizer = AutoTokenizer.from_pretrained(
                        model_id,
                        cache_dir=cache_dir,
                        local_files_only=False,
                    )
                    model = AutoModelForSeq2SeqLM.from_pretrained(
                        model_id,
                        cache_dir=cache_dir,
                        local_files_only=False,
                    )

                model.to(self._device)
                model.eval()

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
        glossary = build_glossary_from_terms(
            repeated_terms,
            translate_term=lambda term: self._translate_raw_text(term),
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
            "num_beams": 4,
            "do_sample": False,
        }

        if self._backend == "nllb":
            self._tokenizer.src_lang = self._src_lang  # type: ignore[assignment]
            forced_bos = self._tokenizer.lang_code_to_id[self._tgt_lang]  # type: ignore[index]
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

    @staticmethod
    def _notify(progress_callback: Optional[StatusCallback], message: str) -> None:
        if progress_callback:
            progress_callback(message)
        logger.info(message)
