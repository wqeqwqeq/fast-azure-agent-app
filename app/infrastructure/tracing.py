"""OpenTelemetry tracing configuration for the application.

Supports two backends:
- local: Sends traces to local Aspire dashboard via OTLP gRPC
- appinsights: Sends traces to Azure Application Insights
"""

import logging

from agent_framework.observability import configure_otel_providers

logger = logging.getLogger(__name__)


def configure_tracing(
    backend: str,
    appinsights_connection_string: str | None = None,
    otlp_endpoint: str = "http://localhost:4317",
    enable_sensitive_data: bool = False,
) -> None:
    """Configure OpenTelemetry tracing based on backend selection.

    Args:
        backend: Tracing backend - "disabled", "local", or "appinsights"
        appinsights_connection_string: Azure App Insights connection string
            (required for appinsights backend)
        otlp_endpoint: OTLP endpoint for local backend (default: http://localhost:4317)
        enable_sensitive_data: Whether to log prompts/responses in traces
    """
    if backend == "disabled":
        logger.info("Tracing is disabled")
        return

    if backend == "local":
        _configure_local_tracing(otlp_endpoint, enable_sensitive_data)
    elif backend == "appinsights":
        _configure_appinsights_tracing(appinsights_connection_string, enable_sensitive_data)
    else:
        logger.warning(f"Unknown tracing backend: {backend}, tracing disabled")


def _configure_local_tracing(otlp_endpoint: str, enable_sensitive_data: bool) -> None:
    """Configure tracing for local Aspire dashboard via OTLP gRPC."""
    from opentelemetry.exporter.otlp.proto.grpc._log_exporter import OTLPLogExporter
    from opentelemetry.exporter.otlp.proto.grpc.metric_exporter import OTLPMetricExporter
    from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter

    exporters = [
        OTLPSpanExporter(endpoint=otlp_endpoint),
        OTLPLogExporter(endpoint=otlp_endpoint),
        OTLPMetricExporter(endpoint=otlp_endpoint),
    ]
    configure_otel_providers(
        exporters=exporters,
        enable_sensitive_data=enable_sensitive_data,
    )
    logger.info(f"Tracing configured for local Aspire dashboard at {otlp_endpoint}")


def _configure_appinsights_tracing(
    connection_string: str | None,
    enable_sensitive_data: bool,
) -> None:
    """Configure tracing for Azure Application Insights using exporters directly.

    Uses Azure Monitor exporters directly instead of configure_azure_monitor()
    to avoid heavy auto-instrumentation that causes startup delays.
    """
    if not connection_string:
        logger.warning("App Insights connection string not provided, tracing disabled")
        return

    from azure.monitor.opentelemetry.exporter import (
        AzureMonitorLogExporter,
        AzureMonitorMetricExporter,
        AzureMonitorTraceExporter,
    )

    exporters = [
        AzureMonitorTraceExporter(connection_string=connection_string),
        AzureMonitorLogExporter(connection_string=connection_string),
        AzureMonitorMetricExporter(connection_string=connection_string),
    ]
    configure_otel_providers(
        exporters=exporters,
        enable_sensitive_data=enable_sensitive_data,
    )
    logger.info("Tracing configured for Azure Application Insights")
