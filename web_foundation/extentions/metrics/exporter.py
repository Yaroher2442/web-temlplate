from typing import List, Dict, Any, AnyStr

from sanic.response import raw

from web_foundation.extentions.metrics.metric import Metric, CounterMetric, SummaryMetric, \
    HistogramMetric
from web_foundation.utils.types import TypeJSON


class MetricExporter:
    @classmethod
    async def export(cls, metrics: List[Metric]) -> Dict[str, Any]:
        raise NotImplementedError

    @classmethod
    def empty(cls):
        return {}


class JsonExporter(MetricExporter):
    @classmethod
    async def export(cls, metrics: List[Metric]) -> Dict[str, TypeJSON]:
        dic = {}
        for metric in metrics:
            if not metric:
                continue
            if not dic.get(metric.name):
                dic[metric.name] = [{"kind": metric.kind,
                                     "value": metric.collect(),
                                     "labels": metric.labels,
                                     "timestamp": metric.timestamp}]
            else:
                dic[metric.name].append({"kind": metric.kind,
                                         "value": metric.collect(),
                                         "labels": metric.labels,
                                         "timestamp": metric.timestamp})
        return dic


class PrometheusExporter(MetricExporter):
    @classmethod
    async def export(cls, export_metrics: List[Metric]) -> AnyStr:
        try:
            from prometheus_client import metrics, registry
            from prometheus_client import metrics
            from prometheus_client.exposition import generate_latest
            from prometheus_client.metrics_core import CounterMetricFamily, \
                HistogramMetricFamily, \
                SummaryMetricFamily, \
                GaugeMetricFamily
            from prometheus_client.registry import Collector

            class CustomCollector(Collector):
                _custom_metrics: List[Metric]

                def __init__(self, custom_metrics: List[Metric]):
                    self._custom_metrics = custom_metrics

                def collect(self):
                    exp_metric = []
                    for metr in self._custom_metrics:
                        if isinstance(metr, CounterMetric):
                            prm_metr = CounterMetricFamily(metr.name, metr.description, labels=metr.labels_keys)
                            prm_metr.add_metric(metr.labels_values, metr.value, timestamp=metr.timestamp)
                            yield prm_metr
                        elif isinstance(metr, SummaryMetric):
                            prm_metr = SummaryMetricFamily(metr.name, metr.description, labels=metr.labels_keys)
                            prm_metr.add_metric(labels=metr.labels_values,
                                                sum_value=metr.value,
                                                count_value=metr.count,
                                                timestamp=metr.timestamp)
                            yield prm_metr
                        elif isinstance(metr, HistogramMetric):
                            prm_metr = HistogramMetricFamily(metr.name, metr.description, labels=metr.labels_keys)
                            prm_metr.add_metric(labels=metr.labels_values,
                                                sum_value=metr.sum,
                                                buckets=metr.buckets_list,
                                                timestamp=metr.timestamp)
                            yield prm_metr

            reg = registry.CollectorRegistry()
            reg.register(CustomCollector(export_metrics))
            return generate_latest(reg)
            # return  self._get_metrics_data()
        except ImportError:
            raise ImportError(
                "You need to install prometheus-client to use PrometheusExporter (web-foundation[prometheus])")

    @staticmethod
    def response_fabric(data):
        return raw(data, content_type='text/plain; version=0.0.4; charset=utf-8')
