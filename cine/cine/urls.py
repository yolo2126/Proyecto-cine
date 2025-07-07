from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static  # ← Importa esto


urlpatterns = [
   path('admin/', admin.site.urls),
   path("", include("cinema.urls")),  # ← Ruta de la app principal
   path("", include("generales.urls")),  # ← Ruta de la app principal
   
]


# Añadir archivos media en modo desarrollo
if settings.DEBUG:
   urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
   urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)


