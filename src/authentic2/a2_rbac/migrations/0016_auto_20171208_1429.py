# -*- coding: utf-8 -*-
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('a2_rbac', '0015_organizationalunit_validate_emails'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='organizationalunit',
            options={'ordering': ('name',), 'verbose_name': 'organizational unit', 'verbose_name_plural': 'organizational units'},
        ),
    ]
