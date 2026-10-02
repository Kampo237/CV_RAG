"""
Autorisation des routes d'administration.

Chemin : en-tête HTTP `Authorization: Bearer <ADMIN_API_KEY>`.
La valeur vit dans l'environnement du serveur, jamais dans le navigateur.

Les routes publiques (chat, lecture /portfolio, dépôt d'un témoignage,
liste des témoignages approuvés, effacement de sa propre session de chat)
ne passent pas par ici.
"""
import os
import secrets

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

# Schéma de sécurité déclaré dans l'OpenAPI : c'est lui qui fait apparaître le
# bouton « Authorize » dans /docs. auto_error=False : on garde nos propres
# réponses (503 si non configuré, 401 sinon) au lieu du 403 par défaut.
bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AdminKey",
    description="Clé d'administration (valeur de ADMIN_API_KEY), envoyée en « Authorization: Bearer … ».",
)


def check_admin_token(token: str | None) -> None:
    """Refuse si la clé manque, ou si le jeton présenté n'est pas exactement le sien."""
    expected = os.getenv("ADMIN_API_KEY", "").strip()
    if not expected:
        raise HTTPException(status_code=503, detail="Administration non configurée")
    if not token or not secrets.compare_digest(token.strip(), expected):
        raise HTTPException(status_code=401, detail="Non autorisé")


def require_admin(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)) -> None:
    """Dépendance FastAPI des routes d'administration."""
    check_admin_token(credentials.credentials if credentials else None)
