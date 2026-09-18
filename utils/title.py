import re
import unicodedata

SEPARATORS = re.compile(r"[\s_\-:|/\\]+")
NON_ALNUM = re.compile(r"[^\w]+", re.UNICODE)

def normalize_title(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "").casefold()
    value = value.replace("&", " and ")
    value = SEPARATORS.sub(" ", value)
    value = NON_ALNUM.sub(" ", value)
    return " ".join(value.split())


def title_tokens(value: str) -> set[str]:
    return set(normalize_title(value).split())


def title_similarity(query: str, candidate: str) -> float:
    query_norm = normalize_title(query)
    candidate_norm = normalize_title(candidate)

    if not query_norm or not candidate_norm:
        return 0.0
    if query_norm == candidate_norm:
        return 1.0
    if query_norm in candidate_norm or candidate_norm in query_norm:
        shorter = min(len(query_norm), len(candidate_norm))
        longer = max(len(query_norm), len(candidate_norm))
        return 0.90 + (shorter / longer) * 0.05

    query_tokens = title_tokens(query)
    candidate_tokens = title_tokens(candidate)
    overlap = len(query_tokens & candidate_tokens)
    union = len(query_tokens | candidate_tokens)
    if not union:
        return 0.0

    jaccard = overlap / union
    containment = overlap / min(len(query_tokens), len(candidate_tokens))
    return (jaccard * 0.6) + (containment * 0.4)


def title_search_regex(value: str) -> str:
    """Build a safe MongoDB regex that searches normalized title-like text."""
    normalized = normalize_title(value)
    if not normalized:
        return ""
    return ".*".join(re.escape(token) for token in normalized.split())
