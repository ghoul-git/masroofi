"""Background worker that reads queued receipts.

    python manage.py process_receipts            # run until Ctrl+C
    python manage.py process_receipts --once     # process what is queued, then exit

Run it in a second terminal next to the web server. It loads the OCR model once,
then repeatedly takes the oldest queued receipt, runs OCR and extraction, and
stores the result as extracted or failed. When the queue is empty it checks again
every --sleep seconds. Several workers can run at once: each receipt is claimed
with SELECT ... FOR UPDATE SKIP LOCKED, so no two take the same one.
"""
import signal
import time

from django.core.management.base import BaseCommand

from expenses.services import receipt_service


def _stop(signum, frame):
    raise KeyboardInterrupt


class Command(BaseCommand):
    help = "Read queued receipts with OCR and OpenAI in the background."

    def add_arguments(self, parser):
        parser.add_argument("--once", action="store_true", help="Process the queued receipts, then exit.")
        parser.add_argument("--sleep", type=float, default=2.0, help="Seconds between checks when idle (default 2).")

    def handle(self, *args, once, sleep, **options):
        # A stop from the host (SIGTERM) is handled like Ctrl+C.
        previous_handler = signal.signal(signal.SIGTERM, _stop)
        try:
            self._run(once, sleep)
        finally:
            signal.signal(signal.SIGTERM, previous_handler)

    def _run(self, once, sleep):
        requeued = receipt_service.requeue_stuck_receipts()
        if requeued:
            self.stdout.write(f"Queued {requeued} receipt(s) again that were stuck in processing.")

        current = None
        processed = 0
        try:
            self.stdout.write("Loading the OCR model...")
            started = time.perf_counter()
            from expenses.ai import ocr  # EasyOCR and PyTorch are only ever imported by this worker
            ocr.get_reader()
            self.stdout.write(f"OCR model loaded in {time.perf_counter() - started:.1f} s. Waiting for receipts.")

            while True:
                current = receipt_service.claim_next_receipt()
                if current is None:
                    if once:
                        break
                    time.sleep(sleep)
                    continue
                started = time.perf_counter()
                result = receipt_service.process_claimed_receipt(current)
                self.stdout.write(f"Receipt {current.pk}: {result} in {time.perf_counter() - started:.1f} s")
                current = None
                processed += 1
        except KeyboardInterrupt:
            if current is not None:
                receipt_service.requeue_receipt(current.pk)
                self.stdout.write(f"Receipt {current.pk} was put back in the queue.")
            self.stdout.write(f"Stopped after {processed} receipt(s).")
            return

        self.stdout.write(self.style.SUCCESS(f"Done: {processed} receipt(s) processed."))
