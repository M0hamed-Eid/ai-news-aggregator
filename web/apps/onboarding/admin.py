from django.contrib import admin

from .models import Interest, Persona, UserDigestSettings, UserExclusion, UserInterest


@admin.register(Persona)
class PersonaAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "sort_order", "is_active")
    list_filter = ("is_active",)
    search_fields = ("name", "slug")
    ordering = ("sort_order", "name")


@admin.register(Interest)
class InterestAdmin(admin.ModelAdmin):
    list_display = ("name", "slug", "category", "sort_order", "is_active")
    list_filter = ("category", "is_active")
    search_fields = ("name", "slug", "category")
    ordering = ("sort_order", "name")


@admin.register(UserInterest)
class UserInterestAdmin(admin.ModelAdmin):
    list_display = ("profile", "interest", "weight", "created_at")
    list_filter = ("interest",)
    search_fields = ("profile__user__email", "interest__name")


@admin.register(UserDigestSettings)
class UserDigestSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "profile",
        "frequency",
        "max_items",
        "is_paused",
        "expertise_level",
        "content_depth",
    )
    list_filter = ("frequency", "is_paused", "expertise_level", "content_depth")
    search_fields = ("profile__user__email",)


@admin.register(UserExclusion)
class UserExclusionAdmin(admin.ModelAdmin):
    list_display = ("profile", "kind", "value", "created_at")
    list_filter = ("kind",)
    search_fields = ("profile__user__email", "value")
