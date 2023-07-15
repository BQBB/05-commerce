from typing import List

from django.contrib.auth import get_user_model
from django.db.models import Q
from django.shortcuts import get_object_or_404
from ninja import Router
from pydantic import UUID4
from commerce.utils import gen_ref_code
from account.authorization import GlobalAuth
from config.utils.schemas import MessageOut

from commerce.models import OrderStatus, Product, Category, City, Vendor, Item, Address, Order
from commerce.schemas import OrderCheckout, AddressCreate, AddressOut, ProductOut, CitiesOut, CitySchema, \
    VendorOut, ItemOut, ItemSchema, ItemCreate
from config.utils.decorators import check_pk


products_controller = Router(tags=['products'])
address_controller = Router(tags=['addresses'])
vendor_controller = Router(tags=['vendors'])
order_controller = Router(tags=['orders'])

User = get_user_model()

@vendor_controller.get('', response=List[VendorOut])
def list_vendors(request):
    return Vendor.objects.all()


@products_controller.get('', response={
    200: List[ProductOut],
    404: MessageOut
})
def list_products(
        request, *,
        q: str = None,
        price_from: int = None,
        price_to: int = None,
        vendor=None,
):
    products_qs = Product.objects.filter(is_active=True).select_related('merchant', 'vendor', 'category', 'label')

    if not products_qs:
        return 404, {'detail': 'No products found'}

    if q:
        products_qs = products_qs.filter(
            Q(name__icontains=q) | Q(description__icontains=q)
        )

    if price_from:
        products_qs = products_qs.filter(discounted_price__gte=price_from)

    if price_to:
        products_qs = products_qs.filter(discounted_price__lte=price_to)

    if vendor:
        products_qs = products_qs.filter(vendor_id=vendor)

    return products_qs


"""
# product = Product.objects.all().select_related('merchant', 'category', 'vendor', 'label')
    # print(product)
    #
    # order = Product.objects.all().select_related('address', 'user').prefetch_related('items')
    # try:
    #     one_product = Product.objects.get(id='8d3dd0f1-2910-457c-89e3-1b0ed6aa720a')
    # except Product.DoesNotExist:
    #     return {"detail": "Not found"}
    # print(one_product)
    #
    # shortcut_function = get_object_or_404(Product, id='8d3dd0f1-2910-457c-89e3-1b0ed6aa720a')
    # print(shortcut_function)
    # print(type(product))
    # print(product.merchant.name)
    # print(type(product.merchant))
    # print(type(product.category))
Product <- Merchant, Label, Category, Vendor
Retrieve 1000 Products form DB
products = Product.objects.all()[:1000] (select * from product limit 1000)
for p in products:
    print(p)

for every product, we retrieve (Merchant, Label, Category, Vendor) records
Merchant.objects.get(id=p.merchant_id) (select * from merchant where id = 'p.merchant_id')
Label.objects.get(id=p.label_id) (select * from merchant where id = 'p.label_id')
Category.objects.get(id=p.category_id) (select * from merchant where id = 'p.category_id')
Vendor.objects.get(id=p.vendor_id) (select * from merchant where id = 'p.vendor_id')
4*1000+1
Solution: Eager loading
products = (select * from product limit 1000)
mids = [p1.merchant_id, p2.merchant_id, ...]
[p1.label_id, p2.label_id, ...]
.
.
.
select * from merchant where id in (mids) * 4 for (label, category and vendor)
4+1
"""


@address_controller.get('', response={
    200: List[AddressOut],
    404: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def list_addresses(request):
    
    if addresses := Address.objects.select_related('city', 'user').filter(
        user=User.objects.get(id=request.auth['pk'])
    ):
        return addresses
    return 404, {'detail': 'No addresses found'}


# @products_controller.get('categories', response=List[CategoryOut])
# def list_categories(request):
#     return Category.objects.all()


@address_controller.get('cities', response={
    200: List[CitiesOut],
    404: MessageOut
})
def list_cities(request):
    if cities_qs := City.objects.all():
        return cities_qs

    return 404, {'detail': 'No cities found'}


@address_controller.get('cities/{id}', response={
    200: CitiesOut,
    404: MessageOut
})
def retrieve_city(request, id: UUID4):
    return get_object_or_404(City, id=id)


@address_controller.post('cities', response={
    201: CitiesOut,
    400: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def create_city(request, city_in: CitySchema):
    
    city = City(**city_in.dict())
    city.save()
    return 201, city


@address_controller.put('cities/{id}', response={
    200: CitiesOut,
    400: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def update_city(request, id: UUID4, city_in: CitySchema):
    
    city = get_object_or_404(City, id=id)
    city.name = city_in.name
    city.save()
    return 200, city


@address_controller.delete('cities/{id}', response={
    204: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def delete_city(request, id: UUID4):
    
    city = get_object_or_404(City, id=id)
    city.delete()
    return 204, {'detail': ''}


@order_controller.get('cart', response={
    200: List[ItemOut],
    404: MessageOut,
    401: MessageOut
})
@check_pk
def view_cart(request):
    
    if cart_items := Item.objects.filter(
        user=User.objects.get(id=request.auth['pk']), ordered=False
    ):
        return cart_items

    return 404, {'detail': 'Your cart is empty, go shop like crazy!'}


@order_controller.post('add-to-cart', response={
    200: MessageOut,
    400: MessageOut,
    401: MessageOut
})
@check_pk
def add_update_cart(request, item_in: ItemCreate):
    
    try:
        item = Item.objects.get(product_id=item_in.product_id, user=User.objects.get(id=request.auth['pk']), ordered=False)
        if item_in.item_qty > 0:
            item.item_qty += item_in.item_qty
        item.save()
    except Item.DoesNotExist:
        if item_in.item_qty < 1:
            return 400, {'detail': 'Quantity Value Must be Greter Than Zero'}
        item = Item.objects.create(**item_in.dict(), user=User.objects.get(id=request.auth['pk']))
    return 200, {'detail': 'Added to cart successfully'}


@order_controller.post('item/{id}/reduce-quantity', response={
    200: MessageOut,
    401: MessageOut
})
@check_pk
def reduce_item_quantity(request, id: UUID4):
    
    item = get_object_or_404(Item, id=id, user=User.objects.get(id=request.auth['pk']), ordered=False)
    if item.item_qty <= 1:
        item.delete()
        return 200, {'detail': 'Item deleted!'}
    item.item_qty -= 1
    item.save()

    return 200, {'detail': 'Item quantity reduced successfully!'}


@order_controller.delete('item/{id}', response={
    204: MessageOut,
    401: MessageOut
})
@check_pk
def delete_item(request, id: UUID4):
    
    item = get_object_or_404(Item, id=id, user=User.objects.get(id=request.auth['pk']), ordered=False)
    item.delete()
    return 204, {'detail': 'Item deleted!'}


@order_controller.post('item/{id}/increase-quantity', response={
    200: MessageOut,
    401: MessageOut
})
@check_pk
def increase_item_quantity(request, id: UUID4):
    
    item = get_object_or_404(Item, id=id, user=User.objects.get(id=request.auth['pk']), ordered=False)
    item.item_qty += 1
    item.save()
    return 200, {'detail': 'Item quantity increased successfully!'}


@address_controller.get('{id}', response={
    200: AddressOut,
    404: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def retrieve_address(request, id: UUID4):
    
    return get_object_or_404(Address, id=id, user=User.objects.get(id=request.auth['pk']))


@address_controller.post('', response={
    201: AddressOut,
    400: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def create_address(request, address_in: AddressCreate):
    
    return 201, Address.objects.create(**address_in.dict(), user=User.objects.get(id=request.auth['pk']))


@address_controller.put('{id}', response={
    200: AddressOut,
    400: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def update_address(request, id: UUID4, address_in: AddressCreate):
    
    address = get_object_or_404(Address, id=id, user=User.objects.get(id=request.auth['pk']))
    for k, v in address_in.dict().items():
        setattr(address, k, v)
    address.save()
    return 200, address


@address_controller.delete('{id}', response={
    204: MessageOut,
    401: MessageOut
}, auth=GlobalAuth())
@check_pk
def delete_address(request, id: UUID4):
    
    address = get_object_or_404(Address, id=id, user=User.objects.get(id=request.auth['pk']))
    address.delete()
    return 204, {'detail': ''}


@order_controller.post('create', response={
    200: MessageOut,
    404: MessageOut,
    401: MessageOut
})
@check_pk
def create_update_order(request):
    
    user = User.objects.prefetch_related('items', 'orders').get(id=request.auth['pk'])
    user_items = user.items.filter(ordered=False)
    if not user_items:
        return 404, {'detail': 'No Items Found To added to Order'}

    try:

        order = user.orders.prefetch_related('items').get(ordered=False)
        list_of_productID_in_order = [item['product_id'] for item in order.items.values('product_id')]
        list_of_difference_items = []
        list_of_intersection_items = [
            (item, item.item_qty) if item.product_id in list_of_productID_in_order else list_of_difference_items.append(
                item.id) for item in user_items]
        Item.objects.filter(id__in=list_of_difference_items).update(ordered=True)

        for item, qty in list(filter(None, list_of_intersection_items)):
            item_duplicated = order.items.get(product_id=item.product_id)
            item_duplicated.item_qty = item_duplicated.item_qty + qty
            item_duplicated.save()
            item.delete()

        order.items.add(*list_of_difference_items)
        order.total = order.order_total
        order.save()
        return 200, {'detail': 'order updated successfully!'}
    except Order.DoesNotExist:
        order_status, _ = OrderStatus.objects.get_or_create(title='NEW', is_default=True)
        order = Order.objects.create(user=user, status=order_status, ref_code=gen_ref_code(6), ordered=False)
        order.items.set(user_items)
        order.total = order.order_total
        user_items.update(ordered=True)
        order.save()
        return 200, {'detail': 'Order Created Successfully!'}


@order_controller.post('checkout', response={
    200: MessageOut,
    404: MessageOut,
    400: MessageOut,
    401: MessageOut
})
@check_pk
def checkout_order(request, order_in: OrderCheckout):
    
    order_status, _ = OrderStatus.objects.get_or_create(title='SHIPPED', is_default=False)
    try:
        order = Order.objects.get(user=User.objects.get(id=request.auth['pk']), ordered=False)
    except Order.DoesNotExist:
        return 404, {'detail': 'Order Does\'nt Found'}
    order.ordered = True
    order.status = order_status
    for k, v in order_in.dict().items():
        setattr(order, k, v)
    order.save()
    return 200, {'detail': 'checkout successfully!'}