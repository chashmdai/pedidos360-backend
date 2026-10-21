"""Render every PDF page for visual review; retain text/layout checks as evidence."""
from pathlib import Path
import hashlib
import json
import subprocess
from PIL import Image,ImageOps,ImageDraw
from pypdf import PdfReader

ROOT=Path(__file__).resolve().parent.parent
pdf=ROOT/'docs/EP3_RABBITMQ_EVIDENCIAS.pdf'
out=ROOT/'tmp/pdfs/ep3'
out.mkdir(parents=True,exist_ok=True)
assert out.resolve().is_relative_to((ROOT/'tmp').resolve())
for old in out.glob('page-*.png'):old.unlink() # Only this renderer's disposable pages.
subprocess.run(['pdftoppm','-r','110','-png',str(pdf),str(out/'page')],check=True)
reader=PdfReader(pdf);pages=[]
for index,page in enumerate(reader.pages,1):
    text=page.extract_text() or ''
    pages.append(dict(page=index,characters=len(text),images=len(page.images),begin=text[:120],end=text[-160:]))
    assert abs(float(page.mediabox.width)-595.276)<1 and abs(float(page.mediabox.height)-841.89)<1
    assert len(text)>30,'Empty or footer-only page'
thumbs=[]
for index,file in enumerate(sorted(out.glob('page-*.png')),1):
    image=Image.open(file).convert('RGB');image.thumbnail((380,540))
    canvas=Image.new('RGB',(400,575),'#d8d8d8');canvas.paste(image,((400-image.width)//2,20))
    ImageDraw.Draw(canvas).text((12,554),'Página '+str(index),fill='black');thumbs.append(canvas)
sheet=Image.new('RGB',(400*3,575*((len(thumbs)+2)//3)),'white')
for index,image in enumerate(thumbs):sheet.paste(image,((index%3)*400,(index//3)*575))
sheet.save(out/'contact-sheet.png')
result=dict(pdfSha256=hashlib.sha256(pdf.read_bytes()).hexdigest(),a4=True,pages=pages,
    note='All pages rendered. Visual review is separate from text checks.',renderDirectory='tmp/pdfs/ep3')
(ROOT/'docs/evidence/ep3/pdf-qa.json').write_text(json.dumps(result,indent=2,ensure_ascii=False)+'\n')
print(json.dumps(pages,indent=2,ensure_ascii=False))
