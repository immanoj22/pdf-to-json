"""Step 21: the title page's only heading is the book title; credits are not headings."""

from test_structure import Book, decide, headings_by_text


def title_book():
    book = Book(9)
    book.unit(1, "Ward Rounds in Dermatology", size=30, bold=True)
    book.unit(1, "Foreword", size=12, bold=True)
    book.unit(1, "Sudhir Pujara", size=12, bold=True)
    book.body(1, count=1)
    for page, title in ((3, "Chapter 1"), (6, "Chapter 2")):
        book.unit(page, title, size=20, bold=True)
        book.body(page)
        book.unit(page + 1, f"{title[-1]}.1 Background of the valley", size=14, bold=True)
        book.body(page + 1)
    return book


def test_credits_on_the_title_page_are_not_headings():
    book = title_book()
    found = headings_by_text(decide(book), book)
    assert found["Ward Rounds in Dermatology"].role == "book_title"
    assert not any("Foreword" in text or "Pujara" in text for text in found)


def test_chapters_are_unaffected():
    book = title_book()
    found = headings_by_text(decide(book), book)
    assert found["Chapter 1"].role == "chapter" and found["Chapter 2"].role == "chapter"
