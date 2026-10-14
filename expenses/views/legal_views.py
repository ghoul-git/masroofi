from django.shortcuts import render


def terms(request):
    return render(request, "expenses/terms.html")


def privacy(request):
    return render(request, "expenses/privacy.html")
