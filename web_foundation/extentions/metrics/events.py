from typing import Any

from web_foundation.extentions.metrics.metric import Metric
from web_foundation.extentions.metrics.exporter import MetricExporter
from web_foundation.kernel.messaging.channel import IMessage


class NewMetricEvent(IMessage):
    message_type = "new_metric"
    destination = "__dispatcher__"
    metric: Metric

    def __init__(self, metric: Metric):
        super().__init__()
        self.metric = metric

    def __str__(self):
        return f"NewMetricEvent({self.metric.__str__()})"


class MetricRequestEvent(IMessage):
    message_type = "metrics_request"
    destination = "__dispatcher__"
    exporter: MetricExporter
    kind: str

    def __init__(self, exporter: MetricExporter, kind: str):
        super().__init__()
        self.kind = kind
        self.exporter = exporter


class MetricResponseEvent(IMessage):
    message_type = "metrics_response"
    metrics_data: Any

    def __init__(self, metrics_data: Any):
        super().__init__()
        self.metrics_data = metrics_data

    def __str__(self):
        return f"MetricResponse({type(self.metrics_data)})"
