"""Telegram channel — sends approval notifications via Cortex's direct bot.

The bot is optional. If CORTEX_TELEGRAM_BOT_TOKEN is not set, this
channel silently does nothing.
"""

import os

from src.server.config.logfire_config import get_logger
from src.server.services.workflow.hitl_models import ApprovalContext

logger = get_logger(__name__)

BOT_TOKEN = os.getenv("CORTEX_TELEGRAM_BOT_TOKEN")
CHAT_IDS = [cid.strip() for cid in os.getenv("CORTEX_TELEGRAM_CHAT_IDS", "").split(",") if cid.strip()]


class TelegramChannel:
    def __init__(self):
        self._bot = None

    async def _get_bot(self):
        if self._bot is not None:
            return self._bot
        if not BOT_TOKEN:
            return None
        try:
            from telegram import Bot

            self._bot = Bot(token=BOT_TOKEN)
            return self._bot
        except Exception as e:
            logger.warning(f"Failed to initialize Telegram bot: {e}")
            return None

    async def send_approval_request(self, context: ApprovalContext) -> None:
        bot = await self._get_bot()
        if not bot or not CHAT_IDS:
            return

        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            text = (
                f"**Approval Required: {context.approval_type}**\n\n"
                f"Workflow node `{context.yaml_node_id}` needs review.\n\n"
                f"{context.node_output[:500]}"
            )
            keyboard = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("Approve", callback_data=f"approve:{context.approval_id}"),
                        InlineKeyboardButton("Reject", callback_data=f"reject:{context.approval_id}"),
                    ],
                ]
            )
            if context.cortex_url:
                keyboard.inline_keyboard.append(
                    [
                        InlineKeyboardButton(
                            "View in Cortex",
                            url=f"{context.cortex_url}/workflows/{context.workflow_run_id}/approvals/{context.approval_id}",
                        ),
                    ]
                )

            for chat_id in CHAT_IDS:
                msg = await bot.send_message(
                    chat_id=chat_id,
                    text=text,
                    reply_markup=keyboard,
                    parse_mode="Markdown",
                )
                logger.info(f"Telegram approval sent to {chat_id}, message_id={msg.message_id}")
        except Exception as e:
            logger.error(f"Failed to send Telegram approval: {e}", exc_info=True)

    async def notify_resolution(
        self, context: ApprovalContext, decision: str, resolved_by: str
    ) -> None:
        bot = await self._get_bot()
        if not bot or not CHAT_IDS:
            return
        try:
            text = f"**Resolved: {decision}** by {resolved_by}\nNode: `{context.yaml_node_id}`"
            for chat_id in CHAT_IDS:
                await bot.send_message(chat_id=chat_id, text=text, parse_mode="Markdown")
        except Exception as e:
            logger.error(f"Failed to send Telegram resolution: {e}", exc_info=True)
