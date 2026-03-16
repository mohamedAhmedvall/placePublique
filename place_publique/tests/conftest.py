"""
Configuration pytest pour Place Publique.
Ajoute le répertoire racine du projet au sys.path.
"""
import sys
from pathlib import Path

# Ajouter le répertoire racine du projet pour les imports absolus
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
