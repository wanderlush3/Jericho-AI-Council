"""
Jericho — PNG Character Card Embedding (TavernCard v2 Spec)

Pure-Python PNG tEXt chunk reader/writer for embedding character-card
JSON inside PNG files.  Follows the convention established by TavernAI /
SillyTavern / gaffe-buck's tavern-v2-character-creator:

• Character data is serialised as JSON, then base64-encoded.
• The base64 string is stored in a PNG **tEXt** chunk with keyword ``chara``.
• On export the chunk is inserted immediately before the IEND chunk.

No external dependencies beyond the standard library.
"""

from __future__ import annotations

import logging
import base64
import json
import struct
import zlib
from typing import Any

from core.characters import CharacterTemplate



log = logging.getLogger(__name__)

# ─── PNG Constants ─────────────────────────────────────────────

_PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_CHARA_KEYWORD = b"chara"


# ─── Low-level chunk helpers ──────────────────────────────────

def _read_chunks(data: bytes) -> list[dict[str, Any]]:
    """Parse a PNG file into a list of chunks.

    Each chunk is ``{"type": str, "data": bytes}``.
    Raises ``ValueError`` on corrupt/invalid PNG data.
    """
    if data[:8] != _PNG_SIGNATURE:
        raise ValueError("Invalid PNG header")

    chunks: list[dict[str, Any]] = []
    idx = 8
    while idx < len(data):
        if idx + 8 > len(data):
            raise ValueError("PNG truncated (chunk header)")
        length = struct.unpack(">I", data[idx : idx + 4])[0]
        chunk_type = data[idx + 4 : idx + 8].decode("ascii")
        idx += 8

        if idx + length + 4 > len(data):
            raise ValueError(f"PNG truncated in {chunk_type} chunk")

        chunk_data = data[idx : idx + length]
        idx += length

        # CRC covers type + data
        stored_crc = struct.unpack(">I", data[idx : idx + 4])[0]
        idx += 4

        computed_crc = zlib.crc32(data[idx - length - 8 : idx - 4]) & 0xFFFFFFFF
        # We recompute over type+data bytes
        computed_crc = zlib.crc32(chunk_type.encode("ascii") + chunk_data) & 0xFFFFFFFF
        if stored_crc != computed_crc:
            raise ValueError(f"CRC mismatch in {chunk_type} chunk")

        chunks.append({"type": chunk_type, "data": chunk_data})

    if not chunks or chunks[0]["type"] != "IHDR":
        raise ValueError("PNG missing IHDR header")
    if chunks[-1]["type"] != "IEND":
        raise ValueError("PNG missing IEND trailer")

    return chunks


def _encode_chunk(chunk_type: str, chunk_data: bytes) -> bytes:
    """Encode a single PNG chunk (length + type + data + CRC)."""
    type_bytes = chunk_type.encode("ascii")
    crc = zlib.crc32(type_bytes + chunk_data) & 0xFFFFFFFF
    return (
        struct.pack(">I", len(chunk_data))
        + type_bytes
        + chunk_data
        + struct.pack(">I", crc)
    )


def _assemble_png(chunks: list[dict[str, Any]]) -> bytes:
    """Re-assemble a PNG file from a list of chunks."""
    parts = [_PNG_SIGNATURE]
    for c in chunks:
        parts.append(_encode_chunk(c["type"], c["data"]))
    return b"".join(parts)


def _encode_text_chunk_data(keyword: str, text: str) -> bytes:
    """Build the DATA portion of a tEXt chunk: keyword NUL text."""
    return keyword.encode("latin-1") + b"\x00" + text.encode("latin-1")


def _decode_text_chunk_data(data: bytes) -> tuple[str, str]:
    """Decode a tEXt chunk's DATA into (keyword, text)."""
    nul = data.index(0)
    keyword = data[:nul].decode("latin-1")
    text = data[nul + 1 :].decode("latin-1")
    return keyword, text


# ─── Public API ────────────────────────────────────────────────


def character_to_tavern_v2(ct: CharacterTemplate) -> dict[str, Any]:
    """Convert a Jericho ``CharacterTemplate`` to TavernCard v2 format.

    Maps Jericho fields to the closest TavernCard v2 equivalents.
    """
    traits_desc = "\n".join(
        f"- {t.name} ({t.trait_type}, intensity {t.intensity}): {t.description}"
        for t in ct.traits
    )

    return {
        "spec": "chara_card_v2",
        "spec_version": "2.0",
        "data": {
            "name": ct.name,
            "description": ct.description,
            "personality": traits_desc,
            "scenario": ct.backstory,
            "first_mes": ct.greeting,
            "mes_example": "\n".join(ct.example_messages),
            "creator_notes": "",
            "system_prompt": ct.system_prompt,
            "post_history_instructions": "",
            "alternate_greetings": [],
            "tags": list(ct.tags),
            "creator": ct.author,
            "character_version": str(ct.version),
            "extensions": {
                "jericho": {
                    "id": ct.id,
                    "status": ct.status,
                    "traits": [
                        {
                            "trait_type": t.trait_type,
                            "name": t.name,
                            "description": t.description,
                            "intensity": t.intensity,
                        }
                        for t in ct.traits
                    ],
                    "created_at": ct.created_at,
                    "updated_at": ct.updated_at,
                    "metadata": ct.metadata,
                },
            },
        },
    }


def embed_character_in_png(
    png_bytes: bytes,
    character: CharacterTemplate,
) -> bytes:
    """Embed character card JSON (TavernCard v2) into a PNG.

    Strips any existing ``tEXt`` chunks, then inserts a new ``chara``
    chunk immediately before the ``IEND`` chunk.

    Returns the modified PNG bytes.
    """
    chunks = _read_chunks(png_bytes)

    # Remove all existing tEXt chunks (matches TavernAI behaviour)
    chunks = [c for c in chunks if c["type"] != "tEXt"]

    # Build the chara payload
    tavern_data = character_to_tavern_v2(character)
    json_str = json.dumps(tavern_data, ensure_ascii=False)
    b64_str = base64.b64encode(json_str.encode("utf-8")).decode("ascii")

    chara_chunk = {
        "type": "tEXt",
        "data": _encode_text_chunk_data("chara", b64_str),
    }

    # Insert before IEND (last chunk)
    chunks.insert(-1, chara_chunk)

    return _assemble_png(chunks)


def extract_character_from_png(png_bytes: bytes) -> dict[str, Any] | None:
    """Extract character card JSON from a PNG's ``chara`` tEXt chunk.

    Returns the parsed dict, or ``None`` if no ``chara`` chunk is found.
    """
    chunks = _read_chunks(png_bytes)

    for c in chunks:
        if c["type"] != "tEXt":
            continue
        keyword, text = _decode_text_chunk_data(c["data"])
        if keyword == "chara":
            try:
                raw = base64.b64decode(text)
                return json.loads(raw.decode("utf-8"))
            except Exception:
                log.debug("png_embed: failed raw", exc_info=True)
                return None

    return None


def create_minimal_png() -> bytes:
    """Create a minimal valid 1×1 transparent PNG for use as a placeholder.

    Useful when no avatar image has been uploaded but an export is needed.
    """
    # IHDR: 1×1, 8-bit RGBA
    ihdr_data = struct.pack(">IIBBBBB", 1, 1, 8, 6, 0, 0, 0)
    # IDAT: single pixel (filter byte 0 + 4 zero bytes for RGBA)
    raw_pixel = b"\x00\x00\x00\x00\x00"
    compressed = zlib.compress(raw_pixel)
    idat_data = compressed
    # IEND: empty
    iend_data = b""

    chunks = [
        {"type": "IHDR", "data": ihdr_data},
        {"type": "IDAT", "data": idat_data},
        {"type": "IEND", "data": iend_data},
    ]
    return _assemble_png(chunks)
