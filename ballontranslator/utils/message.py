import traceback
from typing import Callable, List, Dict

from . import shared
from .log_context import log_failure
from .logger import logger as LOGGER


def create_error_dialog(
    exception: Exception,
    error_msg: str = None,
    exception_type: str = None,
    *,
    stage: str = '',
    page: str = '',
    module_key: str = '',
    module_name: str = '',
    hint: str = '',
    log_message: str = None,
) -> None:
    '''
        Popup a error dialog in main thread
    Args:
        error_msg: Description text prepend before str(exception)
        exception_type: Specify it to avoid errors dialog of the same type popup repeatedly 
    '''

    # Dialogs may be created later or on another thread, outside the original
    # except block, so format the traceback retained by the exception itself.
    detail_traceback = ''.join(traceback.format_exception(
        type(exception), exception, exception.__traceback__,
    ))
    
    if exception_type is None:
        exception_type = ''

    exception_type_empty = exception_type == ''
    show_dialog = exception_type_empty or exception_type not in shared.showed_exception

    if error_msg is None:
        dialog_msg = str(exception)
    else:
        dialog_msg = str(exception) + '\n' + error_msg

    # Always write structured failure logs; dialog dedup only suppresses popups.
    resolved_hint = hint
    if not resolved_hint and (stage or module_key):
        resolved_hint = 'See logs/ for the full session log file.'
    log_failure(
        LOGGER,
        log_message or error_msg or exception.__class__.__name__,
        exception,
        stage=stage,
        page=page,
        module_key=module_key,
        module_name=module_name,
        hint=resolved_hint,
    )
    if dialog_msg != str(exception):
        LOGGER.error('User message: %s', dialog_msg)

    if show_dialog and not shared.HEADLESS:
        shared.create_errdialog_in_mainthread(dialog_msg, detail_traceback, exception_type)


def create_info_dialog(info_msg, btn_type=None, modal: bool = False, frame_less: bool = False, signal_slot_map_list: List[Dict] = None):
    '''
        Popup a info dialog in main thread
    '''
    LOGGER.info(info_msg)
    if not shared.HEADLESS:
        shared.create_infodialog_in_mainthread({'info_msg': info_msg, 'btn_type': btn_type, 'modal': modal, 'frame_less': frame_less, 'signal_slot_map_list': signal_slot_map_list})


def connect_once(signal, exec_func: Callable):
    '''
    signal.emit will only trigger exec_func once
    '''

    def _disconnect_after_called(*func_args, **func_kwargs):

        def _try_disconnect():
            try:
                signal.disconnect(connect_func)
            except:
                print('Failed to disconnect')
                print(traceback.format_exc())

        try:
            exec_func(*func_args, **func_kwargs)
        except Exception as e:
            _try_disconnect()
            raise e
        _try_disconnect()

    connect_func = _disconnect_after_called
    signal.connect(_disconnect_after_called)
