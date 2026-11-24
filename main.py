"""Append new incoming Telegram messages to a local UTF-8 text file."""

import argparse
import asyncio
import json
import logging
import os
from pathlib import Path

from telethon import TelegramClient, events


def append_message(output: Path, event: events.NewMessage.Event) -> None:
    message = event.message
    record = {
        "timestamp": message.date.isoformat(),
        "chat_id": event.chat_id,
        "sender_id": event.sender_id,
        "message_id": message.id,
        "text": message.raw_text,
        "media": type(message.media).__name__ if message.media else None,
    }
    with output.open("a", encoding="utf-8") as stream:
        stream.write(json.dumps(record, ensure_ascii=False) + "\n")


async def log_messages(api_id: int, api_hash: str, output: Path) -> None:
    state_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TelegramLogger"
    state_dir.mkdir(parents=True, exist_ok=True)
    output = output.expanduser().resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("a", encoding="utf-8"):
        pass

    client = TelegramClient(str(state_dir / "account"), api_id, api_hash)
    write_failure: asyncio.Future[None] = asyncio.get_running_loop().create_future()

    @client.on(events.NewMessage(incoming=True))
    async def on_message(event: events.NewMessage.Event) -> None:
        if write_failure.done():
            return
        try:
            append_message(output, event)
        except OSError as error:
            logging.exception("Cannot append to %s; stopping the logger.", output)
            write_failure.set_exception(error)

    try:
        async with client:
            logging.info("Saving new incoming messages to %s. Press Ctrl+C to stop.", output)
            await asyncio.wait(
                [client.disconnected, write_failure],
                return_when=asyncio.FIRST_COMPLETED,
            )
            if write_failure.done():
                write_failure.result()
            await client.disconnected
    finally:
        if not write_failure.done():
            write_failure.cancel()


def main() -> None:
    state_dir = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "TelegramLogger"
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output", type=Path, default=state_dir / "messages.txt",
        help="Text file to append to (default: local TelegramLogger data directory).",
    )
    args = parser.parse_args()
    api_id_text = os.environ.get("TELEGRAM_API_ID", "")
    api_hash = os.environ.get("TELEGRAM_API_HASH", "").strip()
    try:
        api_id = int(api_id_text)
    except ValueError:
        parser.error("Set TELEGRAM_API_ID to the numeric API ID from my.telegram.org.")
    if api_id <= 0:
        parser.error("TELEGRAM_API_ID must be positive.")
    if not api_hash:
        parser.error("Set TELEGRAM_API_HASH to your API hash from my.telegram.org.")

    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    try:
        asyncio.run(log_messages(api_id, api_hash, args.output))
    except KeyboardInterrupt:
        logging.info("Logger stopped.")


if __name__ == "__main__":
    main()
