from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Cart
from store.models import Product


@login_required(login_url='login')
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))

    cart_item, created = Cart.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': quantity}
    )

    if not created:
        cart_item.quantity += quantity
        cart_item.save()
        messages.success(request, f'"{product.name}" quantity updated in your bag.')
    else:
        messages.success(request, f'"{product.name}" added to your bag!')

    return redirect('cart_page')


@login_required(login_url='login')
def cart_page(request):
    cart_items = Cart.objects.filter(user=request.user).select_related('product')
    total = sum(item.subtotal for item in cart_items)
    total_items = sum(item.quantity for item in cart_items)

    return render(request, 'store/cart.html', {
        'cart_items': cart_items,
        'total': total,
        'total_items': total_items,
    })


@login_required(login_url='login')
def update_cart(request, cart_id):
    cart_item = get_object_or_404(Cart, id=cart_id, user=request.user)
    quantity = int(request.POST.get('quantity', 1))

    if quantity > 0:
        cart_item.quantity = quantity
        cart_item.save()
        messages.success(request, 'Cart updated.')
    else:
        cart_item.delete()
        messages.success(request, 'Item removed from cart.')

    return redirect('cart_page')


@login_required(login_url='login')
def remove_from_cart(request, cart_id):
    cart_item = get_object_or_404(Cart, id=cart_id, user=request.user)
    cart_item.delete()
    messages.success(request, f'"{cart_item.product.name}" removed from your bag.')
    return redirect('cart_page')