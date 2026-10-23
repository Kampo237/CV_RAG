"""
Transmission d'un message de visiteur à Jordan — étapes imposées par le code

L'ancien protocole vivait dans le prompt : le modèle pouvait promettre un envoi
sans avoir l'outil, exiger un courriel alors que le visiteur donnait un
téléphone, ou sauter la confirmation. Ici :

  1. prepare(...) valide nom, contact (courriel OU téléphone) et message, puis
     garde un brouillon pour la session ;
  2. send(...) n'envoie que si un brouillon existe, qu'il a été préparé lors
     d'un tour PRÉCÉDENT, et que le dernier message du visiteur est une
     confirmation explicite ;
  3. limites : 2 envois par session, DAILY_CONTACT_LIMIT par jour.

Livraison : outil send_sms du serveur MCP (connexion ouverte seulement au
moment de l'envoi) ; repli sur Twilio en direct si le MCP est injoignable.
Le destinataire est toujours le numéro de Jordan, fixé côté serveur.

État en mémoire : valable en mono-worker, comme le reste de main.py.
"""
import os
import re
import time
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger("rag_pipeline")

MCP_SMS_URL = os.getenv("MCP_SMS_URL", "http://mcp-sms:8010/sse")
MAX_SENDS_PER_SESSION = 2
DAILY_CONTACT_LIMIT = int(os.getenv("DAILY_CONTACT_LIMIT", "20"))
DRAFT_TTL_SECONDS = 1800

_EMAIL = re.compile(r"^[\w.+-]+@[\w-]+(\.[\w-]+)+$")
_CONFIRM = re.compile(
    r"\b(oui|ouais|ouii+|yes|ok|okay|d'accord|je confirme|confirme|confirmé|vas-y|vasy|go|envoie|"
    r"envoie-le|c'est bon|c bon|parfait|exact|correct|valide|parfait)\b",
    re.IGNORECASE,
)
_REFUSE = re.compile(r"\b(non|annule|annuler|pas maintenant|laisse tomber|stop|attends)\b", re.IGNORECASE)
_SPAM = re.compile(
    r"(https?://|www\.)\S+|\b(casino|crypto|bitcoin|viagra|forex|seo services|backlinks?)\b"
    r"|ignore (tes|les|all|previous)|prompt syst|api[ _-]?key",
    re.IGNORECASE,
)


@dataclass
class Draft:
    name: str
    contact: str
    message: str
    turn: int
    created: float = field(default_factory=time.time)

    def sms_text(self) -> str:
        return f"Portfolio — message de {self.name} ({self.contact}) : {self.message}"[:600]


@dataclass
class _Session:
    turn: int = 0
    draft: Optional[Draft] = None
    sent: int = 0


_sessions: dict[str, _Session] = {}
_daily = {"day": "", "count": 0}


def _session(session_id: str) -> _Session:
    return _sessions.setdefault(session_id, _Session())


def start_turn(session_id: str) -> int:
    """À appeler une fois par message reçu par l'agent. Renvoie le numéro du tour."""
    s = _session(session_id)
    s.turn += 1
    if s.draft and time.time() - s.draft.created > DRAFT_TTL_SECONDS:
        s.draft = None
    return s.turn


def has_pending_draft(session_id: str) -> bool:
    s = _sessions.get(session_id)
    return bool(s and s.draft and time.time() - s.draft.created <= DRAFT_TTL_SECONDS)


def cancel_draft(session_id: str) -> bool:
    s = _sessions.get(session_id)
    if s and s.draft:
        s.draft = None
        return True
    return False


# -----------------------------------------------------------------------------
# Validation
# -----------------------------------------------------------------------------

def normalize_contact(raw: str) -> Optional[str]:
    """Courriel valide, ou téléphone de 10 à 15 chiffres (formaté), sinon None."""
    value = (raw or "").strip()
    if _EMAIL.match(value):
        return value.lower()
    digits = re.sub(r"\D", "", value)
    if 10 <= len(digits) <= 15:
        if len(digits) == 10:
            return f"{digits[:3]} {digits[3:6]}-{digits[6:]}"
        if len(digits) == 11 and digits.startswith("1"):
            return f"+1 {digits[1:4]} {digits[4:7]}-{digits[7:]}"
        return "+" + digits
    return None


def prepare(session_id: str, name: str, contact: str, message: str) -> str:
    """Valide et garde un brouillon. Renvoie le texte à transmettre à l'agent."""
    s = _session(session_id)
    if s.sent >= MAX_SENDS_PER_SESSION:
        return "REFUS : limite de messages atteinte pour cette conversation. Ne propose pas d'autre envoi."
    name = re.sub(r"\s+", " ", (name or "").strip())
    message = re.sub(r"\s+", " ", (message or "").strip())
    problems = []
    if len(name) < 2 or len(name) > 80:
        problems.append("le nom du visiteur")
    normalized = normalize_contact(contact)
    if not normalized:
        problems.append("un moyen de le recontacter valide (courriel OU numéro de téléphone)")
    if len(message) < 8:
        problems.append("le message à transmettre (quelques mots au moins)")
    if problems:
        return "INCOMPLET : il manque " + " et ".join(problems) + ". Demande seulement ce qui manque."
    if len(message) > 500:
        message = message[:497] + "…"
    if _SPAM.search(message) or _SPAM.search(name):
        return "REFUS : message refusé (liens, publicité ou contenu suspect). Refuse poliment, sans détailler."
    previous = s.draft
    if previous and (previous.name, previous.contact, previous.message) == (name, normalized, message) \
            and previous.turn < s.turn:
        # Le modèle re-prépare souvent le même message au lieu d'envoyer après « oui » :
        # on garde le brouillon (et sa date) pour que l'envoi reste possible.
        return ("BROUILLON DÉJÀ PRÊT et déjà montré au visiteur. S'il vient de confirmer, appelle "
                "send_contact_message maintenant ; sinon, attends sa confirmation.")
    s.draft = Draft(name=name, contact=normalized, message=message, turn=s.turn)
    return (
        "BROUILLON PRÊT (rien n'est encore envoyé). Montre ce récapitulatif au visiteur et demande-lui "
        "de confirmer explicitement :\n"
        f"- Nom : {name}\n- Contact : {normalized}\n- Message : « {message} »"
    )


async def send(session_id: str, last_user_message: str) -> str:
    """Envoie le brouillon si — et seulement si — le visiteur vient de le confirmer."""
    s = _session(session_id)
    draft = s.draft
    if not draft:
        return "REFUS : aucun brouillon préparé. Utilise d'abord prepare_contact_message."
    if draft.turn >= s.turn:
        return ("REFUS : le visiteur n'a pas encore vu le récapitulatif. Montre-le et attends sa "
                "confirmation dans son prochain message.")
    if _REFUSE.search(last_user_message or "") or not _CONFIRM.search(last_user_message or ""):
        return "REFUS : pas de confirmation explicite du visiteur. Demande-lui de confirmer (oui / non)."
    today = time.strftime("%Y-%m-%d")
    if _daily["day"] != today:
        _daily.update(day=today, count=0)
    if _daily["count"] >= DAILY_CONTACT_LIMIT:
        return "ÉCHEC : service de messages momentanément indisponible. Invite à écrire par courriel."

    ok, detail = await _deliver(draft.sms_text())
    if not ok:
        logger.error(f"[contact] livraison échouée : {detail}")
        return ("ÉCHEC : le message n'a pas pu être transmis (problème technique). Dis-le honnêtement "
                "et propose le courriel du site.")
    s.sent += 1
    s.draft = None
    _daily["count"] += 1
    logger.info(f"[contact] message transmis ({detail})")
    return "ENVOYÉ : le message a bien été transmis à Jordan."


# -----------------------------------------------------------------------------
# Livraison
# -----------------------------------------------------------------------------

async def _deliver(text: str) -> tuple[bool, str]:
    """Via l'outil send_sms du serveur MCP ; repli Twilio direct si le MCP ne répond pas."""
    try:
        from mcp import ClientSession
        from mcp.client.sse import sse_client

        async def _via_mcp() -> str:
            async with sse_client(MCP_SMS_URL) as (read, write):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    result = await session.call_tool("send_sms", {"message": text})
                    return " ".join(getattr(c, "text", "") for c in result.content)

        reply = await asyncio.wait_for(_via_mcp(), timeout=15)
        if reply.startswith("SMS envoyé"):
            return True, "mcp"
        logger.warning(f"[contact] MCP a répondu une erreur : {reply}")
    except Exception as e:
        logger.warning(f"[contact] MCP injoignable ({type(e).__name__}) — repli Twilio direct")
    return await asyncio.to_thread(_deliver_twilio, text)


def _deliver_twilio(text: str) -> tuple[bool, str]:
    sid, token = os.getenv("TWILIO_ACCOUNT_SID"), os.getenv("TWILIO_AUTH_TOKEN")
    sender = os.getenv("TWILIO_FROM_NUMBER")
    recipient = os.getenv("ALERT_PHONE_NUMBER") or os.getenv("JORDAN_PHONE")
    if not all([sid, token, sender, recipient]):
        return False, "configuration Twilio incomplète"
    try:
        from twilio.rest import Client
        message = Client(sid, token).messages.create(body=text, from_=sender, to=recipient)
        return True, f"twilio {message.sid}"
    except Exception as e:
        return False, f"twilio : {type(e).__name__}: {e}"
