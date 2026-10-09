"""Runtime codec tuning for the Raspberry Pi camera service."""

import logging
import multiprocessing

from aiortc.codecs import vpx

log = logging.getLogger(__name__)


def configure_vp8_threads(requested_threads):
    """Override aiortc's conservative one-thread choice at VGA resolution.

    aiortc 1.15 selects one libvpx thread at 640x480. The library does not
    expose this choice through its public API, so keep the small compatibility
    shim here and cover the resulting encoder setting with a test.
    """
    available_cpus = multiprocessing.cpu_count()
    thread_count = min(requested_threads, available_cpus)

    def configured_thread_count(pixels, cpus):
        del pixels
        return min(thread_count, cpus)

    vpx.number_of_threads = configured_thread_count
    log.info(
        "VP8 encoder configured for %s thread(s) per peer; %s CPU(s) available",
        thread_count,
        available_cpus,
    )
    return thread_count
