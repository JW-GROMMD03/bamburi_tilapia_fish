from django.db import models
from django.utils import timezone

class MenuItem(models.Model):
    CATEGORY_CHOICES = [
        ('tilapia', 'Tilapia'),
        ('mbuta', 'Mbuta'),
        ('obambo', 'Obambo'),
        ('ugali', 'Ugali'),
        ('wetfry', 'Wet Fry'),
        ('soda', 'Soda'),
        ('greens', 'Greens'),
        ('chips', 'Chips'),
        ('fuluOmena', 'Fulu/Omena'),
        ('water', 'Water'),
        ('container', 'Container'),
        ('other', 'Other'),
    ]
    
    category = models.CharField(max_length=20, choices=CATEGORY_CHOICES)
    name = models.CharField(max_length=100)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)  # Make sure this exists
    
    class Meta:
        ordering = ['category', 'name']
    
    def __str__(self):
        return f"{self.name} ({self.category}) - {self.price}"