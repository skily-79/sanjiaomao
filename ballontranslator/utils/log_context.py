"""Structured logging helpers for user-visible diagnostics.

>>> format_log_context(stage='detect', page='0001.png')
'stage=detect page=0001.png'
>>> failure_message_for_page('Translation Failed.', '0002.png')
'Translation Failed.\\nPage: 0002.png'
>>> format_stage_timings({'read': 0.01, 'detect': 1.2, 'translate': 'queued'})
'read=0.01s, detect=1.20s, translate=queued'
"""

from __future__ import annotations

import logging
import traceback
from typing import Any, Dict, Mapping, Optional, Union


StageTimes = Mapping[str, Union[float, str, int]]


def format_log_context(
    *,
    stage: str = '',
    page: str = '',
    module_key: str = '',
    module_name: str = '',
    event: str = '',
) -> str:
    """Build a compact key=value context string for log lines.

    >>> format_log_context(event='PIPELINE_START', stage='detect')
    'event=PIPELINE_START stage=detect'
    >>> format_log_context(page='0003.png', module_key='ocr', module_name='mit48px')
    'page=0003.png module=ocr/mit48px'
    """

    parts = []
    if event:
        parts.append(f'event={event}')
    if stage:
        parts.append(f'stage={stage}')
    if page:
        parts.append(f'page={page}')
    if module_key:
        if module_name:
            parts.append(f'module={module_key}/{module_name}')
        else:
            parts.append(f'module={module_key}')
    return ' '.join(parts)


def format_stage_timings(stage_times: StageTimes) -> str:
    """Format per-page pipeline stage timings for logs.

    >>> format_stage_timings({'read': 0.0123, 'detect': 0.5, 'translate': 'queued'})
    'read=0.01s, detect=0.50s, translate=queued'
    """

    chunks = []
    for name, value in stage_times.items():
        if isinstance(value, float):
            chunks.append(f'{name}={value:.2f}s')
        else:
            chunks.append(f'{name}={value}')
    return ', '.join(chunks)


def failure_message_for_page(title: str, page_key: str, page_label: str = 'Page') -> str:
    """Build a dialog-safe page failure summary.

    >>> failure_message_for_page('OCR Failed.', '0004.png', 'Page')
    'OCR Failed.\\nPage: 0004.png'
    """

    if page_key:
        return f'{title}\n{page_label}: {page_key}'
    return title


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    *,
    stage: str = '',
    page: str = '',
    module_key: str = '',
    module_name: str = '',
    stacklevel: int = 2,
) -> None:
    """Emit one structured log line with optional pipeline context."""

    context = format_log_context(
        stage=stage,
        page=page,
        module_key=module_key,
        module_name=module_name,
    )
    if context:
        logger.log(level, f'[{event}] {context} | {message}', stacklevel=stacklevel)
    else:
        logger.log(level, f'[{event}] {message}', stacklevel=stacklevel)


def log_failure(
    logger: logging.Logger,
    message: str,
    error: BaseException,
    *,
    stage: str = '',
    page: str = '',
    module_key: str = '',
    module_name: str = '',
    hint: str = '',
) -> None:
    """Log a concise failure summary plus traceback when available.

    >>> import logging
    >>> from io import StringIO
    >>> stream = StringIO()
    >>> test_logger = logging.getLogger('log_context.doctest')
    >>> test_logger.handlers.clear()
    >>> test_logger.addHandler(logging.StreamHandler(stream))
    >>> test_logger.setLevel(logging.ERROR)
    >>> log_failure(test_logger, 'detect failed', RuntimeError('boom'), stage='detect', page='0001.png', hint='retry Run')
    >>> 'stage=detect' in stream.getvalue()
    True
    """

    summary = str(error).strip() or error.__class__.__name__
    parts = [message, summary]
    if hint:
        parts.append(f'Hint: {hint}')
    log_event(
        logger,
        logging.ERROR,
        'FAILURE',
        ' | '.join(parts),
        stage=stage,
        page=page,
        module_key=module_key,
        module_name=module_name,
        stacklevel=3,
    )
    detail = ''.join(
        traceback.format_exception(type(error), error, error.__traceback__)
    ).strip()
    if detail:
        logger.error(
            'Traceback (%s):\n%s',
            error.__class__.__name__,
            detail,
            stacklevel=2,
        )


def module_failure_hint(module_key: str) -> str:
    """Return a short user-facing hint for common module setup failures."""

    hints = {
        'textdetector': 'Check Settings > Text Detector and ensure model files finished downloading.',
        'ocr': 'Check Settings > OCR and ensure model files finished downloading.',
        'inpainter': 'Check Settings > Inpainter and ensure model files finished downloading.',
        'translator': 'Check Settings > Translator, network access, and required API keys.',
    }
    return hints.get(module_key, 'Check module settings and the latest log file under logs/.')


def download_failure_hint(save_path: str) -> str:
    """Return a short hint after a model download failure."""

    return (
        f'Save the file manually to {save_path}, or retry Run after checking network/proxy access.'
    )


def pipeline_stage_list(enabled_detect: bool, enabled_ocr: bool, enabled_translate: bool, enabled_inpaint: bool) -> str:
    """Return enabled pipeline stages as a comma-separated label.

    >>> pipeline_stage_list(True, True, False, True)
    'detect, ocr, inpaint'
    """

    stages = []
    if enabled_detect:
        stages.append('detect')
    if enabled_ocr:
        stages.append('ocr')
    if enabled_translate:
        stages.append('translate')
    if enabled_inpaint:
        stages.append('inpaint')
    return ', '.join(stages) or 'none'


def summarize_pipeline_modules(
    textdetector: str = '',
    ocr: str = '',
    translator: str = '',
    inpainter: str = '',
) -> str:
    """Summarize selected module keys for pipeline start logs."""

    parts = []
    if textdetector:
        parts.append(f'detect={textdetector}')
    if ocr:
        parts.append(f'ocr={ocr}')
    if translator:
        parts.append(f'translate={translator}')
    if inpainter:
        parts.append(f'inpaint={inpainter}')
    return ', '.join(parts)
