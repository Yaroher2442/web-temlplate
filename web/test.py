from typing import TypeVar, Generic

# PLUGIN_NAME = "SHITPOSTLIGIN"
#
# class SHITPOSTLIGIN:
#     pass
#
# class T:
#     def w(self):
#         pass
#
#
# GenT = TypeVar("GenT", bound=T)
#
#
# class ChanAble(Generic[GenT]):
#     _chan: GenT | None = None
#
#     @property
#     def channel(self) -> GenT:
#         if self._chan:
#             return self._chan
#         else:
#             raise Exception("_channel not set")
#
#     @channel.setter
#     def channel(self, chan: GenT):
#         self._chan = chan
#
#
# class MyT(T):
#
#     def c(self):
#         pass
#
#
# GenM = TypeVar("GenT")
#
#
# class Test(Generic[GenM]):
#     def __init__(self):
#         from typing import get_args
#         print(self.__orig_bases__)
#         print(get_args(self.__orig_bases__))
#
#
# if __name__ == '__main__':
#     # Test[MyT]().channel.c()
#     t = Test[MyT]()

# import asyncio
# from typing import Dict, List
#
# from news.kernel.signal import SignalType
# from news.kernel.types import GenAsyncCall
#
#
# class SignalAble:
#     __signals: Dict[SignalType, List[GenAsyncCall]] | None = None
#
#     def __init__(self):
#         self.on_signal(typed=SignalType.BEFORE_APP_RUN, func=self.test)
#
#     def on_signal(self, typed: SignalType, func: GenAsyncCall):
#         if not self.__signals:
#             self.__signals = {}
#         if not self.__signals.get(typed):
#             self.__signals[typed] = []
#         self.__signals[typed].append(func)
#
#     async def call_signals(self, typed: SignalType, *args, **kwargs):
#         for signal in self.__signals[typed]:
#             await signal(*args, **kwargs)
#
#     async def test(self):
#         print("pidor")
#
#
# async def main():
#     s = SignalAble()
#     await s.call_signals(SignalType.BEFORE_APP_RUN)
#
#
# if __name__ == '__main__':
#     asyncio.run(main())



class Service:
    def set(self, value):
        pass

class P():
    service_method = Service.set

if __name__ == '__main__':
    print(P().service_method.__func__.__qualname__)
    print(dir(P().service_method.__func__))
    print(P().service_method.__name__)
