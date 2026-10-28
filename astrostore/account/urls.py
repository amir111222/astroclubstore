from django.urls import path

from . import views

app_name = "account"

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("verify/", views.verify_view, name="verify"),
    path("resend-code/", views.resend_otp, name="resend_otp"),
    path("logout/", views.logout_view, name="logout"),
    path("profile/", views.profile_view, name="profile"),
    path("addresses/", views.address_list, name="addresses"),
    path("addresses/<int:pk>/edit/", views.address_edit, name="address_edit"),
    path("addresses/<int:pk>/default/", views.address_default, name="address_default"),
    path("addresses/<int:pk>/delete/", views.address_delete, name="address_delete"),
    path("privacy/delete-request/", views.deletion_request, name="deletion_request"),
]
