"""
Observability Service — Structured logging, Prometheus metrics, and Sentry integration.
"""

from services.observability import (
    setup_logging,
    get_logger,
    JSONFormatter,
    # Metrics
    http_requests_total,
    http_request_duration_seconds,
    director_runs_total,
    director_run_duration_seconds,
    visual_generations_total,
    visual_generation_duration_seconds,
    training_jobs_total,
    training_job_duration_seconds,
    active_connections,
    queue_depth,
    cache_hits_total,
    cache_misses_total,
    errors_total,
    # Metrics recording
    record_http_request,
    record_visual_generation,
    record_training_job,
    # Middleware
    PrometheusMiddleware,
    metrics_endpoint,
    # Sentry
    init_sentry,
    capture_exception,
    # Request tracing
    generate_request_id,
    RequestIDMiddleware,
    # Health check
    health_check,
    # Decorators
    track_metrics,
    # Setup
    setup_observability,
    # Global logger
    logger,
)

__all__ = [
    # Logging
    "setup_logging",
    "get_logger",
    "JSONFormatter",
    # Metrics
    "http_requests_total",
    "http_request_duration_seconds",
    "director_runs_total",
    "director_run_duration_seconds",
    "visual_generations_total",
    "visual_generation_duration_seconds",
    "training_jobs_total",
    "training_job_duration_seconds",
    "active_connections",
    "queue_depth",
    "cache_hits_total",
    "cache_misses_total",
    "errors_total",
    # Metrics recording
    "record_http_request",
    "record_visual_generation",
    "record_training_job",
    # Middleware
    "PrometheusMiddleware",
    "metrics_endpoint",
    # Sentry
    "init_sentry",
    "capture_exception",
    # Request tracing
    "generate_request_id",
    "RequestIDMiddleware",
    # Health check
    "health_check",
    # Decorators
    "track_metrics",
    # Setup
    "setup_observability",
    # Global logger
    "logger",
]