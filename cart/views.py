from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from .models import Cart
from store.models import Product


@login_required(login_url='login')
def cart_page(request):
    cart_items = Cart.objects.filter(user=request.user).select_related('product')
    total = sum(item.subtotal for item in cart_items)
    return render(request, 'cart/cart.html', {'cart_items': cart_items, 'total': total})


@login_required(login_url='login')
def add_to_cart(request, product_id):
    product = get_object_or_404(Product, id=product_id)
    quantity = int(request.POST.get('quantity', 1))

    if not product.in_stock:
        messages.error(request, f'"{product.name}" is out of stock.')
        return redirect('product_detail', slug=product.slug)

    cart_item, created = Cart.objects.get_or_create(
        user=request.user,
        product=product,
        defaults={'quantity': quantity}
    )
    if not created:
        cart_item.quantity += quantity
        cart_item.save()

    messages.success(request, f'"{product.name}" added to your bag!')
    return redirect('product_detail', slug=product.slug)


@login_required(login_url='login')
def update_cart_item(request, item_id):
    cart_item = get_object_or_404(Cart, id=item_id, user=request.user)
    if request.method == 'POST':
        action = request.POST.get('action')
        if action == 'increase':
            cart_item.quantity += 1
            cart_item.save()
        elif action == 'decrease':
            if cart_item.quantity > 1:
                cart_item.quantity -= 1
                cart_item.save()
            else:
                cart_item.delete()
    return redirect('cart_page')


@login_required(login_url='login')
def remove_from_cart(request, item_id):
    cart_item = get_object_or_404(Cart, id=item_id, user=request.user)
    cart_item.delete()
    messages.success(request, 'Item removed from bag.')
    return redirect('cart_page')