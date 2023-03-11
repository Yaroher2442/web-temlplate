from tortoise import fields

from web.env.database.models import AbstractDbModel


class TestModel(AbstractDbModel):
    name = fields.TextField(null=True)
