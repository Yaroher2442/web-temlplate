# from typing import Tuple
# from web_foundation import settings
#
# import click
#
#
# def generate(entity, destination):
#     pass
#
#
# def set_setting(name: str, value):
#     match value:
#         case "true":
#             value = True
#         case "false":
#             value = False
#     setattr(settings, name.upper(), value)
#
#
# @click.command()
# @click.option('--generator', type=(str, str), required=False)
# @click.option('--set', type=(str, str), required=False)
# def main(generator: Tuple[str, str] = None, set: Tuple[str, str] = None):
#     if generator:
#         entity, destination = generator
#         generate(entity, destination)
#         return
#     if set:
#         name, value = set
#         set_setting(name, value)
#
#
# if __name__ == '__main__':
#     main()
