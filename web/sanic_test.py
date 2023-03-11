# from typing import TypeVar, Generic
#
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
#     _chan: GenT | None
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
# class Test(Generic[GenM], ChanAble[GenM]):
#     pass
#
#
# if __name__ == '__main__':
#     Test[MyT]().channel.c()

# from _sanic import Sanic
#
# if __name__ == '__main__':
#     s = Sanic(name="Shit")
#     s.run(single_process=True)
