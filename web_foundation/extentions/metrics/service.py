import asyncio

from web_foundation.extentions.metrics.events import MetricRequestEvent, NewMetricEvent, MetricResponseEvent
from web_foundation.extentions.metrics.exporter import MetricExporter
from web_foundation.extentions.metrics.metric import Metric
from web_foundation.kernel.service import Service


class MetricsService(Service):
    async def collect_metrics(self, exporter: MetricExporter, kind: str = "__system_metric__"):
        metrics_response: MetricResponseEvent = await self.wait_for_response(MetricRequestEvent(exporter, kind))
        return metrics_response.metrics_data

    async def give_metric(self, metric: Metric, kind: str = "__system_metric__"):
        metric.kind = kind
        asyncio.create_task(self.channel.produce(NewMetricEvent(metric)))
