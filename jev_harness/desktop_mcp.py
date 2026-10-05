"""Serveur MCP du bureau virtuel: des mains et des yeux peu coûteux pour Claude (texte d'abord, capture en dernier)."""

import asyncio
import os

import httpx
from loguru import logger
from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

TIMEOUT_S = 20
MAX_STEPS = 30
MAX_WAIT_S = 10
SERVER = MCPServer(
    name="bureau-virtuel",
    instructions=(
        "Bureau Wayland virtuel isolé (jamais le bureau réel de l'utilisateur). Préfère desktop_do pour enchaîner "
        "plusieurs gestes en un appel, lis desktop_state (texte) avant de demander une capture, et ne demande "
        "desktop_screenshot qu'en dernier recours (coût en tokens). Coordonnées en pixels du bureau (1600x900)."
    ),
)


def _base() -> str:
    url = os.environ.get("LAB_URL", "")
    if not url:
        raise ToolError("LAB_URL n'est pas défini (adresse du labo, voir README).")
    return url.rstrip("/") + "/api/desktop"


async def _call(method: str, path: str, body: dict | None = None) -> httpx.Response:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT_S) as client:
            r = await client.request(method, f"{_base()}/{path}", json=body)
    except httpx.HTTPError as err:
        logger.error("labo injoignable ({}): {}", path, err)
        raise ToolError(f"Labo injoignable: {err}") from err
    if r.status_code >= 400:
        detail = (
            r.json().get("error", r.text[:200])
            if r.headers.get("content-type", "").startswith("application/json")
            else r.text[:200]
        )
        raise ToolError(f"{path}: {detail}")
    return r


def _summary(state: dict) -> str:
    if not state.get("ready"):
        return "Bureau virtuel arrêté" if not state.get("alive") else "Bureau virtuel en démarrage"
    wins = state.get("windows", [])
    lines = [
        f'#{w["id"]} {w["app"] or "?"} "{w["title"][:60]}" {w["w"]}x{w["h"]}@{w["x"]},{w["y"]}'
        + (" [focus]" if w["focused"] else "")
        for w in wins
    ]
    return f"Bureau actif, {len(wins)} fenêtre(s)" + ("".join("\n" + line for line in lines))


async def _state_text() -> str:
    return _summary((await _call("GET", "state")).json())


@SERVER.tool()
async def desktop_state() -> str:
    """État du bureau virtuel en texte: actif ou non, fenêtres (id, appli, titre, taille, position, focus)."""
    return await _state_text()


@SERVER.tool()
async def desktop_start() -> str:
    """Démarre le bureau virtuel (sway headless isolé) et attend qu'il soit prêt."""
    await _call("POST", "start", {})
    for _ in range(30):
        await asyncio.sleep(1)
        state = (await _call("GET", "state")).json()
        if state.get("ready"):
            return _summary(state)
    raise ToolError("Le bureau virtuel n'est pas prêt après 30 s.")


@SERVER.tool()
async def desktop_stop() -> str:
    """Arrête le bureau virtuel et ferme toutes ses applications."""
    await _call("POST", "stop", {})
    return "Bureau virtuel arrêté"


@SERVER.tool()
async def desktop_screenshot(scale: float = 0.5) -> Image:
    """Capture JPEG du bureau virtuel. Coûteux en tokens: préfère desktop_state. scale de 0.1 à 1 (0.5 par défaut)."""
    r = await _call("GET", f"shot.jpg?scale={min(1.0, max(0.1, scale))}")
    return Image(data=r.content, format="jpeg")


async def _step(step: dict) -> str:
    if len(step) != 1:
        raise ToolError(f"Une étape = une seule action, reçu: {sorted(step)}")
    ((action, arg),) = step.items()
    if action == "wait":
        await asyncio.sleep(min(MAX_WAIT_S, max(0.0, float(arg))))
    elif action == "launch":
        await _call("POST", "launch", {"cmd": str(arg)})
    elif action in ("click", "move") and isinstance(arg, list) and len(arg) >= 2:
        await _call("POST", action, {"x": arg[0], "y": arg[1], **({"button": arg[2]} if len(arg) > 2 else {})})
    elif action in ("type", "key"):
        await _call("POST", action, {"text" if action == "type" else "keys": str(arg)})
    elif action in ("focus", "close"):
        await _call("POST", action, {"id": int(arg)})
    else:
        raise ToolError(f"Action inconnue ou arguments invalides: {action}")
    return action


@SERVER.tool()
async def desktop_do(steps: list[dict]) -> str:
    """Enchaîne plusieurs gestes en UN appel (économise des tours). Chaque étape est un objet à une clé:
    {"launch": "terminal|firefox|chrome|launcher|<commande>"}, {"click": [x, y]} ou [x, y, "right"], {"move": [x, y]},
    {"type": "texte"}, {"key": "ctrl+shift+t"}, {"focus": id}, {"close": id}, {"wait": secondes}.
    Retourne l'état du bureau à la fin (ou l'étape en échec)."""
    if not steps or len(steps) > MAX_STEPS:
        raise ToolError(f"Entre 1 et {MAX_STEPS} étapes.")
    done: list[str] = []
    for i, step in enumerate(steps, 1):
        try:
            done.append(await _step(step))
        except (ToolError, ValueError, TypeError) as err:
            raise ToolError(f"Étape {i} ({step}) en échec après {len(done)} réussie(s): {err}") from err
        await asyncio.sleep(0.15)
    return f"{len(done)} étape(s) faites.\n{await _state_text()}"


if __name__ == "__main__":
    SERVER.run()
