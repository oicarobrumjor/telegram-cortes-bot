import asyncio
import base64
import json
import logging
import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any, Dict, Optional

import google.generativeai as genai
from telegram import Update
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes
from yt_dlp import YoutubeDL
from yt_dlp.utils import DownloadError


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data" / "chats"
STATE_FILE_NAME = "state.json"
COOKIES_FILE_NAME = "cookies.txt"
MAX_CUT_SECONDS = 20 * 60
TELEGRAM_MESSAGE_LIMIT = 4000
TELEGRAM_VIDEO_LIMIT_BYTES = 49 * 1024 * 1024
PREVIEW_WIDTH = 640
PREVIEW_HEIGHT = 360
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-1.5-flash")


logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)
logger = logging.getLogger("telegram-cortes-bot")


def get_chat_dir(chat_id: int) -> Path:
    chat_dir = DATA_DIR / str(chat_id)
    chat_dir.mkdir(parents=True, exist_ok=True)
    return chat_dir


def get_state_path(chat_id: int) -> Path:
    return get_chat_dir(chat_id) / STATE_FILE_NAME


def get_cookies_path(chat_id: int) -> Path:
    return get_chat_dir(chat_id) / COOKIES_FILE_NAME


def load_state(chat_id: int) -> Dict[str, Any]:
    state_path = get_state_path(chat_id)
    if not state_path.exists():
        return {}

    try:
        return json.loads(state_path.read_text(encoding="utf-8"))
    except Exception:
        logger.exception("Falha ao ler estado do chat %s", chat_id)
        return {}


def save_state(chat_id: int, state: Dict[str, Any]) -> None:
    state_path = get_state_path(chat_id)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def delete_path(path_str: Optional[str]) -> None:
    if not path_str:
        return

    path = Path(path_str)
    if path.exists():
        path.unlink()


def ensure_youtube_cookies(chat_id: int) -> Optional[Path]:
    encoded_cookies = os.getenv("YOUTUBE_COOKIES_BASE64", "").strip()
    raw_cookies = os.getenv("YOUTUBE_COOKIES", "").strip()

    content: Optional[str] = None
    if encoded_cookies:
        try:
            content = base64.b64decode(encoded_cookies).decode("utf-8")
        except Exception as exc:
            logger.exception("Falha ao decodificar YOUTUBE_COOKIES_BASE64")
            raise RuntimeError("A variavel YOUTUBE_COOKIES_BASE64 esta invalida.") from exc
    elif raw_cookies:
        content = raw_cookies

    if not content:
        return None

    cookies_path = get_cookies_path(chat_id)
    cookies_path.write_text(content, encoding="utf-8")
    return cookies_path


def clear_chat_storage(chat_id: int, keep_directory: bool = True) -> None:
    chat_dir = get_chat_dir(chat_id)
    if chat_dir.exists():
        shutil.rmtree(chat_dir, ignore_errors=True)
    if keep_directory:
        chat_dir.mkdir(parents=True, exist_ok=True)


def clear_previous_media(chat_id: int) -> None:
    state = load_state(chat_id)
    delete_path(state.get("video_path"))
    delete_path(state.get("subtitle_path"))

    chat_dir = get_chat_dir(chat_id)
    for item in chat_dir.iterdir():
        if item.name == STATE_FILE_NAME:
            continue
        if item.is_file():
            item.unlink(missing_ok=True)
        elif item.is_dir():
            shutil.rmtree(item, ignore_errors=True)

    save_state(chat_id, {})


def parse_time_to_seconds(value: str) -> int:
    parts = value.strip().split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("Use mm:ss ou hh:mm:ss.")
    if not all(part.isdigit() for part in parts):
        raise ValueError("Tempo deve conter apenas numeros separados por ':'.")

    numbers = [int(part) for part in parts]
    if len(numbers) == 2:
        minutes, seconds = numbers
        hours = 0
    else:
        hours, minutes, seconds = numbers

    if minutes >= 60 or seconds >= 60:
        raise ValueError("Minutos e segundos devem ser menores que 60.")

    return hours * 3600 + minutes * 60 + seconds


def normalize_time_label(value: str) -> str:
    parse_time_to_seconds(value)
    return value.strip()


def find_first_existing_file(chat_dir: Path, patterns: list[str]) -> Optional[Path]:
    for pattern in patterns:
        files = sorted(chat_dir.glob(pattern))
        if files:
            return files[0]
    return None


def download_video_for_chat(chat_id: int, url: str) -> Dict[str, Any]:
    chat_dir = get_chat_dir(chat_id)
    clear_previous_media(chat_id)
    cookies_path = ensure_youtube_cookies(chat_id)

    output_template = str(chat_dir / "source.%(ext)s")
    logger.info("Baixando video para chat %s: %s", chat_id, url)

    ydl_opts = {
        "outtmpl": output_template,
        "format": "bv*+ba/b",
        "merge_output_format": "mp4",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "extractor_args": {
            "youtube": {
                "player_client": ["android", "web"],
            }
        },
    }
    if cookies_path:
        ydl_opts["cookiefile"] = str(cookies_path)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
    except DownloadError as exc:
        error_text = str(exc).strip()
        logger.warning("Erro ao baixar video do chat %s: %s", chat_id, error_text)
        if "Sign in to confirm" in error_text or "bot" in error_text.lower():
            raise RuntimeError(
                "O YouTube bloqueou este download no momento.\n\n"
                f"Detalhe: {error_text[:700]}\n\n"
                "Tente outro video publico ou atualize o yt-dlp."
            ) from exc
        raise RuntimeError(
            "Nao foi possivel baixar o video.\n\n"
            f"Detalhe: {error_text[:700]}"
        ) from exc
    except Exception as exc:
        logger.exception("Falha inesperada no download do chat %s", chat_id)
        raise RuntimeError("Ocorreu um erro inesperado ao baixar o video.") from exc

    video_path = find_first_existing_file(
        chat_dir,
        ["source.mp4", "source.mkv", "source.webm", "source.*"],
    )
    if not video_path or not video_path.exists():
        raise RuntimeError("Download concluido, mas o arquivo de video nao foi encontrado.")

    state = {
        "source_url": url,
        "title": info.get("title") or "Video sem titulo",
        "video_path": str(video_path),
        "subtitle_path": None,
    }
    save_state(chat_id, state)
    logger.info("Video salvo no chat %s: %s", chat_id, video_path)
    return state


def run_ffmpeg_cut(
    input_path: Path,
    output_path: Path,
    start_seconds: int,
    end_seconds: int,
    preview: bool = False,
) -> None:
    duration = end_seconds - start_seconds
    command = [
        "ffmpeg",
        "-y",
        "-nostdin",
        "-i",
        str(input_path),
        "-ss",
        str(start_seconds),
        "-t",
        str(duration),
        "-avoid_negative_ts",
        "make_zero",
        "-c:v",
        "libx264",
    ]

    if preview:
        preview_filter = (
            f"scale=w={PREVIEW_WIDTH}:h={PREVIEW_HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={PREVIEW_WIDTH}:{PREVIEW_HEIGHT}:(ow-iw)/2:(oh-ih)/2:color=black"
        )
        command.extend(
            [
                "-vf",
                preview_filter,
                "-preset",
                "veryfast",
                "-crf",
                "30",
                "-c:a",
                "aac",
                "-b:a",
                "96k",
            ]
        )
    else:
        command.extend(
            [
                "-preset",
                "slow",
                "-crf",
                "18",
                "-c:a",
                "aac",
                "-b:a",
                "192k",
            ]
        )

    command.extend(
        [
            "-movflags",
            "+faststart",
            str(output_path),
        ]
    )

    logger.info("Executando ffmpeg: %s", " ".join(command))
    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            text=True,
            check=True,
        )
        if completed.stderr:
            logger.info("ffmpeg stderr: %s", completed.stderr.strip())
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg nao esta instalado ou nao foi encontrado no PATH.") from exc
    except subprocess.CalledProcessError as exc:
        logger.error("Erro no ffmpeg: %s", exc.stderr.strip())
        raise RuntimeError("Falha ao gerar o corte com ffmpeg.") from exc

    if not output_path.exists() or output_path.stat().st_size == 0:
        raise RuntimeError("O ffmpeg terminou, mas o arquivo do corte nao foi gerado corretamente.")


def sanitize_filename(value: str) -> str:
    sanitized = re.sub(r'[<>:"/\\|?*]+', "", value).strip()
    sanitized = re.sub(r"\s+", "_", sanitized)
    return sanitized[:80] or "corte"


def download_subtitle_for_chat(chat_id: int, url: str) -> Path:
    chat_dir = get_chat_dir(chat_id)
    state = load_state(chat_id)
    cookies_path = ensure_youtube_cookies(chat_id)
    delete_path(state.get("subtitle_path"))

    for old_file in chat_dir.glob("subtitle*"):
        if old_file.is_file():
            old_file.unlink(missing_ok=True)

    output_template = str(chat_dir / "subtitle.%(ext)s")
    logger.info("Baixando legenda automatica para chat %s", chat_id)

    ydl_opts = {
        "outtmpl": output_template,
        "skip_download": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["pt-BR", "pt"],
        "subtitlesformat": "srt/best",
        "convertsubtitles": "srt",
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
    }
    if cookies_path:
        ydl_opts["cookiefile"] = str(cookies_path)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            ydl.extract_info(url, download=True)
    except DownloadError as exc:
        logger.warning("Erro ao baixar legenda do chat %s: %s", chat_id, exc)
        raise RuntimeError("Nao foi possivel baixar a legenda automatica em portugues.") from exc
    except Exception as exc:
        logger.exception("Falha inesperada ao baixar legenda do chat %s", chat_id)
        raise RuntimeError("Ocorreu um erro inesperado ao baixar a legenda.") from exc

    subtitle_path = find_first_existing_file(chat_dir, ["subtitle*.srt"])
    if subtitle_path:
        state["subtitle_path"] = str(subtitle_path)
        save_state(chat_id, state)
        return subtitle_path

    fallback = find_first_existing_file(chat_dir, ["subtitle*.*"])
    if not fallback:
        raise RuntimeError("Nenhuma legenda em portugues foi encontrada para este video.")

    converted = chat_dir / "subtitle.srt"
    convert_subtitle_to_srt(fallback, converted)
    state["subtitle_path"] = str(converted)
    save_state(chat_id, state)
    return converted


def convert_subtitle_to_srt(source_path: Path, target_path: Path) -> None:
    if source_path.suffix.lower() == ".srt":
        shutil.copyfile(source_path, target_path)
        return

    command = ["ffmpeg", "-y", "-i", str(source_path), str(target_path)]
    try:
        subprocess.run(command, capture_output=True, text=True, check=True)
    except FileNotFoundError as exc:
        raise RuntimeError("ffmpeg nao esta instalado ou nao foi encontrado no PATH.") from exc
    except subprocess.CalledProcessError as exc:
        logger.error("Falha ao converter legenda: %s", exc.stderr.strip())
        raise RuntimeError("Nao foi possivel converter a legenda para SRT.") from exc


def strip_srt_to_text(srt_content: str) -> str:
    cleaned_lines = []
    for raw_line in srt_content.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.isdigit():
            continue
        if "-->" in line:
            continue
        cleaned_lines.append(line)
    return "\n".join(cleaned_lines).strip()


async def send_long_message(update: Update, text: str) -> None:
    if not update.message:
        return

    chunks = []
    remaining = text
    while remaining:
        if len(remaining) <= TELEGRAM_MESSAGE_LIMIT:
            chunks.append(remaining)
            break
        split_at = remaining.rfind("\n", 0, TELEGRAM_MESSAGE_LIMIT)
        if split_at <= 0:
            split_at = TELEGRAM_MESSAGE_LIMIT
        chunks.append(remaining[:split_at])
        remaining = remaining[split_at:].lstrip()

    for chunk in chunks:
        await update.message.reply_text(chunk)


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    text = (
        "Bot pronto para cortes de videos do YouTube.\n\n"
        "Comandos:\n"
        "/video LINK\n"
        "/corte NOME | INICIO FIM\n"
        "/aut\n"
        "/legenda\n"
        "/maquina\n"
        "/limpar"
    )
    await update.message.reply_text(text)


async def video_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return
    if not context.args:
        await update.message.reply_text("Uso: /video LINK")
        return

    url = context.args[0].strip()
    chat_id = update.effective_chat.id

    await update.message.reply_text("Baixando o video. Isso pode levar alguns instantes.")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)

    try:
        state = await asyncio.to_thread(download_video_for_chat, chat_id, url)
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text(f"Video atual salvo com sucesso:\n{state['title']}")


async def corte_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    raw_text = update.message.text or ""
    _, _, payload = raw_text.partition(" ")
    payload = payload.strip()
    if "|" not in payload:
        await update.message.reply_text("Uso: /corte NOME | INICIO FIM")
        return

    name_part, _, time_part = payload.partition("|")
    clip_name = name_part.strip()
    time_tokens = time_part.strip().split()
    if not clip_name or len(time_tokens) != 2:
        await update.message.reply_text("Uso: /corte NOME | INICIO FIM")
        return

    start_label, end_label = time_tokens
    try:
        start_seconds = parse_time_to_seconds(start_label)
        end_seconds = parse_time_to_seconds(end_label)
    except ValueError as exc:
        await update.message.reply_text(str(exc))
        return

    if end_seconds <= start_seconds:
        await update.message.reply_text("O horario final precisa ser maior que o inicial.")
        return
    if end_seconds - start_seconds > MAX_CUT_SECONDS:
        await update.message.reply_text("O corte pode ter no maximo 20 minutos.")
        return

    chat_id = update.effective_chat.id
    state = load_state(chat_id)
    video_path = state.get("video_path")
    if not video_path or not Path(video_path).exists():
        await update.message.reply_text("Nenhum video atual foi encontrado. Use /video primeiro.")
        return

    safe_name = sanitize_filename(clip_name)
    output_path = get_chat_dir(chat_id) / f"{safe_name}.mp4"
    preview_path = get_chat_dir(chat_id) / f"{safe_name}_preview.mp4"
    for path in (output_path, preview_path):
        if path.exists():
            path.unlink(missing_ok=True)

    await update.message.reply_text("Gerando o corte em alta qualidade e uma previa para conferencia.")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_VIDEO)

    try:
        await asyncio.to_thread(
            run_ffmpeg_cut,
            Path(video_path),
            output_path,
            start_seconds,
            end_seconds,
            False,
        )
        await asyncio.to_thread(
            run_ffmpeg_cut,
            Path(video_path),
            preview_path,
            start_seconds,
            end_seconds,
            True,
        )
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return

    if not output_path.exists() or not preview_path.exists():
        await update.message.reply_text("Os arquivos do corte nao foram encontrados apos o processamento.")
        return

    caption = (
        f"\U0001F3AC Corte: {clip_name}\n"
        f"\u23F1\uFE0F Trecho: {normalize_time_label(start_label)} \u2192 {normalize_time_label(end_label)}"
    )

    file_size = output_path.stat().st_size
    preview_size = preview_path.stat().st_size
    logger.info("Corte HQ gerado para chat %s: %s bytes", chat_id, file_size)
    logger.info("Previa do corte gerada para chat %s: %s bytes", chat_id, preview_size)

    try:
        with preview_path.open("rb") as preview_file:
            await update.message.reply_video(
                video=preview_file,
                caption=f"{caption}\n\nPrevia compactada para revisao rapida.",
                supports_streaming=True,
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
                pool_timeout=30,
            )
    except Exception:
        logger.exception("Falha ao enviar previa do corte do chat %s", chat_id)
        await update.message.reply_text("A previa do corte falhou, mas vou enviar o arquivo final em seguida.")

    try:
        with output_path.open("rb") as video_file:
            await update.message.reply_document(
                document=video_file,
                filename=output_path.name,
                caption=f"{caption}\n\nArquivo final em melhor qualidade.",
                read_timeout=120,
                write_timeout=120,
                connect_timeout=30,
                pool_timeout=30,
            )
    except Exception:
        logger.exception("Falha ao enviar corte do chat %s", chat_id)
        await update.message.reply_text(
            "O corte foi gerado, mas houve falha ao enviar o arquivo no Telegram. "
            "Tente um trecho menor."
        )


async def limpar_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = update.effective_chat.id
    await asyncio.to_thread(clear_chat_storage, chat_id)
    await update.message.reply_text("Video, legenda e estado do chat foram removidos.")


async def aut_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = update.effective_chat.id
    state = load_state(chat_id)
    source_url = state.get("source_url")
    if not source_url:
        await update.message.reply_text("Nenhum video atual foi encontrado. Use /video primeiro.")
        return

    await update.message.reply_text("Baixando a legenda automatica em portugues.")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    try:
        subtitle_path = await asyncio.to_thread(download_subtitle_for_chat, chat_id, source_url)
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return

    await update.message.reply_text(f"Legenda atual salva com sucesso:\n{subtitle_path.name}")


async def legenda_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = update.effective_chat.id
    state = load_state(chat_id)
    subtitle_path = state.get("subtitle_path")
    if not subtitle_path or not Path(subtitle_path).exists():
        await update.message.reply_text("Nenhuma legenda atual foi encontrada. Use /aut primeiro.")
        return

    with Path(subtitle_path).open("rb") as subtitle_file:
        await update.message.reply_document(document=subtitle_file, filename=Path(subtitle_path).name)


def ask_gemini_with_transcript(transcript: str) -> str:
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY nao configurada. Defina a variavel de ambiente para usar /maquina.")

    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(GEMINI_MODEL)
    prompt = (
        "Voce esta analisando a transcricao de um video para criar cortes curtos.\n"
        "Leia a transcricao abaixo e responda em portugues com:\n"
        "1. Um resumo rapido do conteudo.\n"
        "2. De 3 a 5 sugestoes de cortes com titulo e motivo.\n"
        "3. Principais frases ou trechos que parecem mais fortes.\n\n"
        "TRANSCRICAO:\n"
        f"{transcript}"
    )

    try:
        response = model.generate_content(prompt)
    except Exception as exc:
        logger.exception("Erro ao consultar Gemini")
        raise RuntimeError("Falha ao consultar o Gemini. Verifique a chave, o modelo e tente novamente.") from exc

    text = getattr(response, "text", None)
    if text:
        return text

    candidates = getattr(response, "candidates", None) or []
    parts = []
    for candidate in candidates:
        content = getattr(candidate, "content", None)
        if not content:
            continue
        for part in getattr(content, "parts", []) or []:
            part_text = getattr(part, "text", None)
            if part_text:
                parts.append(part_text)

    if not parts:
        raise RuntimeError("O Gemini nao retornou texto utilizavel para esta transcricao.")
    return "\n".join(parts)


async def maquina_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message:
        return

    chat_id = update.effective_chat.id
    state = load_state(chat_id)
    subtitle_path = state.get("subtitle_path")
    if not subtitle_path or not Path(subtitle_path).exists():
        await update.message.reply_text("Nenhuma legenda atual foi encontrada. Use /aut primeiro.")
        return

    try:
        transcript = strip_srt_to_text(Path(subtitle_path).read_text(encoding="utf-8", errors="ignore"))
    except Exception:
        logger.exception("Falha ao ler SRT do chat %s", chat_id)
        await update.message.reply_text("Nao foi possivel ler a legenda atual.")
        return

    if not transcript:
        await update.message.reply_text("A legenda atual nao possui texto utilizavel.")
        return

    await update.message.reply_text("Enviando a transcricao para o Gemini.")
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        result = await asyncio.to_thread(ask_gemini_with_transcript, transcript)
    except RuntimeError as exc:
        await update.message.reply_text(str(exc))
        return

    await send_long_message(update, result)


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.exception("Erro nao tratado", exc_info=context.error)
    if isinstance(update, Update) and update.message:
        await update.message.reply_text("Ocorreu um erro interno. Tente novamente em instantes.")


def build_application() -> Application:
    token = os.getenv("TELEGRAM_BOT_TOKEN")
    if not token:
        raise RuntimeError("Defina TELEGRAM_BOT_TOKEN antes de iniciar o bot.")

    if shutil.which("ffmpeg") is None:
        logger.warning("ffmpeg nao encontrado no PATH. /corte e conversao de legenda podem falhar.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    application = Application.builder().token(token).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("video", video_command))
    application.add_handler(CommandHandler("corte", corte_command))
    application.add_handler(CommandHandler("limpar", limpar_command))
    application.add_handler(CommandHandler("aut", aut_command))
    application.add_handler(CommandHandler("legenda", legenda_command))
    application.add_handler(CommandHandler("maquina", maquina_command))
    application.add_error_handler(error_handler)
    return application


def main() -> None:
    logger.info("Iniciando bot Telegram de cortes")
    application = build_application()
    application.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    main()
