"""Charger un modèle dans EchoHub: reproduit la planification de son MCP (métadonnées GGUF + profil machine → plan).

CLI: python -m jev_harness.echohub_load <identifiant du registre>  (rend la main dès que le chargement est lancé)
"""
import json
import sys
from typing import Any

import httpx

from .echohub import _base

PLATFORMS = {"linux_natif", "wsl2", "windows"}
TIMEOUT_S = 30


class LoadError(Exception):
    pass


def _get(path: str) -> Any:
    r = httpx.get(f"{_base()}{path}", timeout=TIMEOUT_S)
    r.raise_for_status()
    return r.json()


def _post(path: str, body: dict) -> Any:
    r = httpx.post(f"{_base()}{path}", json=body, timeout=TIMEOUT_S)
    if r.status_code >= 400:
        raise LoadError(f"EchoHub {path} → {r.status_code} {r.text[:300]}")
    return r.json()


def _need(value: Any, name: str) -> Any:
    if value is None or (isinstance(value, (int, float)) and value <= 0):
        raise LoadError(f"métadonnées GGUF incomplètes: {name}")
    return value


def _metadata(entry: dict, gguf: dict) -> dict:
    att, experts, ssm = gguf.get("attention") or {}, gguf.get("experts") or {}, gguf.get("ssm") or {}
    layers = _need(gguf.get("block_count"), "nombre de couches")
    meta = {
        "identifiant": entry["id"], "format": entry["format"], "architecture": gguf.get("architecture", ""),
        "taille_octets": _need(entry.get("taille_octets"), "taille"), "nombre_couches": layers,
        "dimension_embedding": _need(gguf.get("longueur_embedding"), "embedding"),
        "dimension_ffn": _need(gguf.get("largeur_ffn_active"), "ffn"),
        "nombre_tetes_attention": _need(att.get("nb_tetes"), "têtes"),
        "nombre_tetes_kv": att.get("nb_tetes_kv") or att.get("nb_tetes"), "dimension_tete": att.get("dimension_cle"),
        "contexte_entrainement_max": _need(gguf.get("contexte_natif"), "contexte"),
        "taille_vocabulaire": _need(gguf.get("taille_vocabulaire"), "vocabulaire"),
        "quantification": gguf.get("quantification_mesuree") or gguf.get("quantification_declaree"),
        "est_moe": (gguf.get("nb_experts") or 0) > 1, "nombre_experts": gguf.get("nb_experts"),
        "nombre_experts_actifs": gguf.get("nb_experts_actifs"),
        "dimension_ffn_expert": experts.get("largeur_ffn_expert"),
        "dimension_ffn_expert_partage": experts.get("largeur_ffn_partagee"),
        "intervalle_attention_pleine": att.get("intervalle_attention_pleine"),
        "dimension_interne_ssm": ssm.get("dimension_interne"), "dimension_etat_ssm": ssm.get("dimension_etat"),
        "noyau_convolution_ssm": ssm.get("noyau_convolution"),
    }
    m = gguf.get("mesures") or {}
    if len(m.get("octets_par_bloc") or []) == layers and len(m.get("octets_experts_par_bloc") or []) == layers:
        meta.update(octets_par_bloc=m["octets_par_bloc"], octets_experts_par_bloc=m["octets_experts_par_bloc"],
                    octets_hors_blocs=m.get("octets_hors_blocs"))
    return meta


def _profile(profil: dict, engines: dict, status: dict) -> dict:
    gpu = profil.get("gpu_principal")
    if gpu is None or profil.get("plateforme") not in PLATFORMS:
        raise LoadError("aucun GPU mesuré ou plateforme hors du champ du planificateur")
    usable = [n for n, k in (("llama.cpp", "llamacpp"), ("vllm", "vllm")) if (engines.get(k) or {}).get("fonctionnel")]
    eng = status.get("etat_moteur")
    loaded = []
    if status.get("etat") == "pret" and eng:
        vram = max(0, (eng.get("vram_apres_octets") or 0) - (eng.get("vram_avant_octets") or 0))
        loaded = [{"identifiant": eng["modele"], "moteur": eng["moteur"], "vram_octets": vram}]
    cc = [gpu["compute_majeur"], gpu["compute_mineur"]] if gpu.get("compute_majeur") is not None else None
    return {"plateforme": profil["plateforme"], "index_gpu": gpu.get("index", 0), "nom_gpu": gpu.get("nom", ""),
            "vram_totale_octets": profil["vram_totale_octets"], "vram_libre_octets": profil["vram_libre_octets"],
            "ram_libre_octets": profil["ram_disponible_octets"], "moteurs_disponibles": usable,
            "modeles_charges": loaded, "capacite_calcul": cc}


def start_load(model_id: str) -> None:
    entry = next((m for m in _get("/models/registre") if m["id"] == model_id), None)
    if entry is None:
        raise LoadError("modèle inconnu dans le registre EchoHub")
    gguf = _get(f"/models/registre/{model_id}/metadonnees")
    demande = {"metadonnees": _metadata(entry, gguf),
               "profil": _profile(_get("/system/profil"), _get("/engines/etat"), _get("/inference/etat")),
               "preferences": {}}
    plan = _post("/inference/planifier", {"demande": demande})["plan"]
    _post("/inference/charger", {"chemin_modele": entry["chemin"], "plan": plan})


if __name__ == "__main__":
    try:
        start_load(sys.argv[1])
        print(json.dumps({"ok": True}))
    except (LoadError, httpx.HTTPError, KeyError) as err:
        print(json.dumps({"error": f"{type(err).__name__}: {err}"}, ensure_ascii=False))
        sys.exit(1)
