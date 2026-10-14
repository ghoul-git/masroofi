def delete(user) -> None:
    """Delete the user. Every row that belongs to them is removed by ON DELETE CASCADE,
    and the receipt image files by the post_delete signal in expenses.signals."""
    user.delete()
