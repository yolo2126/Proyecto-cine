from django.views.generic import TemplateView, DetailView, ListView
from django.utils import timezone
from .models import Customer, Showtime, SnackItem, Movie, NewsletterSubscriber  # <-- importamos NewsletterSubscriber
from django.shortcuts import get_object_or_404, render, redirect
from django.views import View
from django.urls import reverse
from django.contrib import messages
from django import forms  # para crear formulario inline
from .models import Showtime, Ticket, Seat, ReservationStatus
from .models import Customer, Order, OrderTicket, PaymentMethod, Showtime, SnackItem, OrderSnack
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin

# Importaciones para registro de usuario
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.views.generic.edit import FormView
from django.contrib.auth import login


class HomeView(TemplateView):
    template_name = "home.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)

        # Cartelera: próximas 30 funciones ordenadas por hora
        ctx["showtimes"] = (
            Showtime.objects
            .select_related("movie", "auditorium", "auditorium__cinema")
            .filter(
                movie__is_active=True,
                auditorium__cinema__is_active=True,
                start_time__gte=timezone.now(),
            )
            .order_by("start_time")[:30]
        )

        # Snacks destacados: los 6 primeros disponibles (puedes cambiar el criterio)
        ctx["snacks"] = (
            SnackItem.objects
            .select_related("category")
            .filter(is_available=True)
            .order_by("-updated")[:6]
        )
        return ctx


# Formularios inline para newsletter
class NewsletterForm(forms.ModelForm):
    class Meta:
        model = NewsletterSubscriber
        fields = ['email']
        widgets = {
            'email': forms.EmailInput(attrs={'placeholder': 'Tu correo electrónico', 'class': 'form-control'}),
        }


class NewsletterSubscribeView(View):
    def post(self, request):
        form = NewsletterForm(request.POST)
        if form.is_valid():
            email = form.cleaned_data['email']
            if NewsletterSubscriber.objects.filter(email=email).exists():
                messages.info(request, "Este correo ya está suscrito.")
            else:
                form.save()
                messages.success(request, "Gracias por suscribirte al newsletter.")
        else:
            messages.error(request, "Correo inválido, intenta de nuevo.")
        return redirect(request.META.get('HTTP_REFERER', '/'))


class ShowtimeDetailView(DetailView):
    model = Showtime
    template_name = "showtime_detail.html"
    context_object_name = "showtime"

    def get_queryset(self):
        return (
            super()
            .get_queryset()
            .select_related("movie", "auditorium__cinema")
        )


class SnackListView(ListView):
    model = SnackItem
    template_name = "snack_list.html"
    context_object_name = "snacks"
    paginate_by = 12

    def get_queryset(self):
        return (
            SnackItem.objects
            .filter(is_available=True)
            .select_related("category")
            .order_by("name")
        )





class SnackDetailView(LoginRequiredMixin, DetailView):
   model = SnackItem
   template_name = "snack_detail.html"
   context_object_name = "snack"
   login_url = 'login'


   def post(self, request, *args, **kwargs):
       self.object = self.get_object()  # el SnackItem
       qty = int(request.POST.get('qty', 1))
       if qty < 1:
           qty = 1


       # 1) Perfil de cliente
       customer, _ = Customer.objects.get_or_create(user=request.user)


       # 2) Orden PENDING (o la nueva si no existe)
       order, _ = Order.objects.get_or_create(
           customer=customer,
           status=Order.Status.PENDING,
           defaults={'total_amount': 0}
       )


       # 3) Añadimos o actualizamos la línea de snack
       line, created = OrderSnack.objects.get_or_create(
           order=order,
           snack=self.object,
           defaults={'qty': qty, 'price': self.object.price}
       )
       if not created:
           line.qty += qty
           line.save()


       # 4) Recalculamos total (tickets + snacks)
       total_tickets = sum(float(t.price) for t in order.order_tickets.all())
       total_snacks  = sum(s.line_total() for s in order.order_snacks.all())
       order.total_amount = total_tickets + total_snacks
       order.save()


       messages.success(request,
           f"Añadiste {qty} × {self.object.name} a tu orden #{order.id}."
       )
       return redirect('snack_detail', pk=self.object.pk)


class SeatSelectionView(View):
    template_name = "seat_selection.html"

    def get(self, request, pk):
        showtime = get_object_or_404(
            Showtime.objects.select_related("auditorium__cinema", "movie"),
            pk=pk
        )
        aud = showtime.auditorium

        # Asientos “tomados”
        taken = set(
            showtime.tickets
            .filter(status__in=[ReservationStatus.RESERVED, ReservationStatus.PAID])
            .values_list("seat_id", flat=True)
        )

        # Obtener los asientos creados en BD
        seats_qs = aud.seats.all().order_by("row", "col")
        if not seats_qs.exists():
            return render(request, self.template_name, {
                "showtime": showtime, 
                "no_seats": True
            })

        # Agrupamos por fila
        grid = {}
        for seat in seats_qs:
            grid.setdefault(seat.row, []).append(seat)

        return render(request, self.template_name, {
            "showtime": showtime,
            "grid": grid,
            "taken": taken,
        })


# Vista para mostrar todas las películas activas
class PeliculasView(ListView):
    model = Movie
    template_name = "peliculas.html"
    context_object_name = "peliculas"

    def get_queryset(self):
        return Movie.objects.filter(is_active=True).order_by("title")


# Vista para mostrar próximos estrenos
class EstrenosView(ListView):
    model = Movie
    template_name = "estrenos.html"
    context_object_name = "peliculas"

    def get_queryset(self):
        return Movie.objects.filter(
            release_date__gte=timezone.now(),
            is_active=True
        ).order_by("release_date")


# --- Clases para registro de usuario ---

class RegistroForm(UserCreationForm):
    class Meta:
        model = User
        fields = ['username', 'email', 'password1', 'password2']


class RegistrarView(FormView):
    template_name = "registrar.html"
    form_class = RegistroForm
    success_url = '/'  # Redirige a home tras registro exitoso

    def form_valid(self, form):
        user = form.save()
        login(self.request, user)  # Loguea automáticamente al usuario
        return super().form_valid(form)



from django.db import transaction
from django.contrib.auth.mixins import LoginRequiredMixin
from .models import Order, OrderTicket, PaymentMethod, Showtime, SnackItem


class SeatSelectionView(LoginRequiredMixin, View):
   login_url = 'login'
   template_name = 'seat_selection.html'


   def get(self, request, pk):
       showtime = get_object_or_404(
           Showtime.objects.select_related("auditorium__cinema", "movie"),
           pk=pk
       )
       aud = showtime.auditorium
       taken = set(
           showtime.tickets
           .filter(status__in=[ReservationStatus.RESERVED, ReservationStatus.PAID])
           .values_list("seat_id", flat=True)
       )
       seats_qs = aud.seats.all().order_by("row", "col")
       if not seats_qs.exists():
           return render(request, self.template_name, {
               "showtime": showtime,
               "no_seats": True
           })
       grid = {}
       for seat in seats_qs:
           grid.setdefault(seat.row, []).append(seat)
       return render(request, self.template_name, {
           "showtime": showtime,
           "grid": grid,
           "taken": taken,
       })


   @transaction.atomic
   def post(self, request, pk):
       showtime = get_object_or_404(Showtime, pk=pk)
       seat_ids = request.POST.getlist('seats')
       if not seat_ids:
           return self.get(request, pk)


       # <-- Aquí creamos el Customer si no existe -->
       customer, created = Customer.objects.get_or_create(user=request.user)


       tickets, total = [], 0
       for sid in seat_ids:
           ticket, was_created = Ticket.objects.get_or_create(
               showtime=showtime,
               seat_id=sid,
               defaults={
                   'customer': customer,
                   'status': ReservationStatus.RESERVED,
                   'price': showtime.base_price
               }
           )
           if not was_created and ticket.status != ReservationStatus.RESERVED:
               ticket.status = ReservationStatus.RESERVED
               ticket.customer = customer
               ticket.price = showtime.base_price
               ticket.save()
           tickets.append(ticket)
           total += float(ticket.price)


       order = Order.objects.create(
           customer=customer,
           total_amount=total,
           status=Order.Status.PENDING
       )
       for t in tickets:
           OrderTicket.objects.create(order=order, ticket=t)


       return redirect('order_confirm', order_id=order.id)
  




class OrderConfirmView(LoginRequiredMixin, View):
   login_url = 'login'
   template_name = 'order_confirm.html'


   def get(self, request, order_id):
       order = get_object_or_404(
           Order, id=order_id, customer=request.user.customer
       )
       return render(request, self.template_name, {
           'order': order,
           'payment_choices': PaymentMethod.choices
       })


   def post(self, request, order_id):
       order = get_object_or_404(
           Order, id=order_id, customer=request.user.customer
       )
       pm = request.POST.get('payment_method')
       order.payment_method = pm
       order.status = Order.Status.PAID
       order.paid_at = timezone.now()
       order.save()
       return redirect('order_success', order_id=order.id)
  
class OrderSuccessView(LoginRequiredMixin, View):
   login_url = 'login'
   template_name = 'order_success.html'


   def get(self, request, order_id):
       order = get_object_or_404(
           Order, id=order_id, customer__user=request.user
       )
       has_tickets = order.order_tickets.exists()
       has_snacks  = order.order_snacks.exists()


       # <-- Aquí la corrección: -->
       ticket_total = sum(
           float(ot.ticket.price) for ot in order.order_tickets.all()
       )
       snack_total  = sum(
           s.line_total() for s in order.order_snacks.all()
       )


       return render(request, self.template_name, {
           'order': order,
           'has_tickets':  has_tickets,
           'has_snacks':   has_snacks,
           'ticket_total': ticket_total,
           'snack_total':  snack_total,
       })



class OrderListView(LoginRequiredMixin, ListView):
   model = Order
   template_name = 'orders_list.html'
   context_object_name = 'orders'
   login_url = 'login'


   def get_queryset(self):
       # Nos aseguramos de tener Customer
       customer, _ = Customer.objects.get_or_create(user=self.request.user)
       # Devolvemos las órdenes de este cliente, de más reciente a más antigua
       return Order.objects.filter(customer=customer).order_by('-created')
  


import io
from django.http import FileResponse, Http404


from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A6, landscape
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
import qrcode

class TicketPDFView(LoginRequiredMixin, View):
    login_url = 'login'

    def get(self, request, order_id):
        order = get_object_or_404(Order, id=order_id, customer__user=request.user)
        show = order.order_tickets.first().ticket.showtime

        buffer = io.BytesIO()
        p = canvas.Canvas(buffer, pagesize=landscape(A6))
        width, height = landscape(A6)

        # Encabezado principal
        p.setFont("Helvetica-Bold", 16)
        p.drawCentredString(width / 2, height - 15 * mm, "MIAU PELIS CINE")
        p.setLineWidth(1)
        p.line(5 * mm, height - 17 * mm, width - 5 * mm, height - 17 * mm)
        p.setLineWidth(0.3)
        p.line(5 * mm, height - 18 * mm, width - 5 * mm, height - 18 * mm)

        # Información de la orden
        p.setFont("Helvetica", 9)
        y = height - 24 * mm
        p.drawString(5 * mm, y, f"Orden #: {order.id}")
        y -= 5 * mm
        p.drawString(5 * mm, y, f"Película: {show.movie.title}")
        y -= 5 * mm
        p.drawString(5 * mm, y, f"Función: {show.start_time.strftime('%d/%m/%Y %H:%M')}")
        y -= 5 * mm
        p.drawString(5 * mm, y, f"Sala: {show.auditorium.name} ({show.auditorium.cinema.name})")

        y -= 7 * mm
        p.setFont("Helvetica-Bold", 10)
        p.drawString(5 * mm, y, "Asientos:")

        # Lista de asientos
        p.setFont("Helvetica", 9)
        x = 25 * mm
        for ot in order.order_tickets.all():
            p.drawString(x, y, f"{ot.ticket.seat.row}-{ot.ticket.seat.col}")
            x += 15 * mm
            if x > width - 20 * mm:
                x = 25 * mm
                y -= 5 * mm

        y -= 10 * mm

        # Total pagado
        p.setFont("Helvetica-Bold", 12)
        p.drawString(5 * mm, y, f"Total Pagado: ${order.total_amount:.2f}")

        # Código QR
        qr_data = f"ORDER-{order.id}-USER-{request.user.id}"
        qr_img = qrcode.make(qr_data)
        qr_buffer = io.BytesIO()
        qr_img.save(qr_buffer, format="PNG")
        qr_buffer.seek(0)
        qr_reader = ImageReader(qr_buffer)

        # Posición del QR
        p.drawImage(qr_reader, width - 35 * mm, 5 * mm, 30 * mm, 30 * mm)

        # Leyenda QR
        p.setFont("Helvetica-Oblique", 6)
        p.drawCentredString(width - 20 * mm, 4 * mm, "Escanea para validar tu entrada")

        # Finalizamos PDF
        p.showPage()
        p.save()

        buffer.seek(0)
        return FileResponse(
            buffer,
            as_attachment=True,
            filename=f"ticket_{order.id}.pdf"
        )
    
class CancelOrderView(LoginRequiredMixin, View):
   login_url = 'login'


   def post(self, request, order_id):
       order = get_object_or_404(
           Order,
           id=order_id,
           customer__user=request.user,
           status=Order.Status.PENDING
       )


       # Para cada relación OrderTicket, liberamos el ticket y borramos la línea
       for ot in list(order.order_tickets.all()):
           ticket = ot.ticket
           # 1) Marcamos el ticket como cancelado y lo desvinculamos del cliente
           ticket.status = ReservationStatus.CANCELED
           ticket.customer = None
           ticket.save()
           # 2) Eliminamos la asociación con la orden
           ot.delete()


       # Finalmente marcamos la orden como cancelada
       order.status = Order.Status.CANCELED
       order.save()


       messages.success(
           request,
           f"Orden #{order.id} cancelada y asientos liberados correctamente."
       )
       return redirect('orders_list')
