import doctest
import unittest
from unittest import mock

from ballontranslator.utils import log_context
from ballontranslator.utils import shared
from ballontranslator.utils.message import create_error_dialog


class LogContextTests(unittest.TestCase):
    def test_doctests(self):
        failures, tests = doctest.testmod(log_context, verbose=False)
        self.assertEqual(failures, 0)
        self.assertGreater(tests, 0)

    def test_log_event_uses_caller_stacklevel(self):
        test_logger = mock.Mock()
        log_context.log_event(
            test_logger,
            20,
            'TEST_EVENT',
            'hello',
            stage='pipeline',
        )
        test_logger.log.assert_called_once()
        self.assertEqual(test_logger.log.call_args.kwargs.get('stacklevel'), 2)

    def test_create_error_dialog_logs_when_dialog_is_deduped(self):
        shared.showed_exception.add('DedupTest')
        try:
            with mock.patch('ballontranslator.utils.message.log_failure') as log_failure, mock.patch.object(
                shared,
                'create_errdialog_in_mainthread',
            ) as show_error:
                create_error_dialog(RuntimeError('boom'), 'failed', 'DedupTest')

            log_failure.assert_called_once()
            show_error.assert_not_called()
        finally:
            shared.showed_exception.discard('DedupTest')

    def test_create_error_dialog_omits_default_hint_without_context(self):
        with mock.patch('ballontranslator.utils.message.log_failure') as log_failure:
            create_error_dialog(RuntimeError('boom'), 'failed', 'HintTest')

        self.assertEqual(log_failure.call_args.kwargs.get('hint'), '')

    def test_create_error_dialog_adds_default_hint_with_stage(self):
        with mock.patch('ballontranslator.utils.message.log_failure') as log_failure:
            create_error_dialog(
                RuntimeError('boom'),
                'failed',
                'HintTest',
                stage='pipeline',
            )

        self.assertEqual(
            log_failure.call_args.kwargs.get('hint'),
            'See logs/ for the full session log file.',
        )


if __name__ == '__main__':
    unittest.main()
