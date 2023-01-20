import asyncio
from asyncio import Future, CancelledError
from typing import Dict, Any, List

import loguru

from web_foundation import settings
from web_foundation.extentions.metrics.metric import Metric, CounterMetric
from web_foundation.extentions.metrics.events import NewMetricEvent, MetricRequestEvent, MetricResponseEvent
from web_foundation.kernel.messaging.channel import IChannel, EventListener, GenericIMessage
from web_foundation.kernel.isolate import Isolate
from web_foundation.extentions.schedulle.scheduller import TaskScheduler, TaskIMessage
from web_foundation.settings_event import SettingsChangeEvent

MetricsDict = Dict[str, Dict[str, Metric]]


class IDispatcher:
    channels: Dict[str, IChannel]
    events_listeners: Dict[str, EventListener]
    scheduler: TaskScheduler
    collected_metrics: Dict[str, MetricsDict]
    _msg_global_index: int
    state: Dict[str, Any]

    def __init__(self, scheduler: TaskScheduler = None):
        self.scheduler = scheduler
        self.state = {}
        self.channels = {}
        self.events_listeners = {}
        self.collected_metrics = {}
        self.collected_metrics.update({"__system_metric__": {}})
        self._msg_global_index = 0
        if self.scheduler:
            self.scheduler.produce_method = self.broadcast
            self.state.update({"scheduler": {}})
            self.scheduler.state = self.state.get("scheduler")
            self.add_event_listener(TaskIMessage.message_type, self.scheduler.add_task)
        if settings.METRICS_ENABLE:
            self.add_event_listener(NewMetricEvent.message_type, self.on_new_metric)
            self.add_event_listener(MetricRequestEvent.message_type, self.on_metric_request)

        async def on_settings_change(event: SettingsChangeEvent):
            setattr(settings, event.name, event.value)

        self.add_event_listener(SettingsChangeEvent.message_type, on_settings_change)

    def register_isolate(self, isolate: Isolate):
        self.channels.update({isolate.name: isolate.channel})

    def add_event_listener(self, event_type: str, callback: EventListener):
        self.events_listeners[event_type] = callback

    async def track_event(self, msg: GenericIMessage):
        listener = self.events_listeners.get(msg.message_type)
        if listener:
            await listener(msg)

        if settings.METRICS_ENABLE:
            event_counter = CounterMetric("events_counter", self._msg_global_index)
            save_to = self.collected_metrics['__system_metric__']
            save_to.update({"events_counter": {"dispatcher_events_counter": event_counter}})

            named_event_counter = save_to.get("named_events_counter")
            if not named_event_counter:
                mtr = CounterMetric("named_events_counter", value=1)
                mtr.add_label(event_name=msg.message_type)
                named_event_counter = {msg.message_type: mtr}
                save_to["named_events_counter"] = named_event_counter
            elif named_event_counter.get(msg.message_type):
                named_event_counter[msg.message_type].inc()
            else:
                mtr = CounterMetric("named_events_counter", value=1)
                mtr.add_label(event_name=msg.message_type)
                named_event_counter[msg.message_type] = mtr
            if settings.DEBUG:
                loguru.logger.debug(f'MetricsDispatcher - track event {msg}')

    async def on_channel_sent(self, msg: GenericIMessage):
        self._msg_global_index += 1
        msg.index = self._msg_global_index
        asyncio.create_task(self.track_event(msg))
        if msg.destination != "__dispatcher__":
            asyncio.create_task(self.broadcast(msg))

    async def on_metric_request(self, event: MetricRequestEvent):
        exporter = event.exporter
        sender_channel = self.channels.get(event.sender)
        if sender_channel:
            if settings.DEBUG:
                loguru.logger.debug(f"Send METRICS to {sender_channel}")
            if not self.collected_metrics.get(event.kind) or not self.collected_metrics[
                event.kind] or not settings.METRICS_ENABLE:
                resp = MetricResponseEvent(exporter.empty())
                resp.inner_index = event.inner_index
                await sender_channel.sent_to_consume(resp)
                return
            rp = []
            for i in self.collected_metrics[event.kind].values():
                if isinstance(i, dict):
                    for k in i.values():
                        rp.append(k)
                else:
                    rp.append(i)
            data = await exporter.export(rp)
            resp = MetricResponseEvent(data)
            resp.inner_index = event.inner_index
            await sender_channel.sent_to_consume(resp)

    async def on_new_metric(self, event: NewMetricEvent):
        if not self.collected_metrics.get(event.metric.kind):
            self.collected_metrics.update({event.metric.kind: {}})
        metr = self.collected_metrics[event.metric.kind].get(event.metric.name)
        if not metr:
            self.collected_metrics[event.metric.kind].update(
                {event.metric.name: {event.metric.labels_concat: event.metric}})
        else:
            if metr.get(event.metric.labels_concat):
                # loguru.logger.warning(f"get {event.metric}")
                metr[event.metric.labels_concat] += event.metric
            else:
                # loguru.logger.warning(f"set {event.metric}")
                metr[event.metric.labels_concat] = event.metric

    async def broadcast(self, msg: GenericIMessage):
        for worker_name, ch in self.channels.items():
            if msg.sender == worker_name:
                continue
            if msg.destination in ["__all__", worker_name]:
                if settings.DEBUG:
                    loguru.logger.debug(f"Sent {msg} to {ch.worker_name}")
                ch.consume_pipe.put(msg)

    def perform(self, **kwargs) -> List[Future[Any]]:
        tasks = []
        for channel in self.channels.values():
            tasks.append(asyncio.ensure_future(
                channel.listen_produce(
                    self.on_channel_sent
                )))
        return tasks


class IDispatcherIsolate(Isolate):
    dispatcher: IDispatcher

    def __init__(self, name: str, dispatcher: IDispatcher, **kwargs):
        self.dispatcher = dispatcher
        super().__init__(name, **kwargs)

    async def work(self, **kwargs) -> None:
        if self.dispatcher.scheduler:
            self.dispatcher.scheduler.perform()
        try:
            await asyncio.wait(self.dispatcher.perform())
        except CancelledError:
            pass