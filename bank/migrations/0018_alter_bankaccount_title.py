# Generated by Django 4.0.1 on 2023-06-18 16:06

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('bank', '0017_alter_card_color_alter_card_title_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='bankaccount',
            name='title',
            field=models.CharField(default='Банківський рахунок', max_length=30, verbose_name='назва банківського рахунку'),
        ),
    ]
