def delete(user) -> None:
    """Delete the user. Every row that belongs to them, including the receipts and their
    images, is removed by ON DELETE CASCADE."""
    user.delete()
