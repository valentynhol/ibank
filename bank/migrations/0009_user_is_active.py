# Generated by Django 4.0.1 on 2022-05-22 10:12

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bank', '0008_remove_transaction_money_transaction_receiver_money_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='is_active',
            field=models.BooleanField(default=True, verbose_name='активний'),
        ),
    ]