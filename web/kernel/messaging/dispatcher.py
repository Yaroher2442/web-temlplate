import asyncio
from typing import Dict, Any, Coroutine

from web import settings
from web.kernel.messaging.channel import Channel
from web.kernel.messaging.channel import GenIMessage
from web.kernel.types import ChanAble, cheat, SettingsChangeEvent


async def on_settings_change(event: SettingsChangeEvent):
    setattr(settings, event.name, event.value)


class IDispatcher:
    channels: Dict[str, Channel]
    _msg_global_index: int
    state: Dict[str, Any]
    _master_channel: Channel

    def __init__(self):
        self.state = {}
        self.channels = {}
        self._events_listeners = {}
        self.collected_metrics = {}
        self._msg_global_index = 0

    def set_channel(self, chan_able: ChanAble, ext_name: str = None, master: bool = False) -> Channel:
        chan = Channel(len(self.channels) + 1, ext_name if ext_name else chan_able.name)
        chan.add_event_listener(SettingsChangeEvent, on_settings_change)
        chan_able.channel = chan
        cheat(chan_able, ChanAble, chan, nested=False)
        self.channels.update({chan.name: chan})
        if master:
            self._master_channel = chan
        return chan

    async def on_channel_sent(self, msg: GenIMessage):
        self._msg_global_index += 1
        msg.index = self._msg_global_index
        # asyncio.create_task(self.track_event(msg))
        if msg.destination != "__master__":
            asyncio.create_task(self._broadcast(msg))
        else:
            await self._master_channel.sent_to_consume(msg)

    async def _broadcast(self, msg: GenIMessage):
        for worker_name, ch in self.channels.items():
            if msg.sender == worker_name:
                continue
            if msg.destination in ["__all__", worker_name]:
                ch.consume_pipe.put(msg)

    async def send_to_consume(self, chan_name: str, event: GenIMessage):
        sender_channel = self.channels.get(chan_name)
        await sender_channel.produce(event)

    def perform(self, **kwargs) -> list[Coroutine[Any, Any, Any]]:
        tasks = []
        for channel in self.channels.values():
            tasks.append(channel.listen_produce(
                self.on_channel_sent
            ))
        return tasks

    # async def track_event(self, msg: GenericIMessage):
    #     listener = self.events_listeners.get(msg.message_type)
    #     if listener:
    #         await listener(msg)
    #
    #     if settings.METRICS_ENABLE:
    #         event_counter = CounterMetric("events_counter", self._msg_global_index)
    #         save_to = self.collected_metrics['__system_metric__']
    #         save_to.update({"events_counter": {"dispatcher_events_counter": event_counter}})
    #
    #         named_event_counter = save_to.get("named_events_counter")
    #         if not named_event_counter:
    #             mtr = CounterMetric("named_events_counter", value=1)
    #             mtr.add_label(event_name=msg.message_type)
    #             named_event_counter = {msg.message_type: mtr}
    #             save_to["named_events_counter"] = named_event_counter
    #         elif named_event_counter.get(msg.message_type):
    #             named_event_counter[msg.message_type].inc()
    #         else:
    #             mtr = CounterMetric("named_events_counter", value=1)
    #             mtr.add_label(event_name=msg.message_type)
    #             named_event_counter[msg.message_type] = mtr
    #         if settings.DEBUG:
    #             loguru.logger.debug(f'MetricsDispatcher - track event {msg}')
