from django.db import models
from django.contrib.auth.models import User


# =========================
# CATEGORY
# =========================
class Category(models.Model):
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True)
    image = models.ImageField(upload_to='categories/', blank=True, null=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name_plural = "Categories"
        ordering = ['name']

    def __str__(self):
        return self.name


# =========================
# PRODUCT
# =========================
class Product(models.Model):
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, related_name='products')
    producer = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='products')
    name = models.CharField(max_length=200)
    slug = models.SlugField(unique=True, null=True, blank=True)
    description = models.TextField(blank=True)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    image = models.ImageField(upload_to='products/', blank=True, null=True)
    stock = models.PositiveIntegerField(default=0)
    is_available = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True)
    updated_at = models.DateTimeField(auto_now=True, null=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return self.name

    @property
    def in_stock(self):
        return self.stock > 0


# =========================
# ORDER
# =========================
class Order(models.Model):
    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('processing', 'Processing'),
        ('shipped', 'Shipped'),
        ('delivered', 'Delivered'),
        ('cancelled', 'Cancelled'),
    ]

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='orders')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    is_complete = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"Order #{self.id} — {self.user.username}"

    @property
    def total_price(self):
        return sum(item.subtotal for item in self.items.all())

    @property
    def total_items(self):
        return sum(item.quantity for item in self.items.all())


# =========================
# ORDER ITEM
# =========================
class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.PositiveIntegerField(default=1)
    price = models.DecimalField(max_digits=10, decimal_places=2)

    def __str__(self):
        return f"{self.quantity} x {self.product.name}"

    @property
    def subtotal(self):
        return self.price * self.quantity


# =========================
# ORDER TRACKING
# =========================
class OrderTracking(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='tracking')
    status = models.CharField(max_length=20)
    message = models.CharField(max_length=300, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"Order #{self.order.id} — {self.status}"


# =========================
# CANCEL / RETURN
# =========================
class CancelReturnRequest(models.Model):
    TYPE_CHOICES = [
        ('cancel', 'Cancel'),
        ('return', 'Return'),
    ]

    STATUS_CHOICES = [
        ('pending', 'Pending'),
        ('approved', 'Approved'),
        ('rejected', 'Rejected'),
    ]

    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='requests')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    request_type = models.CharField(max_length=10, choices=TYPE_CHOICES)
    reason = models.TextField()
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')
    producer_note = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.request_type.title()} request for Order #{self.order.id}"


# =========================
# SHIPPING ADDRESS
# =========================
class ShippingAddress(models.Model):
    order = models.OneToOneField(Order, on_delete=models.CASCADE, related_name='shipping_address')
    full_name = models.CharField(max_length=200)
    address = models.CharField(max_length=300)
    city = models.CharField(max_length=100)
    state = models.CharField(max_length=100)
    zipcode = models.CharField(max_length=20)
    country = models.CharField(max_length=100, default='India')
    phone = models.CharField(max_length=20, blank=True)

    def __str__(self):
        return f"Shipping for Order #{self.order.id}"


# =========================
# PROFILE
# =========================
class Profile(models.Model):
    ROLE_CHOICES = [
        ('customer', 'Customer'),
        ('producer', 'Producer'),
    ]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='customer')
    phone = models.CharField(max_length=20, blank=True)
    address = models.TextField(blank=True)

    def __str__(self):
        return f"{self.user.username} ({self.role})"

    @property
    def is_producer(self):
        return self.role == 'producer'

    @property
    def is_customer(self):
        return self.role == 'customer'


# =========================
# WISHLIST
# =========================
class Wishlist(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='wishlist')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('user', 'product')

    def __str__(self):
        return f"{self.user.username} — {self.product.name}"


# =========================
# REVIEW
# =========================
class Review(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='reviews')
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    rating = models.PositiveIntegerField(choices=[(i, i) for i in range(1, 6)])
    comment = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'user')
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.user.username} — {self.product.name} ({self.rating}★)"


# =========================
# REVIEW IMAGE (NEW)
# =========================
class ReviewImage(models.Model):
    review = models.ForeignKey(Review, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(upload_to='reviews/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Image for Review #{self.review.id}"


# =========================
# PRODUCT IMAGE GALLERY
# =========================
class ProductImage(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='gallery_images')
    image = models.ImageField(upload_to='products/gallery/')
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['id']

    def __str__(self):
        return f"Image for {self.product.name}"


# =========================
# CHAT ROOM
# =========================
class ChatRoom(models.Model):
    product = models.ForeignKey(Product, on_delete=models.CASCADE, related_name='chat_rooms')
    buyer = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chat_rooms_as_buyer')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('product', 'buyer')
        ordering = ['-created_at']

    def __str__(self):
        return f"Chat: {self.buyer.username} <-> {self.product.producer.username}"

    @property
    def seller(self):
        return self.product.producer


# =========================
# CHAT MESSAGE
# =========================
class ChatMessage(models.Model):
    room = models.ForeignKey(ChatRoom, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE)
    text = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ['timestamp']

    def __str__(self):
        return f"{self.sender.username}: {self.text[:30]}"