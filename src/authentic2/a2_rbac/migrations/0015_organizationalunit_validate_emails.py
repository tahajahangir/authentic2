# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a2_rbac', '0014_auto_20170711_1024'),
    ]

    operations = [
        migrations.AddField(
            model_name='organizationalunit',
            name='validate_emails',
            field=models.BooleanField(default=False, verbose_name='Validate emails'),
        ),
    ]
