# Generated by Django 3.1.2 on 2020-10-17 15:49

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('DrugID_API', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='asset',
            name='group',
            field=models.IntegerField(choices=[(1, 'Pharma'), (2, 'Iso'), (3, 'Black White')]),
        ),
        migrations.AlterField(
            model_name='result',
            name='group',
            field=models.IntegerField(choices=[(1, 'Pharma'), (2, 'Iso'), (3, 'Black White')]),
        ),
        migrations.AlterField(
            model_name='session',
            name='last_group',
            field=models.IntegerField(choices=[(1, 'Pharma'), (2, 'Iso'), (3, 'Black White')]),
        ),
        migrations.AlterField(
            model_name='set',
            name='group',
            field=models.IntegerField(choices=[(1, 'Pharma'), (2, 'Iso'), (3, 'Black White')]),
        ),
        migrations.DeleteModel(
            name='Group',
        ),
    ]
