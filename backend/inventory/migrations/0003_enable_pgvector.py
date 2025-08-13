from django.db import migrations

class Migration(migrations.Migration):
    # Hänge dich an die letzte vorhandene Migration an:
    dependencies = [
        ('inventory', '0002_itemalias'),
    ]

    operations = [
        migrations.RunSQL("CREATE EXTENSION IF NOT EXISTS vector;"),
    ]
