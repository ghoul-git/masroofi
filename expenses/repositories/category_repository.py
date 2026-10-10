from expenses.models import Category

# Categories are shared by all users (the model has no user field),
# so these queries are the only ones that do not filter by user.


def list_all():
    return Category.objects.order_by("name")


def list_names() -> list[str]:
    return list(Category.objects.order_by("name").values_list("name", flat=True))


def get(category_id) -> Category | None:
    return Category.objects.filter(pk=category_id).first()


def get_by_name(name: str) -> Category | None:
    return Category.objects.filter(name__iexact=name).first()
