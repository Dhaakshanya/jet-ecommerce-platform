from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User
from django.contrib import messages
from django.contrib.auth.decorators import login_required, user_passes_test
from django.utils.text import slugify
from django.db.models import Q, Avg, Sum, Count, F
from django.db.models.functions import TruncDate
from django.http import HttpResponse
from django.utils import timezone
from datetime import timedelta
from .models import Profile, Product, Category, Wishlist, Order, OrderItem, OrderTracking, ShippingAddress, CancelReturnRequest, Review, ProductImage, ReviewImage, ChatRoom, ChatMessage, DeletedMessage
from cart.models import Cart
from django.conf import settings
import razorpay
import hmac
import hashlib

import io
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet


# ── Helpers ───────────────────────────────────────────────
def producer_required(view_func):
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not hasattr(request.user, 'profile') or not request.user.profile.is_producer:
            messages.error(request, 'You need a producer account to access this page.')
            return redirect('home')
        return view_func(request, *args, **kwargs)
    wrapper.__name__ = view_func.__name__
    return wrapper


# ══════════════════════════════════════════════════════════
#  AUTH
# ══════════════════════════════════════════════════════════

def register(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        username    = request.POST.get('username', '').strip()
        email       = request.POST.get('email', '').strip()
        password1   = request.POST.get('password1', '')
        password2   = request.POST.get('password2', '')
        is_producer = request.POST.get('is_producer') == 'on'
        if not username or not email or not password1:
            messages.error(request, 'All fields are required.')
        elif password1 != password2:
            messages.error(request, 'Passwords do not match.')
        elif User.objects.filter(username=username).exists():
            messages.error(request, 'Username already taken.')
        elif User.objects.filter(email=email).exists():
            messages.error(request, 'Email already registered.')
        else:
            user = User.objects.create_user(username=username, email=email, password=password1)
            role = 'producer' if is_producer else 'customer'
            Profile.objects.create(user=user, role=role)
            messages.success(request, 'Account created! Please log in.')
            return redirect('login')
    return render(request, 'store/register.html')


def user_login(request):
    if request.user.is_authenticated:
        return redirect('home')
    if request.method == 'POST':
        username = request.POST.get('username', '').strip()
        password = request.POST.get('password', '')
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return redirect('home')
        else:
            messages.error(request, 'Invalid username or password.')
    return render(request, 'store/login.html')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required(login_url='login')
def become_producer(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    profile.role = 'producer'
    profile.save()
    messages.success(request, 'You are now a producer! Welcome to Seller Studio.')
    return redirect('producer_dashboard')


# ══════════════════════════════════════════════════════════
#  HOME PAGE
# ══════════════════════════════════════════════════════════

def home(request):
    categories = Category.objects.all()
    products = Product.objects.filter(is_available=True)
    query = request.GET.get('q', '').strip()
    if query:
        products = products.filter(
            Q(name__icontains=query) |
            Q(description__icontains=query) |
            Q(category__name__icontains=query)
        )
    selected_category = request.GET.get('category', '')
    if selected_category:
        products = products.filter(category__slug=selected_category)
    min_price = request.GET.get('min_price', '')
    max_price = request.GET.get('max_price', '')
    if min_price:
        products = products.filter(price__gte=min_price)
    if max_price:
        products = products.filter(price__lte=max_price)
    sort = request.GET.get('sort', '')
    if sort == 'price_low':
        products = products.order_by('price')
    elif sort == 'price_high':
        products = products.order_by('-price')
    elif sort == 'newest':
        products = products.order_by('-created_at')
    elif sort == 'rating':
        products = products.annotate(avg_rating=Avg('reviews__rating')).order_by('-avg_rating')
    return render(request, 'store/home.html', {
        'products': products, 'categories': categories,
        'selected_category': selected_category, 'query': query,
        'min_price': min_price, 'max_price': max_price, 'sort': sort,
    })


# ══════════════════════════════════════════════════════════
#  PRODUCT DETAIL
# ══════════════════════════════════════════════════════════

def product_detail(request, slug):
    product = get_object_or_404(Product, slug=slug, is_available=True)
    related_products = Product.objects.filter(
        category=product.category, is_available=True
    ).exclude(id=product.id)[:4]
    reviews = Review.objects.filter(product=product).select_related('user').prefetch_related('images')
    avg_rating = reviews.aggregate(Avg('rating'))['rating__avg']
    in_wishlist = False
    user_review = None
    has_purchased = False
    if request.user.is_authenticated:
        in_wishlist = Wishlist.objects.filter(user=request.user, product=product).exists()
        user_review = Review.objects.filter(product=product, user=request.user).first()
        has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            product=product,
            order__status='delivered'
        ).exists()
    gallery_images = product.gallery_images.all()
    return render(request, 'store/product_detail.html', {
        'product': product,
        'related_products': related_products,
        'in_wishlist': in_wishlist,
        'reviews': reviews,
        'avg_rating': avg_rating,
        'user_review': user_review,
        'has_purchased': has_purchased,
        'gallery_images': gallery_images,
    })


# ══════════════════════════════════════════════════════════
#  PRODUCT REVIEWS
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def add_review(request, slug):
    product = get_object_or_404(Product, slug=slug)
    if request.method == 'POST':
        rating  = int(request.POST.get('rating', 5))
        comment = request.POST.get('comment', '').strip()
        has_purchased = OrderItem.objects.filter(
            order__user=request.user,
            product=product,
            order__status='delivered'
        ).exists()
        if not has_purchased:
            messages.error(request, 'You can only review products you have purchased and received.')
        elif not comment:
            messages.error(request, 'Please write a comment.')
        elif rating < 1 or rating > 5:
            messages.error(request, 'Rating must be between 1 and 5.')
        else:
            review, created = Review.objects.get_or_create(
                product=product,
                user=request.user,
                defaults={'rating': rating, 'comment': comment}
            )
            if not created:
                review.rating = rating
                review.comment = comment
                review.save()
                messages.success(request, 'Your review has been updated!')
            else:
                messages.success(request, 'Review submitted! Thank you.')

            # Handle review images (max 4)
            review_images = request.FILES.getlist('review_images')[:4]
            for img in review_images:
                ReviewImage.objects.create(review=review, image=img)

    return redirect('product_detail', slug=slug)


@login_required(login_url='login')
def delete_review(request, slug):
    product = get_object_or_404(Product, slug=slug)
    Review.objects.filter(product=product, user=request.user).delete()
    messages.success(request, 'Review deleted.')
    return redirect('product_detail', slug=slug)


# ══════════════════════════════════════════════════════════
#  WISHLIST
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def toggle_wishlist(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    wishlist_item, created = Wishlist.objects.get_or_create(user=request.user, product=product)
    if not created:
        wishlist_item.delete()
        messages.success(request, f'"{product.name}" removed from wishlist.')
    else:
        messages.success(request, f'"{product.name}" added to wishlist!')
    return redirect('product_detail', slug=product.slug)


@login_required(login_url='login')
def wishlist_page(request):
    items = Wishlist.objects.filter(user=request.user).select_related('product')
    return render(request, 'store/wishlist.html', {'items': items})


# ══════════════════════════════════════════════════════════
#  PRODUCER DASHBOARD
# ══════════════════════════════════════════════════════════

@producer_required
def producer_dashboard(request):
    products = Product.objects.filter(producer=request.user)
    total_products = products.count()
    order_items = OrderItem.objects.filter(product__producer=request.user)
    total_sales = sum(item.quantity for item in order_items)
    total_revenue = sum(item.subtotal for item in order_items)
    # Separate orders by status
    active_order_items = order_items.filter(
        order__status__in=['pending', 'processing', 'shipped']
    ).order_by('-order__created_at')

    delivered_order_items = order_items.filter(
        order__status='delivered'
    ).order_by('-order__created_at')[:20]

    cancelled_order_items = order_items.filter(
        order__status='cancelled'
    ).order_by('-order__created_at')[:20]

    cancel_return_requests = CancelReturnRequest.objects.filter(
        order__items__product__producer=request.user,
        status='pending'
    ).distinct().order_by('-created_at')

    return render(request, 'store/producer_dashboard.html', {
        'products': products,
        'total_products': total_products,
        'total_sales': total_sales,
        'total_revenue': total_revenue,
        'active_order_items': active_order_items,
        'delivered_order_items': delivered_order_items,
        'cancelled_order_items': cancelled_order_items,
        'cancel_return_requests': cancel_return_requests,
    })


@producer_required
def producer_add_product(request):
    categories = Category.objects.all()
    if request.method == 'POST':
        name        = request.POST.get('name', '').strip()
        description = request.POST.get('description', '').strip()
        price       = request.POST.get('price', '')
        stock       = request.POST.get('stock', 0)
        category_id = request.POST.get('category')
        image       = request.FILES.get('image')
        if not name or not price or not category_id:
            messages.error(request, 'Name, price and category are required.')
        else:
            slug = slugify(name)
            if Product.objects.filter(slug=slug).exists():
                slug = f"{slug}-{Product.objects.count()}"
            category = get_object_or_404(Category, id=category_id)
            product = Product.objects.create(
                name=name, slug=slug, description=description,
                price=price, stock=stock, category=category,
                image=image, producer=request.user, is_available=True,
            )
            # Handle multiple gallery images
            gallery_images = request.FILES.getlist('gallery_images')
            for img in gallery_images:
                ProductImage.objects.create(product=product, image=img)
            messages.success(request, f'"{name}" added successfully!')
            return redirect('producer_dashboard')
    return render(request, 'store/producer_add_product.html', {'categories': categories})


@producer_required
def producer_edit_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, producer=request.user)
    categories = Category.objects.all()
    if request.method == 'POST':
        product.name        = request.POST.get('name', product.name).strip()
        product.description = request.POST.get('description', product.description).strip()
        product.price       = request.POST.get('price', product.price)
        product.stock       = request.POST.get('stock', product.stock)
        category_id         = request.POST.get('category')
        product.is_available = request.POST.get('is_available') == 'on'
        if category_id:
            product.category = get_object_or_404(Category, id=category_id)
        if request.FILES.get('image'):
            product.image = request.FILES.get('image')
        product.save()

        # Handle new gallery images
        gallery_images = request.FILES.getlist('gallery_images')
        for img in gallery_images:
            ProductImage.objects.create(product=product, image=img)

        # Handle deletion of selected gallery images
        delete_ids = request.POST.getlist('delete_images')
        if delete_ids:
            ProductImage.objects.filter(id__in=delete_ids, product=product).delete()

        messages.success(request, f'"{product.name}" updated successfully!')
        return redirect('producer_dashboard')
    gallery_images = product.gallery_images.all()
    return render(request, 'store/producer_edit_product.html', {
        'product': product, 'categories': categories, 'gallery_images': gallery_images,
    })


@producer_required
def producer_delete_product(request, product_id):
    product = get_object_or_404(Product, id=product_id, producer=request.user)
    if request.method == 'POST':
        name = product.name
        product.delete()
        messages.success(request, f'"{name}" deleted successfully!')
    return redirect('producer_dashboard')


@producer_required
def update_order_status(request, order_id):
    order = get_object_or_404(Order, id=order_id)
    if request.method == 'POST':
        new_status = request.POST.get('status')
        status_messages = {
            'pending': 'Order received and pending confirmation.',
            'processing': 'Seller is packing your order.',
            'shipped': 'Your order has been shipped and is on the way.',
            'delivered': 'Order delivered successfully.',
            'cancelled': 'Order has been cancelled by the seller.',
        }
        if new_status in status_messages:
            order.status = new_status
            order.save()
            OrderTracking.objects.create(
                order=order,
                status=new_status,
                message=status_messages[new_status],
            )
            messages.success(request, f'Order #{order.id} updated to {new_status.title()}!')
    return redirect('producer_dashboard')


@producer_required
def handle_cancel_return(request, request_id):
    cr_request = get_object_or_404(CancelReturnRequest, id=request_id)
    if request.method == 'POST':
        action = request.POST.get('action')
        producer_note = request.POST.get('producer_note', '').strip()
        if action == 'approve':
            cr_request.status = 'approved'
            cr_request.producer_note = producer_note
            cr_request.save()
            if cr_request.request_type == 'cancel':
                cr_request.order.status = 'cancelled'
                cr_request.order.save()
                OrderTracking.objects.create(
                    order=cr_request.order,
                    status='cancelled',
                    message='Order cancelled — approved by seller.',
                )
            elif cr_request.request_type == 'return':
                OrderTracking.objects.create(
                    order=cr_request.order,
                    status='return approved',
                    message='Return request approved by seller.',
                )
            messages.success(request, f'{cr_request.request_type.title()} request approved!')
        elif action == 'reject':
            cr_request.status = 'rejected'
            cr_request.producer_note = producer_note
            cr_request.save()
            messages.success(request, f'{cr_request.request_type.title()} request rejected.')
    return redirect('producer_dashboard')


# ══════════════════════════════════════════════════════════
#  CHECKOUT
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def checkout(request):
    buy_now_product_id = request.session.get('buy_now_product_id')
    buy_now_quantity = request.session.get('buy_now_quantity', 1)

    if buy_now_product_id:
        # Buy Now flow — single product, not from cart
        product = get_object_or_404(Product, id=buy_now_product_id)
        cart_items = None
        checkout_items = [{'product': product, 'quantity': buy_now_quantity, 'subtotal': product.price * buy_now_quantity}]
        total = product.price * buy_now_quantity
        is_buy_now = True
    else:
        cart_items = Cart.objects.filter(user=request.user).select_related('product')
        if not cart_items:
            messages.error(request, 'Your cart is empty!')
            return redirect('cart_page')
        checkout_items = [{'product': item.product, 'quantity': item.quantity, 'subtotal': item.subtotal} for item in cart_items]
        total = sum(item.subtotal for item in cart_items)
        is_buy_now = False

    if request.method == 'POST':
        full_name = request.POST.get('full_name', '').strip()
        address   = request.POST.get('address', '').strip()
        city      = request.POST.get('city', '').strip()
        state     = request.POST.get('state', '').strip()
        zipcode   = request.POST.get('zipcode', '').strip()
        phone     = request.POST.get('phone', '').strip()
        payment   = request.POST.get('payment_method', 'cod')
        if not full_name or not address or not city or not state or not zipcode:
            messages.error(request, 'Please fill all required fields.')
        else:
            order = Order.objects.create(
                user=request.user,
                status='pending',
                is_complete=(payment == 'cod'),  # COD orders are immediately confirmed
            )
            for item in checkout_items:
                OrderItem.objects.create(
                    order=order, product=item['product'],
                    quantity=item['quantity'], price=item['product'].price,
                )
            ShippingAddress.objects.create(
                order=order, full_name=full_name, address=address,
                city=city, state=state, zipcode=zipcode, phone=phone,
            )
            OrderTracking.objects.create(
                order=order,
                status='pending',
                message='Order placed successfully. Waiting for seller confirmation.',
            )

            if is_buy_now:
                # Clear buy now session data
                request.session.pop('buy_now_product_id', None)
                request.session.pop('buy_now_quantity', None)
            else:
                cart_items.delete()

            if payment == 'razorpay':
                return redirect('razorpay_payment', order_id=order.id)
            return redirect('order_confirmation', order_id=order.id)

    return render(request, 'store/checkout.html', {
        'cart_items': checkout_items, 'total': total, 'is_buy_now': is_buy_now,
    })


@login_required(login_url='login')
def buy_now(request, product_id):
    """Skip the cart entirely — go straight to checkout for one product."""
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1)) if request.method == 'POST' else 1

    if not product.in_stock:
        messages.error(request, f'"{product.name}" is out of stock.')
        return redirect('product_detail', slug=product.slug)

    request.session['buy_now_product_id'] = product.id
    request.session['buy_now_quantity'] = quantity
    request.session.modified = True
    request.session.save()
    return redirect('checkout')


@login_required(login_url='login')
def order_confirmation(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    return render(request, 'store/order_confirmation.html', {'order': order})


@login_required(login_url='login')
def razorpay_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    client = razorpay.Client(auth=(settings.RAZORPAY_KEY_ID, settings.RAZORPAY_KEY_SECRET))
    amount_paise = int(order.total_price * 100)

    razorpay_order = client.order.create({
        'amount': amount_paise,
        'currency': 'INR',
        'receipt': f'order_rcptid_{order.id}',
        'payment_capture': 1,
    })

    return render(request, 'store/razorpay_payment.html', {
        'order': order,
        'amount': amount_paise,
        'razorpay_key': settings.RAZORPAY_KEY_ID,
        'razorpay_order_id': razorpay_order['id'],
    })


@login_required(login_url='login')
def verify_payment(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    if request.method == 'POST':
        razorpay_payment_id = request.POST.get('razorpay_payment_id', '')
        razorpay_order_id   = request.POST.get('razorpay_order_id', '')
        razorpay_signature  = request.POST.get('razorpay_signature', '')

        # Verify signature using HMAC-SHA256 (Razorpay's official method)
        generated_signature = hmac.new(
            key=bytes(settings.RAZORPAY_KEY_SECRET, 'utf-8'),
            msg=bytes(f'{razorpay_order_id}|{razorpay_payment_id}', 'utf-8'),
            digestmod=hashlib.sha256
        ).hexdigest()

        if generated_signature == razorpay_signature:
            order.is_complete = True
            order.save()
            OrderTracking.objects.create(
                order=order,
                status='pending',
                message=f'Payment received via Razorpay (Payment ID: {razorpay_payment_id}).',
            )
            messages.success(request, 'Payment successful! Your order is confirmed.')
            return redirect('order_confirmation', order_id=order.id)
        else:
            messages.error(request, 'Payment verification failed. Please contact support if money was deducted.')
            return redirect('razorpay_payment', order_id=order.id)

    return redirect('razorpay_payment', order_id=order.id)


# ══════════════════════════════════════════════════════════
#  DIRECT CANCEL — Only for PENDING orders
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def direct_cancel_order(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status != 'pending':
        messages.error(request, 'You can only cancel a pending order directly.')
        return redirect('order_tracking', order_id=order.id)
    if request.method == 'POST':
        order.status = 'cancelled'
        order.save()
        OrderTracking.objects.create(
            order=order,
            status='cancelled',
            message='Order cancelled by customer.',
        )
        messages.success(request, f'Order #{order.id} has been cancelled successfully.')
        return redirect('buyer_dashboard')
    return render(request, 'store/confirm_cancel.html', {'order': order})


# ══════════════════════════════════════════════════════════
#  CANCEL/RETURN REQUEST — For processing/shipped/delivered
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def cancel_return_request(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    if order.status == 'pending':
        return redirect('direct_cancel_order', order_id=order.id)
    if order.status == 'cancelled':
        messages.error(request, 'This order is already cancelled.')
        return redirect('order_tracking', order_id=order.id)
    existing = CancelReturnRequest.objects.filter(order=order, user=request.user).first()
    if existing:
        messages.error(request, 'You already have a pending request for this order.')
        return redirect('order_tracking', order_id=order.id)
    if request.method == 'POST':
        request_type = request.POST.get('request_type')
        reason = request.POST.get('reason', '').strip()
        if not reason:
            messages.error(request, 'Please provide a reason.')
        elif request_type not in ['cancel', 'return']:
            messages.error(request, 'Invalid request type.')
        elif request_type == 'return' and order.status != 'delivered':
            messages.error(request, 'Return requests are only allowed for delivered orders.')
        elif request_type == 'cancel' and order.status == 'delivered':
            messages.error(request, 'Cannot cancel a delivered order. Please request a return instead.')
        else:
            CancelReturnRequest.objects.create(
                order=order, user=request.user,
                request_type=request_type, reason=reason,
            )
            messages.success(request, f'Your {request_type} request has been submitted. The seller will review it shortly.')
            return redirect('order_tracking', order_id=order.id)
    return render(request, 'store/cancel_return_request.html', {'order': order})


# ══════════════════════════════════════════════════════════
#  ORDER TRACKING
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def order_tracking(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)
    tracking_history = OrderTracking.objects.filter(order=order).order_by('timestamp')
    stages = ['pending', 'processing', 'shipped', 'delivered']
    current_index = stages.index(order.status) if order.status in stages else 0
    existing_request = CancelReturnRequest.objects.filter(order=order, user=request.user).first()
    return render(request, 'store/order_tracking.html', {
        'order': order,
        'tracking_history': tracking_history,
        'stages': stages,
        'current_index': current_index,
        'existing_request': existing_request,
    })


# ══════════════════════════════════════════════════════════
#  CONSUMER DASHBOARD
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def buyer_dashboard(request):
    orders = Order.objects.filter(user=request.user).prefetch_related('items__product')
    wishlist = Wishlist.objects.filter(user=request.user).select_related('product')
    all_products = Product.objects.filter(is_available=True).select_related('category', 'producer')
    return render(request, 'store/buyer_dashboard.html', {
        'orders': orders,
        'wishlist': wishlist,
        'all_products': all_products,
    })


# ══════════════════════════════════════════════════════════
#  INVOICE PDF DOWNLOAD
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def download_invoice(request, order_id):
    order = get_object_or_404(Order, id=order_id, user=request.user)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = styles['Title']
    title_style.textColor = colors.HexColor('#0a0a0a')
    elements.append(Paragraph("JET — INVOICE", title_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"Order #{order.id}", styles['Heading3']))
    elements.append(Paragraph(f"Date: {order.created_at.strftime('%d %B %Y, %I:%M %p')}", styles['Normal']))
    elements.append(Paragraph(f"Status: {order.status.title()}", styles['Normal']))
    elements.append(Spacer(1, 12))

    if hasattr(order, 'shipping_address'):
        addr = order.shipping_address
        elements.append(Paragraph("<b>Billing / Shipping Address</b>", styles['Heading4']))
        elements.append(Paragraph(addr.full_name, styles['Normal']))
        elements.append(Paragraph(addr.address, styles['Normal']))
        elements.append(Paragraph(f"{addr.city}, {addr.state} - {addr.zipcode}", styles['Normal']))
        elements.append(Paragraph(addr.country, styles['Normal']))
        if addr.phone:
            elements.append(Paragraph(f"Phone: {addr.phone}", styles['Normal']))
        elements.append(Spacer(1, 12))

    data = [['Product', 'Qty', 'Price', 'Subtotal']]
    for item in order.items.all():
        data.append([
            item.product.name,
            str(item.quantity),
            f"Rs. {item.price}",
            f"Rs. {item.subtotal}",
        ])
    data.append(['', '', 'Total', f"Rs. {order.total_price}"])

    table = Table(data, colWidths=[80*mm, 25*mm, 35*mm, 35*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a0a0a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f2f2f0')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e8e8e4')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("Thank you for shopping with JET Marketplace!", styles['Normal']))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="JET_Invoice_Order_{order.id}.pdf"'
    return response


@login_required(login_url='login')
def download_invoice_producer(request, order_id):
    """Allow producer (or admin) to download invoice for an order containing their products."""
    order = get_object_or_404(Order, id=order_id)

    is_admin = request.user.is_superuser
    has_product = OrderItem.objects.filter(order=order, product__producer=request.user).exists()

    if not (is_admin or has_product):
        messages.error(request, 'You do not have permission to view this invoice.')
        return redirect('producer_dashboard')

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, topMargin=20*mm, bottomMargin=20*mm)
    styles = getSampleStyleSheet()
    elements = []

    title_style = styles['Title']
    title_style.textColor = colors.HexColor('#0a0a0a')
    elements.append(Paragraph("JET — INVOICE (Seller Copy)", title_style))
    elements.append(Spacer(1, 6))
    elements.append(Paragraph(f"Order #{order.id}", styles['Heading3']))
    elements.append(Paragraph(f"Customer: {order.user.username}", styles['Normal']))
    elements.append(Paragraph(f"Date: {order.created_at.strftime('%d %B %Y, %I:%M %p')}", styles['Normal']))
    elements.append(Paragraph(f"Status: {order.status.title()}", styles['Normal']))
    elements.append(Spacer(1, 12))

    if hasattr(order, 'shipping_address'):
        addr = order.shipping_address
        elements.append(Paragraph("<b>Shipping Address</b>", styles['Heading4']))
        elements.append(Paragraph(addr.full_name, styles['Normal']))
        elements.append(Paragraph(addr.address, styles['Normal']))
        elements.append(Paragraph(f"{addr.city}, {addr.state} - {addr.zipcode}", styles['Normal']))
        elements.append(Paragraph(addr.country, styles['Normal']))
        if addr.phone:
            elements.append(Paragraph(f"Phone: {addr.phone}", styles['Normal']))
        elements.append(Spacer(1, 12))

    # Filter items: producer sees only their own products, admin sees all
    if is_admin:
        items = order.items.all()
    else:
        items = order.items.filter(product__producer=request.user)

    data = [['Product', 'Qty', 'Price', 'Subtotal']]
    item_total = 0
    for item in items:
        data.append([
            item.product.name,
            str(item.quantity),
            f"Rs. {item.price}",
            f"Rs. {item.subtotal}",
        ])
        item_total += item.subtotal
    data.append(['', '', 'Total', f"Rs. {item_total}"])

    table = Table(data, colWidths=[80*mm, 25*mm, 35*mm, 35*mm])
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#0a0a0a')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTNAME', (0, -1), (-1, -1), 'Helvetica-Bold'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#f2f2f0')),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e8e8e4')),
        ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)
    elements.append(Spacer(1, 20))
    elements.append(Paragraph("JET Marketplace — Seller Invoice Copy", styles['Normal']))

    doc.build(elements)
    pdf = buffer.getvalue()
    buffer.close()

    response = HttpResponse(pdf, content_type='application/pdf')
    response['Content-Disposition'] = f'attachment; filename="JET_Seller_Invoice_Order_{order.id}.pdf"'
    return response


# ══════════════════════════════════════════════════════════
#  ADMIN ANALYTICS DASHBOARD (superuser only)
# ══════════════════════════════════════════════════════════

@user_passes_test(lambda u: u.is_superuser, login_url='login')
def admin_analytics(request):
    total_orders = Order.objects.count()
    total_revenue = sum(o.total_price for o in Order.objects.exclude(status='cancelled'))
    total_users = User.objects.count()
    total_products = Product.objects.count()
    low_stock_products = Product.objects.filter(stock__lt=5, is_available=True)

    thirty_days_ago = timezone.now() - timedelta(days=30)
    daily_revenue = {}
    for order in Order.objects.filter(created_at__gte=thirty_days_ago).exclude(status='cancelled'):
        day = order.created_at.date().isoformat()
        daily_revenue[day] = daily_revenue.get(day, 0) + float(order.total_price)

    sales_labels = sorted(daily_revenue.keys())
    sales_values = [round(daily_revenue[d], 2) for d in sales_labels]

    top_products = (
        OrderItem.objects.values('product__name')
        .annotate(total_sold=Sum('quantity'), total_rev=Sum(F('price') * F('quantity')))
        .order_by('-total_sold')[:5]
    )

    status_breakdown = (
        Order.objects.values('status')
        .annotate(count=Count('id'))
        .order_by('-count')
    )

    recent_users = User.objects.order_by('-date_joined')[:5]

    category_revenue = (
        OrderItem.objects.values('product__category__name')
        .annotate(revenue=Sum(F('price') * F('quantity')))
        .order_by('-revenue')[:6]
    )

    return render(request, 'store/admin_analytics.html', {
        'total_orders': total_orders,
        'total_revenue': total_revenue,
        'total_users': total_users,
        'total_products': total_products,
        'low_stock_products': low_stock_products,
        'sales_labels': sales_labels,
        'sales_values': sales_values,
        'top_products': top_products,
        'status_breakdown': status_breakdown,
        'recent_users': recent_users,
        'category_revenue': category_revenue,
    })



# ══════════════════════════════════════════════════════════
#  CHAT — Per-product buyer-seller chat
# ══════════════════════════════════════════════════════════

@login_required(login_url='login')
def start_chat(request, slug):
    """Buyer clicks 'Chat with Seller' on a product page."""
    product = get_object_or_404(Product, slug=slug)
    if not product.producer:
        messages.error(request, 'This product has no seller to chat with.')
        return redirect('product_detail', slug=slug)
    if request.user == product.producer:
        messages.error(request, 'You cannot chat with yourself.')
        return redirect('product_detail', slug=slug)

    room, created = ChatRoom.objects.get_or_create(product=product, buyer=request.user)
    return redirect('chat_room', room_id=room.id)


@login_required(login_url='login')
def chat_room(request, room_id):
    room = get_object_or_404(ChatRoom, id=room_id)
    # Only buyer or seller can access
    if request.user != room.buyer and request.user != room.seller:
        messages.error(request, 'You do not have access to this chat.')
        return redirect('home')

    # Get messages excluding ones this user deleted for themselves
    deleted_ids = DeletedMessage.objects.filter(
        user=request.user
    ).values_list('message_id', flat=True)
    chat_messages = room.messages.select_related('sender').exclude(id__in=deleted_ids)
    # Mark messages from the other person as read
    room.messages.filter(is_read=False).exclude(sender=request.user).update(is_read=True)

    other_user = room.seller if request.user == room.buyer else room.buyer

    return render(request, 'store/chat_room.html', {
        'room': room,
        'chat_messages': chat_messages,
        'other_user': other_user,
    })


@login_required(login_url='login')
def chat_inbox(request):
    """List all chat rooms for the current user — as buyer or as seller."""
    buyer_rooms = ChatRoom.objects.filter(buyer=request.user).select_related('product', 'product__producer')
    seller_rooms = ChatRoom.objects.filter(product__producer=request.user).select_related('product', 'buyer')

    # Annotate unread counts
    rooms_data = []
    for room in buyer_rooms:
        unread = room.messages.filter(is_read=False).exclude(sender=request.user).count()
        rooms_data.append({'room': room, 'other_user': room.seller, 'role': 'buyer', 'unread': unread})
    for room in seller_rooms:
        unread = room.messages.filter(is_read=False).exclude(sender=request.user).count()
        rooms_data.append({'room': room, 'other_user': room.buyer, 'role': 'seller', 'unread': unread})

    rooms_data.sort(key=lambda r: r['room'].messages.last().timestamp if r['room'].messages.exists() else r['room'].created_at, reverse=True)

    return render(request, 'store/chat_inbox.html', {'rooms_data': rooms_data})


@login_required(login_url='login')
def delete_chat_message(request, message_id):
    """Delete a message for me only, or for everyone."""
    msg = get_object_or_404(ChatMessage, id=message_id)
    room = msg.room

    if request.user != room.buyer and request.user != room.seller:
        messages.error(request, 'You do not have permission.')
        return redirect('chat_room', room_id=room.id)

    if request.method == 'POST':
        delete_type = request.POST.get('delete_type', 'me')
        if delete_type == 'everyone':
            # Hard delete — removes for both sides
            msg.delete()
            messages.success(request, 'Message deleted for everyone.')
        else:
            # Soft delete — only hides for current user
            DeletedMessage.objects.get_or_create(message=msg, user=request.user)
            messages.success(request, 'Message deleted for you.')

    return redirect('chat_room', room_id=room.id)


@login_required(login_url='login')
def delete_chat_room(request, room_id):
    """Delete entire conversation — only buyer or seller can do this."""
    room = get_object_or_404(ChatRoom, id=room_id)

    if request.user != room.buyer and request.user != room.seller:
        messages.error(request, 'You do not have permission to delete this conversation.')
        return redirect('chat_inbox')

    if request.method == 'POST':
        room.delete()
        messages.success(request, 'Conversation deleted.')
        return redirect('chat_inbox')

    return render(request, 'store/confirm_delete_chat.html', {'room': room})