import abc
from dataclasses import dataclass, field
import logging
import re
from typing import Any

logger = logging.getLogger("finchat.security.pii")

DEFAULT_REPLACEMENTS: dict[str, str] = {
    "BD_NID": "<ID_NUMBER>",
    "BANK_ACCOUNT": "<ACCOUNT_NUMBER>",
    "PHONE_NUMBER": "<PHONE_NUMBER>",
    "EMAIL_ADDRESS": "<EMAIL_ADDRESS>",
    "CREDIT_CARD": "<CREDIT_CARD>",
    "IP_ADDRESS": "<IP_ADDRESS>",
    "US_SSN": "<SSN>",
    "DEFAULT": "<REDACTED>",
}

try:
    from presidio_analyzer import AnalyzerEngine, Pattern, PatternRecognizer
    from presidio_analyzer.nlp_engine import NlpEngineProvider
    from presidio_anonymizer import AnonymizerEngine
    from presidio_anonymizer.entities import OperatorConfig
    HAS_PRESIDIO = True
except ImportError:
    AnalyzerEngine = None  # type: ignore[assignment,misc]
    Pattern = None  # type: ignore[assignment,misc]
    PatternRecognizer = None  # type: ignore[assignment,misc]
    NlpEngineProvider = None  # type: ignore[assignment,misc]
    AnonymizerEngine = None  # type: ignore[assignment,misc]
    OperatorConfig = None  # type: ignore[assignment,misc]
    HAS_PRESIDIO = False
BD_NID_17_PATTERN = re.compile(r"\b(?:19|20)\d{15}\b")
BD_NID_13_PATTERN = re.compile(r"\b\d{13}\b")
BD_NID_10_PATTERN = re.compile(r"\b\d{10}\b")
FC_ACCOUNT_PATTERN = re.compile(r"\bFC\d{10}\b", re.IGNORECASE)
CONTEXTUAL_ACCOUNT_PATTERN = re.compile(
    r"(?i)\b(?:acc(?:ount)?(?:\s+(?:no|num|number))?\s*[:#-]?\s*)(\d{8,18})\b"
)
BD_PHONE_INTL_PATTERN = re.compile(r"(?:(?:\+|00)?880|880)1[3-9]\d{8}\b")
BD_PHONE_LOCAL_PATTERN = re.compile(r"\b01[3-9]\d{8}\b")
EMAIL_PATTERN = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"
)
CREDIT_CARD_PATTERN = re.compile(
    r"\b(?:\d{4}[-\s]?){3}\d{4}\b"
)
IP_PATTERN = re.compile(
    r"\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b"
)

NID_CONTEXT_WORDS = {
    "nid", "national id", "national identity", "voter id", "smart card", "identity card", "nid no"
}


@dataclass(slots=True)
class RedactedEntity:
    entity_type: str
    start: int
    end: int
    score: float
    text: str = ""


@dataclass(slots=True)
class RedactionResult:
    original_text: str
    redacted_text: str
    has_pii: bool
    entities: list[RedactedEntity] = field(default_factory=list)

    def __str__(self) -> str:
        return self.redacted_text


class BasePIIRedactor(abc.ABC):
    @abc.abstractmethod
    def redact(
        self,
        text: str,
        replacements: dict[str, str] | None = None,
    ) -> RedactionResult:
        """Scan text and mask sensitive PII entities."""
        pass


class RegexPIIRedactor(BasePIIRedactor):
    """
    Lightweight, high-speed regex-based PII redactor.
    Used as standalone or zero-dependency fallback.
    """

    def redact(
        self,
        text: str,
        replacements: dict[str, str] | None = None,
    ) -> RedactionResult:
        if not text:
            return RedactionResult(
                original_text="",
                redacted_text="",
                has_pii=False,
                entities=[],
            )

        rep_map = {**DEFAULT_REPLACEMENTS, **(replacements or {})}
        detected: list[RedactedEntity] = []

        # 1. FinChat account numbers
        for match in FC_ACCOUNT_PATTERN.finditer(text):
            detected.append(
                RedactedEntity(
                    entity_type="BANK_ACCOUNT",
                    start=match.start(),
                    end=match.end(),
                    score=1.0,
                    text=match.group(),
                )
            )

        # 2. Contextual account numbers
        for match in CONTEXTUAL_ACCOUNT_PATTERN.finditer(text):
            # Mask the digits group specifically
            start = match.start(1)
            end = match.end(1)
            detected.append(
                RedactedEntity(
                    entity_type="BANK_ACCOUNT",
                    start=start,
                    end=end,
                    score=0.85,
                    text=match.group(1),
                )
            )

        # 3. Credit cards (only if 16 digits)
        for match in CREDIT_CARD_PATTERN.finditer(text):
            digits = re.sub(r"\D", "", match.group())
            if len(digits) == 16:
                detected.append(
                    RedactedEntity(
                        entity_type="CREDIT_CARD",
                        start=match.start(),
                        end=match.end(),
                        score=0.9,
                        text=match.group(),
                    )
                )

        # 4. Email addresses
        for match in EMAIL_PATTERN.finditer(text):
            detected.append(
                RedactedEntity(
                    entity_type="EMAIL_ADDRESS",
                    start=match.start(),
                    end=match.end(),
                    score=0.95,
                    text=match.group(),
                )
            )

        # 5. Bangladeshi Phone numbers
        for pattern in (BD_PHONE_INTL_PATTERN, BD_PHONE_LOCAL_PATTERN):
            for match in pattern.finditer(text):
                detected.append(
                    RedactedEntity(
                        entity_type="PHONE_NUMBER",
                        start=match.start(),
                        end=match.end(),
                        score=0.85,
                        text=match.group(),
                    )
                )

        # 6. Bangladeshi NID numbers (17, 13, 10 digits)
        text_lower = text.lower()
        has_nid_context = any(ctx in text_lower for ctx in NID_CONTEXT_WORDS)

        # 17-digit NID has a strong pattern starting with 19xx or 20xx birth year
        for match in BD_NID_17_PATTERN.finditer(text):
            detected.append(
                RedactedEntity(
                    entity_type="BD_NID",
                    start=match.start(),
                    end=match.end(),
                    score=0.9 if has_nid_context else 0.8,
                    text=match.group(),
                )
            )

        # 13 and 10 digits require NID context to avoid false positives with random numbers
        if has_nid_context:
            for pattern in (BD_NID_13_PATTERN, BD_NID_10_PATTERN):
                for match in pattern.finditer(text):
                    detected.append(
                        RedactedEntity(
                            entity_type="BD_NID",
                            start=match.start(),
                            end=match.end(),
                            score=0.75,
                            text=match.group(),
                        )
                    )

        # 7. IP addresses
        for match in IP_PATTERN.finditer(text):
            detected.append(
                RedactedEntity(
                    entity_type="IP_ADDRESS",
                    start=match.start(),
                    end=match.end(),
                    score=0.8,
                    text=match.group(),
                )
            )

        if not detected:
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                has_pii=False,
                entities=[],
            )

        # Deduplicate & resolve overlapping spans (keep higher score or longer match)
        detected.sort(key=lambda e: (e.start, -(e.end - e.start), -e.score))
        resolved: list[RedactedEntity] = []
        last_end = -1
        for item in detected:
            if item.start >= last_end:
                resolved.append(item)
                last_end = item.end
            elif item.score > resolved[-1].score:
                resolved[-1] = item
                last_end = item.end

        # Replace from end to start to maintain string indices
        resolved.sort(key=lambda e: e.start, reverse=True)
        out_chars = list(text)
        for item in resolved:
            replacement = rep_map.get(
                item.entity_type, rep_map.get("DEFAULT", "<REDACTED>")
            )
            out_chars[item.start:item.end] = list(replacement)

        resolved.sort(key=lambda e: e.start)
        return RedactionResult(
            original_text=text,
            redacted_text="".join(out_chars),
            has_pii=True,
            entities=resolved,
        )


class PresidioPIIRedactor(BasePIIRedactor):
    """
    Microsoft Presidio PII Redactor with custom banking recognizers.
    """

    def __init__(self) -> None:
        if not HAS_PRESIDIO:
            raise ImportError(
                "Microsoft Presidio is not installed. Please install presidio-analyzer and presidio-anonymizer."
            )

        # Attempt to initialize with lightweight en_core_web_sm model
        try:
            config = {
                "nlp_engine_name": "spacy",
                "models": [{"lang_code": "en", "model_name": "en_core_web_sm"}],
            }
            provider = NlpEngineProvider(nlp_configuration=config)
            nlp_engine = provider.create_engine()
            self._analyzer = AnalyzerEngine(nlp_engine=nlp_engine)
        except Exception as exc:
            logger.info("Initializing Presidio with default NLP engine (%s)", exc)
            self._analyzer = AnalyzerEngine()

        self._anonymizer = AnonymizerEngine()
        self._register_custom_recognizers(Pattern, PatternRecognizer)

    def _register_custom_recognizers(
        self,
        pattern_cls: Any,
        recognizer_cls: Any,
    ) -> None:
        # 1. FinChat account number recognizer
        fc_account_patterns = [
            pattern_cls(name="fc_account_exact", regex=r"\bFC\d{10}\b", score=0.95),
            pattern_cls(name="context_account_digits", regex=r"\b\d{8,18}\b", score=0.4),
        ]
        self._analyzer.registry.add_recognizer(
            recognizer_cls(
                supported_entity="BANK_ACCOUNT",
                name="fc_bank_account_recognizer",
                patterns=fc_account_patterns,
                context=["account", "acc", "acct", "savings", "checking", "balance"],
            )
        )

        # 2. Bangladeshi National ID (NID) recognizer
        bd_nid_patterns = [
            pattern_cls(name="bd_nid_17", regex=r"\b(?:19|20)\d{15}\b", score=0.85),
            pattern_cls(name="bd_nid_13", regex=r"\b\d{13}\b", score=0.7),
            pattern_cls(name="bd_nid_10", regex=r"\b\d{10}\b", score=0.6),
        ]
        self._analyzer.registry.add_recognizer(
            recognizer_cls(
                supported_entity="BD_NID",
                name="bd_nid_recognizer",
                patterns=bd_nid_patterns,
                context=list(NID_CONTEXT_WORDS),
            )
        )

        # 3. Bangladeshi Phone numbers
        bd_phone_patterns = [
            pattern_cls(
                name="bd_phone_intl",
                regex=r"(?:(?:\+|00)?880|880)1[3-9]\d{8}\b",
                score=0.9,
            ),
            pattern_cls(name="bd_phone_local", regex=r"\b01[3-9]\d{8}\b", score=0.8),
        ]
        self._analyzer.registry.add_recognizer(
            recognizer_cls(
                supported_entity="PHONE_NUMBER",
                name="bd_phone_recognizer",
                patterns=bd_phone_patterns,
                context=["phone", "mobile", "cell", "call", "contact", "whatsapp"],
            )
        )

    def redact(
        self,
        text: str,
        replacements: dict[str, str] | None = None,
    ) -> RedactionResult:
        if not text:
            return RedactionResult(
                original_text="",
                redacted_text="",
                has_pii=False,
                entities=[],
            )

        rep_map = {**DEFAULT_REPLACEMENTS, **(replacements or {})}

        # Run Presidio Analyzer
        analyzer_results = self._analyzer.analyze(
            text=text,
            language="en",
            score_threshold=0.5,
        )

        if not analyzer_results:
            return RedactionResult(
                original_text=text,
                redacted_text=text,
                has_pii=False,
                entities=[],
            )

        # Configure Presidio Anonymizer operators
        op_cls = OperatorConfig or (lambda *args, **kwargs: None)
        operators: dict[str, Any] = {}
        for entity_type, new_value in rep_map.items():
            operators[entity_type] = op_cls(
                "replace", {"new_value": new_value}
            )
        operators["DEFAULT"] = op_cls(
            "replace",
            {"new_value": rep_map.get("DEFAULT", "<REDACTED>")},
        )

        anonymized = self._anonymizer.anonymize(
            text=text,
            analyzer_results=analyzer_results,
            operators=operators,
        )

        entities = [
            RedactedEntity(
                entity_type=res.entity_type,
                start=res.start,
                end=res.end,
                score=res.score,
                text=text[res.start:res.end],
            )
            for res in analyzer_results
        ]

        return RedactionResult(
            original_text=text,
            redacted_text=anonymized.text,
            has_pii=len(entities) > 0,
            entities=entities,
        )


_redactor_instance: BasePIIRedactor | None = None


def get_pii_redactor() -> BasePIIRedactor:
    """
    Get or initialize the global PII redactor.
    Uses Microsoft Presidio if installed, falling back to RegexPIIRedactor.
    """
    global _redactor_instance
    if _redactor_instance is not None:
        return _redactor_instance

    try:
        logger.info("Initializing Microsoft Presidio PII Redactor...")
        _redactor_instance = PresidioPIIRedactor()
        logger.info("Microsoft Presidio PII Redactor successfully initialized.")
    except Exception as exc:
        logger.warning(
            "Presidio initialization failed or package not installed (%s). "
            "Falling back to RegexPIIRedactor.",
            exc,
        )
        _redactor_instance = RegexPIIRedactor()

    return _redactor_instance


def set_pii_redactor(redactor: BasePIIRedactor | None) -> None:
    """Override or reset the active redactor (useful in testing)."""
    global _redactor_instance
    _redactor_instance = redactor


def redact_pii(
    text: str,
    replacements: dict[str, str] | None = None,
) -> RedactionResult:
    """
    Detect and mask PII in text before it reaches any LLM.
    Returns RedactionResult containing redacted_text and detected entities.
    """
    redactor = get_pii_redactor()
    return redactor.redact(text, replacements=replacements)


def redact_text(
    text: str,
    replacements: dict[str, str] | None = None,
) -> str:
    """Convenience helper returning directly the masked string."""
    return redact_pii(text, replacements=replacements).redacted_text


def is_pii_present(text: str) -> bool:
    """Quick boolean check if text contains detectable PII."""
    return redact_pii(text).has_pii
