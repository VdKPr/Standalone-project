"""Configuration loading. All geometric parameters are in nm."""
from __future__ import annotations

from dataclasses import dataclass, fields
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ProcessParams:
    """Design-rule parameters of one pitch preset (all lengths in nm)."""

    cpp: float                  # contacted poly (gate) pitch
    gate_w: float
    fin_pitch: float            # 0 => planar active regions instead of fins
    fin_w: float
    m1_pitch: float
    m1_w: float
    cell_tracks: int            # standard-cell height in M1 tracks
    rail_w: float
    contact_w: float
    sram_cell_w: float
    sram_cell_h: float
    sram_strap_every: int       # add an M1 strap every N bitcell rows; 0 = perfectly periodic
    contact_array_pitch: float
    contact_array_w: float
    fill_pitch: float
    fill_w: float

    @property
    def cell_h(self) -> float:
        return self.cell_tracks * self.m1_pitch

    @classmethod
    def from_dict(cls, d: dict) -> "ProcessParams":
        names = {f.name for f in fields(cls)}
        missing, unknown = names - d.keys(), d.keys() - names
        if missing or unknown:
            raise ValueError(f"preset keys: missing={sorted(missing)} unknown={sorted(unknown)}")
        return cls(**d)


def load_config(path: str | Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def process_params(cfg: dict, preset: str | None = None) -> tuple[str, ProcessParams]:
    name = preset or cfg["preset"]
    if name not in cfg["presets"]:
        raise KeyError(f"unknown preset {name!r}; available: {sorted(cfg['presets'])}")
    return name, ProcessParams.from_dict(cfg["presets"][name])
