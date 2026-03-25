from django.shortcuts import render, get_object_or_404, redirect
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.db import IntegrityError
from django.db.models import Q, Count
from django.db.models.functions import TruncDate
import json
from .models import Book, Borrowing
from django.utils import timezone
from datetime import timedelta

# Registration and admin helpers
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth import login as auth_login
from django.contrib.admin.views.decorators import staff_member_required
from django.views.decorators.http import require_POST
from .forms import BookForm

@login_required
def book_list(request):
    """
    Display a list of all books, showing their availability.
    """
    # Filtering/searching/sorting support
    q = request.GET.get('q', '').strip()
    category = request.GET.get('category', '')
    author = request.GET.get('author', '')
    available = request.GET.get('available', '')  # '1' for only available

    # Sorting support via ?sort=title|author|year|available
    sort = request.GET.get('sort', 'title')
    sort_map = {
        'title': 'title',
        'author': 'author',
        'year': 'publication_year',
        'available': '-is_available',  # show available first
        '-title': '-title',
        '-author': '-author',
        '-year': '-publication_year',
        '-available': 'is_available',
    }

    order_field = sort_map.get(sort, 'title')

    books_qs = Book.objects.all()

    if q:
        books_qs = books_qs.filter(
            Q(title__icontains=q) |
            Q(author__icontains=q) |
            Q(description__icontains=q) |
            Q(isbn__icontains=q)
        )

    if category:
        books_qs = books_qs.filter(category=category)

    if author:
        books_qs = books_qs.filter(author=author)

    if available == '1':
        books_qs = books_qs.filter(is_available=True)

    books = books_qs.order_by(order_field)

    # Get distinct categories and authors for filter dropdowns
    categories = Book.objects.exclude(category__isnull=True).exclude(category__exact='').order_by('category').values_list('category', flat=True).distinct()
    authors = Book.objects.exclude(author__isnull=True).exclude(author__exact='').order_by('author').values_list('author', flat=True).distinct()

    return render(request, 'library/book_list.html', {
        'books': books,
        'current_sort': sort,
        'q': q,
        'selected_category': category,
        'selected_author': author,
        'selected_available': available,
        'categories': categories,
        'authors': authors,
    })

@login_required
def book_detail(request, pk):
    """
    Show details for a single book and allow requesting it.
    """
    book = get_object_or_404(Book, pk=pk)
    
    # Check if the user has an active (pending or approved) request
    existing_request = Borrowing.objects.filter(
        student=request.user,
        book=book,
        status__in=['PENDING', 'APPROVED']
    ).first()
    
    return render(request, 'library/book_detail.html', {
        'book': book,
        'existing_request': existing_request
    })

@login_required
def request_book(request, pk):
    """
    Handle the POST request to borrow a book.
    """
    if request.method != 'POST':
        return redirect('book_detail', pk=pk)

    book = get_object_or_404(Book, pk=pk)

    # Check if book is available
    if not book.is_available:
        messages.error(request, "This book is currently unavailable.")
        return redirect('book_detail', pk=pk)

    # Check if user already has an active request
    has_active_request = Borrowing.objects.filter(
        student=request.user,
        book=book,
        status__in=['PENDING', 'APPROVED']
    ).exists()

    if has_active_request:
        messages.warning(request, "You already have an active request for this book.")
        return redirect('book_detail', pk=pk)
        
    # Create the pending request
    try:
        Borrowing.objects.create(student=request.user, book=book, status='PENDING')
        messages.success(request, "Your request to borrow this book has been submitted.")
    except IntegrityError:
         messages.error(request, "An error occurred. You may have already requested this book.")

    return redirect('book_list')

@login_required
def student_profile(request):
    """
    Show the logged-in student's profile with their borrowing history.
    """
    borrowings = Borrowing.objects.filter(student=request.user).order_by('-request_date')
    return render(request, 'library/student_profile.html', {'borrowings': borrowings})


def register(request):
    """Allow students to create an account using Django's UserCreationForm."""
    if request.method == 'POST':
        form = UserCreationForm(request.POST)
        if form.is_valid():
            user = form.save()
            # Log the user in immediately
            auth_login(request, user)
            messages.success(request, 'Registration successful. You are now logged in.')
            return redirect('book_list')
        else:
            messages.error(request, 'Please correct the errors below.')
    else:
        form = UserCreationForm()

    # Improve form widgets styling for consistency with Tailwind used in templates
    try:
        form.fields['username'].widget.attrs.update({
            'class': 'appearance-none rounded-md relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm',
            'placeholder': 'Username'
        })
        form.fields['password1'].widget.attrs.update({
            'class': 'appearance-none rounded-md relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm',
            'placeholder': 'Password'
        })
        form.fields['password2'].widget.attrs.update({
            'class': 'appearance-none rounded-md relative block w-full px-3 py-2 border border-gray-300 placeholder-gray-500 text-gray-900 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm',
            'placeholder': 'Confirm password'
        })
    except Exception:
        # If fields are not present for some reason, ignore styling updates
        pass

    return render(request, 'library/register.html', {'form': form})


@staff_member_required
def admin_dashboard(request):
    """Admin dashboard showing counts, quick links, and analytics."""
    total_books = Book.objects.count()
    available = Book.objects.filter(is_available=True).count()
    pending_requests = Borrowing.objects.filter(status='PENDING').count()

    # Top 5 most borrowed books
    top_books = Book.objects.annotate(borrow_count=Count('borrowings')).filter(borrow_count__gt=0).order_by('-borrow_count')[:5]
    top_books_labels = [book.title[:30] + '...' if len(book.title) > 30 else book.title for book in top_books]
    top_books_data = [book.borrow_count for book in top_books]

    # Category distribution
    categories_qs = Book.objects.exclude(category__isnull=True).exclude(category__exact='').values('category').annotate(count=Count('id')).order_by('-count')
    category_labels = [item['category'] for item in categories_qs]
    category_data = [item['count'] for item in categories_qs]

    # Borrowing Activity over the Last 7 Days
    seven_days_ago = timezone.now() - timedelta(days=7)
    activity_qs = Borrowing.objects.filter(request_date__gte=seven_days_ago) \
        .annotate(date=TruncDate('request_date')) \
        .values('date') \
        .annotate(count=Count('id')) \
        .order_by('date')
    
    activity_labels = [item['date'].strftime('%Y-%m-%d') for item in activity_qs]
    activity_data_list = [item['count'] for item in activity_qs]

    return render(request, 'library/admin_dashboard.html', {
        'total_books': total_books,
        'available': available,
        'pending_requests': pending_requests,
        'top_books_labels_json': json.dumps(top_books_labels),
        'top_books_data_json': json.dumps(top_books_data),
        'category_labels_json': json.dumps(category_labels),
        'category_data_json': json.dumps(category_data),
        'activity_labels_json': json.dumps(activity_labels),
        'activity_data_json': json.dumps(activity_data_list),
    })


# --- Book CRUD for staff ---
@staff_member_required
def staff_book_list(request):
    books = Book.objects.order_by('title')
    return render(request, 'library/staff_book_list.html', {'books': books})


@staff_member_required
def create_book(request):
    if request.method == 'POST':
        form = BookForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Book created successfully.')
            return redirect('staff_book_list')
    else:
        form = BookForm()
    return render(request, 'library/book_form.html', {'form': form, 'action': 'Create'})


@staff_member_required
def edit_book(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        form = BookForm(request.POST, instance=book)
        if form.is_valid():
            form.save()
            messages.success(request, 'Book updated successfully.')
            return redirect('staff_book_list')
    else:
        form = BookForm(instance=book)
    return render(request, 'library/book_form.html', {'form': form, 'action': 'Edit'})


@staff_member_required
def delete_book(request, pk):
    book = get_object_or_404(Book, pk=pk)
    if request.method == 'POST':
        book.delete()
        messages.success(request, 'Book deleted.')
        return redirect('staff_book_list')
    return render(request, 'library/book_confirm_delete.html', {'book': book})


@staff_member_required
def pending_requests(request):
    """Show pending borrowing requests for admin to act on."""
    requests_qs = Borrowing.objects.filter(status='PENDING').order_by('request_date')
    return render(request, 'library/admin_pending_requests.html', {'requests': requests_qs})


@staff_member_required
@require_POST
def approve_request(request, pk):
    borrowing = get_object_or_404(Borrowing, pk=pk)
    if borrowing.status != 'PENDING':
        messages.warning(request, 'This request is no longer pending.')
        return redirect('admin_pending_requests')
    borrowing.status = 'APPROVED'
    borrowing.approved_date = timezone.now()
    # set return date 3 days after approval
    borrowing.return_date = borrowing.approved_date + timedelta(days=3)
    borrowing.save()

    borrowing.book.is_available = False
    borrowing.book.save()

    # Reject other pending requests for this book
    Borrowing.objects.filter(book=borrowing.book, status='PENDING').exclude(pk=borrowing.pk).update(status='REJECTED')

    messages.success(request, f'Request for "{borrowing.book.title}" by {borrowing.student.username} approved.')
    return redirect('admin_pending_requests')


@staff_member_required
@require_POST
def reject_request(request, pk):
    borrowing = get_object_or_404(Borrowing, pk=pk)
    if borrowing.status != 'PENDING':
        messages.warning(request, 'This request is no longer pending.')
        return redirect('admin_pending_requests')

    borrowing.status = 'REJECTED'
    borrowing.save()

    messages.success(request, f'Request for "{borrowing.book.title}" by {borrowing.student.username} rejected.')
    return redirect('admin_pending_requests')


@staff_member_required
def borrowing_history(request):
    """Show all borrowings (approved, returned, rejected) for admin tracking."""
    # Get all borrowings except pending
    borrowings = Borrowing.objects.exclude(status='PENDING').order_by('-request_date')
    return render(request, 'library/admin_borrowing_history.html', {'borrowings': borrowings})


@staff_member_required
@require_POST
def mark_as_returned(request, pk):
    """Mark an approved borrowing as returned."""
    borrowing = get_object_or_404(Borrowing, pk=pk)
    if borrowing.status != 'APPROVED':
        messages.warning(request, 'Only approved borrowings can be marked as returned.')
        return redirect('borrowing_history')

    borrowing.status = 'RETURNED'
    borrowing.save()

    # Mark the book as available again
    borrowing.book.is_available = True
    borrowing.book.save()

    messages.success(request, f'"{borrowing.book.title}" returned by {borrowing.student.username}.')
    return redirect('borrowing_history')