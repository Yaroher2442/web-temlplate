from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import List, Sequence, Dict, Tuple


class Metric:
    name: str
    value: float
    kind: str
    labels: Dict[str, str]
    description: str
    timestamp: float

    def __init__(self, name: str, value: float = 0.0, labels: Dict[str, str] = None, description: str = None,
                 kind: str = "__system_metric__"):
        self.kind = kind
        self.labels = labels if labels else {}
        self.timestamp = datetime.now().timestamp()
        self.description = description if description else 'Default metric description'
        self.name = name
        self.value = float(value)

    def add_label(self, name: str = None, value: str = None, **kwargs):
        if kwargs:
            self.labels.update(kwargs)
        else:
            self.labels.update({name: value})

    def set(self, value: float):
        self.value = value

    @property
    def labels_keys(self):
        return list(self.labels.keys())

    @property
    def labels_values(self):
        return list(self.labels.values())

    @property
    def labels_concat(self):
        return '_'.join(self.labels.values())

    def inc(self, value: int = 1):
        raise NotImplementedError

    def __str__(self):
        return f"{self.__class__.__name__}({self.name})<{self.value}>"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})<{self.value}>"

    def __eq__(self, other):
        return self.name == other.name

    def __add__(self, metric: Metric):
        self.value += metric.value
        return self

    def __hash__(self):
        return id(self.name)

    def collect(self):
        return self.value


class CounterMetric(Metric):
    def inc(self, value: int = 1):
        self.value += value


class SummaryMetric(Metric):
    _count: int = 0

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._count = 1

    def __add__(self, other: SummaryMetric):
        self._count += other._count
        self.value += other.value
        return self

    def observe(self, value: int = 1):
        self._count += 1
        self.value += value

    def collect(self):
        return self.value / self._count

    def __str__(self):
        return f"{self.__class__.__name__}({self.name})<{self.collect()}>"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})<{self.collect()}>"

    def inc(self, value: int = 1):
        self.value += value

    @property
    def count(self):
        return self._count


class HistogramMetric(Metric):
    _sum: float = 0.0
    _buckets: List[float]
    _temp_bucket: Sequence[float]
    DEFAULT_BUCKETS = (.001, .005, .01, .025, .05, .075, .1, .25, .5, .75, 1.0, 2.5, 5.0, 7.5, 10.0, float("inf"))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._sum = 0.0
        self._temp_bucket = self.DEFAULT_BUCKETS
        self._buckets = [0.0 for _ in range(len(self._temp_bucket))]

    def set_bucket(self, buckets: Sequence[float]):
        buckets = [float(b) for b in buckets]
        if buckets != sorted(buckets):
            raise ValueError('Buckets not in sorted order')
        if buckets and buckets[-1] != float("inf"):
            buckets.append(float("inf"))
        if len(buckets) < 2:
            raise ValueError('Must have at least two buckets')
        self._temp_bucket = buckets
        self._buckets = [0.0 for _ in range(len(self._temp_bucket))]

    def __add__(self, other: HistogramMetric):
        if self._temp_bucket != other._temp_bucket:
            raise ValueError("Buckets of two Histogram is not comparable")
        self._sum += other._sum
        for i, bound in enumerate(self._temp_bucket):
            self._buckets[i] += other._buckets[i]
        return self

    def observe(self, value: float):
        self._sum += value
        for i, bound in enumerate(self._temp_bucket):
            if value <= bound:
                self._buckets[i] += 1

    def collect(self):
        return list(zip(self._temp_bucket, self._buckets))

    def __str__(self):
        return f"{self.__class__.__name__}({self.name})<{self._sum}>"

    def __repr__(self):
        return f"{self.__class__.__name__}({self.name})<{self._sum}>"

    def inc(self, value: int = 1):
        self.value += value

    @property
    def sum(self):
        return self._sum

    @property
    def buckets_list(self) -> List[Tuple[str, float]]:
        lst = []
        for i in range(len(self._buckets)):
            lst.append((str(self._temp_bucket[i]), self._buckets[i]))
        return lst
