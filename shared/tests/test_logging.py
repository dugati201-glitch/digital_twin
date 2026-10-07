import contextlib
import io
import logging
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import yaml

from digital_twin_common.logging import configure_logging


class LoggingTests(unittest.TestCase):
    def test_shared_output_filtering_and_reconfiguration(self):
        source = Path(__file__).resolve().parents[2] / 'config/logging.yaml'
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            configure_logging(source)
            configure_logging(source)
            logging.getLogger('camera_service.capture').info('capture started')
            logging.getLogger('gateway.uart').warning('serial disconnected')
            logging.getLogger('camera_service.capture').debug('hidden')
        self.assertEqual(output.getvalue().count('capture started'), 1)
        self.assertIn('gateway.uart', output.getvalue())
        self.assertNotIn('hidden', output.getvalue())

    def test_invalid_logging_configuration(self):
        source = Path(__file__).resolve().parents[2] / 'config/logging.yaml'
        data = yaml.safe_load(source.read_text())
        with TemporaryDirectory() as directory:
            path = Path(directory) / 'logging.yaml'
            for invalid in [{}, {**data, 'disable_existing_loggers': True},
                            {**data, 'root': {'level': 'WRONG', 'handlers': ['console']}}]:
                path.write_text(yaml.safe_dump(invalid))
                with self.assertRaises(ValueError):
                    configure_logging(path)

    def tearDown(self):
        configure_logging(Path(__file__).resolve().parents[2] / 'config/logging.yaml')
