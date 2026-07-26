"""Testaufbau.

Die Fachlogik (Decoder, Merge, Energie-Integration) enthaelt bewusst keine
Home-Assistant-Importe und soll deshalb auch ohne installiertes HA testbar
sein. Das Paket-``__init__.py`` importiert aber HA - deshalb registrieren wir
hier ein synthetisches Paket, dessen ``__init__`` nie ausgefuehrt wird.
Untermodule werden ueber ``__path__`` ganz normal gefunden.
"""

from __future__ import annotations

import sys
import types
from pathlib import Path

_INTEGRATION = Path(__file__).resolve().parents[1] / "custom_components" / "ecoflow_ocean2"

if "custom_components" not in sys.modules:
    _parent = types.ModuleType("custom_components")
    _parent.__path__ = [str(_INTEGRATION.parent)]
    sys.modules["custom_components"] = _parent

if "custom_components.ecoflow_ocean2" not in sys.modules:
    _package = types.ModuleType("custom_components.ecoflow_ocean2")
    _package.__path__ = [str(_INTEGRATION)]
    sys.modules["custom_components.ecoflow_ocean2"] = _package
