"""
Serveur MCP — SMS via Twilio

Ce serveur expose un outil 'send_sms' via le protocole MCP (Model Context Protocol).
N'importe quel client MCP (Claude Desktop, un agent LangGraph, etc.) peut l'appeler.

Architecture :
  Client MCP (agent) ──MCP protocol──► Ce serveur ──HTTPS──► Twilio API ──► SMS

Lancement :
  python -m mcp_servers.sms_server.server

Transport SSE sur http://localhost:8010/sse
"""

import os
import logging
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP

# Charger les variables d'environnement
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("mcp_sms")

# =============================================================================
# CRÉATION DU SERVEUR MCP
# =============================================================================

# FastMCP est le wrapper haut-niveau du SDK MCP d'Anthropic.
# Il gère automatiquement le protocole (handshake, listing des tools, exécution).
mcp = FastMCP(
    name="sms-server",
    port=8010,
)


# =============================================================================
# CONFIGURATION TWILIO
# =============================================================================

TWILIO_ACCOUNT_SID = os.getenv("TWILIO_ACCOUNT_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_FROM_NUMBER = os.getenv("TWILIO_FROM_NUMBER")

# Destinataire unique des alertes — fixé côté serveur, jamais choisi par l'appelant
# (LLM ou client MCP). Une injection de prompt sur l'agent ne peut donc pas
# détourner ce tool pour spammer un tiers.
ALERT_PHONE_NUMBER = os.getenv("ALERT_PHONE_NUMBER")


def _get_twilio_client():
    """Crée le client Twilio (lazy, une seule fois)."""
    from twilio.rest import Client
    if not all([TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN]):
        raise ValueError("TWILIO_ACCOUNT_SID et TWILIO_AUTH_TOKEN doivent être définis dans .env")
    return Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)


# =============================================================================
# OUTILS MCP (TOOLS)
# =============================================================================

@mcp.tool()
def send_sms(message: str) -> str:
    """
    Envoie un SMS d'alerte au propriétaire du portfolio via Twilio.

    Le destinataire est fixé côté serveur (ALERT_PHONE_NUMBER) et ne peut pas
    être choisi par l'appelant — cet outil sert uniquement à notifier le
    propriétaire, jamais à envoyer un SMS à un tiers.

    Args:
        message: Contenu du SMS (max 1600 caractères)

    Returns:
        Confirmation de l'envoi avec le SID du message Twilio
    """
    if not ALERT_PHONE_NUMBER:
        return "Erreur : ALERT_PHONE_NUMBER n'est pas configuré côté serveur."

    # Validation du message
    if not message or not message.strip():
        return "Erreur : le message ne peut pas être vide"

    if len(message) > 1600:
        return f"Erreur : le message fait {len(message)} caractères (max 1600)"

    try:
        client = _get_twilio_client()

        # Envoi du SMS via Twilio — destinataire toujours ALERT_PHONE_NUMBER
        tw_message = client.messages.create(
            body=message,
            from_=TWILIO_FROM_NUMBER,
            to=ALERT_PHONE_NUMBER,
        )

        logger.info(f"✅ SMS envoyé — SID: {tw_message.sid}")
        return f"SMS envoyé avec succès. ID de confirmation : {tw_message.sid}"

    except Exception as e:
        logger.error(f"❌ Erreur envoi SMS: {e}")
        return f"Erreur lors de l'envoi du SMS : {str(e)}"


@mcp.tool()
def check_sms_status(message_sid: str) -> str:
    """
    Vérifie le statut d'un SMS précédemment envoyé.

    Args:
        message_sid: L'identifiant du message retourné par send_sms (commence par 'SM...')

    Returns:
        Statut du message (queued, sending, sent, delivered, failed, etc.)
    """
    try:
        client = _get_twilio_client()
        message = client.messages(message_sid).fetch()

        return (
            f"Statut du SMS {message_sid} :\n"
            f"  Destinataire : {message.to}\n"
            f"  Statut : {message.status}\n"
            f"  Date d'envoi : {message.date_sent or 'en cours'}\n"
            f"  Prix : {message.price or 'non calculé'} {message.price_unit or ''}"
        )

    except Exception as e:
        logger.error(f"❌ Erreur vérification SMS {message_sid}: {e}")
        return f"Erreur lors de la vérification : {str(e)}"


# =============================================================================
# RESSOURCES MCP (optionnel — infos statiques accessibles par le client)
# =============================================================================

@mcp.resource("sms://config")
def get_sms_config() -> str:
    """Retourne la configuration SMS actuelle (sans données sensibles)."""
    return (
        f"Serveur SMS MCP — Configuration\n"
        f"  Fournisseur : Twilio\n"
        f"  Numéro d'envoi : {TWILIO_FROM_NUMBER}\n"
        f"  Compte : {'configuré' if TWILIO_ACCOUNT_SID else 'NON configuré'}\n"
        f"  Mode : {'trial' if TWILIO_ACCOUNT_SID else 'inactif'}"
    )


# =============================================================================
# POINT D'ENTRÉE
# =============================================================================

if __name__ == "__main__":
    import uvicorn
    from starlette.types import ASGIApp, Receive, Scope, Send

    logger.info(f"🚀 Démarrage du serveur MCP SMS (Twilio)")
    logger.info(f"   Numéro d'envoi : {TWILIO_FROM_NUMBER}")
    logger.info(f"   Transport : SSE sur http://0.0.0.0:8010/sse")

    app = mcp.sse_app()

    # Middleware qui réécrit le header Host en "localhost:8010"
    # avant que la requête n'atteigne le handler SSE du SDK MCP.
    # Le SDK MCP valide le Host et rejette tout ce qui n'est pas
    # localhost — en Docker, le Host est "mcp-sms:8010".
    class RewriteHostMiddleware:
        def __init__(self, app: ASGIApp):
            self.app = app

        async def __call__(self, scope: Scope, receive: Receive, send: Send):
            if scope["type"] == "http":
                # Réécrire les headers pour que Host = localhost:8010
                headers = dict(scope.get("headers", []))
                new_headers = []
                for key, value in scope.get("headers", []):
                    if key == b"host":
                        new_headers.append((b"host", b"localhost:8010"))
                    else:
                        new_headers.append((key, value))
                scope = dict(scope)
                scope["headers"] = new_headers
            await self.app(scope, receive, send)

    wrapped_app = RewriteHostMiddleware(app)
    uvicorn.run(wrapped_app, host="0.0.0.0", port=8010)
