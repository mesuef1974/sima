"""أداة Django الإدارية لسِمة (الترحيلات وما شابه): `uv run python manage.py migrate`."""
from __future__ import annotations

import os
import sys

if __name__ == "__main__":
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "sima.web.settings")
    from django.core.management import execute_from_command_line

    execute_from_command_line(sys.argv)
