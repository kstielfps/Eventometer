"""
Seed default ATC position templates into the database.
Usage: python manage.py seed_positions
"""

from django.core.management.base import BaseCommand
from core.models import PositionTemplate, ATCRating


DEFAULT_POSITIONS = [
    {"name": "DEL", "min_rating": ATCRating.S1, "description": "Delivery – Autorização de tráfego"},
    {"name": "GND", "min_rating": ATCRating.S1, "description": "Ground – Controle de solo"},
    {"name": "TWR", "min_rating": ATCRating.S2, "description": "Tower – Controle de torre"},
    {"name": "APP", "min_rating": ATCRating.S3, "description": "Approach – Controle de aproximação"},
    {"name": "CTR", "min_rating": ATCRating.C1, "description": "Center – Controle de área"},
]


class Command(BaseCommand):
    help = "Cria os templates de posição ATC padrão (DEL, GND, TWR, APP, CTR)"

    def handle(self, *args, **options):
        created_count = 0
        for pos_data in DEFAULT_POSITIONS:
            _, created = PositionTemplate.objects.get_or_create(
                name=pos_data["name"],
                defaults={
                    "min_rating": pos_data["min_rating"],
                    "description": pos_data["description"],
                },
            )
            if created:
                created_count += 1
                self.stdout.write(self.style.SUCCESS(f"  ✓ Criado: {pos_data['name']}"))
            else:
                self.stdout.write(f"  – Já existe: {pos_data['name']}")

        self.stdout.write(self.style.SUCCESS(f"\nTotal criados: {created_count}"))
