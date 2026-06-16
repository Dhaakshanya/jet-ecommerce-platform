from django.contrib import admin
from .models import Category, Product, Order, OrderItem, ShippingAddress


# ── Category ──────────────────────────────────────────────
@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display  = ('name', 'slug')
    prepopulated_fields = {'slug': ('name',)}
    search_fields = ('name',)


# ── Product ───────────────────────────────────────────────
@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display    = ('name', 'category', 'price', 'stock', 'is_available', 'created_at')
    list_filter     = ('category', 'is_available')
    list_editable   = ('price', 'stock', 'is_available')
    prepopulated_fields = {'slug': ('name',)}
    search_fields   = ('name', 'description')
    ordering        = ('-created_at',)


# ── OrderItem inline (shown inside Order) ─────────────────
class OrderItemInline(admin.TabularInline):
    model  = OrderItem
    extra  = 0
    readonly_fields = ('product', 'quantity', 'price', 'subtotal')

    def subtotal(self, obj):
        return f"₹{obj.subtotal}"
    subtotal.short_description = "Subtotal"


# ── ShippingAddress inline ────────────────────────────────
class ShippingAddressInline(admin.StackedInline):
    model  = ShippingAddress
    extra  = 0
    readonly_fields = ('full_name', 'address', 'city', 'state', 'zipcode', 'country', 'phone')


# ── Order ─────────────────────────────────────────────────
@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display  = ('id', 'user', 'status', 'total_price', 'total_items', 'is_complete', 'created_at')
    list_filter   = ('status', 'is_complete')
    list_editable = ('status',)
    search_fields = ('user__username', 'user__email')
    ordering      = ('-created_at',)
    readonly_fields = ('total_price', 'total_items', 'created_at', 'updated_at')
    inlines       = [OrderItemInline, ShippingAddressInline]

    def total_price(self, obj):
        return f"₹{obj.total_price}"
    total_price.short_description = "Total"

    def total_items(self, obj):
        return obj.total_items
    total_items.short_description = "Items"