from expenses.repositories import category_repository


def list_categories():
    return category_repository.list_all()
