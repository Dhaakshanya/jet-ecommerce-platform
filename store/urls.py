from django.urls import path
from . import views

urlpatterns = [
    path('', views.home, name='home'),
    path('product/<slug:slug>/', views.product_detail, name='product_detail'),

    # Auth
    path('register/',        views.register,        name='register'),
    path('login/',           views.user_login,      name='login'),
    path('logout/',          views.logout_view,     name='logout'),
    path('become-producer/', views.become_producer, name='become_producer'),

    # Producer
    path('producer/dashboard/',                          views.producer_dashboard,     name='producer_dashboard'),
    path('producer/product/add/',                        views.producer_add_product,   name='producer_add_product'),
    path('producer/product/edit/<int:product_id>/',      views.producer_edit_product,  name='producer_edit_product'),
    path('producer/product/delete/<int:product_id>/',    views.producer_delete_product,name='producer_delete_product'),
    path('producer/order/update/<int:order_id>/',        views.update_order_status,    name='update_order_status'),
    path('producer/request/handle/<int:request_id>/',    views.handle_cancel_return,   name='handle_cancel_return'),

    # Consumer
    path('dashboard/',                           views.buyer_dashboard,        name='buyer_dashboard'),
    path('order/tracking/<int:order_id>/',       views.order_tracking,         name='order_tracking'),
    path('order/cancel/<int:order_id>/',         views.direct_cancel_order,    name='direct_cancel_order'),
    path('order/cancel-return/<int:order_id>/',  views.cancel_return_request,  name='cancel_return_request'),
    path('order/invoice/<int:order_id>/',        views.download_invoice,       name='download_invoice'),
    path('producer/invoice/<int:order_id>/',     views.download_invoice_producer, name='download_invoice_producer'),

    # Reviews
    path('product/<slug:slug>/review/add/',    views.add_review,    name='add_review'),
    path('product/<slug:slug>/review/delete/', views.delete_review, name='delete_review'),

    # Wishlist
    path('wishlist/',                         views.wishlist_page,   name='wishlist_page'),
    path('wishlist/toggle/<int:product_id>/', views.toggle_wishlist, name='toggle_wishlist'),

    # Checkout
    path('checkout/',                          views.checkout,           name='checkout'),
    path('order/confirmation/<int:order_id>/', views.order_confirmation, name='order_confirmation'),
    path('order/payment/<int:order_id>/',      views.razorpay_payment,   name='razorpay_payment'),
    path('order/payment/verify/<int:order_id>/', views.verify_payment,    name='verify_payment'),

    # Chat
    path('chat/start/<slug:slug>/',  views.start_chat,  name='start_chat'),
    path('chat/room/<int:room_id>/', views.chat_room,   name='chat_room'),
    path('chat/inbox/',              views.chat_inbox,  name='chat_inbox'),

    # Admin Analytics
    path('admin-analytics/', views.admin_analytics, name='admin_analytics'),
]