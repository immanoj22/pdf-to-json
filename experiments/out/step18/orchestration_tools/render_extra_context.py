"""Additional original-source context for fixed targets, never a sample redraw."""
import sys
from evaluation_routes import BASE,ROOT,SOURCE_KEYS,finished,sha,write_new

def main(book,label,*page_args):
    finished()
    from reference_paths import reference_path
    from book_core.extraction.pymupdf_backend import PyMuPDFExtractor
    source=reference_path(SOURCE_KEYS[book]);extractor=PyMuPDFExtractor('cpu')
    dest=BASE/'audit'/book/label;dest.mkdir(exist_ok=False)
    rows=[]
    for number in map(int,page_args):
        raster=extractor.render_page(source,number,dpi=160)
        path=dest/f'page_{number:06d}.png';path.write_bytes(raster.png)
        rows.append({'page':number,'path':path.relative_to(ROOT).as_posix(),'sha256':sha(path)})
    write_new(dest/'receipt.json',{'source_sha256':sha(source),'render_method':'Original PDF, frozen PyMuPDFExtractor, 160 dpi','pages':rows,'judgments_generated':0})

if __name__=='__main__':main(*sys.argv[1:])
