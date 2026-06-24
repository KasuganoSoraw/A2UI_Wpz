from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler
from pathlib import Path


LOG_DIR_NAME = 'logs'
LOG_FILE_NAME = 'chat_ui_builder.log'
_CONFIGURED_FLAG = '_chat_ui_builder_configured'


class ColoredCategoryFormatter(logging.Formatter):
  RESET = '\033[0m'
  BOLD = '\033[1m'
  COLORS = {
      'streaming_frame': '\033[96m',
      'parsed_delta': '\033[94m',
      'emitting_frame': '\033[92m',
      'compiling_delta': '\033[95m',
      'warning': '\033[93m',
      'error': '\033[91m',
      'default': '',
  }

  def __init__(self, fmt: str, datefmt: str | None = None) -> None:
    super().__init__(fmt=fmt, datefmt=datefmt)
    self.enable_color = self._supports_color()

  def _supports_color(self) -> bool:
    if os.getenv('NO_COLOR'):
      return False
    return hasattr(os.sys.stderr, 'isatty') and os.sys.stderr.isatty()

  def _color_for_record(self, record: logging.LogRecord, message: str) -> str:
    if record.levelno >= logging.ERROR:
      return self.COLORS['error']
    if record.levelno >= logging.WARNING:
      return self.COLORS['warning']
    if 'Streaming frame body=' in message:
      return self.COLORS['streaming_frame']
    if 'Parsed planning delta=' in message:
      return self.COLORS['parsed_delta']
    if 'Emitting planning A2UI frame=' in message:
      return self.COLORS['emitting_frame']
    if 'Compiling delta type=' in message:
      return self.COLORS['compiling_delta']
    return self.COLORS['default']

  def format(self, record: logging.LogRecord) -> str:
    rendered = super().format(record)
    if not self.enable_color:
      return rendered
    color = self._color_for_record(record, record.getMessage())
    if not color:
      return rendered
    if record.levelno >= logging.WARNING:
      return f'{self.BOLD}{color}{rendered}{self.RESET}'
    return f'{color}{rendered}{self.RESET}'


class PlainFileFormatter(logging.Formatter):
  def format(self, record: logging.LogRecord) -> str:
    full_message = getattr(record, 'full_message', None)
    if full_message is None:
      return super().format(record)

    copied = logging.makeLogRecord(record.__dict__.copy())
    copied.msg = full_message
    copied.args = ()
    return super().format(copied)


def ensure_log_dir(base_dir: Path) -> Path:
  log_dir = base_dir / LOG_DIR_NAME
  log_dir.mkdir(parents=True, exist_ok=True)
  return log_dir


def build_console_handler(log_level: int) -> logging.Handler:
  console = logging.StreamHandler()
  console.setLevel(log_level)
  console.setFormatter(
      ColoredCategoryFormatter(
          fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
          datefmt='%Y-%m-%d %H:%M:%S',
      )
  )
  return console


def build_file_handler(log_path: Path, log_level: int) -> logging.Handler:
  file_handler = RotatingFileHandler(
      log_path,
      maxBytes=2 * 1024 * 1024,
      backupCount=3,
      encoding='utf-8',
  )
  file_handler.setLevel(log_level)
  file_handler.setFormatter(
      PlainFileFormatter(
          fmt='%(asctime)s %(levelname)s %(name)s %(message)s',
          datefmt='%Y-%m-%d %H:%M:%S',
      )
  )
  return file_handler


def configure_logging(log_level: int) -> None:
  root_logger = logging.getLogger()
  if getattr(root_logger, _CONFIGURED_FLAG, False):
    return

  base_dir = Path(__file__).resolve().parents[3]
  log_dir = ensure_log_dir(base_dir)
  log_path = log_dir / LOG_FILE_NAME

  root_logger.setLevel(log_level)
  root_logger.handlers.clear()
  root_logger.addHandler(build_console_handler(log_level))
  root_logger.addHandler(build_file_handler(log_path, log_level))
  setattr(root_logger, _CONFIGURED_FLAG, True)
