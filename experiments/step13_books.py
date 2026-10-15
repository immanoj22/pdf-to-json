"""Step 13 book registry: books 1-4 (unchanged Step 7 registry) plus the math development book.

The sealed math hold-out and the ENT/mideast books are deliberately absent.
"""

from step7_layouts import BOOKS as EARLIER

MATH_BOOK = "statistics"
BOOKS = {**EARLIER, MATH_BOOK: ("statistics_pdf", "development")}
CNXML = {MATH_BOOK: "statistics_cnxml"}
