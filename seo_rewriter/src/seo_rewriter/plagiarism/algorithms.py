"""Scientific plagiarism detection algorithms.

Based on research papers:
- Charikar, M. S. (2002). Similarity estimation techniques from rounding algorithms.
- Schleimer, S., Wilkerson, D. S., & Aiken, A. (2003). Winnowing: local algorithms for document fingerprinting.
- Broder, A. Z. (1997). On the resemblance and containment of documents.
"""

import re
import hashlib
from typing import Sequence
from collections import Counter

import mmh3  # MurmurHash3 for fast hashing


def normalize_text(text: str) -> str:
    """Normalize text for comparison.

    - Convert to lowercase
    - Remove punctuation
    - Collapse whitespace
    """
    text = text.lower()
    text = re.sub(r'[^\w\s]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


def tokenize(text: str) -> list[str]:
    """Tokenize text into words."""
    normalized = normalize_text(text)
    return normalized.split()


def get_ngrams(tokens: Sequence[str], n: int = 3) -> list[tuple[str, ...]]:
    """Extract n-grams from token sequence.

    Args:
        tokens: List of tokens
        n: Size of n-grams

    Returns:
        List of n-gram tuples
    """
    if len(tokens) < n:
        return [tuple(tokens)] if tokens else []
    return [tuple(tokens[i : i + n]) for i in range(len(tokens) - n + 1)]


def ngram_similarity(text1: str, text2: str, n: int = 3) -> tuple[float, int, int, int]:
    """Calculate n-gram overlap similarity.

    Based on: Jaccard coefficient applied to n-grams

    Args:
        text1: Original text
        text2: Rewritten text
        n: N-gram size

    Returns:
        Tuple of (similarity, common_count, total1, total2)
    """
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    ngrams1 = set(get_ngrams(tokens1, n))
    ngrams2 = set(get_ngrams(tokens2, n))

    if not ngrams1 or not ngrams2:
        return 0.0, 0, len(ngrams1), len(ngrams2)

    intersection = ngrams1 & ngrams2
    union = ngrams1 | ngrams2

    similarity = len(intersection) / len(union) if union else 0.0
    return similarity, len(intersection), len(ngrams1), len(ngrams2)


def jaccard_similarity(text1: str, text2: str) -> float:
    """Calculate Jaccard similarity coefficient.

    Reference: Broder, A. Z. (1997). On the resemblance and containment of documents.

    J(A,B) = |A ∩ B| / |A ∪ B|

    Args:
        text1: Original text
        text2: Rewritten text

    Returns:
        Jaccard similarity (0-1)
    """
    tokens1 = set(tokenize(text1))
    tokens2 = set(tokenize(text2))

    if not tokens1 or not tokens2:
        return 0.0

    intersection = tokens1 & tokens2
    union = tokens1 | tokens2

    return len(intersection) / len(union)


def simhash(text: str, hash_bits: int = 128) -> int:
    """Calculate SimHash fingerprint.

    Reference: Charikar, M. S. (2002). Similarity estimation techniques from rounding algorithms.

    SimHash creates a fingerprint where similar documents have similar hashes.
    Uses locality-sensitive hashing to detect near-duplicates.

    Args:
        text: Input text
        hash_bits: Number of bits in hash (default 128)

    Returns:
        SimHash fingerprint as integer
    """
    tokens = tokenize(text)

    if not tokens:
        return 0

    # Initialize bit counters
    v = [0] * hash_bits

    for token in tokens:
        # Get hash for token using MurmurHash3
        token_hash = mmh3.hash128(token, signed=False)

        for i in range(hash_bits):
            bit = (token_hash >> i) & 1
            if bit:
                v[i] += 1
            else:
                v[i] -= 1

    # Build final hash
    fingerprint = 0
    for i in range(hash_bits):
        if v[i] > 0:
            fingerprint |= 1 << i

    return fingerprint


def simhash_similarity(text1: str, text2: str, hash_bits: int = 128) -> float:
    """Calculate similarity using SimHash.

    Uses Hamming distance between SimHash fingerprints.

    Args:
        text1: Original text
        text2: Rewritten text
        hash_bits: Number of bits in hash

    Returns:
        Similarity score (0-1)
    """
    hash1 = simhash(text1, hash_bits)
    hash2 = simhash(text2, hash_bits)

    # Calculate Hamming distance
    xor = hash1 ^ hash2
    hamming_distance = bin(xor).count('1')

    # Convert to similarity
    similarity = 1.0 - (hamming_distance / hash_bits)
    return similarity


def hash_shingle(shingle: tuple[str, ...]) -> int:
    """Hash a shingle (k-gram) using MurmurHash3."""
    text = ' '.join(shingle)
    return mmh3.hash(text, signed=False)


def winnowing(text: str, k: int = 5, window_size: int = 4) -> set[int]:
    """Extract document fingerprint using Winnowing algorithm.

    Reference: Schleimer, S., Wilkerson, D. S., & Aiken, A. (2003).
    "Winnowing: local algorithms for document fingerprinting."
    SIGMOD '03.

    The algorithm:
    1. Generate k-grams (shingles) from text
    2. Hash each k-gram
    3. Select minimum hash from each window of size w
    4. Use selected hashes as document fingerprint

    This guarantees:
    - If documents share a substring of length >= k + window_size - 1, at least one fingerprint matches
    - Fingerprint density is bounded

    Args:
        text: Input text
        k: Size of k-grams (shingles)
        window_size: Size of selection window

    Returns:
        Set of fingerprint hashes
    """
    tokens = tokenize(text)

    if len(tokens) < k:
        return {hash_shingle(tuple(tokens))} if tokens else set()

    # Generate k-grams and their hashes
    kgrams = get_ngrams(tokens, k)
    hashes = [hash_shingle(kg) for kg in kgrams]

    if len(hashes) < window_size:
        # Return minimum hash if window is larger than document
        return {min(hashes)} if hashes else set()

    # Winnowing: select minimum from each window
    fingerprints = set()
    prev_min_idx = -1

    for i in range(len(hashes) - window_size + 1):
        window = hashes[i : i + window_size]
        min_val = min(window)
        min_idx = i + window.index(min_val)

        # Only add if this is a new minimum position
        # This reduces fingerprint size while maintaining guarantees
        if min_idx != prev_min_idx:
            fingerprints.add(min_val)
            prev_min_idx = min_idx

    return fingerprints


def winnowing_similarity(text1: str, text2: str, k: int = 5, window_size: int = 4) -> float:
    """Calculate similarity using Winnowing fingerprints.

    Args:
        text1: Original text
        text2: Rewritten text
        k: K-gram size
        window_size: Winnowing window size

    Returns:
        Jaccard similarity of fingerprint sets (0-1)
    """
    fp1 = winnowing(text1, k, window_size)
    fp2 = winnowing(text2, k, window_size)

    if not fp1 or not fp2:
        return 0.0

    intersection = fp1 & fp2
    union = fp1 | fp2

    return len(intersection) / len(union)


def word_frequency_similarity(text1: str, text2: str) -> float:
    """Calculate cosine similarity based on word frequencies.

    Useful for detecting semantic similarity even with word reordering.

    Args:
        text1: Original text
        text2: Rewritten text

    Returns:
        Cosine similarity (0-1)
    """
    tokens1 = tokenize(text1)
    tokens2 = tokenize(text2)

    freq1 = Counter(tokens1)
    freq2 = Counter(tokens2)

    # Get all unique words
    all_words = set(freq1.keys()) | set(freq2.keys())

    if not all_words:
        return 0.0

    # Calculate dot product and magnitudes
    dot_product = sum(freq1.get(w, 0) * freq2.get(w, 0) for w in all_words)
    magnitude1 = sum(v ** 2 for v in freq1.values()) ** 0.5
    magnitude2 = sum(v ** 2 for v in freq2.values()) ** 0.5

    if magnitude1 == 0 or magnitude2 == 0:
        return 0.0

    return dot_product / (magnitude1 * magnitude2)
