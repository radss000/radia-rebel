"""Versioned validation-corpus loading and ground-truth materialization."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, Iterable, Mapping, Tuple

LABELS = ("different", "related", "close", "very_close")
LABEL_RANK = {label: rank for rank, label in enumerate(LABELS)}


@dataclass(frozen=True)
class CorpusTrack:
    id: str
    path: str
    family: str
    close_group: str
    identity_group: str
    fixture: Mapping[str, Any]


@dataclass(frozen=True)
class PairAnnotation:
    track_a: str
    track_b: str
    label: str
    source: str


@dataclass(frozen=True)
class ValidationCorpus:
    manifest_path: Path
    corpus_id: str
    corpus_version: str
    release_eligible: bool
    annotation_protocol: Mapping[str, Any]
    embedding_spec: Mapping[str, Any]
    tracks: Tuple[CorpusTrack, ...]
    annotations: Mapping[Tuple[str, str], PairAnnotation]
    fingerprint: str

    @property
    def track_ids(self) -> Tuple[str, ...]:
        return tuple(track.id for track in self.tracks)

    def audio_path(self, track: CorpusTrack) -> Path:
        return (self.manifest_path.parent / track.path).resolve()

    def annotation_for(self, left_id: str, right_id: str) -> PairAnnotation:
        if left_id == right_id:
            raise ValueError("A track cannot be annotated against itself")
        key = tuple(sorted((left_id, right_id)))
        try:
            return self.annotations[key]
        except KeyError as exc:
            raise KeyError(f"Missing annotation for pair {key[0]} / {key[1]}") from exc


def _pair_key(left_id: str, right_id: str) -> Tuple[str, str]:
    if left_id == right_id:
        raise ValueError("Pair members must be different")
    return tuple(sorted((left_id, right_id)))


def _derived_label(left: CorpusTrack, right: CorpusTrack) -> str:
    if left.identity_group and left.identity_group == right.identity_group:
        return "very_close"
    if left.close_group and left.close_group == right.close_group:
        return "close"
    if left.family and left.family == right.family:
        return "related"
    return "different"


def _require_string(data: Mapping[str, Any], key: str, context: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{context}.{key} must be a non-empty string")
    return value.strip()


def _load_tracks(raw_tracks: Iterable[Mapping[str, Any]]) -> Tuple[CorpusTrack, ...]:
    tracks = []
    seen_ids = set()
    for index, raw in enumerate(raw_tracks):
        context = f"tracks[{index}]"
        track_id = _require_string(raw, "id", context)
        if track_id in seen_ids:
            raise ValueError(f"Duplicate track id: {track_id}")
        seen_ids.add(track_id)
        fixture = raw.get("fixture")
        if not isinstance(fixture, Mapping):
            raise ValueError(f"{context}.fixture must be an object")
        tracks.append(
            CorpusTrack(
                id=track_id,
                path=_require_string(raw, "path", context),
                family=_require_string(raw, "family", context),
                close_group=_require_string(raw, "close_group", context),
                identity_group=_require_string(raw, "identity_group", context),
                fixture=dict(fixture),
            )
        )
    if len(tracks) < 5:
        raise ValueError("Validation corpus requires at least 5 tracks")
    return tuple(tracks)


def _materialize_annotations(
    tracks: Tuple[CorpusTrack, ...],
    overrides: Iterable[Mapping[str, Any]],
) -> Dict[Tuple[str, str], PairAnnotation]:
    annotations: Dict[Tuple[str, str], PairAnnotation] = {}
    track_by_id = {track.id: track for track in tracks}
    for left_index, left in enumerate(tracks):
        for right in tracks[left_index + 1 :]:
            key = _pair_key(left.id, right.id)
            annotations[key] = PairAnnotation(
                track_a=key[0],
                track_b=key[1],
                label=_derived_label(left, right),
                source="fixture_recipe_v1",
            )

    for index, raw in enumerate(overrides):
        left_id = _require_string(raw, "track_a", f"pair_overrides[{index}]")
        right_id = _require_string(raw, "track_b", f"pair_overrides[{index}]")
        if left_id not in track_by_id or right_id not in track_by_id:
            raise ValueError(f"Unknown track in pair override: {left_id} / {right_id}")
        label = _require_string(raw, "label", f"pair_overrides[{index}]")
        if label not in LABEL_RANK:
            raise ValueError(f"Unknown annotation label: {label}")
        key = _pair_key(left_id, right_id)
        annotations[key] = PairAnnotation(
            track_a=key[0],
            track_b=key[1],
            label=label,
            source=str(raw.get("source") or "explicit_override"),
        )

    expected = len(tracks) * (len(tracks) - 1) // 2
    if len(annotations) != expected:
        raise ValueError(f"Corpus annotations are incomplete: {len(annotations)} / {expected}")
    return annotations


def load_corpus(manifest_path: str | Path) -> ValidationCorpus:
    path = Path(manifest_path).resolve()
    raw_bytes = path.read_bytes()
    data = json.loads(raw_bytes)
    if data.get("schema_version") != 1:
        raise ValueError("Unsupported validation corpus schema_version")
    tracks = _load_tracks(data.get("tracks") or [])
    protocol = data.get("annotation_protocol")
    embedding_spec = data.get("embedding_spec")
    if not isinstance(protocol, Mapping) or not isinstance(embedding_spec, Mapping):
        raise ValueError("annotation_protocol and embedding_spec must be objects")
    relevance_floor = protocol.get("relevance_floor")
    if relevance_floor not in LABEL_RANK:
        raise ValueError("annotation_protocol.relevance_floor must be a known label")
    annotations = _materialize_annotations(tracks, data.get("pair_overrides") or [])
    return ValidationCorpus(
        manifest_path=path,
        corpus_id=_require_string(data, "corpus_id", "manifest"),
        corpus_version=_require_string(data, "corpus_version", "manifest"),
        release_eligible=bool(data.get("release_eligible", False)),
        annotation_protocol=dict(protocol),
        embedding_spec=dict(embedding_spec),
        tracks=tracks,
        annotations=annotations,
        fingerprint=hashlib.sha256(raw_bytes).hexdigest(),
    )
