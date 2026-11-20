# مراجعة الأتمتة 2026-11-14 (ت11): قرارات مسار المصمّم الخارجي تُحفظ قرارات بوابة باسم designer. تغيير خيارات فقط، بلا SQL.

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("registry", "0002_verdict_switch_medium"),
    ]

    operations = [
        migrations.AlterField(
            model_name="gatedecision",
            name="gate",
            field=models.CharField(
                choices=[
                    ("strategy", "المنصة الاستراتيجية"),
                    ("directions", "اتجاه الهوية"),
                    ("book", "دليل الهوية"),
                    ("designer", "سكتش المصمّم الخارجي"),
                ],
                max_length=12,
            ),
        ),
    ]
