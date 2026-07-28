from django.contrib.postgres.operations import BtreeGistExtension
from django.db import migrations


class Migration(migrations.Migration):
    """Enable btree_gist so exclusion constraints can use equality on FKs."""

    initial = True

    dependencies = []

    operations = [
        BtreeGistExtension(),
    ]
