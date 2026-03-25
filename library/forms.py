from django import forms
from .models import Book


class BookForm(forms.ModelForm):
    class Meta:
        model = Book
        fields = ['title', 'author', 'isbn', 'category', 'publication_year', 'description', 'is_available']
        widgets = {
            'title': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-md'}),
            'author': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-md'}),
            'isbn': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-md'}),
            'category': forms.TextInput(attrs={'class': 'w-full px-3 py-2 border rounded-md'}),
            'publication_year': forms.NumberInput(attrs={'class': 'w-full px-3 py-2 border rounded-md'}),
            'description': forms.Textarea(attrs={'class': 'w-full px-3 py-2 border rounded-md', 'rows':4}),
        }
