"""Celery notification consumer and PostgreSQL-backed recovery loop."""

import argparse
import logging
import signal
import time
import uuid

import httpx
from celery import Celery  # type: ignore[import-untyped]

from eventflow.config import get_settings
from eventflow.delivery import (
    claim_delivery,
    dispatch_outbox,
    finish_delivery,
    make_sync_engine,
    reconcile_deliveries,
)
from eventflow.webhook import UnsafeDestination, send_webhook

logger = logging.getLogger(__name__)
celery_app = Celery("eventflow", broker=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_acks_on_failure_or_timeout=True,
    task_reject_on_worker_lost=False,
    worker_prefetch_multiplier=1,
    broker_transport_options={"visibility_timeout": 300},
    task_time_limit=30,
    task_soft_time_limit=25,
    task_ignore_result=True,
)


class DeliveryDeadline(Exception):
    pass


def deadline_reached(_signum: int, _frame: object) -> None:
    raise DeliveryDeadline()


@celery_app.task(name="eventflow.deliver")  # type: ignore[untyped-decorator]
def deliver(delivery_id: str) -> None:
    engine = make_sync_engine()
    try:
        claim = claim_delivery(engine, uuid.UUID(delivery_id))
        if claim is None:
            return
        old_handler = signal.signal(signal.SIGALRM, deadline_reached)
        signal.setitimer(signal.ITIMER_REAL, 20)
        response_status: int | None = None
        retry_after: str | None = None
        error: str | None = None
        try:
            result = send_webhook(claim)
            response_status, retry_after = result.status_code, result.retry_after
        except UnsafeDestination:
            error = "unsafe_destination"
        except (OSError, httpx.HTTPError):
            error = "transport_error"
        except DeliveryDeadline:
            error = "deadline"
        finally:
            signal.setitimer(signal.ITIMER_REAL, 0)
            signal.signal(signal.SIGALRM, old_handler)
        finish_delivery(engine, claim, response_status, error, retry_after)
        logger.info(
            "delivery_attempt_completed organization_id=%s delivery_id=%s attempt_id=%s status=%s",
            claim.organization_id,
            claim.delivery_id,
            claim.attempt_id,
            response_status if response_status is not None else error,
        )
    finally:
        engine.dispose()


def publish(delivery_id: uuid.UUID) -> None:
    deliver.delay(str(delivery_id))


def run_dispatcher(once: bool = False) -> None:
    engine = make_sync_engine()
    try:
        while True:
            try:
                dispatch_outbox(engine, publish)
                reconcile_deliveries(engine, publish)
            except Exception:
                logger.error("dispatcher_cycle_failed")
                if once:
                    raise
            if once:
                return
            time.sleep(10)
    finally:
        engine.dispose()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO)
    run_dispatcher(once=args.once)


if __name__ == "__main__":
    main()
